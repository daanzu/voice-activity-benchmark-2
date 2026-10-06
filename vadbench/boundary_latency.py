"""Causal episode-level latency. Availability is never a backdated boundary.

References are construction-defined turns with separate acoustic support. The
first overlapping episode owns a turn; fragments cannot retrospectively replace
it. Every turn stays in deadline denominators, including misses and censored EOF.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import numpy as np
from .metrics import interval_mask, merge_intervals

EPS = 1e-9
ONSET_DEADLINES = (.05, .1, .2)
END_DEADLINES = (.1, .2, .3, .5)

@dataclass(frozen=True)
class Controller:
    on: float = .5
    off: float = .5
    start_s: float = 0.
    silence_s: float = .2

    def __post_init__(self):
        if not all(math.isfinite(x) for x in asdict(self).values()):
            raise ValueError('Controller values must be finite')
        if not 0 < self.off <= self.on <= 1 or min(self.start_s, self.silence_s) < 0:
            raise ValueError('Require 0 < off <= on <= 1 and nonnegative durations')

    @property
    def id(self):
        return f'on={self.on:.17g};off={self.off:.17g};start={self.start_s:.6g};silence={self.silence_s:.6g}'


def validate_trace(trace, duration_s):
    trace = np.asarray(trace, dtype=float)
    if trace.size == 0:
        return np.empty((0, 4))
    if trace.ndim != 2 or trace.shape[1] != 4 or not np.isfinite(trace).all():
        raise ValueError('Expected finite N x 4 source-start/end, score, acquisition trace')
    a, b, s, t = trace.T
    if np.any(b <= a) or np.any(np.diff(a) <= 0) or np.any(np.diff(b) <= 0):
        raise ValueError('Source intervals must be increasing and positive')
    if np.any(a[1:] < b[:-1]-EPS) or np.any(np.diff(t) < 0):
        raise ValueError('Overlapping score intervals or reversed acquisition clock')
    if np.any((s < 0) | (s > 1)) or np.any(t < b-EPS) or np.any(t > duration_s+EPS):
        raise ValueError('Invalid score or noncausal/out-of-range acquisition')
    return trace


def causal_episodes(trace, controller=Controller(), duration_s=None):
    """Evidence durations use actual sample-time coverage, never frame counts.

    Timer decisions occur only at received-score emissions. Silence zero still
    requires one negative frame. Equality is positive for both thresholds. EOF
    is recorded as right-censoring, never emitted as an END notification.
    """
    if duration_s is None:
        duration_s = float(np.asarray(trace)[-1, 3]) if len(trace) else 0.
    trace = validate_trace(trace, duration_s)
    out, active, pending, low = [], None, None, None
    last_end = None
    for begin, end, score, acquisition in trace:
        if last_end is not None and begin > last_end+EPS:
            # Missing score coverage cannot count toward confirmation or silence.
            pending = low = None
        if active is None:
            if score >= controller.on:
                if pending is None:
                    pending = dict(begin=float(begin), evidence_end=float(end))
                if end-pending['begin'] >= controller.start_s-EPS:
                    active = dict(start_s=pending['begin'], start_available_s=float(acquisition),
                                  first_evidence_end_s=pending['evidence_end'])
                    pending = None
            else:
                pending = None
        elif score >= controller.off:
            low = None
        else:
            if low is None:
                low = float(begin)
            if end-low >= controller.silence_s-EPS:
                active.update(end_s=low, end_available_s=float(acquisition), censored=False)
                out.append(active)
                active = pending = low = None
        last_end = end
    if active is not None:
        active.update(end_s=float(trace[-1, 1]), end_available_s=None, censored=True)
        out.append(active)
    return out


def overlap(intervals, a, b):
    return sum(max(0., min(y, b)-max(x, a)) for x, y in intervals)


def _union(intervals):
    return merge_intervals(intervals, gap=0.)


def reference_turns(record):
    """Use explicit turns; old corpus replay uses source placements, not 200ms merging."""
    if 'turns' in record:
        turns = record['turns']
    else:
        placements = [s['inserted_interval'] for s in record.get('provenance', {}).get('sources', [])]
        # Overlapping synthetic speakers form a generic-speech union turn here.
        placements = _union(placements or record['speech_intervals'])
        turns = []
        for a, b in placements:
            spans = [[max(a, x), min(b, y)] for x, y in record['speech_intervals']
                     if min(b, y) > max(a, x)]
            if not spans:
                continue
            start, end = spans[0][0], spans[-1][1]
            turns.append(dict(id=f"{record['id']}:turn-{len(turns)}", onset_s=start, offset_s=end,
                onset_uncertainty_s=[max(0., start-.02), start+.02],
                offset_uncertainty_s=[end-.02, min(record['duration_s'], end+.02)],
                acoustic_intervals=spans,
                internal_pauses=[[x[1], y[0]] for x, y in zip(spans, spans[1:]) if y[0]>x[1]]))
    prior = -math.inf
    ids = set()
    for turn in turns:
        a, b = turn['onset_s'], turn['offset_s']
        if not 0 <= a < b <= record['duration_s'] or a < prior-EPS or turn['id'] in ids:
            raise ValueError('Turns must be unique, sorted, nonoverlapping and within stream')
        ids.add(turn['id']); prior = b
        for name, ref in [('onset', a), ('offset', b)]:
            bounds = turn[name+'_uncertainty_s']
            if len(bounds) != 2 or not all(math.isfinite(x) for x in bounds) or not bounds[0] <= ref <= bounds[1]:
                raise ValueError('Boundary uncertainty must enclose reference')
        spans = turn['acoustic_intervals']
        if not spans or any(not a-EPS <= x < y <= b+EPS for x, y in spans):
            raise ValueError('Acoustic support must be nonempty and contained in turn')
    return turns


def quantiles(values, total=None):
    """Nearest-rank CDF; null + reached=false means insufficient successful turns."""
    finite = sorted(float(x) for x in values if x is not None and math.isfinite(x))
    denominator = len(finite) if total is None else total
    result = dict(observations=len(finite), denominator=denominator)
    for q in (.5, .9, .95):
        rank = math.ceil(q*denominator)
        reached = denominator > 0 and rank <= len(finite)
        result['p'+str(round(q*100))] = dict(reached=reached, seconds=finite[rank-1] if reached else None)
    return result


def _deadline(delays, deadlines):
    return {str(round(d*1000)): dict(successes=sum(x is not None and -EPS <= x <= d+EPS for x in delays),
        total=len(delays), fraction=sum(x is not None and -EPS <= x <= d+EPS for x in delays)/len(delays)
        if delays else None) for d in deadlines}


def prepare_records(records):
    """Precompute only reference-derived quantities for repeated controller replay."""
    prepared = []
    for record in records:
        if '_boundary_reference' in record:
            prepared.append(record)
            continue
        item = dict(record)
        times = np.arange(.0005, record['duration_s'], .001)
        speech = interval_mask(times, record['speech_intervals'])
        uncertain = interval_mask(times, record.get('uncertain_intervals', []))
        spans = _union(record['speech_intervals'])
        item['_boundary_reference'] = dict(turns=reference_turns(record), spans=spans,
            negative_s=float(np.sum(~speech & ~uncertain))*.001,
            acoustic_s=sum(b-a for a, b in spans), negative_times=times[~speech & ~uncertain])
        prepared.append(item)
    return prepared


def evaluate_boundaries(records, traces, controller=Controller(), *, details=False):
    counts = dict(turns=0, episodes=0, missed_turns=0, no_distinct_start_turns=0,
        early_active_turns=0, censored_turns=0, premature_end_turns=0, fragmented_turns=0,
        extra_fragments=0, merged_episodes=0, merged_turns=0, internal_pause_cuts=0,
        false_starts=0, uncertain_starts=0, unassigned_episodes=0)
    rows = []
    onset, end, joint = [], [], []
    onset_possible, onset_certain, end_possible, end_certain = [], [], [], []
    signed_start, signed_end, notification_start_clips, backdated_clips = [], [], [], []
    negative_s = acoustic_s = source_clipped_s = operational_clipped_s = covered_s = 0.
    source_fp_s = operational_fp_s = 0.
    for record in prepare_records(records):
        trace = validate_trace(traces[record['id']], record['duration_s'])
        reference = record['_boundary_reference']
        turns = reference['turns']
        events = causal_episodes(trace, controller, record['duration_s'])
        counts['turns'] += len(turns); counts['episodes'] += len(events)
        # Reference-only denominator, identical across every backend/controller.
        negative_s += reference['negative_s']
        acoustic_s += reference['acoustic_s']
        aligned = _union([[max(0., e['start_s']), min(record['duration_s'], e['end_s'])] for e in events
                          if e['end_s'] > max(0., e['start_s'])])
        operational = _union([[e['start_available_s'], e['end_available_s'] if not e['censored'] else record['duration_s']]
                              for e in events])
        source_fp_s += float(np.sum(interval_mask(reference['negative_times'], aligned)))*.001
        operational_fp_s += float(np.sum(interval_mask(reference['negative_times'], operational)))*.001
        for a, b in reference['spans']:
            source_clipped_s += (b-a)-overlap(aligned, a, b)
            operational_clipped_s += (b-a)-overlap(operational, a, b)
        covered_s += sum(max(0., min(b, record['duration_s'])-max(0., a)) for a, b, _, _ in trace)
        related = [[i for i, turn in enumerate(turns)
                    if overlap(turn['acoustic_intervals'], e['start_s'], e['end_s']) > EPS] for e in events]
        matched, used_events = {}, set()
        # Strict chronological, no maximal-overlap selection or after-the-fact rescue.
        for ei, associated in enumerate(related):
            if len(associated) > 1:
                counts['merged_episodes'] += 1
                counts['merged_turns'] += len(associated)-1
            candidate = next((ri for ri in associated if ri not in matched), None)
            if candidate is not None:
                matched[candidate] = ei; used_events.add(ei)
            e = events[ei]
            a, b = max(0., e['start_s']), max(0., e['first_evidence_end_s'])
            first_support = overlap(record['speech_intervals'], a, b)
            uncertain_support = overlap(record.get('uncertain_intervals', []), a, b)
            if first_support <= EPS:
                if uncertain_support > EPS:
                    counts['uncertain_starts'] += 1
                else:
                    counts['false_starts'] += 1
            for ri in associated:
                t = turns[ri]
                if e['end_available_s'] is not None and any(
                    p-EPS <= e['end_available_s'] < q-EPS for p, q in t.get('internal_pauses', [])):
                    counts['internal_pause_cuts'] += 1
        counts['unassigned_episodes'] += len(events)-len(used_events)
        for ri, turn in enumerate(turns):
            a, b = turn['onset_s'], turn['offset_s']
            als, ahs = turn['onset_uncertainty_s']; bls, bhs = turn['offset_uncertainty_s']
            overlaps = [ei for ei, rs in enumerate(related) if ri in rs]
            fragment = len(overlaps) > 1
            counts['fragmented_turns'] += int(fragment)
            counts['extra_fragments'] += max(0, len(overlaps)-1)
            counts['missed_turns'] += int(not overlaps)
            event = events[matched[ri]] if ri in matched else None
            od = ed = None
            op = oc = ep = ec = None
            early = premature = censored = False
            if event is not None:
                sn, en = event['start_available_s'], event['end_available_s']
                early = sn < a-EPS or event['first_evidence_end_s'] <= a+EPS
                censored = event['censored']
                premature = en is not None and (en < b-EPS or event['end_s'] < b-EPS)
                # A merged episode cannot furnish distinct responses for later turns.
                if not early and sn < b-EPS:
                    od = max(0., sn-a)
                if not censored and not premature:
                    ed = max(0., en-b)
                # Sensitivity bands are evaluated independently of nominal success.
                if sn >= als-EPS and event['first_evidence_end_s'] > als+EPS and sn < b-EPS:
                    op = max(0., sn-min(ahs, event['first_evidence_end_s']-EPS))
                if sn >= ahs-EPS and event['first_evidence_end_s'] > ahs+EPS and sn < b-EPS:
                    oc = sn-als
                if not censored and en >= bls-EPS and event['end_s'] >= bls-EPS:
                    ep = max(0., en-min(bhs, event['end_s']))
                if not censored and en >= bhs-EPS and event['end_s'] >= bhs-EPS:
                    ec = en-bls
                signed_start.append(event['start_s']-a)
                signed_end.append(event['end_s']-b)
                notification_start_clips.append(overlap(turn['acoustic_intervals'], a, min(b, sn)))
                backdated_clips.append(overlap(turn['acoustic_intervals'], a, min(b, event['start_s'])))
            counts['early_active_turns'] += int(early)
            counts['censored_turns'] += int(censored)
            counts['premature_end_turns'] += int(premature)
            counts['no_distinct_start_turns'] += int(od is None)
            onset.append(od); end.append(ed)
            onset_possible.append(op); onset_certain.append(oc)
            end_possible.append(ep); end_certain.append(ec)
            intact = od is not None and ed is not None and not fragment and len(related[matched[ri]]) == 1
            joint.append((od, ed, intact))
            if details:
                rows.append(dict(record_id=record['id'], turn_id=turn['id'], condition=record['condition']['name'],
                    onset_s=a, offset_s=b, matched_episode=matched.get(ri), onset_latency_s=od, end_latency_s=ed,
                    missed=not overlaps, early_active=early, premature_end=premature, censored=censored,
                    fragmented=fragment, intact=intact, event=event))
    result = dict(controller=asdict(controller), controller_id=controller.id, counts=counts,
        negative_hours=negative_s/3600, acoustic_speech_s=acoustic_s,
        false_starts_per_negative_hour=counts['false_starts']/(negative_s/3600) if negative_s else None,
        source_aligned_clipped_s=max(0., source_clipped_s), operational_clipped_s=max(0., operational_clipped_s),
        source_aligned_speech_recall=1-source_clipped_s/acoustic_s if acoustic_s else None,
        operational_speech_recall=1-operational_clipped_s/acoustic_s if acoustic_s else None,
        source_aligned_false_positive_s=source_fp_s, operational_false_positive_s=operational_fp_s,
        source_aligned_false_positive_fraction=source_fp_s/negative_s if negative_s else None,
        operational_false_positive_fraction=operational_fp_s/negative_s if negative_s else None,
        score_covered_s=covered_s,
        onset=dict(all_turn_quantiles=quantiles(onset, len(onset)), conditional_quantiles=quantiles(onset),
            deadlines_ms=_deadline(onset, ONSET_DEADLINES),
            uncertainty_possible_deadlines_ms=_deadline(onset_possible, ONSET_DEADLINES),
            uncertainty_certain_deadlines_ms=_deadline(onset_certain, ONSET_DEADLINES)),
        end=dict(all_turn_quantiles=quantiles(end, len(end)), conditional_quantiles=quantiles(end),
            deadlines_ms=_deadline(end, END_DEADLINES),
            uncertainty_possible_deadlines_ms=_deadline(end_possible, END_DEADLINES),
            uncertainty_certain_deadlines_ms=_deadline(end_certain, END_DEADLINES)),
        joint_intact_deadlines={f'{round(s*1000)}/{round(e*1000)}':dict(
            successes=sum(ok and a <= s+EPS and b <= e+EPS for a, b, ok in joint), total=len(joint),
            fraction=sum(ok and a <= s+EPS and b <= e+EPS for a, b, ok in joint)/len(joint) if joint else None)
            for s in ONSET_DEADLINES for e in END_DEADLINES},
        diagnostic=dict(source_start_error=quantiles(signed_start), source_end_error=quantiles(signed_end),
            notification_onset_clipping=quantiles(notification_start_clips),
            backdated_onset_clipping=quantiles(backdated_clips)))
    if details:
        result['turn_results'] = rows
    return result
