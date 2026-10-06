"""Freeze development-only controller selections, then evaluate untouched test."""
from __future__ import annotations
import argparse
from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import time
import numpy as np
from .boundary_latency import (Controller, ONSET_DEADLINES, END_DEADLINES,
    evaluate_boundaries, prepare_records)
from .recall_first import choose_threshold, target_definition, audit_trace_coverage
from .run import BACKENDS

SILENCES = (0., .032, .064, .1, .15, .2, .3, .5)
CONFIRMATIONS = (0., .032, .064)
RECALL_TARGETS = ((99,100), (995,1000), (999,1000))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False)+'\n')


def candidate_controllers(dev, traces, binary=False):
    """Four development-selected score cutoffs, duration/hysteresis grid; no zero cutoff."""
    if not dev or any(r['split'] != 'dev' for r in dev):
        raise ValueError('Controller selection requires development-only records')
    thresholds = {.5}
    threshold_choices = []
    for n, d in RECALL_TARGETS:
        target = target_definition(f'recall-{n}/{d}', f'{n/d:.3%}', n, d)
        choice = choose_threshold(dev, traces, target, binary=binary)
        threshold_choices.append(dict(target=target, **choice))
        if choice['feasible']:
            thresholds.add(choice['threshold'])
    controllers = {}
    for on in sorted(thresholds):
        for ratio in ((1.,) if binary else (1., .5)):
            for start in CONFIRMATIONS:
                for silence in SILENCES:
                    c = Controller(on, on*ratio, start, silence)
                    controllers[c.id] = c
    return list(controllers.values()), threshold_choices


def objectives(metric):
    n = metric['counts']['turns']
    if not n or metric['negative_hours'] <= 0:
        raise ValueError('Selection requires speech turns and reference-negative exposure')
    return [1-metric['onset']['deadlines_ms']['100']['fraction'],
            1-metric['end']['deadlines_ms']['300']['fraction'],
            1-metric['source_aligned_speech_recall'],
            metric['false_starts_per_negative_hour'],
            metric['operational_false_positive_fraction'],
            metric['counts']['premature_end_turns']/n,
            metric['counts']['fragmented_turns']/n]


def pareto_indices(metrics):
    x = np.asarray([objectives(m) for m in metrics])
    return [i for i in range(len(x)) if not np.any(np.all(x <= x[i]+1e-12, axis=1) &
                                                    np.any(x < x[i]-1e-12, axis=1))]


def choose_points(metrics):
    """Predeclared representatives, not a production recommendation/error budget."""
    def cost(m):
        return (m['operational_false_positive_fraction'], m['false_starts_per_negative_hour'], m['counts']['premature_end_turns'],
                m['counts']['fragmented_turns'], m['controller_id'])
    selections = [dict(policy='recall-priority', label='Maximum source-aligned speech coverage',
        index=min(range(len(metrics)), key=lambda i:(-metrics[i]['source_aligned_speech_recall'], *cost(metrics[i]))))]
    for s in ONSET_DEADLINES:
        for e in END_DEADLINES:
            key=f'{round(s*1000)}/{round(e*1000)}'
            selections.append(dict(policy='joint-'+key.replace('/', '-'),
                label=f'Best development intact-turn success within START {round(s*1000)} / END {round(e*1000)} ms',
                index=min(range(len(metrics)), key=lambda i:(-metrics[i]['joint_intact_deadlines'][key]['fraction'],
                    -metrics[i]['source_aligned_speech_recall'], *cost(metrics[i])))))
    return selections


def load_inputs(manifest_path, raw_dir, backends):
    manifest = json.loads(Path(manifest_path).read_text())
    records = manifest['records']
    traces, runs = {}, {}
    for backend in backends:
        path = Path(raw_dir)/f'{backend}.json'
        run = json.loads(path.read_text())
        if run.get('backend') != backend:
            raise ValueError('Backend identity mismatch')
        with np.load(path.with_suffix('.npz'), allow_pickle=False) as z:
            traces[backend] = {key: z[key] for key in z.files}
        audit_trace_coverage(records, traces[backend], run, digest(manifest_path))
        runs[backend] = run
    return manifest, traces, runs


def analyze(manifest_path, raw_dir, output, backends=BACKENDS, *, exploratory=False):
    manifest_path, raw_dir, output = map(Path, (manifest_path, raw_dir, output))
    if (output/'frozen-selections.json').exists():
        raise FileExistsError('Immutable analysis output exists; choose a fresh directory')
    output.mkdir(parents=True, exist_ok=True)
    manifest, traces, runs = load_inputs(manifest_path, raw_dir, backends)
    if not exploratory:
        freeze_path=manifest_path.parent/'FROZEN.json'
        test_path=manifest_path.parent/'test-manifest.json'
        if not freeze_path.exists() or not test_path.exists():
            raise ValueError('Frozen stress analysis requires FROZEN.json and test-manifest.json; old corpus must use --exploratory')
        freeze=json.loads(freeze_path.read_text())
        frozen_test=json.loads(test_path.read_text())
        if (freeze.get('stage') != 'before_model_scoring_and_selection'
            or freeze.get('manifest_sha256') != digest(manifest_path)
            or freeze.get('test_manifest_sha256') != digest(test_path)
            or frozen_test != dict(manifest, records=[r for r in manifest['records'] if r['split']=='test'])
            or any('turns' not in r for r in manifest['records'])):
            raise ValueError('Frozen corpus/test manifest/explicit turn identity verification failed')
    records = manifest['records']
    dev = prepare_records([r for r in records if r['split']=='dev'])
    test = prepare_records([r for r in records if r['split']=='test'])
    if not dev or not test or len(dev)+len(test) != len(records):
        raise ValueError('Expected nonempty disjoint dev/test record sets')
    # Record manifest and code hashes BEFORE any threshold/controller selection.
    frozen_inputs = dict(manifest_sha256=digest(manifest_path),
        test_manifest_sha256=digest(manifest_path.parent/'test-manifest.json')
            if (manifest_path.parent/'test-manifest.json').exists() else None,
        source_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('boundary*.py')},
        raw_sha256={b:{ext:digest(raw_dir/f'{b}.{ext}') for ext in ['npz','json']} for b in backends},
        mode='exploratory_old_corpus' if exploratory else 'frozen_synthetic_stress_test',
        test_used_for_selection=False,
        test_label_access_before_selection='manifest/reference validation only, not controller choice')
    write_json(output/'frozen-inputs.json', frozen_inputs)
    selections, curves, shared, threshold_choices = [], [], [], []
    dev_cache = {}
    begin = time.monotonic()
    for backend in backends:
        candidates, thresholds = candidate_controllers(dev, traces[backend],
            runs[backend]['adapter']['score_kind']=='binary')
        threshold_choices.append(dict(backend=backend, choices=thresholds))
        metrics=[]
        for c in candidates:
            m=evaluate_boundaries(dev, traces[backend], c)
            metrics.append(m);dev_cache[backend,c.id]=m
        frontier = set(pareto_indices(metrics))
        curves.extend(dict(backend=backend, metric=m, pareto=i in frontier) for i,m in enumerate(metrics))
        for selection in choose_points(metrics):
            m=metrics[selection.pop('index')]
            selections.append(dict(backend=backend, **selection, controller=m['controller'], dev=m, test=None))
        for silence in (0., .2):
            c=Controller(silence_s=silence)
            shared.append(dict(backend=backend, configuration=f'common-{round(silence*1000)}ms',
                controller=asdict(c), dev=dev_cache[backend,c.id], test=None))
        print(f'Dev {backend}: {len(metrics)} configurations, {len(frontier)} Pareto points; {time.monotonic()-begin:.1f}s', flush=True)
    # All choices and their source hashes are committed to disk before test scoring.
    write_json(output/'frozen-selections.json', dict(**frozen_inputs,
        threshold_choices=threshold_choices, selections=[{k:v for k,v in s.items() if k not in ('dev','test')} for s in selections],
        grid=dict(silence_s=SILENCES, start_confirmation_s=CONFIRMATIONS, off_on_ratios=[1.,.5],
            thresholds='0.5 plus attainable dev speech-frame recall 99/99.5/99.9 percent; binary native 0.5 only'),
        selection='12 predeclared START/END joint-success targets plus max source-coverage reference; tie: coverage, operational false-positive duration, false START, premature END, fragmentation, stable controller ID'))
    cache, breakdowns = {}, []
    for row in shared+selections:
        backend=row['backend'];c=Controller(**row['controller']);key=(backend,c.id)
        if key not in cache:
            cache[key]=evaluate_boundaries(test,traces[backend],c,details=True)
        row['test']={k:v for k,v in cache[key].items() if k!='turn_results'}
    # Frozen selection breakdowns retain all turns, no subgroup retuning.
    grouped=defaultdict(list)
    for record in test:
        grouped[record['condition']['name']].append(record)
    subset_cache={}
    for row in selections:
        backend=row['backend'];c=Controller(**row['controller'])
        for condition, subset in grouped.items():
            key=(backend,c.id,condition)
            if key not in subset_cache:
                subset_cache[key]=evaluate_boundaries(subset,traces[backend],c)
            breakdowns.append(dict(backend=backend,policy=row['policy'],condition=condition,metric=subset_cache[key]))
    details=[dict(backend=b,controller_id=c,turn_results=m['turn_results']) for (b,c),m in cache.items()]
    write_json(output/'per-turn-test.json', details)
    write_json(output/'development-curves.json', curves)
    summary=dict(schema_version=1,analysis_type='boundary_latency',
        manifest_sha256=digest(manifest_path), backends=list(backends),
        dataset=dict(records=len(records),dev_records=len(dev),test_records=len(test),
            duration_s=sum(r['duration_s'] for r in records),dev_turns=sum(len(r['_boundary_reference']['turns']) for r in dev),
            test_turns=sum(len(r['_boundary_reference']['turns']) for r in test)),
        methodology=dict(mode=frozen_inputs['mode'], timing='simulated audio acquisition, excludes real computation and device I/O',
            matching='first acoustic-overlapping episode, chronological one-to-one; no fragment rescue',
            end_metric='first-episode END boundary success; early or nominally clipped endpoints fail; joint_intact additionally requires no fragmentation or merges',
            turn_definition='explicit construction identity; acoustic activity and interior pauses are separate',
            denominator='every turn, including misses, early-active, unmatched, premature, censored and uncertain references',
            quantiles='nearest-rank inverse empirical CDF; unsuccessful responses count as infinity; null+reached=false means unreachable',
            false_starts='first positive evidence interval has no acoustic or uncertain support, even if episode later overlaps speech',
            negative_exposure='reference-only 1ms definite-negative grid, backend-independent',
            source_alignment='adapter source clocks; native undocumented alignment retained, not inferred; native overhang is not a raw posterior',
            uncertainty='nominal, possible and certain boundary bands; source-activity proxies, not phonetic/human truth',
            selection='development-only frozen points; all deadlines exploratory design choices, no production error budget or winner',
            frontier='dev nondominated onset100 failure/end300 failure/source missed fraction/false START rate/operational false-positive fraction/premature END/fragmentation',
            limits='Synthetic English TTS, repeated source families; test frozen but only two voices per split; no independent-turn confidence intervals or semantic turn-completion claims'),
        shared=shared,selections=selections,development_curves=curves,breakdowns=breakdowns,
        runtime=dict(python=platform.python_version(),analysis_wall_s=time.monotonic()-begin),
        inference_metadata={b:runs[b] for b in backends},frozen_inputs=frozen_inputs)
    write_json(output/'summary.json',summary)
    (output/'dataset-manifest.json').write_bytes(manifest_path.read_bytes())
    for name in ['FROZEN.json', 'test-manifest.json']:
        if (manifest_path.parent/name).exists():
            (output/name).write_bytes((manifest_path.parent/name).read_bytes())
    print(json.dumps(dict(output=str(output),selections=len(selections),candidates=len(curves))),flush=True)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--backends',nargs='+',default=BACKENDS)
    p.add_argument('--exploratory',action='store_true');a=p.parse_args()
    analyze(a.manifest,a.raw,a.output,a.backends,exploratory=a.exploratory)

if __name__=='__main__':main()
