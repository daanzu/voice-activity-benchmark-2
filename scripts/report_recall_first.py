"""Write recall-first findings from verified computed artifacts; no inference."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fmt(value, scale=1, digits=3):
    return 'n/a' if value is None else f'{value*scale:.{digits}f}'


def report(directory):
    directory = Path(directory)
    summary = json.loads((directory/'summary.json').read_text())
    runs = json.loads((directory/'runs.json').read_text())
    targets = {t['id']: t for t in summary['targets']}
    references = {r['backend']: r for r in summary['classic_references']}
    def table(rows):
        lines = ['| Backend | Positive threshold | Dev recall % | Holdout recall % | Holdout FP % | FP seconds | False events | Events / negative hour |',
                 '|---|---:|---:|---:|---:|---:|---:|---:|']
        for r in rows:
            if not r['feasible']:
                lines.append(f"| {r['backend']} | unattainable | max {fmt(r['max_dev_recall'],100)} | n/a | n/a | n/a | n/a | n/a |")
                continue
            d, h = r['dev'], r['test']
            lines.append(f"| {r['backend']} | {r['threshold']:.10g} | {fmt(d['speech_frame_recall'],100)} | {fmt(h['speech_frame_recall'],100)} | {fmt(h['false_positive_fraction'],100)} | {fmt(h['false_positive_seconds'],digits=2)} | {h['false_activations']} | {fmt(h['false_activations_per_negative_hour'])} |")
        return lines
    lines = ['# Recall-first streaming VAD tradeoffs', '',
             '**Fresh October 5, 2026 reconstruction. Synthetic source-activity labels, not human phonetic ground truth or a production guarantee.**', '',
             'This experiment asks how much non-speech time becomes active when speech-frame recall takes priority. It extends the development display sweep from the historical minimum 0.05 down to 1e-12, targets 99%, 99.5%, and 99.9% development speech-frame recall, and separately meets or exceeds the native development recall of classic WebRTC modes 0–3.', '',
             'All twelve detector configurations were rerun on the byte-identical original 240-stream, 80-minute corpus. The 96 development streams and 144 holdout streams, source WAVs, mixture WAVs, labels, and full manifest are unchanged. Historical results remain untouched. The prior October 4 work was not recoverable; the figures below come exclusively from the retained October 5 scores.', '',
             '## What was selected', '',
             '- Only known development speech-frame scores determine the threshold. The highest strictly-positive cutoff meeting the exact required speech-frame count minimizes false-positive frame duration over all positive cutoffs, without a coarse-grid approximation. Equal-score ties stay together; the highest feasible cutoff breaks equal-FP choices with the smallest recall overshoot. The exact rational target avoids rounding errors at classic-mode parity.',
             '- All 84 backend/target choices are written to frozen-thresholds.json before any holdout evaluation. Thresholds are then reused unchanged on holdout. A development target is not a holdout guarantee; the achieved holdout recall is always shown.',
             '- Classic modes return binary scores: their only operational point is the native 0.5 threshold. A mode missing a target is explicitly unattainable, without converting its negative decisions to speech.',
             '- Probability scores equal to zero cannot become positive under a strictly-positive cutoff. Targets requiring those zero-score speech frames are also unattainable. Threshold 0 is reported only as an always-positive diagnostic, never as an operational target solution.',
             '- The optimized false-positive measure is known non-speech frame duration. False activation events and their rate are separate outputs, not a selection constraint. A longer merged activation can reduce event counts while increasing false-positive duration.',
             '- Recall means raw aligned speech-frame recall, not event detection, captured/prerolled audio, or ASR transcript recall. The shared 200 ms endpoint controller remains unchanged.', '',
             '## Fixed recall targets', '']
    for identifier in ['recall-99','recall-99.5','recall-99.9']:
        lines += [f"### {targets[identifier]['label']} on development", '']
        lines += table([r for r in summary['selections'] if r['target_id']==identifier]) + ['']
    lines += ['## Classic-mode parity targets', '',
              'The target is each classic mode’s development recall. Every candidate is frozen on development, so holdout rows can exceed or miss the classic mode’s holdout recall. Compare the actual held-out recall and FP duration together; these are not holdout-tuned equal-recall estimates.', '']
    for mode in range(4):
        backend = f'classic-{mode}'
        ref = references[backend]
        d, h = ref['dev'], ref['test']
        lines += [f'### Match {backend}', '',
                  f"Native reference: dev recall **{fmt(d['speech_frame_recall'],100,6)}%**; holdout recall **{fmt(h['speech_frame_recall'],100,6)}%**, FP **{fmt(h['false_positive_fraction'],100)}%** ({fmt(h['false_positive_seconds'],digits=2)} seconds), **{h['false_activations']}** false events ({fmt(h['false_activations_per_negative_hour'])}/negative hour).", '']
        rows = [r for r in summary['selections'] if r['target_id']=='match-'+backend]
        lines += table(rows) + ['']
    lines += ['## Specific tradeoffs in this rerun', '']
    silero = [r for r in summary['selections'] if r['backend']=='silero' and r['target_id'].startswith('recall-')]
    for row in silero:
        if row['feasible']:
            h = row['test']
            lines.append(f"- Direct Silero at {100*row['target_recall']:g}% development target: holdout recall {fmt(h['speech_frame_recall'],100)}%, FP duration {fmt(h['false_positive_fraction'],100)}%, {h['false_activations']} false events")
    row = next(r for r in summary['selections'] if r['backend']=='rnnoise' and r['target_id']=='match-classic-0')
    if row['feasible']:
        h, baseline = row['test'], references['classic-0']['test']
        lines.append(f"- RNNoise at the classic-0 development recall target: holdout recall {fmt(h['speech_frame_recall'],100,6)}% versus classic-0 {fmt(baseline['speech_frame_recall'],100,6)}%; FP duration {fmt(h['false_positive_fraction'],100)}% versus {fmt(baseline['false_positive_fraction'],100)}%; false events {h['false_activations']} versus {baseline['false_activations']}. Duration and event count measure different costs; this is not a single-metric winner claim")
    lines += ['', '## Always-positive diagnostic (excluded from selection)', '',
              '| Backend | Holdout raw speech-frame recall % | Holdout FP % | Event recall % | False events | Forced EOF events |',
              '|---|---:|---:|---:|---:|---:|']
    for r in summary['diagnostics']:
        h = r['test']
        lines.append(f"| {r['backend']} | {fmt(h['speech_frame_recall'],100)} | {fmt(h['false_positive_fraction'],100)} | {fmt(h['event_recall'],100)} | {h['false_activations']} | {h['forced_eof_events']} |")
    lines += ['', 'A positive score floor can also produce an all-positive operating point at a positive threshold (for example, a score floor of 0.1); such a point remains feasible but its 100% FP duration is a degenerate tradeoff, not useful discrimination. Threshold 0 labels every covered frame positive. It can merge multiple reference utterances into one detection, so the one-to-one event recall is not necessarily 100%, and apparent false-event rates do not capture its continuous false-positive duration. EOF-forced endings are excluded from endpoint-delay statistics.', '',
              '## Reproducibility and host effects', '',
              f"Manifest SHA-256: `{summary['manifest_sha256']}`. Raw trace checksums, exact thresholds, every development curve point, split metrics, native source/model/package hashes, and run metadata are retained next to this report. Generated WAVs and native/model dependencies stay private/regenerable; no third-party binaries are redistributed.", '',
              f"Current measured CPU: **{runs['silero']['environment']['cpu_model']}**. The historical published-package comparison used Intel Xeon Platinum 8573C. Native binaries compiled with host-specific flags can differ, and probability outputs may drift with runtime/build/hardware. Therefore this new run has its own results directory and provenance; older recorded values are not overwritten or silently combined.", '',
              'Fixed-reference metrics from this run are compared with the historical comparison in historical-reference-deltas.json. These checks can reveal aggregate differences but cannot establish bitwise score identity when historical raw scores are unavailable.', '',
              '## Limits', '',
              '- Four synthetic English TTS voices, with two per split and repeated texts within split, share one Flite engine. The fixed holdout is not evidence of real-microphone or human-speech generalization',
              '- Labels are clean-source activity proxies; uncertain activity collars, internal pauses and reverberation tails are excluded. Generic speech includes background voices',
              '- Different native frame coverage can give slightly different positive/negative denominators. All confusion counts and exposure times are retained rather than assuming identical denominators',
              '- Native frame size/state, causal resampling, score alignment, model provenance and shared endpointing are inherited unchanged. Unknown native score alignment remains uncalibrated',
              '- FP rate here means FP / (FP + TN) over known-negative frames, not false discoveries among positive predictions. FP seconds and event counts are both reported',
              '- False-event rates have limited known-negative exposure and are descriptive, not an assurance of a production rate. Retained Poisson intervals do not model repeated-voice or condition dependence',
              '- The study follows prior observed benchmark results and is not preregistered or blind. Threshold selection uses development only; no claim is made that tuning or repeated analysis was unseen',
              '- Runtime measurements are one shared-host pass with no CPU affinity/frequency control. They are retained for provenance, not a controlled speed comparison with previous hosts',
              '- No new endpoint latency, preroll, ASR, noise corpus, or device-latency study is included', '',
              '## Reproduce', '',
              'See [setup and protocol](../../docs/RECALL_FIRST.md). [Independent review](INDEPENDENT_REVIEW.md) and [validation](VALIDATION.md) record checks against the final artifacts.', '']
    text = '\n'.join(lines)
    (directory/'FINDINGS.md').write_text(text)
    (directory/'REPORT.md').write_text(text)
    historical = json.loads((ROOT/'results/silero-lite-comparison/summary.json').read_text())
    delta_rows = []
    keys = ['tp','fp','fn','tn','missed_speech_fraction','false_positive_fraction','false_activations','false_activations_per_negative_hour']
    for row in summary['fixed_references']:
        old = historical['reference_points'][row['backend']]
        new = row['test']
        if old['threshold'] != new['threshold']:
            raise ValueError('Historical reference threshold differs')
        delta_rows.append(dict(backend=row['backend'], threshold=row['threshold'],
                               historical={k:old[k] for k in keys}, current={k:new[k] for k in keys},
                               delta={k:new[k]-old[k] for k in keys}))
    (directory/'historical-reference-deltas.json').write_text(json.dumps(dict(
        baseline='results/silero-lite-comparison/summary.json at 5bf4ae0',
        purpose='Aggregate fixed-reference check; not bitwise score comparison', comparisons=delta_rows), indent=2)+'\n')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT/'results/recall-first')
    args = parser.parse_args()
    report(args.results)


if __name__ == '__main__':
    main()
