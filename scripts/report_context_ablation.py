#!/usr/bin/env python3
"""Verify paired raw traces and report fixed/dev-calibrated context-only effects."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vadbench.metrics import calibrate, endpoint, evaluate, merge_intervals, THRESHOLDS

ARMS = ('context-disabled', 'context-enabled')
EXPECTED_MANIFEST = '73b60d803250b52d2c5cdea7e3a6458a3cf6907a2c171e4610a4b0234cbed52a'
COUNT_KEYS = ('tp', 'fp', 'fn', 'tn', 'false_activations', 'reference_events',
              'detected_events', 'fragmentation_events')
RATE_KEYS = ('missed_speech_fraction', 'false_positive_fraction',
             'false_activations_per_negative_hour', 'event_recall',
             'fragmentation_per_reference')


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def rates(counts):
    tp, fp, fn, tn, false, ref, detected, fragments = counts.T
    return np.column_stack((fn / (tp + fn), fp / (fp + tn),
                            false / ((fp + tn) * .01 / 3600), detected / ref,
                            fragments / ref))


def paired_bootstrap(records, per_stream, seed=20261003, repetitions=5000):
    """Paired whole-stream resampling within each fixed condition stratum.

    Thresholds remain frozen. This is descriptive within-corpus uncertainty;
    voices/texts repeat, and calibration uncertainty is not represented.
    """
    rng = np.random.default_rng(seed)
    strata = sorted({r['condition']['name'] for r in records})
    indices = np.column_stack([
        rng.choice([i for i, r in enumerate(records) if r['condition']['name'] == name],
                   size=(repetitions, sum(r['condition']['name'] == name for r in records)),
                   replace=True) for name in strata])
    count_arrays = {arm: np.array([[per_stream[arm][r['id']][k] for k in COUNT_KEYS]
                                  for r in records], dtype=float) for arm in ARMS}
    deltas = rates(count_arrays[ARMS[1]][indices].sum(axis=1)) - rates(count_arrays[ARMS[0]][indices].sum(axis=1))
    point = (rates(count_arrays[ARMS[1]].sum(axis=0)[None, :]) -
             rates(count_arrays[ARMS[0]].sum(axis=0)[None, :]))[0]
    return dict(method='paired percentile bootstrap; whole streams; stratified by condition',
                seed=seed, repetitions=repetitions, delta_direction='enabled minus disabled',
                caveat='Descriptive synthetic-corpus resampling only; repeated voices/texts are dependent; frozen thresholds; no calibration uncertainty or natural-audio coverage claim',
                metrics={key: dict(delta=float(point[i]), percentile95=np.quantile(deltas[:, i], [.025, .975]).tolist())
                         for i, key in enumerate(RATE_KEYS)})


def matched_timings(record, trace, threshold):
    truth = merge_intervals(record['speech_intervals'])
    events = endpoint(trace, threshold)
    pairs = []
    for ei, event in enumerate(events):
        for ri, (a, b) in enumerate(truth):
            overlap = max(0, min(event['end'], b) - max(event['start'], a))
            if overlap > 0:
                pairs.append((overlap, ei, ri))
    used_events, used_truth, result = set(), set(), {}
    for overlap, ei, ri in sorted(pairs, reverse=True):
        if ei in used_events or ri in used_truth:
            continue
        used_events.add(ei); used_truth.add(ri)
        event = events[ei]; a, b = truth[ri]
        result[f'{record["id"]}:{ri}'] = dict(
            onset_notification_s=event['start_notification'] - a,
            onset_clipping_s=max(0, event['start'] - a),
            end_notification_s=None if event['forced_eof'] else event['end_notification'] - b,
            end_clipping_s=max(0, b - event['end']))
    return result


def paired_timing(records, traces, thresholds):
    matches = {arm: {key: value for r in records for key, value in
                    matched_timings(r, traces[arm][r['id']], thresholds[arm]).items()} for arm in ARMS}
    common = sorted(set(matches[ARMS[0]]) & set(matches[ARMS[1]]))
    result = dict(matched_reference_events_both=len(common),
                  matched_disabled_only=len(set(matches[ARMS[0]]) - set(common)),
                  matched_enabled_only=len(set(matches[ARMS[1]]) - set(common)),
                  interpretation='Same matched reference events in both arms; signed enabled-minus-disabled per-event deltas; selection still conditional on detection')
    for key in ('onset_notification_s', 'onset_clipping_s', 'end_notification_s', 'end_clipping_s'):
        values = [matches[ARMS[1]][i][key] - matches[ARMS[0]][i][key] for i in common
                  if matches[ARMS[1]][i][key] is not None and matches[ARMS[0]][i][key] is not None]
        result[key] = dict(count=len(values), delta_mean=float(np.mean(values)) if values else None,
                           delta_p50=float(np.median(values)) if values else None,
                           delta_p05=float(np.quantile(values, .05)) if values else None,
                           delta_p95=float(np.quantile(values, .95)) if values else None)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/synthetic/manifest.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/context-ablation')
    parser.add_argument('--native-raw', type=Path, default=ROOT / 'results/silero-lite-comparison/raw/silero-lite-0.3.0.npz')
    args = parser.parse_args(); output = args.output
    manifest_bytes = args.manifest.read_bytes()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    assert manifest_hash == EXPECTED_MANIFEST
    manifest = json.loads(manifest_bytes); records = manifest['records']
    dev = [r for r in records if r['split'] == 'dev']
    holdout = [r for r in records if r['split'] == 'test']
    traces = {}; run_records = {}; timing = {}
    for arm in ARMS:
        runs = []; all_traces = []
        for repetition in (1, 2, 3):
            stem = output / f'raw/pass{repetition}' / arm
            run = json.loads(stem.with_suffix('.json').read_text())
            assert run['status'] == 'ok' and run['manifest_sha256'] == manifest_hash
            assert len(run['timing']) == 240
            with np.load(stem.with_suffix('.npz')) as data:
                all_traces.append({key: data[key] for key in data.files})
            runs.append(run)
        for data in all_traces[1:]:
            assert set(data) == set(all_traces[0])
            assert all(np.array_equal(data[key], all_traces[0][key]) for key in data), 'Accuracy differs across repeated runs'
        traces[arm] = all_traces[0]; run_records[arm] = runs
        timing[arm] = dict(passes=[dict(
            wall_rtf=sum(t['wall_s'] for t in r['timing']) / 4800,
            cpu_rtf=sum(t['cpu_s'] for t in r['timing']) / 4800,
            inference_rtf=sum(t['inference_s'] for t in r['timing']) / 4800,
            wall_s=sum(t['wall_s'] for t in r['timing']),
            startup_s=r['startup_s'], peak_process_rss_kib=r['peak_process_rss_kib']) for r in runs])
        for metric in ('wall_rtf', 'cpu_rtf', 'inference_rtf', 'wall_s', 'startup_s', 'peak_process_rss_kib'):
            values = [p[metric] for p in timing[arm]['passes']]
            timing[arm][metric] = dict(median=float(np.median(values)), min=min(values), max=max(values))
    differences = []
    for r in records:
        a, b = [traces[arm][r['id']] for arm in ARMS]
        assert a.shape == b.shape
        assert np.array_equal(a[:, [0, 1, 3]], b[:, [0, 1, 3]]), 'Ablation clocks differ'
        differences.append(np.abs(a[:, 2] - b[:, 2]))
    difference = np.concatenate(differences)
    selections, curves = {}, {}
    for arm in ARMS:
        selections[arm], curves[arm] = calibrate(dev, traces[arm])
    protocols = {}
    per_stream_protocols = {}
    for name, thresholds in [('fixed_0.5', {arm: .5 for arm in ARMS}),
                             ('dev_calibrated', {arm: selections[arm]['threshold'] for arm in ARMS})]:
        per_stream = {arm: {r['id']: evaluate([r], traces[arm], thresholds[arm]) for r in holdout} for arm in ARMS}
        per_stream_protocols[name] = per_stream
        protocols[name] = dict(
            thresholds=thresholds,
            holdout={arm: evaluate(holdout, traces[arm], thresholds[arm]) for arm in ARMS},
            conditions={condition: {arm: evaluate([r for r in holdout if r['condition']['name'] == condition], traces[arm], thresholds[arm]) for arm in ARMS}
                        for condition in sorted({r['condition']['name'] for r in holdout})},
            paired_uncertainty=paired_bootstrap(holdout, per_stream),
            paired_matched_reference_timings=paired_timing(holdout, traces, thresholds))
    native_comparison = None
    if args.native_raw.is_file():
        native_diffs = []
        with np.load(args.native_raw) as native:
            for r in records:
                a, b = native[r['id']], traces['context-enabled'][r['id']]
                assert a.shape == b.shape and np.array_equal(a[:, [0, 1, 3]], b[:, [0, 1, 3]])
                native_diffs.append(np.abs(a[:, 2] - b[:, 2]))
        diffs = np.concatenate(native_diffs)
        native_comparison = dict(frames=len(diffs), maximum_absolute_score_difference=float(diffs.max()),
                                 mean_absolute_score_difference=float(diffs.mean()),
                                 scores_differing_by_more_than_1e_6=int(np.sum(diffs > 1e-6)),
                                 note='Validation oracle only; prior actual 0.3.0 native-package trace, not a timing comparator')
    summary = dict(schema_version=1, manifest_sha256=manifest_hash,
                   dataset=dict(streams=len(records), duration_s=4800, split_counts=dict(Counter(r['split'] for r in records)), holdout_reference_events=protocols['fixed_0.5']['holdout']['context-enabled']['reference_events']),
                   arms={arm: run_records[arm][0]['adapter'] for arm in ARMS},
                   calibration=dict(split='dev', false_activations_per_negative_hour_budget=5,
                                    false_positive_fraction_cap=.01, threshold_grid=THRESHOLDS.tolist(), selections=selections),
                   protocols=protocols, timing=timing,
                   paired_trace_checks=dict(frames=len(difference), identical_clocks=True, all_three_passes_bitwise_identical=True,
                                            maximum_absolute_score_difference=float(difference.max()), mean_absolute_score_difference=float(difference.mean())),
                   enabled_vs_actual_0_3_0=native_comparison,
                   cross_threshold_holdout={str(t): {arm: evaluate(holdout, traces[arm], t) for arm in ARMS}
                                            for t in sorted({selections[arm]['threshold'] for arm in ARMS})},
                   sources=dict(base_repository_commit='a0f9e600dfdba202d9d960ea4679f3eed7a37328',
                                released_old_package_commit='a4222a5c2c6ca7b7fb1fbcc2af1d19374772d273',
                                released_fixed_package_commit='64837cae29c0a920a679f4883f3a186d37de1f86'),
                   source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [ROOT / 'vadbench/context_ablation.py', ROOT / 'vadbench/adapters.py', ROOT / 'vadbench/run.py', ROOT / 'vadbench/metrics.py', Path(__file__)]})
    dump(output / 'summary.json', summary)
    dump(output / 'development-curves.json', curves)
    dump(output / 'per-stream-holdout.json', per_stream_protocols)
    dump(output / 'runs.json', run_records)
    (output / 'dataset-manifest.json').write_bytes(manifest_bytes)
    print(json.dumps(dict(protocols=protocols, timing=timing, native_comparison=native_comparison), indent=2))


if __name__ == '__main__':
    main()
