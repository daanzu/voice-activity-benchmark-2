"""Freeze dev choices, then score holdout and generate machine-readable plots/report."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np
from .metrics import calibrate,evaluate

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--raw',type=Path,default=Path('results/synthetic/raw'))
    parser.add_argument('--output',type=Path,default=Path('results/synthetic'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(args.manifest.read_text());records=manifest['records']
    dev=[r for r in records if r['split']=='dev'];test=[r for r in records if r['split']=='test']
    results=[];curves={};blocked=[]
    for path in sorted(args.raw.glob('*.json')):
        raw=json.loads(path.read_text());name=raw['backend']
        if raw['status']!='ok':blocked.append(raw);continue
        expected=hashlib.sha256(args.manifest.read_bytes()).hexdigest()
        if raw['manifest_sha256']!=expected:raise ValueError(f'Manifest changed since run: {name}')
        with np.load(path.with_suffix('.npz')) as loaded:traces={k:loaded[k] for k in loaded.files}
        selected,curve=calibrate(dev,traces)
        curves[name]=curve
        holdout=evaluate(test,traces,selected['threshold'])
        foreground=evaluate(test,traces,selected['threshold'],task='target')
        duration=sum(t['audio_s'] for t in raw['timing'])
        result=dict(backend=name,dev=selected,test=holdout,foreground_diagnostic=foreground,
                    conditions={condition:evaluate([r for r in test if r['condition']['name']==condition],traces,selected['threshold']) for condition in sorted({r['condition']['name'] for r in test})},
                    performance=dict(wall_rtf=sum(t['wall_s'] for t in raw['timing'])/duration,
                        cpu_rtf=sum(t['cpu_s'] for t in raw['timing'])/duration,
                        inference_rtf=sum(t['inference_s'] for t in raw['timing'])/duration,
                        resampling_rtf=sum(t['resampling_s'] for t in raw['timing'])/duration,
                        startup_s=raw['startup_s'],peak_process_rss_kib=raw['peak_process_rss_kib']),
                    adapter=raw['adapter'],methodology=raw['methodology'],environment=raw['environment'])
        results.append(result)
    # Treat aggressiveness as a dev-only choice, not four independent holdout attempts.
    classic=[r for r in results if r['backend'].startswith('classic-')]
    selected_classic=min(classic,key=lambda r:(r['dev']['missed_speech_fraction'],r['dev']['false_positive_fraction'])) if classic else None
    included=[r for r in results if not r['backend'].startswith('classic-') or r is selected_classic]
    summary=dict(schema_version=1,manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                 dataset=dict(streams=len(records),hours=sum(r['duration_s'] for r in records)/3600,
                     split_counts=dict(Counter(r['split'] for r in records)),generation=manifest.get('generation')),
                 calibration=dict(split='dev',false_activations_per_negative_hour_budget=5,
                     false_positive_fraction_cap=.01,threshold_grid='0.05:0.05:0.95, 0.999, 1.001',
                     selected_classic=selected_classic['backend'] if selected_classic else None),
                 results=included,all_development_choices={r['backend']:r['dev'] for r in results},blocked=blocked)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    (args.output/'development-curves.json').write_text(json.dumps(curves,indent=2))
    # Copy exact immutable manifest as provenance; WAV files remain generated assets.
    (args.output/'dataset-manifest.json').write_bytes(args.manifest.read_bytes())
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['svg.fonttype']='none';plt.rcParams['svg.hashsalt']='vadbench-20261002'
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for name,curve in curves.items():
        if name.startswith('classic-') and selected_classic and name!=selected_classic['backend']:continue
        axes[0].plot([r['false_positive_fraction'] for r in curve],[1-r['missed_speech_fraction'] for r in curve],label=name,marker='.',ms=3)
    axes[0].set(xlabel='Non-speech false-positive fraction (dev)',ylabel='Speech recall (dev)',title='Synthetic development operating curves',xlim=(0,1),ylim=(0,1));axes[0].legend(fontsize=8)
    labels=[r['backend'] for r in included]
    axes[1].barh(labels,[r['test']['missed_speech_fraction'] for r in included]);axes[1].set(xlabel='Missed speech fraction (holdout)',title='Dev-selected thresholds, untouched synthetic holdout',xlim=(0,1))
    fig.tight_layout();fig.savefig(args.output/'accuracy.svg',metadata={'Date':None});plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    axes[0].barh(labels,[r['performance']['wall_rtf'] for r in included]);axes[0].set(xlabel='Wall-clock real-time factor (lower is faster)',title='Causal streaming pipeline, shared CPU')
    valid=[r for r in included if r['test']['end_notification_p95_s'] is not None]
    axes[1].barh([r['backend'] for r in valid],[r['test']['end_notification_p95_s']*1000 for r in valid]);axes[1].set(xlabel='Signed end notification delay, p95 (ms)',title='Matched events only; see recall and early endings')
    fig.tight_layout();fig.savefig(args.output/'performance.svg',metadata={'Date':None});plt.close(fig)
    def f(value,scale=1):return 'n/a' if value is None else f'{value*scale:.3f}'
    lines=['# Synthetic streaming benchmark results','',
        '**Synthetic-domain experiment, not real-microphone accuracy or human phonetic ground truth.**','',
        f"{len(records)} streams, {summary['dataset']['hours']:.2f} hours; {len(dev)} development and {len(test)} untouched holdout streams. Four synthesis voices are split between dev/test. The same synthesis engine is shared, so this is not cross-engine generalization.",'',
        'Labels come from known source placement plus clean-signal activity proxies, with uncertainty excluded. Generic speech includes background voices. A foreground-only diagnostic is separately reported and is not a fair expectation for speaker-agnostic VAD. See [dataset methodology](../../docs/DATASET.md).','',
        '## Frozen operating point','',
        'Thresholds and classic aggressiveness are selected only on development data: minimize missed speech subject to at most 5 unmatched activations per negative-audio hour AND at most 1% non-speech frame false positives. The grid includes a never-positive threshold, explicitly visible below. This can select an unusable all-miss detector; no feasible useful operating point is a result, not a reason to retune on holdout. Constraints need not transfer to holdout.','',
        '| Backend | Threshold | Holdout miss % | Holdout false-positive % | False events/negative hour | Event recall % | Extra fragments |','|---|---:|---:|---:|---:|---:|---:|']
    for r in included:
        m=r['test'];lines.append(f"| {r['backend']} | {f(m['threshold'])} | {f(m['missed_speech_fraction'],100)} | {f(m['false_positive_fraction'],100)} | {f(m['false_activations_per_negative_hour'])} | {f(m['event_recall'],100)} | {m['fragmentation_events']} |")
    lines+=['','![Accuracy plots](accuracy.svg)','','## Timing and notification','',
        '| Backend | Wall RTF | CPU RTF | Startup s | Peak process MiB | Onset clipping p95 ms | End notification p50 / p95 ms | Matched latency events |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in included:
        m=r['test'];p=r['performance'];lines.append(f"| {r['backend']} | {f(p['wall_rtf'])} | {f(p['cpu_rtf'])} | {f(p['startup_s'])} | {f(p['peak_process_rss_kib'],1/1024)} | {f(m['onset_clipping_p95_s'],1000)} | {f(m['end_notification_p50_s'],1000)} / {f(m['end_notification_p95_s'],1000)} | {m['latency_matched_event_count']} |")
    lines+=['','![Performance plots](performance.svg)','','## Interpretation and limits','',
        '- Unknown native score alignment is left uncompensated and recorded as null. Frame-boundary accuracy for these adapters is not alignment-calibrated; native lookahead is documented separately. AGC2 is a historical extraction; FSMN is raw posterior, not native segmentation.',
        '- Native frame sizes, context, state, and causal FIR resampling are preserved. Input arrives in simulated 10 ms capture blocks. Retrospective score alignment is separate from actual acquisition-time notification.',
        '- A common 200 ms silence endpoint rule is used, with no padding or separate exit threshold. It does not reproduce each vendor’s native endpoint defaults. EOF-forced endings are excluded from latency distributions.',
        '- Event reference intervals merge clean activity gaps up to 200 ms. Matching is globally greedy one-to-one by descending overlap; overlapping extra fragments are counted separately. Long merged detections cannot count as multiple correct events. Delays are conditional on matched events; read them together with recall, premature notifications, source end clipping, fragmentation, and misses in summary.json.',
        '- False activation events are unmatched segments with no reference overlap per known-negative hour; the separate frame false-positive cap prevents a single long activation from gaming event counts. Unmatched events with any known-negative grid support count as false activations; events supported only by uncertainty are separately censored.',
        '- Development has only 32 minutes and holdout 48 minutes, with still less known-negative time. Low false-event rates are quantized and statistically uncertain; this is not evidence of a production 5/hour guarantee.',
        '- Single measured corpus pass after warmup; shared unpinned cloud CPU, no frequency control. RTF includes buffering, resampling, dispatch, and inference; excludes WAV reads and reset. Startup is adapter construction, not a full process import.',
        '- Memory is isolated-backend peak process RSS including Python, dependencies, and stored traces. It is not model-only RAM. File/package size and RSS must not be conflated.',
        '- Notification delays use simulated audio-acquisition time and exclude compute scheduling. They are algorithmic pipeline delays, not measured device-to-application wall latency.',
        '- Synthetic fan, typing, music-like interference and TTS speech do not represent real rooms or microphones. No human labeling was performed. Do not generalize the ranking to natural speech without external validation.',
        '- Historical results and REPORT.md remain unchanged. Machine-readable full metrics, adapter pins, provenance, blocked status, and calibration curves are adjacent.','']
    if blocked:
        lines+=['## Blocked backends','']+[f"- {r['backend']}: {r['error']}" for r in blocked]
    (args.output/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'completed':[r['backend'] for r in included],'blocked':[r['backend'] for r in blocked],'output':str(args.output)},indent=2))
if __name__=='__main__':main()
