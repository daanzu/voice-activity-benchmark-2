"""Development-only minimum-FP thresholds at specified speech-frame recall.

This analysis is separate from the historical false-event-budget calibration.
The holdout is never passed to threshold selection. Zero thresholds are reported
only as always-positive diagnostics, including for binary classic WebRTC modes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np

from .metrics import THRESHOLDS, aligned_grid, evaluate
from .run import BACKENDS

# Curves are a display sweep, not an approximation used for target selection.
DISPLAY_THRESHOLDS = np.unique(np.r_[np.geomspace(1e-12, .05, 81), THRESHOLDS])
FIXED_TARGETS = [('recall-99', '99% speech-frame recall', 99, 100),
                 ('recall-99.5', '99.5% speech-frame recall', 995, 1000),
                 ('recall-99.9', '99.9% speech-frame recall', 999, 1000)]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def checked_records(records, split):
    records = list(records)
    if not records or any(r.get('split') != split for r in records):
        raise ValueError(f'Expected nonempty {split}-only records')
    return records


def frame_arrays(records, traces):
    positive, negative = [], []
    for record in records:
        trace = np.asarray(traces[record['id']])
        if trace.ndim != 2 or trace.shape[1] != 4 or not len(trace):
            raise ValueError('Expected nonempty four-column score traces')
        if not np.isfinite(trace).all() or np.any((trace[:, 2] < 0) | (trace[:, 2] > 1)):
            raise ValueError('Scores must be finite probabilities or binary values in [0,1]')
        _, labels, scores, valid = aligned_grid(record, trace)
        positive.append(scores[valid & labels])
        negative.append(scores[valid & ~labels])
    return np.concatenate(positive), np.concatenate(negative)


def metrics(records, traces, threshold):
    result = evaluate(records, traces, threshold)
    result['speech_frame_recall'] = (1 - result['missed_speech_fraction']
                                     if result['missed_speech_fraction'] is not None else None)
    result['false_positive_seconds'] = result['fp'] * .01
    result['speech_seconds'] = (result['tp'] + result['fn']) * .01
    return result


def target_definition(identifier, label, numerator, denominator, reference_backend=None):
    fraction = Fraction(numerator, denominator)
    if not 0 < fraction <= 1:
        raise ValueError('Recall target must be in (0,1]')
    return dict(id=identifier, label=label, recall=float(fraction),
                numerator=fraction.numerator, denominator=fraction.denominator,
                reference_backend=reference_backend)


def choose_threshold(dev_records, traces, target, *, binary=False):
    """Pick max positive threshold that captures the required dev speech frames.

    Counts use exact rational targets to avoid floating-point ceil errors at a
    classic-mode parity boundary. With score >= threshold, a larger threshold
    cannot increase false-positive duration. Equal-score ties are kept together;
    ties in FP duration favor this highest feasible threshold and hence the least
    speech-recall overshoot. False-event counts are not optimized.
    """
    dev_records = checked_records(dev_records, 'dev')
    positive, negative = frame_arrays(dev_records, traces)
    if not len(positive) or not len(negative):
        raise ValueError('Development requires known speech and non-speech frames')
    fraction = Fraction(target['numerator'], target['denominator'])
    if not 0 < fraction <= 1:
        raise ValueError('Recall target must be in (0,1]')
    required = (fraction.numerator * len(positive) + fraction.denominator - 1) // fraction.denominator
    if binary:
        if not np.all(np.isin(np.r_[positive, negative], [0., 1.])):
            raise ValueError('Binary backend returned a non-binary score')
        threshold = .5
        maximum = int(np.count_nonzero(positive >= threshold))
    else:
        maximum = int(np.count_nonzero(positive > 0))
        threshold = float(np.partition(positive, len(positive) - required)[len(positive) - required])
    feasible = maximum >= required and threshold > 0
    return dict(feasible=bool(feasible), threshold=float(threshold) if feasible else None,
                required_speech_frames=int(required), known_speech_frames=len(positive),
                max_dev_recall=maximum / len(positive),
                reason=None if feasible else ('native binary point misses target' if binary else
                                               'target requires including exact-zero speech scores'),
                selection='native binary point' if binary else 'highest feasible strictly-positive dev score cutoff')


def audit_trace_coverage(records, traces, raw, expected_manifest_hash):
    if raw.get('status') != 'ok' or raw.get('manifest_sha256') != expected_manifest_hash:
        raise ValueError(f'Incomplete run or manifest mismatch: {raw.get("backend")}')
    ids = [r['id'] for r in records]
    if len(set(ids)) != len(ids) or set(traces) != set(ids):
        raise ValueError('Raw trace record coverage mismatch')
    for record in records:
        trace = traces[record['id']]
        if trace.ndim != 2 or trace.shape[1] != 4 or not len(trace) or not np.isfinite(trace).all():
            raise ValueError(f'Malformed trace: {record["id"]}')
        if np.any(trace[:, 1] <= trace[:, 0]) or np.any(np.diff(trace[:, 1]) <= 0):
            raise ValueError('Unordered score intervals')
        if np.any(np.diff(trace[:, 3]) < 0) or np.any(trace[:, 3] > record['duration_s'] + 1e-9):
            raise ValueError('Invalid acquisition clock')
    frame_arrays(records, traces)  # Verify score bounds and evaluation input.


def analyze(manifest_path, raw_directory, output):
    manifest_path, raw_directory, output = map(Path, (manifest_path, raw_directory, output))
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text())
    records = manifest['records']
    dev = checked_records([r for r in records if r['split'] == 'dev'], 'dev')
    test = checked_records([r for r in records if r['split'] == 'test'], 'test')
    if len(dev) + len(test) != len(records):
        raise ValueError('Unknown dataset split')
    manifest_hash = sha256(manifest_path)
    raw_runs, traces_by_backend = {}, {}
    for backend in BACKENDS:
        raw_path = raw_directory / f'{backend}.json'
        raw = json.loads(raw_path.read_text())
        if raw.get('backend') != backend:
            raise ValueError('Backend identity mismatch')
        with np.load(raw_path.with_suffix('.npz'), allow_pickle=False) as loaded:
            traces = {key: loaded[key] for key in loaded.files}
        audit_trace_coverage(records, traces, raw, manifest_hash)
        raw_runs[backend], traces_by_backend[backend] = raw, traces

    references = []
    targets = [target_definition(*args) for args in FIXED_TARGETS]
    for backend in [f'classic-{mode}' for mode in range(4)]:
        traces = traces_by_backend[backend]
        dev_metric = metrics(dev, traces, .5)
        references.append(dict(backend=backend, threshold=.5, dev=dev_metric,
                               test=None))
        targets.append(target_definition('match-' + backend, backend + ' development recall',
                                        dev_metric['tp'], dev_metric['tp'] + dev_metric['fn'], backend))
    # Phase 1: freeze ALL thresholds using development-only records and traces.
    selections = []
    for backend in BACKENDS:
        for target in targets:
            choice = choose_threshold(dev, traces_by_backend[backend], target,
                                      binary=raw_runs[backend]['adapter']['score_kind'] == 'binary')
            selections.append(dict(backend=backend, target_id=target['id'], target_recall=target['recall'],
                                   **choice, dev=None, test=None))
    frozen = [{k: row[k] for k in ('backend', 'target_id', 'target_recall', 'feasible', 'threshold',
                                  'required_speech_frames', 'known_speech_frames', 'max_dev_recall',
                                  'reason', 'selection')} for row in selections]
    write_json(output / 'frozen-thresholds.json', dict(manifest_sha256=manifest_hash, split='dev',
                                                     targets=targets, selections=frozen))
    # Phase 2: evaluate the frozen positive cutoffs on each split without retuning.
    for reference in references:
        reference['test'] = metrics(test, traces_by_backend[reference['backend']], .5)
    cache = {}
    def point(backend, split, threshold):
        key = (backend, split, threshold)
        if key not in cache:
            cache[key] = metrics(dev if split == 'dev' else test, traces_by_backend[backend], threshold)
        return cache[key]
    for row in selections:
        if row['feasible']:
            for split, destination in [('dev', 'dev'), ('test', 'test')]:
                row[destination] = point(row['backend'], split, row['threshold'])
    curves, diagnostics, max_positive_points, fixed_references = {}, [], [], []
    for backend in BACKENDS:
        print('Scoring development sweep:', backend, flush=True)
        binary = raw_runs[backend]['adapter']['score_kind'] == 'binary'
        chosen = [r['threshold'] for r in selections if r['backend'] == backend and r['feasible']]
        thresholds = np.unique(np.r_[[.5] if binary else DISPLAY_THRESHOLDS, chosen])
        curves[backend] = [point(backend, 'dev', float(t)) for t in thresholds]
        diagnostics.append(dict(backend=backend, threshold=0., diagnostic='always-positive; excluded from selection',
                                dev=point(backend, 'dev', 0.), test=point(backend, 'test', 0.)))
        floor = .5 if binary else float(np.nextafter(0., 1.))
        max_positive_points.append(dict(backend=backend, threshold=floor,
                                        dev=point(backend, 'dev', floor), test=None,
                                        diagnostic='maximum recall with strictly-positive cutoff; dev only'))
        threshold = {'fsmn': .8, 'speex': .35}.get(backend, .5)
        fixed_references.append(dict(backend=backend, threshold=threshold,
                                     dev=point(backend, 'dev', threshold), test=point(backend, 'test', threshold)))

    provenance_path = output / 'provenance.json'
    provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    summary = dict(schema_version=1, analysis_type='recall_first', manifest_sha256=manifest_hash,
                   dataset=dict(streams=len(records), hours=sum(r['duration_s'] for r in records) / 3600,
                                split_counts=dict(Counter(r['split'] for r in records)), generation=manifest['generation']),
                   calibration=dict(split='dev', target_metric='speech_frame_recall', objective='minimum false-positive frame duration',
                                    selection='highest feasible strictly-positive cutoff from exact development speech-score order statistics; score >= cutoff',
                                    tie_break='highest feasible threshold; equal score ties included together, minimizing recall overshoot among minimum-FP choices',
                                    binary_policy='native 0.5 point only; unmet recall is unattainable',
                                    threshold_zero='always-positive diagnostic only; never a feasible candidate',
                                    false_event_policy='reported separately; not minimized or constrained',
                                    holdout_policy='all choices frozen before evaluating holdout; holdout may miss development target',
                                    display_threshold_grid=DISPLAY_THRESHOLDS.tolist()),
                   targets=targets, selections=selections, classic_references=references, diagnostics=diagnostics,
                   max_positive_points=max_positive_points, fixed_references=fixed_references,
                   provenance=provenance, raw_trace_sha256={b: sha256(raw_directory / f'{b}.npz') for b in BACKENDS},
                   source_sha256={str(p.relative_to(Path(__file__).resolve().parents[1])): sha256(p)
                                  for p in sorted(Path(__file__).parent.glob('*.py'))},
                   frozen_thresholds_sha256=sha256(output / 'frozen-thresholds.json'))
    write_json(output / 'summary.json', summary)
    curve_keys = ('threshold', 'task', 'tp', 'fp', 'fn', 'tn', 'missed_speech_fraction',
                  'speech_frame_recall', 'false_positive_fraction', 'false_positive_seconds',
                  'false_activations', 'negative_hours', 'false_activations_per_negative_hour',
                  'reference_events', 'detected_events', 'event_recall', 'fragmentation_events',
                  'excluded_seconds')
    curve_output = {backend: [{key: point[key] for key in curve_keys} for point in points]
                    for backend, points in curves.items()}
    (output / 'development-curves.json').write_text(json.dumps(curve_output, separators=(',', ':'), allow_nan=False) + '\n')
    write_json(output / 'runs.json', raw_runs)
    (output / 'dataset-manifest.json').write_bytes(manifest_path.read_bytes())
    print(json.dumps({'backends': len(BACKENDS), 'targets': len(targets), 'selections': len(selections),
                      'feasible': sum(r['feasible'] for r in selections), 'output': str(output)}), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--raw', type=Path, default=Path('results/recall-first/raw'))
    parser.add_argument('--output', type=Path, default=Path('results/recall-first'))
    args = parser.parse_args()
    analyze(args.manifest, args.raw, args.output)


if __name__ == '__main__':
    main()
