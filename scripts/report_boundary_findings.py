"""Render saved boundary metrics and paired causal ambiguity, without model reruns."""
from pathlib import Path
import argparse
import json
from collections import defaultdict
import html
import gzip
import hashlib
import numpy as np
from vadbench.boundary_latency import Controller, causal_episodes


def paired_diagnostics(records, raw, shared):
    pairs = defaultdict(dict)
    for r in records:
        if r.get('split') == 'test' and 'causal_pair' in r:
            pairs[r['causal_pair']['id']][r['causal_pair']['branch']] = r
    results=[]
    for baseline in shared:
        backend=baseline['backend'];controller=Controller(**baseline['controller'])
        with np.load(Path(raw)/f'{backend}.npz',allow_pickle=False) as z:
            for key, branches in pairs.items():
                stop,resume=branches['stop'],branches['resume']
                boundary=stop['turns'][0]['offset_s'];horizon=stop['causal_pair']['resume_time_s']
                outputs={name:causal_episodes(z[r['id']],controller,r['duration_s']) for name,r in branches.items()}
                observable={name:[e for e in events if e['end_available_s'] is not None and
                    boundary <= e['end_available_s'] <= horizon] for name,events in outputs.items()}
                stop_times=[e['end_available_s'] for e in observable['stop']]
                resume_times=[e['end_available_s'] for e in observable['resume']]
                if stop_times != resume_times:
                    raise ValueError('Identical causal histories produced different pre-resume ENDs')
                results.append(dict(backend=backend,configuration=baseline['configuration'],pair_id=key,
                    prefix_id=stop['causal_pair']['shared_prefix_id'],pause_s=stop['causal_pair']['requested_pause_s'],
                    stop_nominal_offset_s=boundary,resume_support_start_s=horizon,
                    identical_pre_resume_end_times_s=stop_times,
                    earliest_stop_response_before_resume_s=stop_times[0]-boundary if stop_times else None,
                    cuts_resume_before_future_speech=bool(stop_times)))
    return results


def q(metric,side,p):
    item=metric[side]['all_turn_quantiles'][p]
    return f"{item['seconds']*1000:.0f}" if item['reached'] else 'unreached'


def pct(value):
    return 'n/a' if value is None else f'{100*value:.1f}%'


def deadline(metric, side, ms):
    return pct(metric[side]['deadlines_ms'][str(ms)]['fraction'])


def render(directory):
    directory=Path(directory);p=directory/'summary.json'
    data=p.read_bytes() if p.exists() else gzip.decompress(p.with_suffix('.json.gz').read_bytes())
    s=json.loads(data)
    m=json.loads((directory/'dataset-manifest.json').read_text())
    pairs=paired_diagnostics(m['records'],directory/'raw',s['shared'])
    gaps=defaultdict(list)
    for record in m['records']:
        if record['condition']['name']=='pause_resume':
            prefix,continuation=record['provenance']['sources']
            gap=1000*(continuation['activity_intervals'][0][0]-prefix['activity_intervals'][-1][1])
            gaps[record['split'],round(record['condition']['pause_s']*1000)].append(gap)
    gap_audit=dict(manifest_sha256=hashlib.sha256((directory/'dataset-manifest.json').read_bytes()).hexdigest(),
        definition='Inserted gap is nonzero-support to nonzero-support; actual RMS gap is first continuation source activity minus last prefix source activity in emitted clean-source labels',
        results=[dict(split=split,inserted_support_gap_ms=ms,actual_rms_gap_ms=dict(min=min(v),max=max(v)),families=len(v),values_ms=v) for (split,ms),v in sorted(gaps.items())])
    (directory/'pause-gap-audit.json').write_text(json.dumps(gap_audit,indent=2)+'\n')
    actual_gaps={ms:v for (split,ms),v in gaps.items() if split=='test'}
    (directory/'causal-pairs.json').write_text(json.dumps(pairs,indent=2,allow_nan=False)+'\n')
    highlights=[]
    by_shared={(r['backend'],r['configuration']):r['test'] for r in s['shared']}
    if ('silero','common-0ms') in by_shared and ('silero','common-200ms') in by_shared:
        a=by_shared['silero','common-0ms'];b=by_shared['silero','common-200ms']
        highlights.append(f"- Direct Silero / identical Lite 0.4: removing 200 ms added silence changes test END≤300 ms from {deadline(b,'end',300)} to {deadline(a,'end',300)}; first-episode premature/clipped endings {b['counts']['premature_end_turns']}→{a['counts']['premature_end_turns']}. START≤100 ms stays {deadline(a,'onset',100)}")
    if ('rnnoise','common-0ms') in by_shared and ('rnnoise','common-200ms') in by_shared:
        a=by_shared['rnnoise','common-0ms'];b=by_shared['rnnoise','common-200ms']
        highlights.append(f"- RNNoise behaves differently: retaining 200 ms added silence improves END≤300 ms from {deadline(a,'end',300)} to {deadline(b,'end',300)} while first-episode cuts fall {a['counts']['premature_end_turns']}→{b['counts']['premature_end_turns']}. Zero added silence is not a universal choice")
    silero_selection=next((r for r in s['selections'] if r['backend']=='silero' and r['policy']=='joint-100-300'),None)
    if silero_selection and ('silero','common-0ms') in by_shared:
        highlights.append(f"- A development-tuned point is not guaranteed to beat a fixed test baseline: Silero's dev-selected START100/END300 point reaches {pct(silero_selection['test']['joint_intact_deadlines']['100/300']['fraction'])} test intact-turn success, versus {pct(by_shared['silero','common-0ms']['joint_intact_deadlines']['100/300']['fraction'])} at the shared 0 ms baseline. No holdout retuning was performed")
    lines=['# Rapid speech onset and ending: synthetic benchmark', '',
        '## Main findings', '', *highlights, '',
        'These comparisons use the frozen nominal acoustic proxy. They are diagnostics with all-turn denominators, not production recommendations; uncertainty and controlled-pause caveats below are essential.', '',
        '## What was measured', '',
        f"{s['dataset']['records']} frozen synthetic streams ({s['dataset']['duration_s']/60:.2f} minutes), "
        f"{s['dataset']['test_turns']} test turns, {len(s['backends'])} configurations. START and END availability follow the causal "
        '10 ms input-acquisition clock. These numbers include native framing, buffering and observed model/native state. '
        'They exclude actual computation and physical capture/device latency. Backdated source boundaries are reported separately.', '',
        '**Every turn stays in the denominator.** Early-active STARTs, missing responses, premature/clipped first episodes, '
        'fragments and forced EOF cannot become an artificially fast successful turn. P50/P90/P95 are failure-aware '
        'nearest-rank quantiles: “unreached” means too few turns succeeded. END uses the first overlapping episode, '
        'so a premature first episode cannot be rescued by a later final fragment. Joint intact-turn success additionally rejects any fragmentation or merge.', '',
        '**Limits:** English Flite speech, two voices per split, repeated controlled prefix variants, clean-source RMS proxies '
        'rather than human phonetic labels. Exact low-energy source support produces broad uncertainty bands. '
        'Use the nominal/possible/certain deadline tables together. This cannot establish a production winner or solve semantic turn completion.', '',
        '## Same controller: frozen test', '',
        'All rows use start cutoff 0.5, no hysteresis and no extra start confirmation. Native internal overhang remains. '
        'The only change is added trailing-silence duration. START ≤100 ms and END ≤300 ms are illustrative columns; '
        'all requested deadline grids and error counts are retained in JSON and the explorer. '
        '**A low nominal START success can mean activation before the RMS-proxy onset, not slow detection or missed speech.** '
        'Inspect early-active counts and possible/certain bands, especially where low-energy source support precedes the proxy.', '',
        '| Configuration | Added silence | START ≤100 ms nominal / possible / certain | Early-active | END ≤300 ms | START P50/P90/P95 ms | END P50/P90/P95 ms | Premature/clipped first ends | Fragmented turns | False STARTs / neg h |',
        '|---|---:|---:|---:|---:|---|---|---:|---:|---:|']
    for row in s['shared']:
        x=row['test'];c=x['counts']
        lines.append(f"| {row['backend']} | {row['controller']['silence_s']*1000:.0f} ms | {deadline(x,'onset',100)} / {pct(x['onset']['uncertainty_possible_deadlines_ms']['100']['fraction'])} / {pct(x['onset']['uncertainty_certain_deadlines_ms']['100']['fraction'])} | {c['early_active_turns']}/{c['turns']} | {deadline(x,'end',300)} | "
            f"{' / '.join(q(x,'onset',p) for p in ['p50','p90','p95'])} | {' / '.join(q(x,'end',p) for p in ['p50','p90','p95'])} | "
            f"{c['premature_end_turns']}/{c['turns']} | {c['fragmented_turns']}/{c['turns']} | {x['false_starts_per_negative_hour']:.1f} |")
    lines += ['', '## Development-only choices', '',
        'Score cutoffs use the native 0.5 point plus attainable 99%, 99.5% and 99.9% development speech-frame recall anchors. '
        'The sweep combines silence 0/32/64/100/150/200/300/500 ms, start confirmation 0/32/64 ms, and off/on ratios 1 or 0.5. '
        'Binary modes keep their native point. Durations are measured in seconds, not equated frame counts.', '',
        'All selections are frozen before test scoring: one maximum source-aligned speech-coverage reference and 12 '
        'illustrative joint START/END deadline choices. The deadline choices maximize development intact-turn success; '
        'ties favor source coverage, less operational false-positive time, fewer false STARTs, fewer premature ENDs, fewer fragmented turns and stable ID. '
        'These are alternatives to inspect, not an accepted production false-positive budget. The full development Pareto '
        'front preserves latency/error tradeoffs, including recall costs.', '',
        '| Detector | Frozen dev choice for START100/END300 | Dev intact success | Test intact success | Test source-aligned coverage | Test false STARTs / neg h |',
        '|---|---|---:|---:|---:|---:|']
    for row in s['selections']:
        if row['policy']!='joint-100-300':continue
        c=row['controller'];x=row['test'];d=row['dev']
        lines.append(f"| {row['backend']} | on={c['on']:.6g}, off={c['off']:.6g}, confirm={c['start_s']*1000:.0f} ms, silence={c['silence_s']*1000:.0f} ms | "
            f"{pct(d['joint_intact_deadlines']['100/300']['fraction'])} | {pct(x['joint_intact_deadlines']['100/300']['fraction'])} | "
            f"{pct(x['source_aligned_speech_recall'])} | {x['false_starts_per_negative_hour']:.1f} |")
    lines += ['', '## Stop versus resume: unavoidable causal ambiguity', '',
        '**The original 50–800 ms labels are inserted nonzero-support gaps, not RMS-active speech gaps.** '
        'Flite retains faint source tails before/after the nominal activity proxy. In this test, a 50 ms insertion gives '
        f"{min(actual_gaps[50]):.1f}–{max(actual_gaps[50]):.1f} ms between RMS-active spans. "
        'Use the separately [hard-gated short-pause diagnostic](../boundary-pause-probe/FINDINGS.md) for actual '
        '50–800 ms RMS gaps. That diagnostic freezes existing controllers and explicitly introduces artificial boundary/splice risks.', '',
        'Each stop/resume pair has byte-identical PCM through the later resume sample. Across every backend, raw scores '
        'before that sample must match. Any END emitted after the stopped phrase but before the unseen continuation '
        'also cuts the paired resumed turn. No causal VAD can distinguish those histories before they diverge. '
        'Longer silence postpones that decision and reduces some cuts; it adds stop latency. This is a construction '
        'demonstration, not a claim that natural conversations have these pause probabilities.', '',
        '| Detector | Added silence | Paired test histories with a stop END before the unseen resume |', '|---|---:|---:|']
    for row in s['shared']:
        subset=[p for p in pairs if p['backend']==row['backend'] and p['configuration']==row['configuration']]
        lines.append(f"| {row['backend']} | {row['controller']['silence_s']*1000:.0f} ms | {sum(p['cuts_resume_before_future_speech'] for p in subset)}/{len(subset)} |")
    lines += ['', 'Measured acoustic-proxy gap, which differs from the inserted exact-silence gap ([audit](pause-gap-audit.json)):', '',
        '| Inserted support gap | Actual test RMS-activity gap min–max |', '|---:|---:|']
    for pause, values in sorted(actual_gaps.items()):
        lines.append(f'| {pause} ms | {min(values):.1f}–{max(values):.1f} ms |')
    lines += ['', 'Pre-resume ENDs by inserted pause (each cell has four paired prefix families):', '',
        '| Detector / added silence | 50 ms | 100 ms | 150 ms | 200 ms | 300 ms | 500 ms | 800 ms |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in s['shared']:
        cells=[]
        for pause in (.05,.1,.15,.2,.3,.5,.8):
            subset=[p for p in pairs if p['backend']==row['backend'] and p['configuration']==row['configuration'] and abs(p['pause_s']-pause)<1e-9]
            cells.append(f"{sum(p['cuts_resume_before_future_speech'] for p in subset)}/{len(subset)}")
        lines.append(f"| {row['backend']} / {row['controller']['silence_s']*1000:.0f} ms | "+' | '.join(cells)+' |')
    lines += ['', 'The same four test prefixes are repeated at seven pause durations. Do not interpret 28 pairs as 28 independent voices or bootstrap individual variants as independent observations.', '',
        '## Artifacts', '',
        '- [Protocol and reproduction](../../docs/BOUNDARY_LATENCY.md)',
        '- [Corpus construction](../../docs/BOUNDARY_DATASET.md)',
        '- [Frozen inputs](frozen-inputs.json) and [selections](frozen-selections.json)',
        '- [Full summary](summary.json.gz), [development sweep](development-curves.json.gz), [per-turn test outcomes](per-turn-test.json.gz)',
        '- [Causal-pair diagnostics](causal-pairs.json), [inference verification](INFERENCE_AUDIT.json)',
        '- [Interactive notebook](../../notebooks/explore_boundaries.py)',
        '- [Independent methodology and code review](INDEPENDENT_REVIEW.md)', '',
        'Old-corpus replay in `exploratory/` is deliberately exploratory: both former splits were already examined. '
        'It supplied diagnostics and regression coverage; it is not a fresh holdout.', '']
    (directory/'FINDINGS.md').write_text('\n'.join(lines))
    # Small inspectable static SVG: no plotting runtime dependency.
    rows=[r for r in s['shared'] if r['configuration']=='common-200ms']
    colors=['#2563eb','#f97316'];svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="700" viewBox="0 0 1000 700">',
        '<rect width="1000" height="700" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#172033;font-size:14px}</style>',
        '<text x="30" y="30" style="font-size:22px;font-weight:bold">Frozen synthetic test: all-turn deadline success</text>',
        '<text x="30" y="55">Shared cutoff 0.5, 200 ms added silence; simulated acquisition only</text>']
    for i,r in enumerate(rows):
        y=92+i*42;svg.append(f'<text x="30" y="{y+12}">{html.escape(r["backend"])}</text>')
        for j,(side,deadline_ms) in enumerate([('onset',100),('end',300)]):
            value=r['test'][side]['deadlines_ms'][str(deadline_ms)]['fraction'];x=225+j*365
            svg.append(f'<rect x="{x}" y="{y}" width="{value*280:.2f}" height="20" rx="3" fill="{colors[j]}"/>')
            svg.append(f'<text x="{x+value*280+7:.2f}" y="{y+15}">{pct(value)}</text>')
    svg += ['<text x="225" y="625">START within 100 ms</text>','<text x="590" y="625">First-episode END within 300 ms</text>', '<text x="30" y="655" style="font-size:12px">Nominal RMS boundaries: early-active responses can lower success; inspect uncertainty bands in the report.</text>', '<text x="30" y="676" style="font-size:12px">Original pause labels are support gaps, with longer RMS gaps. Artificial short-gap probe is reported separately.</text>', '</svg>']
    (directory/'deadlines.svg').write_text('\n'.join(svg))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--results',default='results/boundary-latency')
    render(parser.parse_args().results)
