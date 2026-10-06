"""Independent retained-result audit; no production evaluator/selector imports.

The default path uses only the Python standard library and retained JSON. Add
--raw to validate all NPZ traces and independently replay both shared baseline
controllers. NumPy is imported only for loading/validating raw arrays. This is
an arithmetic/provenance audit, not an independent endorsement of the labels.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import gzip
import json
import math
from pathlib import Path


BACKENDS = ('classic-0', 'classic-1', 'classic-2', 'classic-3', 'silero',
            'silero-lite-0.3.0', 'silero-lite-0.4.0', 'agc2', 'ten',
            'fsmn', 'rnnoise', 'speex')
MANIFEST_SHA256 = '9fba764ac3692dba68712e5b6ea78904288bc479cf44292c4a8a81ed089a7106'
TEST_SHA256 = 'd92496d5f067835f07026989340ccf91b59c3d8157ac0499c426793f739a7154'
ONSET_MS = (50, 100, 200)
END_MS = (100, 200, 300, 500)
EPS = 1e-9
REPO = Path(__file__).resolve().parents[1]


def retained_bytes(path):
    path = Path(path)
    if path.exists():
        return path.read_bytes()
    compressed = path.with_name(path.name+'.gz')
    if compressed.exists():
        return gzip.decompress(compressed.read_bytes())
    raise FileNotFoundError(path)


def sha256(path):
    """Hash original logical bytes, including when storage is lossless gzip."""
    return hashlib.sha256(retained_bytes(path)).hexdigest()


def read_json(path):
    def reject_constant(value):
        raise ValueError('Nonstandard JSON number: '+value)
    return json.loads(retained_bytes(path), parse_constant=reject_constant)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def close(actual, expected, label):
    if expected is None:
        require(actual is None, f'{label}: {actual!r} != None')
    else:
        require(isinstance(actual, (int, float)) and math.isfinite(actual)
                and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-8),
                f'{label}: {actual!r} != {expected!r}')


def controller_id(c):
    return f'on={c["on"]:.17g};off={c["off"]:.17g};start={c["start_s"]:.6g};silence={c["silence_s"]:.6g}'


def expected_quantiles(values, denominator=None):
    values = sorted(v for v in values if v is not None)
    n = len(values) if denominator is None else denominator
    answer = dict(observations=len(values), denominator=n)
    for p in (50, 90, 95):
        rank = (p*n+99)//100
        reached = 0 < rank <= len(values)
        answer[f'p{p}'] = dict(reached=reached,
                                seconds=values[rank-1] if reached else None)
    return answer


def check_quantiles(q, label, *, nonnegative=True):
    n, observations = q['denominator'], q['observations']
    require(isinstance(n, int) and isinstance(observations, int)
            and 0 <= observations <= n, f'{label}: invalid quantile denominator')
    previous = -math.inf
    for p in (50, 90, 95):
        item = q[f'p{p}']
        reached = n > 0 and (p*n+99)//100 <= observations
        require(item['reached'] is reached, f'{label}: incorrect p{p} reachability')
        value = item['seconds']
        if reached:
            require(isinstance(value, (int, float)) and math.isfinite(value),
                    f'{label}: reached quantile is not finite')
            require(value >= previous, f'{label}: quantiles out of order')
            require(not nonnegative or value >= -EPS, f'{label}: negative latency/clipping')
            previous = value
        else:
            require(value is None, f'{label}: unreachable quantile must be null')


def check_deadline(entry, n, label):
    successes, total = entry['successes'], entry['total']
    require(total == n and isinstance(successes, int) and 0 <= successes <= n,
            f'{label}: wrong all-turn deadline numerator/denominator')
    close(entry['fraction'], successes/n if n else None, label+' fraction')


def check_metric(metric, expected_turns, label):
    c, counts = metric['controller'], metric['counts']
    require(metric['controller_id'] == controller_id(c), label+': controller ID')
    require(0 < c['off'] <= c['on'] <= 1 and c['start_s'] >= 0
            and c['silence_s'] >= 0, label+': invalid controller')
    require(counts['turns'] == expected_turns, label+': dropped or extra turns')
    for name, count in counts.items():
        require(isinstance(count, int) and count >= 0, f'{label}/{name}: negative/noninteger count')
        if name.endswith('_turns') and name != 'merged_turns':
            require(count <= expected_turns, f'{label}/{name}: greater than turns')
    for name in ('negative_hours', 'acoustic_speech_s', 'score_covered_s',
                 'source_aligned_clipped_s', 'operational_clipped_s'):
        require(math.isfinite(metric[name]) and metric[name] >= -EPS,
                f'{label}/{name}: invalid exposure/error')
    for prefix in ('source_aligned', 'operational'):
        recall = metric[prefix+'_speech_recall']
        speech, clipped = metric['acoustic_speech_s'], metric[prefix+'_clipped_s']
        require(clipped <= speech+EPS, label+': clipping exceeds speech')
        close(recall, 1-clipped/speech if speech else None, label+'/'+prefix+' recall')
        fp = metric[prefix+'_false_positive_s']
        negative_s = metric['negative_hours']*3600
        require(math.isfinite(fp) and 0 <= fp <= negative_s+EPS, label+': invalid false-positive duration')
        close(metric[prefix+'_false_positive_fraction'], fp/negative_s if negative_s else None,
              label+'/'+prefix+' false-positive fraction')
    hours = metric['negative_hours']
    close(metric['false_starts_per_negative_hour'], counts['false_starts']/hours if hours else None,
          label+'/false START rate')
    for side, deadlines in (('onset', ONSET_MS), ('end', END_MS)):
        for name in ('deadlines_ms', 'uncertainty_possible_deadlines_ms',
                     'uncertainty_certain_deadlines_ms'):
            table = metric[side][name]
            require(set(table) == {str(d) for d in deadlines}, label+': deadline grid')
            previous = -1
            for d in deadlines:
                item = table[str(d)]
                check_deadline(item, expected_turns, f'{label}/{side}/{name}/{d}')
                require(item['successes'] >= previous, label+': deadlines nonmonotonic')
                previous = item['successes']
        for d in deadlines:
            certain = metric[side]['uncertainty_certain_deadlines_ms'][str(d)]['successes']
            nominal = metric[side]['deadlines_ms'][str(d)]['successes']
            possible = metric[side]['uncertainty_possible_deadlines_ms'][str(d)]['successes']
            require(certain <= nominal <= possible, label+': uncertainty envelope ordering')
        all_q, conditional = metric[side]['all_turn_quantiles'], metric[side]['conditional_quantiles']
        check_quantiles(all_q, label+'/'+side+'/all')
        check_quantiles(conditional, label+'/'+side+'/conditional')
        require(all_q['denominator'] == expected_turns
                and all_q['observations'] == conditional['denominator'] == conditional['observations'],
                label+': conditional/all-turn population mismatch')
        for p in ('p50', 'p90', 'p95'):
            if all_q[p]['reached']:
                require(conditional[p]['reached'] and
                        conditional[p]['seconds'] <= all_q[p]['seconds']+EPS,
                        label+': conditional quantile exceeds failure-aware quantile')
    joint = metric['joint_intact_deadlines']
    require(set(joint) == {f'{a}/{b}' for a in ONSET_MS for b in END_MS}, label+': joint grid')
    for key, entry in joint.items():
        check_deadline(entry, expected_turns, label+'/joint/'+key)
        a, b = key.split('/')
        require(entry['successes'] <= min(metric['onset']['deadlines_ms'][a]['successes'],
                                         metric['end']['deadlines_ms'][b]['successes']),
                label+': joint success exceeds marginal success')
    for name, value in metric['diagnostic'].items():
        # Signed source alignment errors are intentionally allowed to be negative.
        check_quantiles(value, label+'/'+name, nonnegative='error' not in name)


def objective_vector(m):
    n = m['counts']['turns']
    return (1-m['onset']['deadlines_ms']['100']['fraction'],
            1-m['end']['deadlines_ms']['300']['fraction'],
            1-m['source_aligned_speech_recall'], m['false_starts_per_negative_hour'],
            m['operational_false_positive_fraction'],
            m['counts']['premature_end_turns']/n, m['counts']['fragmented_turns']/n)


def independent_pareto(metrics):
    vectors = [objective_vector(m) for m in metrics]
    return {i for i, candidate in enumerate(vectors)
            if not any(all(a <= b+1e-12 for a, b in zip(other, candidate))
                       and any(a < b-1e-12 for a, b in zip(other, candidate))
                       for other in vectors)}


def independent_choices(metrics):
    """Recompute the declared lexicographic choices from retained dev rows."""
    def tie(m):
        return (-m['source_aligned_speech_recall'], m['operational_false_positive_fraction'],
                m['false_starts_per_negative_hour'],
                m['counts']['premature_end_turns'], m['counts']['fragmented_turns'],
                m['controller_id'])
    choices = {'recall-priority': sorted(metrics, key=tie)[0]}
    for a in ONSET_MS:
        for b in END_MS:
            key = f'{a}/{b}'
            choices[f'joint-{a}-{b}'] = sorted(metrics, key=lambda m:
                (-m['joint_intact_deadlines'][key]['fraction'],)+tie(m))[0]
    return choices


def union(spans):
    answer = []
    for a, b in sorted(spans):
        if answer and a <= answer[-1][1]:
            answer[-1][1] = max(b, answer[-1][1])
        else:
            answer.append([a, b])
    return answer


def intersect_seconds(spans, a, b):
    return sum(max(0., min(right, b)-max(left, a)) for left, right in spans)


def grid_indices(spans, duration):
    n = max(0, math.ceil((duration-.0005)/.001))
    points = set()
    for a, b in spans:
        lo = max(0, math.ceil((a-.0005)/.001))
        hi = min(n, math.ceil((b-.0005)/.001))
        points.update(range(lo, hi))
    return points


def reference_exposure(records):
    """Integer-index 1ms grid union, independent of production NumPy masks."""
    negative_points = 0
    acoustic = 0.
    for r in records:
        acoustic += sum(b-a for a, b in union(r['speech_intervals']))
        n = max(0, math.ceil((r['duration_s']-.0005)/.001))
        masked = grid_indices(r['speech_intervals']+r.get('uncertain_intervals', []), r['duration_s'])
        negative_points += n-len(masked)
    return dict(negative_hours=negative_points*.001/3600, acoustic_speech_s=acoustic)


def baseline_episodes(trace, silence_s):
    """Alternate run-length oracle for on=off=.5 with no START confirmation.

    Partition score evidence into contiguous sign runs, splitting at coverage
    gaps. START is the first received positive sample after closure; a negative
    run closes at its first sample-end reaching the required elapsed duration.
    An unfinished active interval has no END, including at EOF.
    """
    rows = [tuple(float(x) for x in row) for row in trace]
    runs = []
    for index, row in enumerate(rows):
        positive = row[2] >= .5
        if not runs or positive != runs[-1][0] or row[0] > rows[index-1][1]+EPS:
            runs.append([positive, index, index+1])
        else:
            runs[-1][2] = index+1
    episodes = []
    current = None
    for positive, first, last in runs:
        if positive:
            if current is None:
                current = dict(start_s=rows[first][0], start_available_s=rows[first][3],
                               first_evidence_end_s=rows[first][1])
        elif current is not None:
            end_index = next((i for i in range(first, last)
                              if rows[i][1]-rows[first][0] >= silence_s-EPS), None)
            if end_index is not None:
                current.update(end_s=rows[first][0], end_available_s=rows[end_index][3], censored=False)
                episodes.append(current)
                current = None
    if current is not None:
        current.update(end_s=rows[-1][1], end_available_s=None, censored=True)
        episodes.append(current)
    return episodes


def oracle_turn_rows(record, events):
    """Chronological bipartite matching, with first episode ownership retained."""
    turns = record['turns']
    touching = {i: [j for j, t in enumerate(turns)
                    if intersect_seconds(t['acoustic_intervals'], e['start_s'], e['end_s']) > EPS]
                for i, e in enumerate(events)}
    ownership = {}
    for i in range(len(events)):
        free = [j for j in touching[i] if j not in ownership]
        if free:
            ownership[free[0]] = i
    rows = []
    for j, t in enumerate(turns):
        overlapping = [i for i in range(len(events)) if j in touching[i]]
        ei = ownership.get(j)
        event = events[ei] if ei is not None else None
        a, b = t['onset_s'], t['offset_s']
        early = bool(event and (event['start_available_s'] < a-EPS or
                                event['first_evidence_end_s'] <= a+EPS))
        premature = bool(event and event['end_available_s'] is not None and
                         (event['end_available_s'] < b-EPS or
                          event['end_s'] < b-EPS))
        censored = bool(event and event['censored'])
        onset = (max(0., event['start_available_s']-a) if event and not early
                 and event['start_available_s'] < b-EPS else None)
        end = (max(0., event['end_available_s']-b) if event and not premature
               and not censored else None)
        rows.append(dict(record_id=record['id'], turn_id=t['id'], condition=record['condition']['name'],
            onset_s=a, offset_s=b, matched_episode=ei, onset_latency_s=onset, end_latency_s=end,
            missed=not overlapping, early_active=early, premature_end=premature, censored=censored,
            fragmented=len(overlapping) > 1,
            intact=onset is not None and end is not None and len(overlapping) == 1
                   and len(touching[ei]) == 1,
            event=event))
    return rows, touching, ownership


def check_turn_aggregation(metric, rows, label, references):
    require(len(rows) == metric['counts']['turns'], label+': per-turn row count')
    ids = [(r['record_id'], r['turn_id']) for r in rows]
    require(len(ids) == len(set(ids)) and set(ids) == set(references), label+': per-turn identities')
    count_names = dict(missed='missed_turns', early_active='early_active_turns',
                       premature_end='premature_end_turns', censored='censored_turns',
                       fragmented='fragmented_turns')
    for flag, count in count_names.items():
        require(sum(r[flag] for r in rows) == metric['counts'][count], label+'/'+count)
    require(sum(r['onset_latency_s'] is None for r in rows) == metric['counts']['no_distinct_start_turns'],
            label+': no-distinct STARTs')
    for side, name, deadlines in (('onset', 'onset_latency_s', ONSET_MS),
                                  ('end', 'end_latency_s', END_MS)):
        values = [r[name] for r in rows]
        require(all(v is None or math.isfinite(v) and v >= 0 for v in values), label+': negative/nonfinite delay')
        require(metric[side]['all_turn_quantiles'] == expected_quantiles(values, len(rows)),
                label+'/'+side+': all-turn quantile values')
        require(metric[side]['conditional_quantiles'] == expected_quantiles(values),
                label+'/'+side+': conditional quantile values')
        for deadline in deadlines:
            expected = sum(v is not None and v <= deadline/1000+EPS for v in values)
            require(metric[side]['deadlines_ms'][str(deadline)]['successes'] == expected,
                    label+'/'+side+': deadline differs from per-turn delays')
    for a in ONSET_MS:
        for b in END_MS:
            n = sum(r['intact'] and r['onset_latency_s'] <= a/1000+EPS
                    and r['end_latency_s'] <= b/1000+EPS for r in rows)
            require(metric['joint_intact_deadlines'][f'{a}/{b}']['successes'] == n,
                    label+': joint numerator differs from per-turn delays')
    sensitivity = {side: {kind: [] for kind in ('possible', 'certain')} for side in ('onset', 'end')}
    diagnostics = {key: [] for key in metric['diagnostic']}
    for r in rows:
        t = references[(r['record_id'], r['turn_id'])]
        require(r['onset_s'] == t['onset_s'] and r['offset_s'] == t['offset_s'], label+': reference drift')
        e = r['event']
        op = oc = ep = ec = None
        if e is None:
            require(r['matched_episode'] is None and r['onset_latency_s'] is None and r['end_latency_s'] is None,
                    label+': unmatched turn has response')
            require(not any(r[k] for k in ('early_active', 'premature_end', 'censored', 'intact')),
                    label+': unmatched turn has event flags')
        else:
            a, b = t['onset_s'], t['offset_s']
            alo, ahi = t['onset_uncertainty_s']
            blo, bhi = t['offset_uncertainty_s']
            sn, en = e['start_available_s'], e['end_available_s']
            require(sn+EPS >= e['first_evidence_end_s'] > e['start_s']
                    and (en is None or en+EPS >= sn), label+': noncausal event clock')
            early = sn < a-EPS or e['first_evidence_end_s'] <= a+EPS
            premature = en is not None and (en < b-EPS or e['end_s'] < b-EPS)
            require(r['early_active'] is early and r['premature_end'] is premature
                    and r['censored'] == e['censored'] == (en is None), label+': event flag mismatch')
            close(r['onset_latency_s'], max(0., sn-a) if not early and sn < b-EPS else None,
                  label+': event-derived onset')
            close(r['end_latency_s'], max(0., en-b) if en is not None and not premature else None,
                  label+': event-derived end')
            if sn >= alo-EPS and e['first_evidence_end_s'] > alo+EPS and sn < b-EPS:
                op = max(0., sn-min(ahi, e['first_evidence_end_s']-EPS))
            if sn >= ahi-EPS and e['first_evidence_end_s'] > ahi+EPS and sn < b-EPS:
                oc = sn-alo
            if en is not None and en >= blo-EPS and e['end_s'] >= blo-EPS:
                ep = max(0., en-min(bhi, e['end_s']))
            if en is not None and en >= bhi-EPS and e['end_s'] >= bhi-EPS:
                ec = en-blo
            diagnostics['source_start_error'].append(e['start_s']-a)
            diagnostics['source_end_error'].append(e['end_s']-b)
            diagnostics['notification_onset_clipping'].append(intersect_seconds(t['acoustic_intervals'], a, min(b, sn)))
            diagnostics['backdated_onset_clipping'].append(intersect_seconds(t['acoustic_intervals'], a, min(b, e['start_s'])))
        sensitivity['onset']['possible'].append(op)
        sensitivity['onset']['certain'].append(oc)
        sensitivity['end']['possible'].append(ep)
        sensitivity['end']['certain'].append(ec)
        if r['missed']:
            require(r['event'] is None and r['onset_latency_s'] is None and r['end_latency_s'] is None,
                    label+': missed turn counted successful')
        if r['early_active']:
            require(r['onset_latency_s'] is None, label+': early START counted successful')
        if r['premature_end'] or r['censored']:
            require(r['end_latency_s'] is None, label+': premature/forced EOF counted successful')
        if r['fragmented']:
            require(not r['intact'], label+': fragment counted intact')
    for side, deadlines in (('onset', ONSET_MS), ('end', END_MS)):
        for kind, values in sensitivity[side].items():
            for deadline in deadlines:
                n = sum(v is not None and -EPS <= v <= deadline/1000+EPS for v in values)
                require(metric[side]['uncertainty_'+kind+'_deadlines_ms'][str(deadline)]['successes'] == n,
                        label+': uncertainty numerator differs from event/reference bands')
    for key, values in diagnostics.items():
        require(metric['diagnostic'][key] == expected_quantiles(values), label+': event-derived diagnostic '+key)


def raw_oracle(records, traces, silence_s):
    """Recompute all counts and clipping for the two shared baseline controls."""
    counts = Counter({k: 0 for k in ('turns', 'episodes', 'missed_turns', 'no_distinct_start_turns',
        'early_active_turns', 'censored_turns', 'premature_end_turns', 'fragmented_turns',
        'extra_fragments', 'merged_episodes', 'merged_turns', 'internal_pause_cuts',
        'false_starts', 'uncertain_starts', 'unassigned_episodes')})
    rows = []
    sums = Counter({k: 0. for k in ('source_aligned_clipped_s', 'operational_clipped_s', 'score_covered_s',
                                   'source_aligned_false_positive_s', 'operational_false_positive_s')})
    for record in records:
        trace = traces[record['id']]
        events = baseline_episodes(trace, silence_s)
        part, touching, ownership = oracle_turn_rows(record, events)
        rows += part
        counts['turns'] += len(part)
        counts['episodes'] += len(events)
        counts['unassigned_episodes'] += len(events)-len(ownership)
        for flag, name in (('missed', 'missed_turns'), ('early_active', 'early_active_turns'),
                           ('premature_end', 'premature_end_turns'), ('censored', 'censored_turns'),
                           ('fragmented', 'fragmented_turns')):
            counts[name] += sum(r[flag] for r in part)
        counts['no_distinct_start_turns'] += sum(r['onset_latency_s'] is None for r in part)
        counts['extra_fragments'] += sum(max(0, sum(j in ts for ts in touching.values())-1)
                                          for j in range(len(part)))
        for i, e in enumerate(events):
            counts['merged_episodes'] += len(touching[i]) > 1
            counts['merged_turns'] += max(0, len(touching[i])-1)
            a, b = max(0., e['start_s']), max(0., e['first_evidence_end_s'])
            if intersect_seconds(record['speech_intervals'], a, b) <= EPS:
                key = ('uncertain_starts' if intersect_seconds(record.get('uncertain_intervals', []), a, b) > EPS
                       else 'false_starts')
                counts[key] += 1
            for j in touching[i]:
                if e['end_available_s'] is not None and any(p-EPS <= e['end_available_s'] < q-EPS
                    for p, q in record['turns'][j].get('internal_pauses', [])):
                    counts['internal_pause_cuts'] += 1
        aligned = union([[max(0., e['start_s']), min(record['duration_s'], e['end_s'])]
                         for e in events if e['end_s'] > max(0., e['start_s'])])
        operational = union([[e['start_available_s'], e['end_available_s']
                               if e['end_available_s'] is not None else record['duration_s']] for e in events])
        masked = grid_indices(record['speech_intervals']+record.get('uncertain_intervals', []), record['duration_s'])
        sums['source_aligned_false_positive_s'] += len(grid_indices(aligned, record['duration_s'])-masked)*.001
        sums['operational_false_positive_s'] += len(grid_indices(operational, record['duration_s'])-masked)*.001
        for a, b in union(record['speech_intervals']):
            sums['source_aligned_clipped_s'] += (b-a)-intersect_seconds(aligned, a, b)
            sums['operational_clipped_s'] += (b-a)-intersect_seconds(operational, a, b)
        sums['score_covered_s'] += sum(max(0., min(b, record['duration_s'])-max(0., a)) for a, b, _, _ in trace)
    return dict(counts), rows, dict(sums)


def audit_results(directory, *, raw=False, repo=REPO):
    directory, repo = Path(directory), Path(repo)
    artifact_hashes = {}
    compressed_hashes = {}
    for name in ('summary.json', 'development-curves.json', 'per-turn-test.json'):
        path = directory/name
        artifact_hashes[name] = sha256(path)
        packed = directory/(name+'.gz')
        if packed.exists():
            blob = packed.read_bytes()
            require(gzip.decompress(blob) == retained_bytes(path), name+': gzip content differs from logical artifact')
            require(blob[4:8] == b'\0\0\0\0', name+': gzip creation timestamp is not deterministic')
            compressed_hashes[packed.name] = hashlib.sha256(blob).hexdigest()
    summary = read_json(directory/'summary.json')
    manifest = read_json(directory/'dataset-manifest.json')
    frozen = read_json(directory/'frozen-selections.json')
    inputs = read_json(directory/'frozen-inputs.json')
    curves = read_json(directory/'development-curves.json')
    retained_turns = read_json(directory/'per-turn-test.json')
    require(sha256(directory/'dataset-manifest.json') == MANIFEST_SHA256, 'Exact frozen manifest hash changed')
    require(sha256(directory/'test-manifest.json') == TEST_SHA256, 'Exact frozen test manifest hash changed')
    require(read_json(directory/'test-manifest.json') == dict(manifest,
                records=[r for r in manifest['records'] if r['split'] == 'test']), 'Test split differs from frozen records')
    freeze = read_json(directory/'FROZEN.json')
    require(freeze['manifest_sha256'] == MANIFEST_SHA256 and freeze['test_manifest_sha256'] == TEST_SHA256
            and freeze['stage'] == 'before_model_scoring_and_selection', 'Invalid corpus freeze')
    require(summary['manifest_sha256'] == MANIFEST_SHA256 and summary['frozen_inputs'] == inputs,
            'Summary provenance differs from frozen inputs')
    for k, v in inputs.items():
        require(frozen[k] == v, 'Selection frozen-input mismatch: '+k)
    require(inputs['manifest_sha256'] == MANIFEST_SHA256 and inputs['test_manifest_sha256'] == TEST_SHA256,
            'Frozen input manifest hash')
    require(inputs['test_used_for_selection'] is False, 'Test-used-for-selection declaration')
    for name, expected in inputs['source_sha256'].items():
        require(sha256(repo/'vadbench'/name) == expected, 'Source changed after selection: '+name)
    require(set(summary['backends']) == set(BACKENDS) and len(summary['backends']) == 12, 'Expected all 12 backends')
    require(set(summary['inference_metadata']) == set(BACKENDS), 'Inference metadata backend coverage')
    require(set(inputs['raw_sha256']) == set(BACKENDS), 'Raw frozen hash backend coverage')
    records = manifest['records']
    require(len({r['id'] for r in records}) == len(records), 'Duplicate manifest IDs')
    splits = {s: [r for r in records if r['split'] == s] for s in ('dev', 'test')}
    turns = {s: sum(len(r['turns']) for r in rs) for s, rs in splits.items()}
    require(turns == {'dev': 120, 'test': 120}, 'Expected 120 dev and 120 test turns')
    expected_dataset = dict(records=len(records), dev_records=len(splits['dev']), test_records=len(splits['test']),
        duration_s=sum(r['duration_s'] for r in records), dev_turns=turns['dev'], test_turns=turns['test'])
    require(summary['dataset'] == expected_dataset, 'Dataset totals mismatch')
    exposures = {s: reference_exposure(rs) for s, rs in splits.items()}
    for backend, run in summary['inference_metadata'].items():
        require(run['status'] == 'ok' and run['backend'] == backend and run['manifest_sha256'] == MANIFEST_SHA256,
                backend+': unfinished/wrong inference metadata')
        timing_ids = [t['id'] for t in run['timing']]
        require(len(timing_ids) == len(records) and set(timing_ids) == {r['id'] for r in records},
                backend+': raw timing record coverage')
        # JSON is retained in the repository; raw NPZ is only mandatory with --raw.
        p = directory/'raw'/f'{backend}.json'
        require(p.exists() and read_json(p) == run, backend+': raw JSON metadata differs')
        require(sha256(p) == inputs['raw_sha256'][backend]['json'], backend+': raw JSON hash changed')
    require(curves == summary['development_curves'], 'Retained development curve copies differ')
    grouped = defaultdict(list)
    for row in curves:
        grouped[row['backend']].append(row)
        check_metric(row['metric'], turns['dev'], row['backend']+'/candidate')
        for k, v in exposures['dev'].items():
            close(row['metric'][k], v, row['backend']+'/dev/'+k)
    require(set(grouped) == set(BACKENDS), 'Candidate backend coverage')
    anchors = {r['backend']:r['choices'] for r in frozen['threshold_choices']}
    require(len(anchors) == len(frozen['threshold_choices']) == 12 and set(anchors) == set(BACKENDS),
            'Frozen threshold-anchor backend coverage')
    choices = {}
    candidate_counts, pareto_counts = {}, {}
    for backend, group in grouped.items():
        metrics = [r['metric'] for r in group]
        require(len({m['controller_id'] for m in metrics}) == len(metrics), backend+': duplicate candidates')
        require(len(anchors[backend]) == 3, backend+': missing frozen recall anchors')
        cutoffs = {.5} | {r['threshold'] for r in anchors[backend] if r['feasible']}
        ratios = (1.,) if summary['inference_metadata'][backend]['adapter']['score_kind'] == 'binary' else (1., .5)
        expected_grid = {controller_id(dict(on=on, off=on*ratio, start_s=start, silence_s=silence))
                         for on in cutoffs for ratio in ratios for start in (0., .032, .064)
                         for silence in (0., .032, .064, .1, .15, .2, .3, .5)}
        require({m['controller_id'] for m in metrics} == expected_grid, backend+': missing/extra development grid cells')
        expected_frontier = independent_pareto(metrics)
        require({i for i, row in enumerate(group) if row['pareto']} == expected_frontier,
                backend+': Pareto nondominance mismatch')
        choices[backend] = independent_choices(metrics)
        candidate_counts[backend], pareto_counts[backend] = len(group), len(expected_frontier)
    require(len(frozen['selections']) == len(summary['selections']) == 12*13, 'Expected 13 selections per backend')
    require([{k:v for k,v in r.items() if k not in ('dev', 'test')} for r in summary['selections']]
            == frozen['selections'], 'Frozen selection drift')
    frozen_keys = [(r['backend'], r['policy']) for r in summary['selections']]
    require(len(frozen_keys) == len(set(frozen_keys)), 'Duplicate selection policies')
    all_detail = {(r['backend'], r['controller_id']):r['turn_results'] for r in retained_turns}
    require(len(all_detail) == len(retained_turns), 'Duplicate per-turn controller entries')
    refs = {(r['id'], t['id']): t for r in splits['test'] for t in r['turns']}
    used_details = set()
    require(len(summary['shared']) == 24, 'Expected two shared controls per backend')
    require({(r['backend'], r['configuration']) for r in summary['shared']} ==
            {(b, f'common-{s}ms') for b in BACKENDS for s in (0, 200)}, 'Shared baseline coverage')
    for row in summary['shared']+summary['selections']:
        b, c = row['backend'], row['controller']
        label = b+'/'+row.get('policy', row.get('configuration', '?'))
        if 'policy' in row:
            require(row['dev'] == choices[b][row['policy']], label+': dev-selected choice differs from independent sorting')
        else:
            silence = 0. if row['configuration'] == 'common-0ms' else .2
            require(c == dict(on=.5, off=.5, start_s=0., silence_s=silence), label+': altered common controller')
        for split in ('dev', 'test'):
            require(c == row[split]['controller'], label+': controller differs between freeze/dev/test')
            check_metric(row[split], turns[split], label+'/'+split)
            for k, v in exposures[split].items():
                close(row[split][k], v, label+'/'+split+'/'+k)
        key = b, controller_id(c)
        require(key in all_detail, label+': missing test per-turn rows')
        used_details.add(key)
        check_turn_aggregation(row['test'], all_detail[key], label, refs)
    require(used_details == set(all_detail), 'Unused/unexpected per-turn controllers')
    conditions = {r['condition']['name'] for r in splits['test']}
    groups = defaultdict(list)
    for row in summary['breakdowns']:
        groups[row['backend'], row['policy']].append(row)
    require(set(groups) == set(frozen_keys), 'Breakdown policy coverage')
    for selection in summary['selections']:
        key = selection['backend'], selection['policy']
        parts = groups[key]
        require(len(parts) == len(conditions) and {r['condition'] for r in parts} == conditions,
                str(key)+': breakdown condition coverage')
        total = selection['test']
        for row in parts:
            subset = [r for r in splits['test'] if r['condition']['name'] == row['condition']]
            metric = row['metric']
            require(metric['controller'] == selection['controller'], str(key)+': subgroup retuning')
            check_metric(metric, sum(len(r['turns']) for r in subset), str(key)+'/'+row['condition'])
            for name, value in reference_exposure(subset).items():
                close(metric[name], value, str(key)+'/'+row['condition']+'/'+name)
        for name, value in total['counts'].items():
            require(sum(r['metric']['counts'][name] for r in parts) == value, str(key)+': additive '+name)
        for name in ('negative_hours', 'acoustic_speech_s', 'source_aligned_clipped_s',
                     'operational_clipped_s', 'score_covered_s', 'source_aligned_false_positive_s',
                     'operational_false_positive_s'):
            close(sum(r['metric'][name] for r in parts), total[name], str(key)+': additive '+name)
        for side in ('onset', 'end'):
            for category in ('deadlines_ms', 'uncertainty_possible_deadlines_ms', 'uncertainty_certain_deadlines_ms'):
                for deadline, entry in total[side][category].items():
                    for n in ('successes', 'total'):
                        require(sum(r['metric'][side][category][deadline][n] for r in parts) == entry[n],
                                str(key)+': additive deadline '+n)
        for deadline, entry in total['joint_intact_deadlines'].items():
            for n in ('successes', 'total'):
                require(sum(r['metric']['joint_intact_deadlines'][deadline][n] for r in parts) == entry[n],
                        str(key)+': additive joint '+n)
    preservation = read_json(directory/'historical-preservation.json')
    historical = preservation['committed_files_sha256']
    archive_hashes = preservation['retained_archive_files_sha256']
    require(len(historical) == 79 and len(archive_hashes) == 12,
            'Historical preservation manifest coverage changed')
    for name, expected in historical.items():
        require((repo/name).exists() and sha256(repo/name) == expected, 'Historical file changed: '+name)
    if raw:
        for name, expected in archive_hashes.items():
            require((repo/name).exists() and sha256(repo/name) == expected, 'Historical raw archive changed: '+name)
    oracle_rows = 0
    if raw:
        import numpy as np
        for backend in BACKENDS:
            path = directory/'raw'/f'{backend}.npz'
            require(sha256(path) == inputs['raw_sha256'][backend]['npz'], backend+': raw NPZ hash changed')
            with np.load(path, allow_pickle=False) as data:
                require(set(data.files) == {r['id'] for r in records} and len(data.files) == len(records),
                        backend+': NPZ record coverage')
                traces = {k:data[k] for k in data.files}
            for record in records:
                a = traces[record['id']]
                label = backend+'/'+record['id']
                require(a.ndim == 2 and a.shape[1] == 4 and len(a) > 0 and np.isfinite(a).all(), label+': malformed trace')
                require(np.all(a[:, 1] > a[:, 0]) and np.all(np.diff(a[:, 0]) > 0)
                        and np.all(np.diff(a[:, 1]) > 0) and np.all(a[1:, 0] >= a[:-1, 1]-EPS), label+': source clock')
                require(np.all((0 <= a[:, 2]) & (a[:, 2] <= 1)) and np.all(np.diff(a[:, 3]) >= 0)
                        and np.all(a[:, 3] >= a[:, 1]-EPS) and np.all(a[:, 3] <= record['duration_s']+EPS), label+': acquisition clock/scores')
            for baseline in (r for r in summary['shared'] if r['backend'] == backend):
                silence = baseline['controller']['silence_s']
                for split in ('dev', 'test'):
                    counts, rows, sums = raw_oracle(splits[split], traces, silence)
                    metric = baseline[split]
                    require(counts == metric['counts'], backend+f'/{split}/{silence}: oracle count mismatch')
                    for k, v in sums.items():
                        close(metric[k], v, backend+f'/{split}/{silence}/'+k)
                    split_refs = {(r['id'], t['id']): t for r in splits[split] for t in r['turns']}
                    check_turn_aggregation(metric, rows, backend+f'/{split}/{silence}/oracle', split_refs)
                    if split == 'test':
                        require(rows == all_detail[backend, controller_id(baseline['controller'])],
                                backend+f'/{silence}: oracle per-turn event/matching mismatch')
                    oracle_rows += len(rows)
    return dict(status='passed', backend_count=12, records=len(records), turns_per_split=turns,
                candidate_counts=candidate_counts, pareto_counts=pareto_counts,
                selection_count=len(frozen_keys), per_turn_controller_count=len(all_detail),
                breakdown_count=len(summary['breakdowns']), preserved_historical_files=len(historical),
                preserved_historical_archives=len(archive_hashes) if raw else 0,
                raw_checked=raw, independent_baseline_turn_evaluations=oracle_rows,
                manifest_sha256=MANIFEST_SHA256, test_manifest_sha256=TEST_SHA256,
                logical_artifact_sha256=artifact_hashes, compressed_artifact_sha256=compressed_hashes)


def write_report(path, result, command):
    lines = ['# Independent retained-result audit', '',
             f'Executed {datetime.now(timezone.utc).isoformat(timespec="seconds")}. Status: **PASS**.', '',
             f'Command: `{command}`', '',
             'The audit imports no production evaluator, controller, selector, or Pareto implementation.', '',
             '## Verified', '',
             f'- Exact corpus manifest SHA-256: `{result["manifest_sha256"]}`',
             f'- Exact test manifest SHA-256: `{result["test_manifest_sha256"]}`',
             '- Frozen references, code hashes, raw JSON metadata hashes and complete 12-backend status/record coverage',
             '- 272 records; 120 development and 120 test turns. All full-test rows retain all 120 turns',
             '- Integer nonnegative error counts, clipped-speech identities, false START exposure denominators, deadline fractions and monotonicity',
             '- All-turn versus conditional quantile population/reachability, and exact quantiles/deadline numerators from retained per-turn outcomes',
             f'- Independently sorted all {result["selection_count"]} development-only choices; exact frozen/dev/test controller identity',
             '- Independently recomputed seven-objective Pareto membership for every development candidate',
             f'- All {result["breakdown_count"]} condition rows: no subgroup retuning, reference exposure, additive counts and deadline numerators',
             f'- {result["preserved_historical_files"]} committed historical result/core-source files match historical-preservation.json',
             f'- {result["preserved_historical_archives"]} separately retained historical NPZ archives checked in raw-audit mode', '']
    if result['raw_checked']:
        lines += ['## Independent raw replay', '',
                  '- All 12 NPZ hashes and all 272 trace identities per backend verified; source/acquisition clocks and score bounds checked',
                  f'- Alternate sign-run oracle replayed both 0 ms and 200 ms common controllers on both splits: {result["independent_baseline_turn_evaluations"]:,} turn evaluations',
                  '- All event/matching/count/deadline/quantile outcomes agreed; retained test events compared exactly',
                  '- Missed turns, early-active starts, premature first ends, fragmented turns and EOF censoring cannot become successful intact turns', '']
    else:
        lines += ['## Not executed', '', '- Raw NPZ replay requires rerunning this script with `--raw` and NumPy', '']
    lines += ['## Candidate/frontier sizes', '', '| Backend | Candidates | Pareto |', '|---|---:|---:|']
    lines += [f'| {b} | {result["candidate_counts"][b]} | {result["pareto_counts"][b]} |' for b in BACKENDS]
    lines += ['', '## Audited result identities', '']
    for name, digest in result['logical_artifact_sha256'].items():
        lines.append(f'- Original `{name}` bytes: `{digest}`')
    for name, digest in result['compressed_artifact_sha256'].items():
        lines.append(f'- Compressed storage `{name}` bytes: `{digest}`')
    lines += ['', '## Scope limits', '',
              'Arithmetic agreement does not validate synthetic labels as human phonetic truth, native model alignment as ground truth, '
              'or transfer to natural speech. Selected-controller per-turn JSON is checked for consistency; raw replay independently '
              'covers the shared 0.5/no-confirmation/no-hysteresis controls, not the entire development grid. '
              'Signed source-alignment errors may legitimately be negative; response delays and clipping may not. '
              'Freeze-file contents establish retained input identity, not independently attested wall-clock chronology. '
              'Historical provenance checks cover result files and core source, not intentionally edited documentation, CI or ignore rules.', '']
    lines += ['## Invariant failure found and corrected', '',
              'The first result-generation attempt failed this independent audit because nominal boundary successes could '
              'exceed the claimed possible-band successes. For example, the development classic-0 controller with '
              '64 ms START confirmation and zero trailing silence reported 24/120 nominal START-within-50-ms successes '
              'but 0/120 possible successes. The nominal calculation had used lower uncertainty limits for evidence '
              'eligibility while sensitivity calculations used a stricter hypothetical-boundary family.', '',
              'The corrected implementation requires START first-evidence end after the nominal onset and END source '
              'endpoint at or after the nominal offset. Uncertainty alternatives use the same boundary family. '
              'The corpus, raw inference, development grid and declared selection priorities were unchanged; '
              'development selection and test scoring were regenerated after the correction. The final audit retains '
              'the original certain ≤ nominal ≤ possible assertion and passes it for all retained metric rows. '
              'This is a post-outcome implementation correction, not evidence that the final analysis was never inspected.', '']
    Path(path).write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path, default=REPO/'results/boundary-latency')
    parser.add_argument('--raw', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = audit_results(args.directory, raw=args.raw)
    if args.report:
        command = 'python scripts/audit_boundary_results.py '+str(args.directory)+(' --raw' if args.raw else '')
        write_report(args.report, result, command)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
