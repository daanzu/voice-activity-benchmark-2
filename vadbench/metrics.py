"""Explicit synthetic labels, score alignment, common endpointing, dev calibration."""
import numpy as np
from scipy.stats import chi2

GRID = 0.01
THRESHOLDS = np.unique(np.round(np.r_[np.arange(.05,.9,.05), np.arange(.9,.99,.01),
    np.arange(.99,1,.0001), .99991,.99995,.99999,.999999,.9999999,1.,1.001], 7))

def interval_mask(times, intervals):
    result = np.zeros(len(times), dtype=bool)
    for begin, end in intervals:
        result |= (times >= begin) & (times < end)
    return result

def merge_intervals(intervals, gap=0.2):
    merged=[]
    for begin,end in sorted(intervals):
        if merged and begin-merged[-1][1] <= gap:
            merged[-1][1] = max(merged[-1][1],end)
        else:
            merged.append([begin,end])
    return merged

def aligned_grid(record, trace, task='speech'):
    times=np.arange(GRID/2, record['duration_s'], GRID)
    label=interval_mask(times,record['speech_intervals' if task=='speech' else 'target_intervals'])
    uncertain=interval_mask(times,record.get('uncertain_intervals',[]))
    starts,ends,scores,emissions=trace.T
    index=np.searchsorted(ends,times,side='right')
    valid=index<len(ends)
    index=np.minimum(index,len(ends)-1)
    valid &= times >= starts[index]
    valid &= ~uncertain
    return times,label,scores[index],valid

def endpoint(trace, threshold, silence_s=0.2):
    """No padding/hysteresis: start at first positive, stop after 200 ms negatives.

    Returns source-aligned boundaries and actual simulated input-acquisition event
    times. A stream ending before silence is observed is an explicitly forced EOF.
    """
    events=[]; active=None; low_begin=None
    for begin,end,score,emission in trace:
        if score >= threshold:
            if active is None:
                active={'start':float(begin),'start_notification':float(emission)}
            low_begin=None
        elif active is not None:
            if low_begin is None:
                low_begin=float(begin)
            if end-low_begin >= silence_s-1e-9:
                active.update(end=low_begin,end_notification=float(emission),forced_eof=False)
                events.append(active);active=None;low_begin=None
    if active is not None:
        active.update(end=float(trace[-1,1]),end_notification=float(trace[-1,3]),forced_eof=True)
        events.append(active)
    return events

def evaluate(records,traces,threshold,task='speech'):
    tp=fp=fn=tn=excluded=0
    false_events=reference_events=detected_events=early_ends=forced=fragmentations=ambiguous_events=0
    onset=[]; end_delay=[]; onset_notify=[]; end_clipping=[]
    for record in records:
        trace=traces[record['id']]
        times,label,scores,valid=aligned_grid(record,trace,task)
        pred=scores >= threshold
        tp+=int(np.sum(valid & label & pred));fn+=int(np.sum(valid & label & ~pred))
        fp+=int(np.sum(valid & ~label & pred));tn+=int(np.sum(valid & ~label & ~pred))
        excluded+=int(np.sum(~valid))
        truth=merge_intervals(record['speech_intervals' if task=='speech' else 'target_intervals'])
        events=endpoint(trace,threshold)
        reference_events+=len(truth)
        # Global descending overlap assignment; neither events nor references reused.
        pairs=[]
        for ei,event in enumerate(events):
            for ri,(a,b) in enumerate(truth):
                overlap=max(0,min(event['end'],b)-max(event['start'],a))
                if overlap>0:pairs.append((overlap,ei,ri))
        used_events=set();used_truth=set();matches=[]
        for overlap,ei,ri in sorted(pairs,reverse=True):
            if ei not in used_events and ri not in used_truth:
                used_events.add(ei);used_truth.add(ri);matches.append((ei,ri))
        for ei,event in enumerate(events):
            if ei in used_events:continue
            if any(pair[1]==ei for pair in pairs):
                fragmentations+=1
                continue
            support=(times>=event['start']) & (times<event['end'])
            if np.any(support & valid & ~label):false_events+=1
            else:ambiguous_events+=1
        for ei,ri in matches:
            event=events[ei];a,b=truth[ri]
            onset.append(max(0,event['start']-a))
            onset_notify.append(event['start_notification']-a)
            end_clipping.append(max(0,b-event['end']))
            if event['forced_eof']:
                forced+=1
            else:
                delay=event['end_notification']-b
                end_delay.append(delay);early_ends+=int(delay<0)
        detected_events+=len(used_truth)
    def quantile(xs,q):
        return float(np.quantile(xs,q)) if xs else None
    negative_s=(fp+tn)*GRID
    hours=negative_s/3600
    poisson_ci=[float(chi2.ppf(.025,2*false_events)/2/hours) if false_events else 0.,float(chi2.ppf(.975,2*(false_events+1))/2/hours)] if hours else None
    return dict(threshold=float(threshold),task=task,tp=tp,fp=fp,fn=fn,tn=tn,
                missed_speech_fraction=fn/(tp+fn) if tp+fn else None,
                false_positive_fraction=fp/(fp+tn) if fp+tn else None,
                false_activations=false_events, fragmentation_events=fragmentations, ambiguous_events=ambiguous_events, negative_hours=negative_s/3600,
                false_activations_per_negative_hour=false_events/(negative_s/3600) if negative_s else None,
                false_activation_rate_poisson95=poisson_ci,
                excluded_seconds=excluded*GRID,reference_events=reference_events,
                detected_events=detected_events,event_recall=detected_events/reference_events if reference_events else None,
                onset_clipping_p50_s=quantile(onset,.5),onset_clipping_p95_s=quantile(onset,.95),
                onset_notification_p50_s=quantile(onset_notify,.5),onset_notification_p95_s=quantile(onset_notify,.95),
                end_notification_p50_s=quantile(end_delay,.5),end_notification_p95_s=quantile(end_delay,.95),
                premature_notification_fraction=early_ends/len(end_delay) if end_delay else None,
                end_clipping_p50_s=quantile(end_clipping,.5),end_clipping_p95_s=quantile(end_clipping,.95),
                fragmentation_per_reference=fragmentations/reference_events if reference_events else None,
                latency_matched_event_count=len(end_delay),forced_eof_events=forced)

def calibrate(records,traces,target_false_events=5.0):
    # Includes an explicit never-positive setting; report if this is selected.
    candidates=[evaluate(records,traces,t) for t in THRESHOLDS]
    feasible=[r for r in candidates if (r['false_activations_per_negative_hour'] or 0)<=target_false_events and (r['false_positive_fraction'] or 0)<=.01]
    best=min(feasible,key=lambda r:(r['missed_speech_fraction'],r['false_positive_fraction'],r['threshold']))
    return best,candidates
