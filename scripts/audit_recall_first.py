"""Independent retained-result audit; imports no vadbench selector or metrics code.

Run after inference and analysis finish. This independently maps raw intervals
onto the published 10 ms grid with bisect, sorts speech scores rather than using
the selector's partition, and recomputes frame and event metrics. It never runs
inference or modifies the primary measurements.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import chi2


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label_grid(record):
    # Preserve the benchmark's explicitly specified floating-point grid so the
    # audit tests identical observations, not a different rounding convention.
    centers = np.arange(.005, record['duration_s'], .01)
    labels = np.array([any(a <= t < b for a, b in record['speech_intervals'])
                       for t in centers])
    uncertain = np.array([any(a <= t < b for a, b in record.get('uncertain_intervals', []))
                          for t in centers])
    return centers, labels, uncertain


def grid(record, trace, label_data=None):
    centers, labels, uncertain = label_data if label_data is not None else label_grid(record)
    ends = trace[:, 1].tolist()
    ix = np.array([bisect_right(ends, float(t)) for t in centers])
    in_range = ix < len(trace)
    safe_ix = np.minimum(ix, len(trace) - 1)
    covered = in_range & (centers >= trace[safe_ix, 0])
    valid = covered & ~uncertain
    return dict(times=centers, labels=labels, scores=trace[safe_ix, 2], valid=valid,
                covered=covered, uncertain=uncertain)


def events(trace, cutoff):
    result, active, negative_start = [], None, None
    for start, stop, score, received in trace:
        if score >= cutoff:
            if active is None:
                active = (start, received)
            negative_start = None
        elif active is not None:
            if negative_start is None:
                negative_start = start
            if stop - negative_start >= .2 - 1e-9:
                result.append((*active, negative_start, received, False))
                active = negative_start = None
    if active is not None:
        result.append((*active, trace[-1, 1], trace[-1, 3], True))
    return result


def merged_truth(record):
    truth = []
    for start, stop in sorted(record['speech_intervals']):
        if truth and start - truth[-1][1] <= .2:
            truth[-1][1] = max(stop, truth[-1][1])
        else:
            truth.append([start, stop])
    return truth


def independent_metrics(records, traces, grids, cutoff):
    counts = Counter()
    distributions = {k: [] for k in ('onset_clipping', 'onset_notification',
                                      'end_clipping', 'end_notification')}
    for record in records:
        trace, g = traces[record['id']], grids[record['id']]
        y, p, v = g['labels'], g['scores'] >= cutoff, g['valid']
        for name, mask in [('tp', y & p), ('fn', y & ~p), ('fp', ~y & p), ('tn', ~y & ~p)]:
            counts[name] += int(np.count_nonzero(mask & v))
        counts['excluded'] += int(np.count_nonzero(~v))
        predicted, truth = events(trace, cutoff), merged_truth(record)
        counts['reference_events'] += len(truth)
        overlaps = []
        for ei, event in enumerate(predicted):
            for ri, (start, stop) in enumerate(truth):
                overlap = min(event[2], stop) - max(event[0], start)
                if overlap > 0:
                    overlaps.append((overlap, ei, ri))
        matched_e, matched_r, matches = set(), set(), []
        for _, ei, ri in sorted(overlaps, reverse=True):
            if ei not in matched_e and ri not in matched_r:
                matched_e.add(ei)
                matched_r.add(ri)
                matches.append((ei, ri))
        overlaps_e = {ei for _, ei, _ in overlaps}
        for ei, event in enumerate(predicted):
            if ei in matched_e:
                continue
            if ei in overlaps_e:
                counts['fragmentation_events'] += 1
            elif np.any((g['times'] >= event[0]) & (g['times'] < event[2]) & v & ~y):
                counts['false_activations'] += 1
            else:
                counts['ambiguous_events'] += 1
        for ei, ri in matches:
            start, onset_time, stop, end_time, forced = predicted[ei]
            truth_start, truth_stop = truth[ri]
            distributions['onset_clipping'].append(max(0, start - truth_start))
            distributions['onset_notification'].append(onset_time - truth_start)
            distributions['end_clipping'].append(max(0, truth_stop - stop))
            if forced:
                counts['forced_eof_events'] += 1
            else:
                distributions['end_notification'].append(end_time - truth_stop)
        counts['detected_events'] += len(matched_r)
    tp, fp, fn, tn = (counts[k] for k in ('tp', 'fp', 'fn', 'tn'))
    negatives_h = (fp + tn) * .01 / 3600
    false = counts['false_activations']
    delays = distributions['end_notification']
    result = {key: counts[key] for key in ('tp', 'fp', 'fn', 'tn', 'reference_events',
              'detected_events', 'false_activations', 'fragmentation_events',
              'ambiguous_events', 'forced_eof_events')}
    result.update(threshold=float(cutoff), task='speech',
        missed_speech_fraction=fn/(tp+fn) if tp+fn else None,
        speech_frame_recall=tp/(tp+fn) if tp+fn else None,
        false_positive_fraction=fp/(fp+tn) if fp+tn else None,
        false_positive_seconds=fp*.01, speech_seconds=(tp+fn)*.01,
        negative_hours=negatives_h, excluded_seconds=counts['excluded']*.01,
        false_activations_per_negative_hour=false/negatives_h if negatives_h else None,
        false_activation_rate_poisson95=([float(chi2.ppf(.025, 2*false)/2/negatives_h) if false else 0.,
                                        float(chi2.ppf(.975, 2*(false+1))/2/negatives_h)] if negatives_h else None),
        event_recall=counts['detected_events']/counts['reference_events'] if counts['reference_events'] else None,
        fragmentation_per_reference=counts['fragmentation_events']/counts['reference_events'] if counts['reference_events'] else None,
        latency_matched_event_count=len(delays),
        premature_notification_fraction=sum(d < 0 for d in delays)/len(delays) if delays else None)
    for name, values in distributions.items():
        for percentile in (50, 95):
            result[f'{name}_p{percentile}_s'] = float(np.percentile(values, percentile)) if values else None
    return result


def support(records, grids):
    c = Counter()
    for record in records:
        g = grids[record['id']]
        c['total_frames'] += len(g['times'])
        c['known_speech_frames'] += int(np.count_nonzero(g['labels'] & g['valid']))
        c['known_negative_frames'] += int(np.count_nonzero(~g['labels'] & g['valid']))
        c['uncertain_frames'] += int(np.count_nonzero(g['uncertain']))
        c['uncovered_known_speech_frames'] += int(np.count_nonzero(~g['covered'] & ~g['uncertain'] & g['labels']))
        c['uncovered_known_negative_frames'] += int(np.count_nonzero(~g['covered'] & ~g['uncertain'] & ~g['labels']))
    return dict(c)


def audit(directory):
    directory = Path(directory)
    summary = json.loads((directory/'summary.json').read_text())
    frozen = json.loads((directory/'frozen-thresholds.json').read_text())
    manifest_path = directory/'dataset-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    records = manifest['records']
    splits = {split: [r for r in records if r['split'] == split] for split in ('dev', 'test')}
    differences, coverage, checks, metric_cache = [], {}, Counter(), {}

    def compare(path, actual, expected):
        checks['comparisons'] += 1
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                differences.append(f'{path}: expected object, found {actual!r}')
            else:
                for key, value in expected.items():
                    compare(f'{path}.{key}', actual.get(key), value)
        elif isinstance(expected, (list, tuple)):
            if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
                differences.append(f'{path}: sequence differs')
            else:
                for i, (a, e) in enumerate(zip(actual, expected)):
                    compare(f'{path}[{i}]', a, e)
        elif isinstance(expected, float):
            if not isinstance(actual, (int, float)) or not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
                differences.append(f'{path}: retained {actual!r}; independent {expected!r}')
        elif actual != expected:
            differences.append(f'{path}: retained {actual!r}; independent {expected!r}')

    compare('manifest_hash', summary['manifest_sha256'], digest(manifest_path))
    compare('frozen_hash', summary['frozen_thresholds_sha256'], digest(directory/'frozen-thresholds.json'))
    compare('frozen_manifest', frozen['manifest_sha256'], digest(manifest_path))
    compare('frozen_split', frozen['split'], 'dev')
    compare('frozen_targets', frozen['targets'], summary['targets'])
    compare('frozen_selection_count', len(frozen['selections']), len(summary['selections']))
    compare('selection_count', len(summary['selections']), 84)
    compare('unique_selection_count', len({(r['backend'],r['target_id']) for r in summary['selections']}), 84)
    for frozen_row, row in zip(frozen['selections'], summary['selections']):
        compare('frozen_choice', {key:row[key] for key in frozen_row}, frozen_row)
    targets = {t['id']: t for t in summary['targets']}
    compare('target_count', len(targets), 7)
    for name, expected in [('recall-99', Fraction(99,100)), ('recall-99.5', Fraction(995,1000)), ('recall-99.9', Fraction(999,1000))]:
        target = targets[name]
        compare(name, Fraction(target['numerator'],target['denominator']), expected)
    backend_names = list(summary['raw_trace_sha256'])
    compare('backend_count', len(backend_names), 12)
    independently_measured = {}
    labels = {r['id']:label_grid(r) for r in records}
    for backend in backend_names:
        raw_path = directory/'raw'/f'{backend}.npz'
        raw = json.loads(raw_path.with_suffix('.json').read_text())
        compare(f'{backend}.status', raw['status'], 'ok')
        compare(f'{backend}.manifest', raw['manifest_sha256'], digest(manifest_path))
        compare(f'{backend}.raw_hash', summary['raw_trace_sha256'][backend], digest(raw_path))
        with np.load(raw_path, allow_pickle=False) as z:
            traces = {key:z[key] for key in z.files}
        compare(f'{backend}.ids', sorted(traces), sorted(r['id'] for r in records))
        for rid, trace in traces.items():
            if trace.ndim != 2 or trace.shape[1] != 4 or len(trace) == 0 or not np.isfinite(trace).all():
                raise ValueError(f'Malformed raw trace: {backend}/{rid}')
            compare(f'{backend}.{rid}.bounded_scores', bool(np.all((trace[:,2] >= 0) & (trace[:,2] <= 1))), True)
            compare(f'{backend}.{rid}.ordered_nonoverlapping_intervals', bool(np.all(trace[:,1] > trace[:,0]) and np.all(trace[1:,0] >= trace[:-1,1] - 1e-12)), True)
        grids = {r['id']: grid(r, traces[r['id']],labels[r['id']]) for r in records}
        coverage[backend] = {split:support(recs,grids) for split,recs in splits.items()}

        def point(split, cutoff):
            key = (backend, split, cutoff)
            if key not in metric_cache:
                metric_cache[key] = independent_metrics(splits[split],traces,grids,cutoff)
            return metric_cache[key]

        positive = np.concatenate([grids[r['id']]['scores'][grids[r['id']]['valid'] & grids[r['id']]['labels']] for r in splits['dev']])
        ordered = sorted(positive.tolist(), reverse=True)
        binary = raw['adapter']['score_kind'] == 'binary'
        if binary:
            compare(f'{backend}.binary', bool(all(np.isin(t[:,2],[0.,1.]).all() for t in traces.values())), True)
        max_count = sum(p > 0 for p in ordered)
        for row in [r for r in summary['selections'] if r['backend'] == backend]:
            target = targets[row['target_id']]
            fraction = Fraction(target['numerator'],target['denominator'])
            required = math.ceil(fraction*len(ordered))
            feasible = max_count >= required
            cutoff = (.5 if binary else ordered[required-1]) if feasible else None
            label = f'{backend}/{row["target_id"]}'
            compare(label+'.feasible', row['feasible'], feasible)
            # Exact equality is intentional for threshold/order-statistic identity.
            compare(label+'.exact_threshold', row['threshold'] == cutoff, True)
            compare(label+'.required', row['required_speech_frames'], required)
            compare(label+'.support', row['known_speech_frames'], len(ordered))
            compare(label+'.max_recall', row['max_dev_recall'], max_count/len(ordered))
            checks['choices'] += 1
            if feasible:
                checks['feasible_choices'] += 1
                for split in splits:
                    measured = point(split,cutoff)
                    compare(label+'.'+split, row[split], measured)
                    if split == 'dev':
                        compare(label+'.meets_target', measured['tp'] >= required, True)
                if not binary:
                    compare(label+'.strictly_higher_fails', sum(p > cutoff for p in ordered) < required, True)
            else:
                compare(label+'.dev', row['dev'], None)
                compare(label+'.test', row['test'], None)
        for section in ('classic_references', 'diagnostics', 'max_positive_points', 'fixed_references'):
            for row in [r for r in summary[section] if r['backend'] == backend]:
                for split in splits:
                    if row.get(split) is not None:
                        compare(f'{section}/{backend}/{split}', row[split], point(split,row['threshold']))
                if section == 'classic_references':
                    m = point('dev',.5)
                    independently_measured[backend] = m
                if section == 'diagnostics':
                    compare(f'{backend}.zero_diagnostic', row['threshold'], 0.)
                    for split in splits:
                        compare(f'{backend}.zero_all_speech_{split}', point(split,0.)['fn'], 0)
                        compare(f'{backend}.zero_all_negative_{split}', point(split,0.)['tn'], 0)
    for backend, m in independently_measured.items():
        target = targets['match-'+backend]
        compare(backend+'.parity_fraction', Fraction(target['numerator'],target['denominator']), Fraction(m['tp'],m['tp']+m['fn']))
    checks['unique_metric_points'] = len(metric_cache)
    checks['raw_traces'] = len(records)*len(backend_names)
    return dict(status='passed' if not differences else 'failed', checks=dict(checks), differences=differences,
                coverage=coverage, summary_sha256=digest(directory/'summary.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=Path('results/recall-first'))
    parser.add_argument('--json', type=Path, help='Optional independent audit output')
    args = parser.parse_args()
    result = audit(args.results)
    output = json.dumps(result, indent=2, allow_nan=False)+'\n'
    if args.json:
        args.json.write_text(output)
    print(output)
    if result['differences']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
