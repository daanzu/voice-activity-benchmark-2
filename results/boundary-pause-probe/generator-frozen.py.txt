"""Frozen hard-gated Flite pause diagnostic; never selects or tunes a controller."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import wave

import numpy as np

from .boundary_dataset import (BASE_ONSET_SAMPLES, DURATION, PAUSES_MS, TEXTS,
    VOICES, _activity_samples, _merge, _seconds, prepare_source)
from .boundary_latency import Controller, causal_episodes, evaluate_boundaries, prepare_records
from .boundary_report import load_inputs
from .dataset import FRAME, SR, digest
from .run import BACKENDS

VERSION = 'hard-gated-flite-pause-v1'
EDGE_FADE_SAMPLES = SR // 1000
GATE_COLLAR_SAMPLES = SR // 1000


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def write_result(path, value):
    """One canonical representation, deterministically compressed above 1 MB."""
    path = Path(path)
    data = json_bytes(value)
    if len(data) > 1_000_000:
        path = path.with_suffix(path.suffix + '.gz')
        path.write_bytes(gzip.compress(data, mtime=0))
    else:
        path.write_bytes(data)
    return path


def specs():
    return [dict(split=split, replicate=replicate, pause_ms=pause, branch=branch)
            for split in ('dev', 'test') for replicate in range(4)
            for pause in PAUSES_MS for branch in ('stop', 'resume')]


def gate_source(text, voice, cache):
    """Crop to a stable first/last source-local RMS-active frame, then taper.

    Cropping changes the normalization used by the RMS proxy. Recompute it after
    each proposed crop/taper, and trim again only if an outer frame became quiet.
    Every candidate is faded from the original PCM, never cumulatively faded.
    This is an artificial speech excision, not preserved phonetic completeness.
    """
    prepared = prepare_source(text, voice, Path(cache))
    original = prepared['pcm']
    a, b = prepared['activity'][0][0], prepared['activity'][-1][1]
    passes = 0
    while True:
        passes += 1
        pcm = original[a:b].copy()
        n = min(EDGE_FADE_SAMPLES, len(pcm) // 2)
        if n:
            pcm[:n] = np.rint(pcm[:n].astype(float) * np.linspace(0., 1., n)).astype('<i2')
            pcm[-n:] = np.rint(pcm[-n:].astype(float) * np.linspace(1., 0., n)).astype('<i2')
        activity = _activity_samples(pcm)
        if not activity:
            raise ValueError('Gating erased all RMS activity')
        left, right = activity[0][0], activity[-1][1]
        if left == 0 and right == len(pcm):
            break
        if not (0 <= left < right <= len(pcm)) or right-left >= len(pcm):
            raise ValueError('Gating failed to shrink to active boundaries')
        a, b = a + left, a + right
    support = np.flatnonzero(pcm)
    return dict(pcm=pcm, activity=activity, metadata=dict(prepared['metadata'],
        original_prepared_pcm_sha256=prepared['metadata']['prepared_pcm_sha256'],
        original_prepared_samples=len(original), crop_interval_samples=[a, b],
        gate_passes=passes, edge_fade_samples=n, gated_pcm_sha256=sha_bytes(pcm.tobytes()),
        gated_samples=len(pcm), exact_nonzero_support_samples=[int(support[0]), int(support[-1])+1],
        label_policy='10 ms source-local RMS of emitted gated PCM normalized to -20 dBFS',
        endpoint_transform='artificial hard gate with 1 ms linear edge fades'))


def build_record(spec, output, sources):
    split, rep, pause, branch = (spec[k] for k in ('split', 'replicate', 'pause_ms', 'branch'))
    prefix, continuation = sources[split, rep, 'prefix'], sources[split, rep, 'continuation']
    prefix_end = BASE_ONSET_SAMPLES + len(prefix['pcm'])
    resume = prefix_end + pause * SR // 1000
    rid = f'{split}-gate-{rep:02d}-{pause:03d}-{branch}'
    pair_id = f'{split}-gate-pair-{rep:02d}-{pause:03d}'
    pcm = np.zeros(DURATION * SR, dtype='<i2')
    parts = [(prefix, BASE_ONSET_SAMPLES)]
    if branch == 'resume':
        parts.append((continuation, resume))
    activity, provenance, uncertain = [], [], []
    for source, offset in parts:
        end = offset + len(source['pcm'])
        if end > len(pcm):
            raise ValueError('Source does not fit without truncation')
        pcm[offset:end] = source['pcm']
        shifted = [[x+offset, y+offset] for x, y in source['activity']]
        activity.extend(shifted)
        for x, y in shifted:
            for edge in (x, y):
                # Tight gate collars are construction uncertainty, not phonetic certainty.
                collar = GATE_COLLAR_SAMPLES if edge in (offset, end) else FRAME
                uncertain.append([edge-collar, edge+collar])
        provenance.append(dict(source['metadata'], inserted_interval=[offset/SR, end/SR],
            inserted_interval_samples=[offset, end], activity_intervals=_seconds(shifted)))
    activity = _merge(activity)
    onset, offset = activity[0][0], activity[-1][1]
    turn = dict(id=rid+'-turn', onset_s=onset/SR, offset_s=offset/SR,
        onset_uncertainty_s=[(onset-GATE_COLLAR_SAMPLES)/SR, (onset+GATE_COLLAR_SAMPLES)/SR],
        offset_uncertainty_s=[(offset-GATE_COLLAR_SAMPLES)/SR, (offset+GATE_COLLAR_SAMPLES)/SR],
        acoustic_intervals=_seconds(activity),
        internal_pauses=[[prefix_end/SR, resume/SR]] if branch == 'resume' else [])
    relative = Path('runtime-output/audio') / (rid+'.wav')
    path = Path(output)/relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(SR); wav.writeframes(pcm.tobytes())
    return dict(id=rid, split=split, path=relative.as_posix(), duration_s=DURATION,
        sha256=digest(path), turns=[turn], speech_intervals=_seconds(activity),
        target_intervals=_seconds(activity), background_intervals=[],
        uncertain_intervals=_seconds(_merge(uncertain)),
        condition=dict(name='hard_gate_'+branch, family='pause', branch=branch, pause_s=pause/1000,
            pause_ms=pause, replicate=rep, artificial_hard_gate=True, noise_type='none'),
        provenance=dict(sources=provenance, label_type='artificial_hard_gate_source_local_rms_proxy',
            original_split=split, reused_primary_texts_and_voices=True),
        causal_pair=dict(id=pair_id, branch=branch, shared_prefix_id=f'{split}-gate-prefix-{rep:02d}',
            requested_pause_s=pause/1000, prefix_activity_end_sample=prefix_end,
            resume_sample=resume, resume_time_s=resume/SR, shared_prefix_end_sample=resume,
            shared_prefix_pcm_sha256=sha_bytes(pcm[:resume].tobytes()),
            identical_history_interval_s=[0., resume/SR],
            measured_rms_gap_samples=resume-prefix_end, measured_rms_gap_ms=(resume-prefix_end)*1000/SR))


def read_pcm(root, record):
    path = Path(root)/record['path']
    if digest(path) != record['sha256']:
        raise ValueError('WAV hash mismatch')
    with wave.open(str(path), 'rb') as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) != (SR, 1, 2, SR*DURATION):
            raise ValueError('WAV format mismatch')
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')


def validate_manifest(manifest, root):
    """Remeasure emitted PCM, not merely placement fields or requested gaps."""
    records = manifest['records']
    if len(records) != 112 or {r['id'] for r in records}.__len__() != 112:
        raise ValueError('Expected 112 unique diagnostic streams')
    design = {(r['split'], r['condition']['replicate'], r['condition']['pause_ms'],
               r['condition']['branch']) for r in records}
    if design != {(s['split'], s['replicate'], s['pause_ms'], s['branch']) for s in specs()}:
        raise ValueError('Incomplete diagnostic design')
    pairs, observed_gaps = defaultdict(dict), defaultdict(list)
    for record in records:
        pcm = read_pcm(root, record)
        spans = []
        reconstructed = np.zeros_like(pcm)
        source_bounds = []
        for source in record['provenance']['sources']:
            a, b = source['inserted_interval_samples']
            chunk = pcm[a:b]
            if len(chunk) != source['gated_samples'] or sha_bytes(chunk.tobytes()) != source['gated_pcm_sha256']:
                raise ValueError('Emitted source differs from frozen gated source')
            actual = _activity_samples(chunk)
            if actual[0][0] != 0 or actual[-1][1] != len(chunk):
                raise ValueError('Emitted gate boundary is not RMS active')
            shifted = [[x+a, y+a] for x, y in actual]
            if source['activity_intervals'] != _seconds(shifted):
                raise ValueError('Emitted PCM activity differs from source labels')
            spans.extend(shifted); source_bounds.append((shifted[0][0], shifted[-1][1]))
            reconstructed[a:b] = chunk
        if not np.array_equal(pcm, reconstructed):
            raise ValueError('Unlabeled PCM exists outside gated sources')
        if record['speech_intervals'] != _seconds(_merge(spans)) or record['target_intervals'] != record['speech_intervals']:
            raise ValueError('Emitted PCM activity differs from record labels')
        turn = record['turns'][0]
        if (turn['onset_s'], turn['offset_s']) != (spans[0][0]/SR, spans[-1][1]/SR):
            raise ValueError('Turn boundaries differ from measured activity')
        pair = record['causal_pair']; horizon = pair['resume_sample']
        if pair['prefix_activity_end_sample'] != source_bounds[0][1]:
            raise ValueError('Prefix endpoint differs from emitted PCM RMS boundary')
        if sha_bytes(pcm[:horizon].tobytes()) != pair['shared_prefix_pcm_sha256']:
            raise ValueError('Prefix hash differs from emitted PCM')
        pairs[pair['id']][pair['branch']] = (record, pcm)
        if pair['branch'] == 'resume':
            measured = source_bounds[1][0]-source_bounds[0][1]
            desired = record['condition']['pause_ms']*SR//1000
            if measured != desired or measured != pair['measured_rms_gap_samples'] or source_bounds[1][0] != horizon:
                raise ValueError('Measured RMS-activity gap differs from requested gap')
            if np.any(pcm[source_bounds[0][1]:source_bounds[1][0]]):
                raise ValueError('Nonzero PCM contaminates the artificial pause')
            if turn['internal_pauses'] != [[source_bounds[0][1]/SR, source_bounds[1][0]/SR]]:
                raise ValueError('Pause label differs from emitted PCM')
            observed_gaps[record['condition']['pause_ms']].append(measured*1000/SR)
        elif turn['internal_pauses']:
            raise ValueError('Stopped branch must not contain an internal pause')
    for pair in pairs.values():
        if set(pair) != {'stop', 'resume'}:
            raise ValueError('Missing causal branch')
        a, x = pair['stop']; b, y = pair['resume']; n = a['causal_pair']['resume_sample']
        if a['causal_pair'] != dict(b['causal_pair'], branch='stop') or not np.array_equal(x[:n], y[:n]):
            raise ValueError('Causal prefix bytes or metadata differ')
    return dict(records=len(records), causal_pairs=len(pairs), duration_s=len(records)*DURATION,
        actual_rms_gap_ms={str(k):dict(min=min(v), max=max(v), resume_streams=len(v)) for k,v in sorted(observed_gaps.items())},
        emitted_pcm_activity_verified=True, byte_identical_prefixes_verified=True,
        activity_definition='Source-local 10 ms RMS proxy remeasured from emitted PCM; not samplewise phonetic activity')


def generate(output, source_cache, frozen_selections):
    output = Path(output)
    if any((output/name).exists() for name in ('manifest.json', 'FROZEN.json', 'summary.json', 'summary.json.gz')):
        raise FileExistsError('Immutable diagnostic exists; choose a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    (output/'runtime-output').mkdir(exist_ok=True)
    (output/'runtime-output/.gitignore').write_text('*\n!.gitignore\n')
    choices = json.loads(Path(frozen_selections).read_text())
    if len(choices['selections']) != 156:
        raise ValueError('Expected all 156 primary frozen policies')
    sources = {(split, rep, role):gate_source(TEXTS[split][role][rep], VOICES[split][rep%2], source_cache)
               for split in VOICES for rep in range(4) for role in ('prefix', 'continuation')}
    records = [build_record(spec, output, sources) for spec in specs()]
    specification = dict(version=VERSION, records=112, duration_s=DURATION,
        sample_rate=SR, pause_ms=PAUSES_MS, prefixes_per_split=4, branches=['stop','resume'],
        gate_collar_ms=1, internal_rms_transition_collar_ms=10, edge_fade_ms=1,
        source_rms_proxy='Emitted per-source PCM normalized to -20 dBFS; 10 ms RMS >= max(-48 dBFS, peak frame RMS -40 dB)',
        gate='Iterate cropping first/last RMS-active bounds after a fresh 1 ms linear edge taper until both terminal frames stay active',
        voices=VOICES, texts={s:{k:TEXTS[s][k] for k in ('prefix','continuation')} for s in VOICES},
        split_policy='Primary dev/test labels preserved as provenance; texts and voices reused, not a fresh independent holdout',
        selection_policy='Reuse 156 frozen primary policies and shared 0/200 ms baselines; no diagnostic fitting or ranking selection',
        limitation='Artificial hard-gated speech excises faint speech and can introduce splice/taper artifacts; not full-utterance phonetic truth',
        baseline_by_pause='Report test provenance only, four repeated prefix families per branch/pause',
        spec=specs())
    source_hashes = {name:digest(Path(__file__).with_name(name)) for name in
                     ('boundary_pause_probe.py','boundary_dataset.py','dataset.py','boundary_latency.py','run.py')}
    manifest = dict(schema_version=3, generation=specification, records=records)
    audit = validate_manifest(manifest, output)
    (output/'generator-frozen.py.txt').write_bytes(Path(__file__).read_bytes())
    (output/'specification.json').write_bytes(json_bytes(specification))
    (output/'manifest.json').write_bytes(json_bytes(manifest))
    (output/'test-manifest.json').write_bytes(json_bytes(dict(manifest, records=[r for r in records if r['split']=='test'])))
    frozen = dict(stage='before_model_inference', manifest_sha256=digest(output/'manifest.json'),
        test_manifest_sha256=digest(output/'test-manifest.json'), specification_sha256=digest(output/'specification.json'),
        generator_snapshot_sha256=digest(output/'generator-frozen.py.txt'), source_sha256=source_hashes,
        primary_frozen_selections_sha256=digest(frozen_selections),
        primary_manifest_sha256=choices['manifest_sha256'], audit=audit,
        policy='Never overwrite this design or select/tune on these results; retain primary study unchanged')
    (output/'FROZEN.json').write_bytes(json_bytes(frozen))
    return frozen


def controller_plan(primary):
    plan, controllers = [], {}
    for backend in BACKENDS:
        for silence in (0., .2):
            c = Controller(silence_s=silence)
            key = backend+'|'+c.id
            controllers[key] = (backend, c)
            plan.append(dict(backend=backend, configuration=f'common-{round(silence*1000)}ms',
                             kind='shared', metric_key=key, controller=asdict(c)))
    for row in primary['selections']:
        backend = row['backend']; c = Controller(**row['controller']); key = backend+'|'+c.id
        controllers[key] = (backend, c)
        plan.append(dict(row, kind='frozen', metric_key=key))
    return plan, controllers


def audit_causal_traces(records, traces):
    pairs = defaultdict(dict)
    for record in records:
        pairs[record['causal_pair']['id']][record['causal_pair']['branch']] = record
    checks = []
    for backend, run in traces.items():
        for pair_id, branches in pairs.items():
            horizon = branches['stop']['causal_pair']['resume_time_s']
            selected = [run[r['id']][run[r['id']][:,3] <= horizon+1e-9] for r in branches.values()]
            if not np.array_equal(*selected):
                raise ValueError(f'Pre-resume acquisition outputs differ: {backend} {pair_id}')
            checks.append(dict(backend=backend, pair_id=pair_id, identical_acquisition_rows=len(selected[0])))
    return checks


def paired_cuts(records, trace, controller):
    pairs = defaultdict(dict)
    for record in records:
        pairs[record['causal_pair']['id']][record['causal_pair']['branch']] = record
    rows = []
    for pair_id, branches in pairs.items():
        stop = branches['stop']; pair = stop['causal_pair']
        boundary, horizon = pair['prefix_activity_end_sample']/SR, pair['resume_time_s']
        available = {}
        for name, record in branches.items():
            events = causal_episodes(trace[record['id']], controller, record['duration_s'])
            available[name] = [e['end_available_s'] for e in events if e['end_available_s'] is not None
                               and boundary-1e-9 <= e['end_available_s'] < horizon-1e-9]
        if available['stop'] != available['resume']:
            raise ValueError('Identical histories produced different pre-resume ENDs')
        rows.append(dict(pair_id=pair_id, pause_ms=stop['condition']['pause_ms'],
            actual_rms_gap_ms=pair['measured_rms_gap_ms'], prefix_id=pair['shared_prefix_id'],
            prefix_end_s=boundary, resume_s=horizon,
            pre_resume_end_available_s=available['stop'], cuts_resume_before_future_speech=bool(available['stop'])))
    return rows


def analyze(output, frozen_selections):
    output = Path(output)
    if (output/'summary.json').exists() or (output/'summary.json.gz').exists():
        raise FileExistsError('Immutable diagnostic analysis exists')
    frozen = json.loads((output/'FROZEN.json').read_text())
    for filename,key in [('manifest.json','manifest_sha256'), ('test-manifest.json','test_manifest_sha256'),
                         ('specification.json','specification_sha256'), ('generator-frozen.py.txt','generator_snapshot_sha256')]:
        if digest(output/filename) != frozen[key]:
            raise ValueError('Frozen diagnostic input changed: '+filename)
    if frozen['stage'] != 'before_model_inference' or digest(frozen_selections) != frozen['primary_frozen_selections_sha256']:
        raise ValueError('Primary frozen selection identity changed')
    for name, expected in frozen['source_sha256'].items():
        if digest(Path(__file__).with_name(name)) != expected:
            raise ValueError('Frozen implementation changed: '+name)
    manifest, traces, runs = load_inputs(output/'manifest.json', output/'runtime-output/raw', BACKENDS)
    audit = validate_manifest(manifest, output)
    causal = audit_causal_traces(manifest['records'], traces)
    test = prepare_records([r for r in manifest['records'] if r['split']=='test'])
    if json.loads((output/'test-manifest.json').read_text()) != dict(manifest, records=[r for r in manifest['records'] if r['split']=='test']):
        raise ValueError('Test manifest does not equal provenance-test subset')
    plan, controllers = controller_plan(json.loads(Path(frozen_selections).read_text()))
    metrics, per_turn, causal_by_controller = {}, {}, {}
    for key, (backend, controller) in controllers.items():
        result = evaluate_boundaries(test, traces[backend], controller, details=True)
        per_turn[key] = result.pop('turn_results')
        metrics[key] = result
        causal_by_controller[key] = paired_cuts(test, traces[backend], controller)
    grouped = defaultdict(list)
    for record in test:
        grouped[record['condition']['branch'], record['condition']['pause_ms']].append(record)
    baseline_by_pause = []
    for row in plan:
        if row['kind'] != 'shared':
            continue
        backend, controller = row['backend'], Controller(**row['controller'])
        for (branch, pause), records in grouped.items():
            gaps = [r['causal_pair']['measured_rms_gap_ms'] for r in records]
            baseline_by_pause.append(dict(backend=backend, configuration=row['configuration'], branch=branch,
                pause_ms=pause, actual_rms_gap_ms=dict(min=min(gaps), max=max(gaps)),
                metric=evaluate_boundaries(records, traces[backend], controller)))
    summary = dict(schema_version=1, analysis_type='hard_gated_pause_diagnostic',
        dataset=dict(records=112, dev_records=56, test_records=56, test_turns=56,
            test_prefix_families=4, duration_s=112*DURATION, actual_rms_gap_ms=audit['actual_rms_gap_ms']),
        limitations=manifest['generation']['limitation'], split_policy=manifest['generation']['split_policy'],
        methodology=dict(timing='Simulated acquisition clock; excludes physical capture and computation',
            scoring='Unmodified strict nominal boundary_latency.py; first-overlapping episode, all-turn denominators',
            selection='156 primary frozen policy references, zero diagnostic selection; controllers deduplicated for replay',
            uncertainty='Outer artificial gates ±1 ms; interior 10 ms RMS transitions ±10 ms; no claim of phonetic accuracy',
            repetition='28 stopped rows repeat four unique stopped phrases; all-turn aggregates weight the seven matched pause variants equally',
            gap='Between first/last source-local RMS-active 10 ms frame bounds remeasured from emitted PCM; all inserted gap samples zero',
            cuts='END availability in [prefix RMS offset, resume RMS onset), strictly before continuation; paired histories and raw acquisition outputs exact-equal'),
        frozen_inputs=frozen, backends=BACKENDS,
        shared=[r for r in plan if r['kind']=='shared'],
        frozen_selections=[r for r in plan if r['kind']=='frozen'],
        aggregate_metrics=metrics, baseline_by_pause=baseline_by_pause,
        causal_by_controller=causal_by_controller,
        inference_audit=dict(backends=len(runs), records_per_backend=len(manifest['records']),
            raw_trace_comparisons=len(causal), identical_pre_resume_acquisition_outputs=True,
            statuses={b:r['status'] for b,r in runs.items()},
            raw_sha256={b:{suffix:digest(output/'runtime-output/raw'/f'{b}.{suffix}') for suffix in ('npz','json')} for b in BACKENDS}))
    write_result(output/'per-turn-test.json', per_turn)
    write_result(output/'causal-trace-audit.json', causal)
    path = write_result(output/'summary.json', summary)
    write_report(output, summary)
    return dict(summary=str(path), unique_controllers=len(controllers), frozen_policy_references=156,
                baseline_pause_rows=len(baseline_by_pause), audit=audit)


def write_report(output, summary):
    lines = ['# Hard-gated short-pause diagnostic', '',
        'This separate controlled diagnostic reuses the primary study’s Flite texts and voices. It is **not a fresh independent holdout**. '
        'It artificially removes faint outer speech, then applies 1 ms edge fades. Hard gating/splicing can create artifacts and remove phonetic content. '
        'The full-utterance primary study is unchanged.', '',
        '112 eight-second streams: both provenance splits, four prefix families, seven pause durations, stop/resume branches. '
        'All 56 emitted resumed streams were remeasured; actual source-local RMS gaps are exactly 50, 100, 150, 200, 300, 500, and 800 ms. '
        'All 12 backends have exact-equal raw acquisition outputs before each paired continuation. '
        'The table below uses only the 56 test-provenance streams, with four correlated phrase families per pause.', '',
        '## Shared baselines: causal premature cuts', '',
        'Each cell counts paired histories with an END notification inside the artificial pause, strictly before continuation. '
        'A stopped-phrase END this early must also cut the byte-identical resumed history.', '',
        '| Detector / added silence | 50 ms | 100 ms | 150 ms | 200 ms | 300 ms | 500 ms | 800 ms |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in summary['shared']:
        cuts = summary['causal_by_controller'][row['metric_key']]
        cells = [f"{sum(r['cuts_resume_before_future_speech'] for r in cuts if r['pause_ms']==p)}/4" for p in PAUSES_MS]
        lines.append(f"| {row['backend']} / {row['controller']['silence_s']*1000:.0f} ms | "+' | '.join(cells)+' |')
    lines += ['', '## Aggregate shared-baseline outcomes', '',
        'All 56 test-provenance turns stay in each denominator. Stop branches are repeated at the seven pause values for causal matching. '
        'These correlated variants are not 56 independent utterances. START/END are acquisition availability, not backdated boundaries.', '',
        '| Detector / silence | Recall | START ≤100 ms | END ≤300 ms | Premature first END | Fragmented | False START / negative hour |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for row in summary['shared']:
        m = summary['aggregate_metrics'][row['metric_key']]
        lines.append(f"| {row['backend']} / {row['controller']['silence_s']*1000:.0f} ms | "
            f"{100*m['source_aligned_speech_recall']:.2f}% | {100*m['onset']['deadlines_ms']['100']['fraction']:.1f}% | "
            f"{100*m['end']['deadlines_ms']['300']['fraction']:.1f}% | {m['counts']['premature_end_turns']}/56 | "
            f"{m['counts']['fragmented_turns']}/56 | {m['false_starts_per_negative_hour']:.1f} |")
    lines += ['', '## Frozen-policy reuse', '',
        f"All 156 primary development-selected policy references were reused unchanged. Along with 24 shared baseline references, "
        f"they map to {len(summary['aggregate_metrics'])} unique backend/controllers; cached raw traces were replayed once per unique controller. "
        'No threshold selection, frontier fitting, or tuning used this diagnostic. The full aggregate metrics, nominal/possible/certain deadlines, '
        'all-turn and successful-only quantiles, recall, false activity, and error counts are retained once per unique controller. '
        'Baseline duration/branch breakdowns are in baseline_by_pause; causal cuts are retained per unique controller.', '',
        '## Reproduction and evidence', '',
        '- [Protocol and schema](../../docs/BOUNDARY_PAUSE_PROBE.md)',
        '- [Pre-inference freeze](FROZEN.json), [design](specification.json), [manifest](manifest.json), [test provenance](test-manifest.json)',
        '- Summary: '+('summary.json.gz' if (Path(output)/'summary.json.gz').exists() else 'summary.json'),
        '- Per-turn outcomes and causal trace audit use compact JSON, deterministically gzipped above 1 MB',
        '- Raw traces/audio are local runtime artifacts; no second copy of primary corpus or its results is made', '']
    (Path(output)/'FINDINGS.md').write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['generate','analyze','validate'])
    parser.add_argument('--output', type=Path, default=Path('results/boundary-pause-probe'))
    parser.add_argument('--source-cache', type=Path, default=Path('data/boundary-v1/sources'))
    parser.add_argument('--frozen-selections', type=Path, default=Path('results/boundary-latency/frozen-selections.json'))
    args = parser.parse_args()
    if args.stage == 'generate':
        result = generate(args.output, args.source_cache, args.frozen_selections)
    elif args.stage == 'analyze':
        result = analyze(args.output, args.frozen_selections)
    else:
        result = validate_manifest(json.loads((args.output/'manifest.json').read_text()), args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
