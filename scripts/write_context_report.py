#!/usr/bin/env python3
"""Write the repository-format Markdown report from verified ablation JSON."""
import argparse
import json
from pathlib import Path

ARMS = ('context-disabled', 'context-enabled')


def fmt(value, scale=1, digits=2):
    return 'n/a' if value is None else f'{value * scale:.{digits}f}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('results/context-ablation'))
    args = parser.parse_args(); out = args.output
    s = json.loads((out / 'summary.json').read_text())
    fixed = s['protocols']['fixed_0.5']['holdout']
    tuned = s['protocols']['dev_calibrated']['holdout']
    off, on = [fixed[a] for a in ARMS]
    miss_reduction = 1 - on['missed_speech_fraction'] / off['missed_speech_fraction']
    oracle = s['enabled_vs_actual_0_3_0']
    oracle_description = ('Not checked: optional native trace was not supplied' if oracle is None else
                          f'All {oracle["frames"]:,} scores match the prior actual 0.3.0 native-package run bit-for-bit' if oracle['maximum_absolute_score_difference'] == 0 else
                          f'{oracle["frames"]:,} scores compared with actual 0.3.0; maximum absolute difference {oracle["maximum_absolute_score_difference"]:.9g}')
    lines = [
        '# Silero v5.1 missing context ablation', '',
        'Recorded 2026-10-03 UTC. Same model, same runtime, same streams; only the preceding waveform prefix is enabled or omitted.', '',
        f'**The missing-context bug materially harms this synthetic benchmark.** At the fixed 0.5 threshold, correcting it reduces missed speech from **{fmt(off["missed_speech_fraction"],100)}% to {fmt(on["missed_speech_fraction"],100)}%** ({fmt(miss_reduction,100,1)}% relative reduction), non-speech false-positive frames from **{fmt(off["false_positive_fraction"],100,3)}% to {fmt(on["false_positive_fraction"],100,3)}%**, and extra speech fragments from **{off["fragmentation_events"]} to {on["fragmentation_events"]}**. This isolates waveform context, without a model upgrade.', '',
        f'Under the unchanged development-only strict budget, the thresholds are 0.94 without context and 0.96 with context. Holdout missed speech falls from **{fmt(tuned[ARMS[0]]["missed_speech_fraction"],100)}% to {fmt(tuned[ARMS[1]]["missed_speech_fraction"],100)}%**, while both produce two false activations in 0.566 known-negative hours. The fixed 0.5 detector still produces 70 false activations with context, so the fix alone does not meet that strict budget at 0.5.', '',
        '**Scope:** 240 synthetic 20-second streams (80 minutes), with 96 development and 144 fixed holdout streams. All audio is 16 kHz. Accuracy labels are clean-source activity proxies with uncertainty excluded, not human phonetic annotations. These results do not establish real-microphone or production generalization.', '',
        '## Exact experiment', '',
        '| Control | Value |', '|---|---|',
        '| Model in both arms | Exact v5.1 ONNX bytes bundled in published silero-vad-lite 0.3.0 |',
        '| Model SHA-256 | `2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f` |',
        '| Runtime in both arms | Python ONNX Runtime 1.19.0, CPUExecutionProvider, graph optimization ALL, one intra/inter-op thread |',
        '| Missing-context arm | 512 fresh float32 samples; no waveform prefix; recurrent state retained |',
        '| Corrected arm | Same 512 fresh samples plus previous 64 samples; first prefix zero-filled; recurrent state retained |',
        '| Independent stream reset | Zero recurrent state and context in both arms |',
        '| Capture and endpoint controller | Unchanged 10 ms acquisition blocks, 32 ms native frames, common 200 ms trailing-silence rule; no hysteresis or padding |',
        '| Manifest SHA-256 | `73b60d803250b52d2c5cdea7e3a6458a3cf6907a2c171e4610a4b0234cbed52a` |',
        '| Trace verification | 150,000 paired frames, identical source/acquisition clocks; three runs per arm yield bitwise-identical scores |',
        f'| Corrected-arm oracle | {oracle_description} |', '',
        'The missing-context arm is an **emulation of the old input/state contract**, not execution of the old 0.2.1 wheel. No executable-stack security setting was disabled. The old native wrapper fed exactly the 32 ms window, kept its recurrent state, and had no reset API. A fresh old object is the state-reset equivalent used here. This experiment isolates missing waveform context; it does not measure accidental state leakage across streams or the reset API addition. The Python adapter updates context bookkeeping in both arms; only the ONNX input prefix changes.', '',
        'Verified source references:',
        '- [Released v0.2.1 native source](https://github.com/daanzu/py-silero-vad-lite/blob/a4222a5c2c6ca7b7fb1fbcc2af1d19374772d273/src/silero_vad_lite/silero_vad.cpp#L46-L89)',
        '- [Released v0.3.0 corrected source](https://github.com/daanzu/py-silero-vad-lite/blob/64837cae29c0a920a679f4883f3a186d37de1f86/src/silero_vad_lite/silero_vad.cpp)',
        '- [Official v5.1 wrapper contract](https://github.com/snakers4/silero-vad/blob/84768cefdf5a3852400e9d8237f7315d14b64a08/src/silero_vad/utils_vad.py#L46-L95)',
        '- [v0.3.0 reference fixture and model hash](https://github.com/daanzu/py-silero-vad-lite/blob/64837cae29c0a920a679f4883f3a186d37de1f86/tests/generate_context_fixture.py)', '',
        'Both released tags contain the same model Git blob `b3e3a900c0d70e67b5e2b90a33ad856ee7947930` (2,327,524 bytes). The run metadata names pre-fix commit `216ba7a62f1382b5973d4510637503d8a8a0e490`; its old C++/Python source is byte-identical to released v0.2.1. The exact released tag is recorded in summary.json and the independent review.', '',
        '## Accuracy on the fixed holdout', '',
        'Generic speech includes foreground and background voices. The holdout contains 240 merged reference events, 605.31 seconds of labeled speech and 2,037.95 seconds (0.5661 hours) of known non-speech. Another 236.74 seconds are excluded as uncertain or uncovered.', '',
        '| Protocol | Context | Threshold | Missed speech % | Non-speech FP % | False events | False events / negative hour | Event recall % | Extra fragments |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for protocol, p in s['protocols'].items():
        for arm, m in p['holdout'].items():
            lines.append(f'| {"Fixed" if protocol == "fixed_0.5" else "Dev-calibrated"} | {arm.split("-")[1]} | {m["threshold"]:.2f} | {fmt(m["missed_speech_fraction"],100)} | {fmt(m["false_positive_fraction"],100,4)} | {m["false_activations"]} | {fmt(m["false_activations_per_negative_hour"])} | {fmt(m["event_recall"],100)} | {m["fragmentation_events"]} |')
    lines += ['', 'The unchanged calibration grid minimizes development missed speech subject to at most five false activation events per known-negative hour and at most 1% false-positive frames. Thresholds are selected separately for each arm on the same 96 development streams, then frozen. Both chosen thresholds have one development false activation; development misses are 64.33% without context and 27.51% with context. The grid and every development result are retained in development-curves.json. No threshold is selected from holdout.', '',
        'The fixed 0.5 comparison is the clean same-threshold effect. The dev-calibrated comparison includes the different optimal thresholds under the same rule. Cross-applying each selected threshold confirms that the gain is not only a threshold artifact:', '',
        '| Shared threshold | Missing-context miss % | Corrected miss % | Missing / corrected false events |', '|---|---:|---:|---:|']
    for threshold, arms in s['cross_threshold_holdout'].items():
        a, b = [arms[arm] for arm in ARMS]
        lines.append(f'| {threshold} | {fmt(a["missed_speech_fraction"],100)} | {fmt(b["missed_speech_fraction"],100)} | {a["false_activations"]} / {b["false_activations"]} |')
    lines += ['', '## Paired uncertainty', '',
        'All deltas below are corrected minus missing context. Intervals are the 2.5th/97.5th percentiles of 5,000 paired whole-stream bootstrap resamples, keeping the 12 conditions and their sample counts fixed. The same resampled stream IDs are used in both arms; thresholds remain frozen. These are descriptive within-corpus intervals: repeated TTS voices/texts violate population independence, and development calibration uncertainty is not included.', '',
        '| Protocol | Metric | Change | Descriptive paired 95% interval |', '|---|---|---:|---:|']
    metric_labels = {'missed_speech_fraction': ('Missed speech, percentage points', 100),
                     'false_positive_fraction': ('False-positive frames, percentage points', 100),
                     'false_activations_per_negative_hour': ('False events per negative hour', 1),
                     'event_recall': ('Event recall, percentage points', 100),
                     'fragmentation_per_reference': ('Extra fragments per reference', 1)}
    for protocol, p in s['protocols'].items():
        for key, m in p['paired_uncertainty']['metrics'].items():
            label, scale = metric_labels[key]; lo, hi = m['percentile95']
            lines.append(f'| {"Fixed 0.5" if protocol == "fixed_0.5" else "Dev-calibrated"} | {label} | {fmt(m["delta"],scale,3)} | {fmt(lo,scale,3)} to {fmt(hi,scale,3)} |')
    lines += ['', 'At fixed 0.5, the event-recall change is small and its interval includes zero, even though speech-frame misses and fragmentation improve strongly. At the calibrated operating points both arms have two false events: the descriptive Poisson 95% rate interval is 0.43–12.76 events per negative hour. Observing 3.53/hour here does not establish a production five/hour guarantee.', '',
        '## Onset and end timing', '',
        'Times below are relative to synthetic clean-source proxy boundaries and use simulated input acquisition time, excluding compute scheduling. Quantiles include matched events only; missed events and different matching populations can bias the comparison. The one-to-one maximum-overlap greedy matcher is unchanged.', '',
        '| Protocol | Context | Matched events | Onset notification p50 / p95 ms | End notification p50 / p95 ms | Onset clipping p95 ms | End clipping p95 ms | Premature end % |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for protocol, p in s['protocols'].items():
        for arm, m in p['holdout'].items():
            lines.append(f'| {"Fixed 0.5" if protocol == "fixed_0.5" else "Dev-calibrated"} | {arm.split("-")[1]} | {m["latency_matched_event_count"]} | {fmt(m["onset_notification_p50_s"],1000,0)} / {fmt(m["onset_notification_p95_s"],1000,0)} | {fmt(m["end_notification_p50_s"],1000,0)} / {fmt(m["end_notification_p95_s"],1000,0)} | {fmt(m["onset_clipping_p95_s"],1000,0)} | {fmt(m["end_clipping_p95_s"],1000,0)} | {fmt(m["premature_notification_fraction"],100)} |')
    lines += ['', 'Corrected end notifications can be later because the detector stops cutting speech off early. At fixed 0.5, premature notifications fall from 25.54% to 3.42% and p95 end clipping falls from 2,950 ms to 62 ms; a shorter signed end delay would not by itself be an improvement. At the strict threshold, missing context yields a negative median end notification (550 ms before the true proxy end) and 64.78% premature ends.', '',
        'For a paired reference-event check, 230 reference events are matched in both arms at fixed 0.5: the median per-event onset notification change is -40 ms and end notification change is +70 ms. At the calibrated points, 153 are matched in both: median onset change -30 ms, end change +760 ms. Full distributions and unmatched-side counts are in summary.json. No EOF-forced event is included in end-delay quantiles.', '',
        '## Results by condition', '',
        'Each condition has 12 holdout streams (four minutes). `n/a` means the condition has no speech references or no matched event; it is not zero. Music conditions use synthetic music-like tones rather than recordings. Every speech-bearing condition has fewer missed speech frames with corrected context at fixed 0.5. Corrected fixed-threshold false activations remain concentrated in music-like conditions (41 music-only, 29 speech-plus-music).', '']
    for protocol, p in s['protocols'].items():
        lines += [f'### {"Fixed threshold 0.5" if protocol == "fixed_0.5" else "Development calibrated thresholds"}', '',
                  '| Condition | Context | Miss % | FP % | False events | Recall % | Extra fragments | Onset p95 ms | End p95 ms |',
                  '|---|---|---:|---:|---:|---:|---:|---:|---:|']
        for condition, arms in p['conditions'].items():
            for arm, m in arms.items():
                lines.append(f'| {condition} | {arm.split("-")[1]} | {fmt(m["missed_speech_fraction"],100)} | {fmt(m["false_positive_fraction"],100,3)} | {m["false_activations"]} | {fmt(m["event_recall"],100)} | {m["fragmentation_events"]} | {fmt(m["onset_notification_p95_s"],1000,0)} | {fmt(m["end_notification_p95_s"],1000,0)} |')
        lines.append('')
    lines += ['## Runtime cost', '',
        'Three complete 80-minute corpus passes per arm were measured in fresh sequential processes after ten warmup frames, in order disabled/enabled, enabled/disabled, disabled/enabled. All three passes are retained; no best-run selection. CPU affinity/frequency was uncontrolled on a shared Intel Xeon Platinum 8573C host. WAV reading and resets are outside streaming timing; buffering, dispatch, conversion, inference, and context bookkeeping are inside. This measures the same Python runtime path in both arms, not the old-versus-new native wheel speed.', '',
        '| Context | Wall seconds per 80 min, median [range] | Wall RTF, median [range] | CPU RTF median | Adapter inference RTF median | Peak process MiB range |',
        '|---|---:|---:|---:|---:|---:|']
    for arm, t in s['timing'].items():
        w, r, rss = t['wall_s'], t['wall_rtf'], t['peak_process_rss_kib']
        lines.append(f'| {arm.split("-")[1]} | {fmt(w["median"])} [{fmt(w["min"])}–{fmt(w["max"])}] | {fmt(r["median"],digits=6)} [{fmt(r["min"],digits=6)}–{fmt(r["max"],digits=6)}] | {fmt(t["cpu_rtf"]["median"],digits=6)} | {fmt(t["inference_rtf"]["median"],digits=6)} | {fmt(rss["min"],1/1024,1)}–{fmt(rss["max"],1/1024,1)} |')
    off_time, on_time = [s['timing'][a]['wall_rtf']['median'] for a in ARMS]
    paired_overhead = [(b['wall_rtf'] / a['wall_rtf'] - 1) * 100 for a, b in
                       zip(s['timing'][ARMS[0]]['passes'], s['timing'][ARMS[1]]['passes'])]
    lines += ['', f'The corrected arm has {fmt((on_time/off_time-1)*100, digits=1)}% higher median wall RTF in these runs; its per-pass overhead ranges from {min(paired_overhead):+.2f}% to {max(paired_overhead):+.2f}% when paired by pass. The broad shared-host variability prevents a precise overhead claim. Both median CPU RTFs are roughly 0.005–0.006, meaning roughly 5–6 ms of CPU time per second of audio under this benchmark. Real-time deployment utilization and device scheduling costs were not measured. Peak RSS includes Python/runtime and retained traces, not just model RAM. A 64-sample prefix is past audio and introduces no extra future-audio wait.', '',
        '## Limits and validation', '',
        '- Main accuracy and throughput use 16 kHz only. Contract tests cover 8 kHz shapes (256 fresh + 32 context); no 8 kHz corpus accuracy result is claimed.',
        '- Synthetic fan, typing, music-like tones, TTS voices, echo and filtering cover specific constructed conditions. Only two held-out TTS voices and repeated within-split texts are present. No human voice, real room, microphone or phonetic annotation was evaluated.',
        '- The corpus/split and calibration grid are inherited unchanged. This ablation was requested after prior model-comparison results were observed; it is not a preregistered or blind study.',
        '- A matched event needs positive overlap, not complete utterance capture. A detector can therefore have high event recall while missing much of each utterance. Inspect miss fraction, fragmentation and clipping together.',
        '- The false-event metric counts unmatched segments with known-negative support. Overlapping extra fragments are tracked separately. Non-speech false-positive frames prevent long activations from hiding behind low event counts.',
        '- The known-negative exposure is short, and bootstrap resampling does not estimate between-speaker, between-engine, natural-audio or threshold-selection uncertainty. Timing repeats capture this host only.',
        '- Full contract, arithmetic, result and inherited tests were run; see tests.log and INDEPENDENT_REVIEW.md. The unrelated TEN integration test requires its separately licensed runtime and is skipped in this run.', '',
        '## Reproduce and inspect', '',
        'Start from repository commit `a0f9e600dfdba202d9d960ea4679f3eed7a37328` plus the supplied source changes. Follow the existing setup to install pinned 0.3.0 assets and generate or reuse the exact corpus. No old native wheel is needed.', '',
        '```sh',
        'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run --manifest data/synthetic/manifest.json --output results/context-ablation/raw/pass1 --backends context-disabled context-enabled',
        'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run --manifest data/synthetic/manifest.json --output results/context-ablation/raw/pass2 --backends context-enabled context-disabled',
        'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run --manifest data/synthetic/manifest.json --output results/context-ablation/raw/pass3 --backends context-disabled context-enabled',
        'python scripts/report_context_ablation.py --native-raw results/silero-lite-comparison/raw/silero-lite-0.3.0.npz',
        'python scripts/write_context_report.py',
        'python -m unittest discover -s tests -v',
        '```', '',
        'The optional `--native-raw` oracle points at a completed actual native 0.3.0 package trace. `summary.json` contains both protocols, all condition scores, descriptive uncertainty, paired-reference timing, cross-threshold checks and performance. `per-stream-holdout.json` and `development-curves.json` support independent re-analysis. `runs.json` and raw per-pass metadata retain environment, code/model/audio hashes and stream timings; compressed traces remain local generated assets. The exact manifest is copied to `dataset-manifest.json`. Historical benchmark results are unchanged.', '',
        '**Conclusion:** keep the corrected waveform context. On this controlled v5.1 test it substantially reduces missed speech, false positives, fragmentation and premature endpointing. Validate the intended thresholds on representative real recordings before drawing production conclusions.', '']
    (out / 'REPORT.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
