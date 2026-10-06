# Rapid speech onset and ending: synthetic benchmark

## Main findings

- Direct Silero / identical Lite 0.4: removing 200 ms added silence changes test END≤300 ms from 43.3% to 75.8%; first-episode premature/clipped endings 28→29. START≤100 ms stays 93.3%
- RNNoise behaves differently: retaining 200 ms added silence improves END≤300 ms from 61.7% to 67.5% while first-episode cuts fall 46→28. Zero added silence is not a universal choice
- A development-tuned point is not guaranteed to beat a fixed test baseline: Silero's dev-selected START100/END300 point reaches 62.5% test intact-turn success, versus 69.2% at the shared 0 ms baseline. No holdout retuning was performed

These comparisons use the frozen nominal acoustic proxy. They are diagnostics with all-turn denominators, not production recommendations; uncertainty and controlled-pause caveats below are essential.

## What was measured

272 frozen synthetic streams (36.27 minutes), 120 test turns, 12 configurations. START and END availability follow the causal 10 ms input-acquisition clock. These numbers include native framing, buffering and observed model/native state. They exclude actual computation and physical capture/device latency. Backdated source boundaries are reported separately.

**Every turn stays in the denominator.** Early-active STARTs, missing responses, premature/clipped first episodes, fragments and forced EOF cannot become an artificially fast successful turn. P50/P90/P95 are failure-aware nearest-rank quantiles: “unreached” means too few turns succeeded. END uses the first overlapping episode, so a premature first episode cannot be rescued by a later final fragment. Joint intact-turn success additionally rejects any fragmentation or merge.

**Limits:** English Flite speech, two voices per split, repeated controlled prefix variants, clean-source RMS proxies rather than human phonetic labels. Exact low-energy source support produces broad uncertainty bands. Use the nominal/possible/certain deadline tables together. This cannot establish a production winner or solve semantic turn completion.

## Same controller: frozen test

All rows use start cutoff 0.5, no hysteresis and no extra start confirmation. Native internal overhang remains. The only change is added trailing-silence duration. START ≤100 ms and END ≤300 ms are illustrative columns; all requested deadline grids and error counts are retained in JSON and the explorer. **A low nominal START success can mean activation before the RMS-proxy onset, not slow detection or missed speech.** Inspect early-active counts and possible/certain bands, especially where low-energy source support precedes the proxy.

| Configuration | Added silence | START ≤100 ms nominal / possible / certain | Early-active | END ≤300 ms | START P50/P90/P95 ms | END P50/P90/P95 ms | Premature/clipped first ends | Fragmented turns | False STARTs / neg h |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| classic-0 | 0 ms | 61.7% / 100.0% / 0.0% | 46/120 | 66.7% | 10 / unreached / unreached | 210 / unreached / unreached | 28/120 | 28/120 | 287.8 |
| classic-0 | 200 ms | 0.0% / 100.0% / 0.0% | 120/120 | 3.3% | unreached / unreached / unreached | 400 / unreached / unreached | 22/120 | 22/120 | 87.9 |
| classic-1 | 0 ms | 61.7% / 100.0% / 0.0% | 46/120 | 66.7% | 10 / unreached / unreached | 210 / unreached / unreached | 28/120 | 28/120 | 235.9 |
| classic-1 | 200 ms | 0.0% / 100.0% / 0.0% | 120/120 | 3.3% | unreached / unreached / unreached | 400 / unreached / unreached | 22/120 | 22/120 | 87.9 |
| classic-2 | 0 ms | 66.7% / 100.0% / 0.0% | 40/120 | 75.0% | 20 / unreached / unreached | 110 / unreached / unreached | 28/120 | 28/120 | 387.8 |
| classic-2 | 200 ms | 66.7% / 100.0% / 0.0% | 40/120 | 51.7% | 20 / unreached / unreached | 300 / unreached / unreached | 28/120 | 28/120 | 103.9 |
| classic-3 | 0 ms | 98.3% / 100.0% / 0.0% | 0/120 | 38.3% | 30 / 60 / 70 | unreached / unreached / unreached | 74/120 | 55/120 | 667.6 |
| classic-3 | 200 ms | 98.3% / 100.0% / 0.0% | 0/120 | 48.3% | 30 / 60 / 70 | 440 / unreached / unreached | 47/120 | 28/120 | 127.9 |
| silero | 0 ms | 93.3% / 98.3% / 0.0% | 0/120 | 75.8% | 50 / 90 / 110 | 120 / unreached / unreached | 29/120 | 29/120 | 24.0 |
| silero | 200 ms | 93.3% / 98.3% / 0.0% | 0/120 | 43.3% | 50 / 90 / 110 | 310 / unreached / unreached | 28/120 | 28/120 | 12.0 |
| silero-lite-0.3.0 | 0 ms | 81.7% / 89.2% / 0.0% | 0/120 | 63.3% | 50 / 130 / 150 | 120 / unreached / unreached | 44/120 | 33/120 | 72.0 |
| silero-lite-0.3.0 | 200 ms | 81.7% / 89.2% / 0.0% | 0/120 | 48.3% | 50 / 130 / 150 | 310 / unreached / unreached | 39/120 | 28/120 | 28.0 |
| silero-lite-0.4.0 | 0 ms | 93.3% / 98.3% / 0.0% | 0/120 | 75.8% | 50 / 90 / 110 | 120 / unreached / unreached | 29/120 | 29/120 | 24.0 |
| silero-lite-0.4.0 | 200 ms | 93.3% / 98.3% / 0.0% | 0/120 | 43.3% | 50 / 90 / 110 | 310 / unreached / unreached | 28/120 | 28/120 | 12.0 |
| agc2 | 0 ms | 93.3% / 100.0% / 0.0% | 8/120 | 21.7% | 20 / 80 / unreached | unreached / unreached / unreached | 94/120 | 58/120 | 643.6 |
| agc2 | 200 ms | 76.7% / 100.0% / 0.0% | 28/120 | 27.5% | 30 / unreached / unreached | unreached / unreached / unreached | 87/120 | 28/120 | 271.8 |
| ten | 0 ms | 90.8% / 100.0% / 0.0% | 10/120 | 70.0% | 20 / 90 / unreached | 100 / unreached / unreached | 36/120 | 36/120 | 419.8 |
| ten | 200 ms | 80.0% / 100.0% / 0.0% | 23/120 | 60.8% | 30 / unreached / unreached | 290 / unreached / unreached | 27/120 | 27/120 | 135.9 |
| fsmn | 0 ms | 6.7% / 98.3% / 0.0% | 112/120 | 69.2% | unreached / unreached / unreached | 280 / unreached / unreached | 28/120 | 28/120 | 1467.1 |
| fsmn | 200 ms | 0.0% / 0.8% / 0.0% | 120/120 | 1.7% | unreached / unreached / unreached | 460 / 550 / unreached | 12/120 | 12/120 | 927.5 |
| rnnoise | 0 ms | 91.7% / 100.0% / 0.0% | 8/120 | 61.7% | 30 / 80 / unreached | 100 / unreached / unreached | 46/120 | 46/120 | 167.9 |
| rnnoise | 200 ms | 90.0% / 100.0% / 0.0% | 10/120 | 67.5% | 30 / 80 / unreached | 280 / unreached / unreached | 28/120 | 28/120 | 84.0 |
| speex | 0 ms | 51.7% / 100.0% / 0.0% | 58/120 | 20.0% | 50 / unreached / unreached | 380 / unreached / unreached | 28/120 | 28/120 | 80.0 |
| speex | 200 ms | 51.7% / 100.0% / 0.0% | 58/120 | 0.0% | 50 / unreached / unreached | 560 / unreached / unreached | 26/120 | 26/120 | 56.0 |

## Development-only choices

Score cutoffs use the native 0.5 point plus attainable 99%, 99.5% and 99.9% development speech-frame recall anchors. The sweep combines silence 0/32/64/100/150/200/300/500 ms, start confirmation 0/32/64 ms, and off/on ratios 1 or 0.5. Binary modes keep their native point. Durations are measured in seconds, not equated frame counts.

All selections are frozen before test scoring: one maximum source-aligned speech-coverage reference and 12 illustrative joint START/END deadline choices. The deadline choices maximize development intact-turn success; ties favor source coverage, less operational false-positive time, fewer false STARTs, fewer premature ENDs, fewer fragmented turns and stable ID. These are alternatives to inspect, not an accepted production false-positive budget. The full development Pareto front preserves latency/error tradeoffs, including recall costs.

| Detector | Frozen dev choice for START100/END300 | Dev intact success | Test intact success | Test source-aligned coverage | Test false STARTs / neg h |
|---|---|---:|---:|---:|---:|
| classic-0 | on=0.5, off=0.5, confirm=64 ms, silence=32 ms | 45.0% | 35.8% | 99.9% | 223.9 |
| classic-1 | on=0.5, off=0.5, confirm=64 ms, silence=32 ms | 45.0% | 35.8% | 99.9% | 191.9 |
| classic-2 | on=0.5, off=0.5, confirm=32 ms, silence=0 ms | 66.7% | 53.3% | 98.9% | 387.8 |
| classic-3 | on=0.5, off=0.5, confirm=0 ms, silence=64 ms | 65.8% | 53.3% | 94.0% | 443.7 |
| silero | on=0.166286, off=0.0831428, confirm=32 ms, silence=0 ms | 69.2% | 62.5% | 99.4% | 48.0 |
| silero-lite-0.3.0 | on=0.0321231, off=0.0321231, confirm=32 ms, silence=0 ms | 60.8% | 60.0% | 99.3% | 399.8 |
| silero-lite-0.4.0 | on=0.166286, off=0.0831428, confirm=32 ms, silence=0 ms | 69.2% | 62.5% | 99.4% | 48.0 |
| agc2 | on=0.5, off=0.25, confirm=0 ms, silence=150 ms | 15.0% | 27.5% | 93.3% | 319.8 |
| ten | on=0.5, off=0.5, confirm=0 ms, silence=150 ms | 49.2% | 51.7% | 99.2% | 327.8 |
| fsmn | on=0.734974, off=0.734974, confirm=0 ms, silence=64 ms | 13.3% | 3.3% | 100.0% | 299.8 |
| rnnoise | on=0.5, off=0.25, confirm=0 ms, silence=100 ms | 40.8% | 65.8% | 97.9% | 76.0 |
| speex | on=0.86, off=0.86, confirm=32 ms, silence=0 ms | 13.3% | 50.8% | 98.6% | 135.9 |

## Stop versus resume: unavoidable causal ambiguity

**The original 50–800 ms labels are inserted nonzero-support gaps, not RMS-active speech gaps.** Flite retains faint source tails before/after the nominal activity proxy. In this test, a 50 ms insertion gives 401.6–508.4 ms between RMS-active spans. Use the separately [hard-gated short-pause diagnostic](../boundary-pause-probe/FINDINGS.md) for actual 50–800 ms RMS gaps. That diagnostic freezes existing controllers and explicitly introduces artificial boundary/splice risks.

Each stop/resume pair has byte-identical PCM through the later resume sample. Across every backend, raw scores before that sample must match. Any END emitted after the stopped phrase but before the unseen continuation also cuts the paired resumed turn. No causal VAD can distinguish those histories before they diverge. Longer silence postpones that decision and reduces some cuts; it adds stop latency. This is a construction demonstration, not a claim that natural conversations have these pause probabilities.

| Detector | Added silence | Paired test histories with a stop END before the unseen resume |
|---|---:|---:|
| classic-0 | 0 ms | 27/28 |
| classic-0 | 200 ms | 16/28 |
| classic-1 | 0 ms | 27/28 |
| classic-1 | 200 ms | 16/28 |
| classic-2 | 0 ms | 28/28 |
| classic-2 | 200 ms | 23/28 |
| classic-3 | 0 ms | 21/28 |
| classic-3 | 200 ms | 26/28 |
| silero | 0 ms | 28/28 |
| silero | 200 ms | 20/28 |
| silero-lite-0.3.0 | 0 ms | 28/28 |
| silero-lite-0.3.0 | 200 ms | 23/28 |
| silero-lite-0.4.0 | 0 ms | 28/28 |
| silero-lite-0.4.0 | 200 ms | 20/28 |
| agc2 | 0 ms | 14/28 |
| agc2 | 200 ms | 21/28 |
| ten | 0 ms | 28/28 |
| ten | 200 ms | 25/28 |
| fsmn | 0 ms | 23/28 |
| fsmn | 200 ms | 12/28 |
| rnnoise | 0 ms | 28/28 |
| rnnoise | 200 ms | 25/28 |
| speex | 0 ms | 25/28 |
| speex | 200 ms | 12/28 |

Measured acoustic-proxy gap, which differs from the inserted exact-silence gap ([audit](pause-gap-audit.json)):

| Inserted support gap | Actual test RMS-activity gap min–max |
|---:|---:|
| 50 ms | 401.6–508.4 ms |
| 100 ms | 451.6–558.4 ms |
| 150 ms | 501.6–608.4 ms |
| 200 ms | 551.6–658.4 ms |
| 300 ms | 651.6–758.4 ms |
| 500 ms | 851.6–958.4 ms |
| 800 ms | 1151.6–1258.4 ms |

Pre-resume ENDs by inserted pause (each cell has four paired prefix families):

| Detector / added silence | 50 ms | 100 ms | 150 ms | 200 ms | 300 ms | 500 ms | 800 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| classic-0 / 0 ms | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| classic-0 / 200 ms | 0/4 | 1/4 | 1/4 | 2/4 | 4/4 | 4/4 | 4/4 |
| classic-1 / 0 ms | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| classic-1 / 200 ms | 0/4 | 1/4 | 1/4 | 2/4 | 4/4 | 4/4 | 4/4 |
| classic-2 / 0 ms | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| classic-2 / 200 ms | 1/4 | 2/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| classic-3 / 0 ms | 3/4 | 3/4 | 3/4 | 3/4 | 3/4 | 3/4 | 3/4 |
| classic-3 / 200 ms | 2/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| silero / 0 ms | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| silero / 200 ms | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| silero-lite-0.3.0 / 0 ms | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| silero-lite-0.3.0 / 200 ms | 0/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| silero-lite-0.4.0 / 0 ms | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| silero-lite-0.4.0 / 200 ms | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| agc2 / 0 ms | 2/4 | 2/4 | 2/4 | 2/4 | 2/4 | 2/4 | 2/4 |
| agc2 / 200 ms | 3/4 | 3/4 | 3/4 | 3/4 | 3/4 | 3/4 | 3/4 |
| ten / 0 ms | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| ten / 200 ms | 2/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| fsmn / 0 ms | 0/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| fsmn / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 |
| rnnoise / 0 ms | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| rnnoise / 200 ms | 2/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| speex / 0 ms | 2/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| speex / 200 ms | 0/4 | 0/4 | 0/4 | 1/4 | 3/4 | 4/4 | 4/4 |

The same four test prefixes are repeated at seven pause durations. Do not interpret 28 pairs as 28 independent voices or bootstrap individual variants as independent observations.

## Artifacts

- [Protocol and reproduction](../../docs/BOUNDARY_LATENCY.md)
- [Corpus construction](../../docs/BOUNDARY_DATASET.md)
- [Frozen inputs](frozen-inputs.json) and [selections](frozen-selections.json)
- [Full summary](summary.json.gz), [development sweep](development-curves.json.gz), [per-turn test outcomes](per-turn-test.json.gz)
- [Causal-pair diagnostics](causal-pairs.json), [inference verification](INFERENCE_AUDIT.json)
- [Interactive notebook](../../notebooks/explore_boundaries.py)
- [Independent methodology and code review](INDEPENDENT_REVIEW.md)

Old-corpus replay in `exploratory/` is deliberately exploratory: both former splits were already examined. It supplied diagnostics and regression coverage; it is not a fresh holdout.
