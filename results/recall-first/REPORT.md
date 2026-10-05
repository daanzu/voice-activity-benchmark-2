# Recall-first streaming VAD tradeoffs

**Fresh October 5, 2026 reconstruction. Synthetic source-activity labels, not human phonetic ground truth or a production guarantee.**

This experiment asks how much non-speech time becomes active when speech-frame recall takes priority. It extends the development display sweep from the historical minimum 0.05 down to 1e-12, targets 99%, 99.5%, and 99.9% development speech-frame recall, and separately meets or exceeds the native development recall of classic WebRTC modes 0–3.

All twelve detector configurations were rerun on the byte-identical original 240-stream, 80-minute corpus. The 96 development streams and 144 holdout streams, source WAVs, mixture WAVs, labels, and full manifest are unchanged. Historical results remain untouched. The prior October 4 work was not recoverable; the figures below come exclusively from the retained October 5 scores.

## What was selected

- Only known development speech-frame scores determine the threshold. The highest strictly-positive cutoff meeting the exact required speech-frame count minimizes false-positive frame duration over all positive cutoffs, without a coarse-grid approximation. Equal-score ties stay together; the highest feasible cutoff breaks equal-FP choices with the smallest recall overshoot. The exact rational target avoids rounding errors at classic-mode parity.
- All 84 backend/target choices are written to frozen-thresholds.json before any holdout evaluation. Thresholds are then reused unchanged on holdout. A development target is not a holdout guarantee; the achieved holdout recall is always shown.
- Classic modes return binary scores: their only operational point is the native 0.5 threshold. A mode missing a target is explicitly unattainable, without converting its negative decisions to speech.
- Probability scores equal to zero cannot become positive under a strictly-positive cutoff. Targets requiring those zero-score speech frames are also unattainable. Threshold 0 is reported only as an always-positive diagnostic, never as an operational target solution.
- The optimized false-positive measure is known non-speech frame duration. False activation events and their rate are separate outputs, not a selection constraint. A longer merged activation can reduce event counts while increasing false-positive duration.
- Recall means raw aligned speech-frame recall, not event detection, captured/prerolled audio, or ASR transcript recall. The shared 200 ms endpoint controller remains unchanged.

## Fixed recall targets

### 99% speech-frame recall on development

| Backend | Positive threshold | Dev recall % | Holdout recall % | Holdout FP % | FP seconds | False events | Events / negative hour |
|---|---:|---:|---:|---:|---:|---:|---:|
| classic-0 | 0.5 | 99.879 | 99.993 | 42.611 | 868.40 | 399 | 704.826 |
| classic-1 | 0.5 | 99.844 | 99.979 | 41.657 | 848.94 | 397 | 701.293 |
| classic-2 | 0.5 | 99.650 | 99.863 | 39.268 | 800.26 | 486 | 858.510 |
| classic-3 | unattainable | max 97.515 | n/a | n/a | n/a | n/a | n/a |
| silero | 0.001703977585 | 99.002 | 97.454 | 31.081 | 633.42 | 572 | 1010.427 |
| silero-lite-0.3.0 | 0.004530906677 | 99.002 | 97.310 | 11.761 | 239.69 | 781 | 1379.622 |
| silero-lite-0.4.0 | 0.001703977585 | 99.002 | 97.454 | 31.081 | 633.42 | 572 | 1010.427 |
| agc2 | 0.01635152102 | 99.002 | 99.399 | 30.666 | 624.96 | 618 | 1091.685 |
| ten | 0.07352694124 | 99.005 | 99.334 | 99.454 | 2026.83 | 52 | 91.857 |
| fsmn | 0.1424005032 | 99.002 | 98.094 | 78.457 | 1594.39 | 473 | 837.914 |
| rnnoise | 0.05385382101 | 99.002 | 99.866 | 17.063 | 347.74 | 689 | 1217.105 |
| speex | 0.47 | 99.040 | 98.764 | 33.605 | 684.85 | 210 | 370.961 |

### 99.5% speech-frame recall on development

| Backend | Positive threshold | Dev recall % | Holdout recall % | Holdout FP % | FP seconds | False events | Events / negative hour |
|---|---:|---:|---:|---:|---:|---:|---:|
| classic-0 | 0.5 | 99.879 | 99.993 | 42.611 | 868.40 | 399 | 704.826 |
| classic-1 | 0.5 | 99.844 | 99.979 | 41.657 | 848.94 | 397 | 701.293 |
| classic-2 | 0.5 | 99.650 | 99.863 | 39.268 | 800.26 | 486 | 858.510 |
| classic-3 | unattainable | max 97.515 | n/a | n/a | n/a | n/a | n/a |
| silero | 0.0007891654968 | 99.505 | 97.854 | 51.962 | 1058.96 | 448 | 791.383 |
| silero-lite-0.3.0 | 0.002930372953 | 99.508 | 97.818 | 20.069 | 408.99 | 761 | 1344.292 |
| silero-lite-0.4.0 | 0.0007891654968 | 99.505 | 97.854 | 51.962 | 1058.96 | 448 | 791.383 |
| agc2 | 0.006677865982 | 99.503 | 99.749 | 35.288 | 719.15 | 557 | 983.930 |
| ten | 0.06628075242 | 99.503 | 99.741 | 99.870 | 2035.30 | 48 | 84.791 |
| fsmn | 0.1212406158 | 99.503 | 98.708 | 88.559 | 1799.68 | 192 | 340.126 |
| rnnoise | 0.01415067352 | 99.503 | 99.949 | 19.877 | 405.08 | 975 | 1722.319 |
| speex | 0.42 | 99.583 | 99.252 | 34.865 | 710.53 | 305 | 538.777 |

### 99.9% speech-frame recall on development

| Backend | Positive threshold | Dev recall % | Holdout recall % | Holdout FP % | FP seconds | False events | Events / negative hour |
|---|---:|---:|---:|---:|---:|---:|---:|
| classic-0 | unattainable | max 99.879 | n/a | n/a | n/a | n/a | n/a |
| classic-1 | unattainable | max 99.844 | n/a | n/a | n/a | n/a | n/a |
| classic-2 | unattainable | max 99.650 | n/a | n/a | n/a | n/a | n/a |
| classic-3 | unattainable | max 97.515 | n/a | n/a | n/a | n/a | n/a |
| silero | 0.0003534555435 | 99.901 | 98.379 | 63.897 | 1302.18 | 419 | 740.156 |
| silero-lite-0.3.0 | 0.0006277263165 | 99.906 | 99.746 | 47.441 | 966.83 | 611 | 1079.320 |
| silero-lite-0.4.0 | 0.0003534555435 | 99.901 | 98.379 | 63.897 | 1302.18 | 419 | 740.156 |
| agc2 | 0.002131462097 | 99.901 | 99.977 | 39.129 | 797.42 | 498 | 879.708 |
| ten | 0.05629726499 | 99.903 | 99.970 | 99.983 | 2037.61 | 48 | 84.791 |
| fsmn | 0.09461200237 | 99.901 | 99.628 | 96.604 | 1963.17 | 72 | 127.547 |
| rnnoise | 0.001746727503 | 99.903 | 99.987 | 32.308 | 658.42 | 745 | 1316.028 |
| speex | 0.34 | 99.925 | 99.884 | 44.342 | 903.67 | 340 | 600.604 |

## Classic-mode parity targets

The target is each classic mode’s development recall. Every candidate is frozen on development, so holdout rows can exceed or miss the classic mode’s holdout recall. Compare the actual held-out recall and FP duration together; these are not holdout-tuned equal-recall estimates.

### Match classic-0

Native reference: dev recall **99.878990%**; holdout recall **99.993392%**, FP **42.611%** (868.40 seconds), **399** false events (704.826/negative hour).

| Backend | Positive threshold | Dev recall % | Holdout recall % | Holdout FP % | FP seconds | False events | Events / negative hour |
|---|---:|---:|---:|---:|---:|---:|---:|
| classic-0 | 0.5 | 99.879 | 99.993 | 42.611 | 868.40 | 399 | 704.826 |
| classic-1 | unattainable | max 99.844 | n/a | n/a | n/a | n/a | n/a |
| classic-2 | unattainable | max 99.650 | n/a | n/a | n/a | n/a | n/a |
| classic-3 | unattainable | max 97.515 | n/a | n/a | n/a | n/a | n/a |
| silero | 0.000397413969 | 99.882 | 98.326 | 62.078 | 1265.11 | 425 | 750.754 |
| silero-lite-0.3.0 | 0.0006382763386 | 99.890 | 99.737 | 47.271 | 963.35 | 610 | 1077.553 |
| silero-lite-0.4.0 | 0.000397413969 | 99.882 | 98.326 | 62.078 | 1265.11 | 425 | 750.754 |
| agc2 | 0.002380430698 | 99.879 | 99.955 | 38.930 | 793.37 | 505 | 892.073 |
| ten | 0.05824851245 | 99.879 | 99.941 | 99.974 | 2037.41 | 48 | 84.791 |
| fsmn | 0.09685051441 | 99.879 | 99.569 | 96.117 | 1953.27 | 78 | 138.176 |
| rnnoise | 0.001929005142 | 99.882 | 99.985 | 31.771 | 647.48 | 757 | 1337.226 |
| speex | 0.36 | 99.884 | 99.790 | 41.028 | 836.12 | 403 | 711.892 |

### Match classic-1

Native reference: dev recall **99.844032%**; holdout recall **99.978523%**, FP **41.657%** (848.94 seconds), **397** false events (701.293/negative hour).

| Backend | Positive threshold | Dev recall % | Holdout recall % | Holdout FP % | FP seconds | False events | Events / negative hour |
|---|---:|---:|---:|---:|---:|---:|---:|
| classic-0 | 0.5 | 99.879 | 99.993 | 42.611 | 868.40 | 399 | 704.826 |
| classic-1 | 0.5 | 99.844 | 99.979 | 41.657 | 848.94 | 397 | 701.293 |
| classic-2 | unattainable | max 99.650 | n/a | n/a | n/a | n/a | n/a |
| classic-3 | unattainable | max 97.515 | n/a | n/a | n/a | n/a | n/a |
| silero | 0.0004170536995 | 99.844 | 98.308 | 61.351 | 1250.30 | 422 | 745.455 |
| silero-lite-0.3.0 | 0.001044839621 | 99.844 | 99.328 | 42.798 | 872.20 | 617 | 1089.919 |
| silero-lite-0.4.0 | 0.0004170536995 | 99.844 | 98.308 | 61.351 | 1250.30 | 422 | 745.455 |
| agc2 | 0.002842783928 | 99.844 | 99.937 | 38.509 | 784.79 | 518 | 915.037 |
| ten | 0.05918914825 | 99.844 | 99.936 | 99.970 | 2037.34 | 48 | 84.791 |
| fsmn | 0.09895819426 | 99.844 | 99.511 | 95.609 | 1942.95 | 84 | 148.805 |
| rnnoise | 0.002430857625 | 99.844 | 99.983 | 30.353 | 618.57 | 810 | 1430.850 |
| speex | 0.37 | 99.844 | 99.699 | 39.437 | 803.70 | 419 | 740.156 |

### Match classic-2

Native reference: dev recall **99.650415%**; holdout recall **99.862880%**, FP **39.268%** (800.26 seconds), **486** false events (858.510/negative hour).

| Backend | Positive threshold | Dev recall % | Holdout recall % | Holdout FP % | FP seconds | False events | Events / negative hour |
|---|---:|---:|---:|---:|---:|---:|---:|
| classic-0 | 0.5 | 99.879 | 99.993 | 42.611 | 868.40 | 399 | 704.826 |
| classic-1 | 0.5 | 99.844 | 99.979 | 41.657 | 848.94 | 397 | 701.293 |
| classic-2 | 0.5 | 99.650 | 99.863 | 39.268 | 800.26 | 486 | 858.510 |
| classic-3 | unattainable | max 97.515 | n/a | n/a | n/a | n/a | n/a |
| silero | 0.0006398260593 | 99.653 | 98.009 | 55.023 | 1121.34 | 440 | 777.252 |
| silero-lite-0.3.0 | 0.002318143845 | 99.653 | 98.203 | 25.744 | 524.64 | 643 | 1135.847 |
| silero-lite-0.4.0 | 0.0006398260593 | 99.653 | 98.009 | 55.023 | 1121.34 | 440 | 777.252 |
| agc2 | 0.004564613104 | 99.650 | 99.848 | 36.980 | 753.64 | 546 | 964.499 |
| ten | 0.06411926448 | 99.650 | 99.805 | 99.912 | 2036.15 | 48 | 84.791 |
| fsmn | 0.1143981218 | 99.650 | 98.961 | 91.094 | 1851.20 | 149 | 263.952 |
| rnnoise | 0.008788046427 | 99.650 | 99.962 | 22.527 | 459.09 | 1011 | 1785.912 |
| speex | 0.4 | 99.710 | 99.473 | 36.059 | 734.86 | 363 | 641.233 |

### Match classic-3

Native reference: dev recall **97.515261%**; holdout recall **96.989972%**, FP **34.622%** (705.57 seconds), **608** false events (1074.020/negative hour).

| Backend | Positive threshold | Dev recall % | Holdout recall % | Holdout FP % | FP seconds | False events | Events / negative hour |
|---|---:|---:|---:|---:|---:|---:|---:|
| classic-0 | 0.5 | 99.879 | 99.993 | 42.611 | 868.40 | 399 | 704.826 |
| classic-1 | 0.5 | 99.844 | 99.979 | 41.657 | 848.94 | 397 | 701.293 |
| classic-2 | 0.5 | 99.650 | 99.863 | 39.268 | 800.26 | 486 | 858.510 |
| classic-3 | 0.5 | 97.515 | 96.990 | 34.622 | 705.57 | 608 | 1074.020 |
| silero | 0.02644973993 | 97.518 | 96.522 | 1.374 | 28.00 | 180 | 317.967 |
| silero-lite-0.3.0 | 0.01408693194 | 97.515 | 96.587 | 4.474 | 91.18 | 516 | 911.504 |
| silero-lite-0.4.0 | 0.02644973993 | 97.518 | 96.522 | 1.374 | 28.00 | 180 | 317.967 |
| agc2 | 0.05954703689 | 97.515 | 97.545 | 24.026 | 489.63 | 870 | 1536.838 |
| ten | 0.0903788507 | 97.518 | 98.117 | 93.737 | 1910.32 | 182 | 321.500 |
| fsmn | 0.2376139164 | 97.515 | 97.010 | 24.681 | 501.56 | 1057 | 1872.463 |
| rnnoise | 0.2643046677 | 97.515 | 99.643 | 10.440 | 212.77 | 313 | 552.909 |
| speex | 0.6 | 97.558 | 97.857 | 32.590 | 664.16 | 190 | 335.631 |

## Specific tradeoffs in this rerun

- Direct Silero at 99% development target: holdout recall 97.454%, FP duration 31.081%, 572 false events
- Direct Silero at 99.5% development target: holdout recall 97.854%, FP duration 51.962%, 448 false events
- Direct Silero at 99.9% development target: holdout recall 98.379%, FP duration 63.897%, 419 false events
- RNNoise at the classic-0 development recall target: holdout recall 99.985132% versus classic-0 99.993392%; FP duration 31.771% versus 42.611%; false events 757 versus 399. Duration and event count measure different costs; this is not a single-metric winner claim

## Always-positive diagnostic (excluded from selection)

| Backend | Holdout raw speech-frame recall % | Holdout FP % | Event recall % | False events | Forced EOF events |
|---|---:|---:|---:|---:|---:|
| classic-0 | 100.000 | 100.000 | 40.000 | 48 | 96 |
| classic-1 | 100.000 | 100.000 | 40.000 | 48 | 96 |
| classic-2 | 100.000 | 100.000 | 40.000 | 48 | 96 |
| classic-3 | 100.000 | 100.000 | 40.000 | 48 | 96 |
| silero | 100.000 | 100.000 | 40.000 | 48 | 96 |
| silero-lite-0.3.0 | 100.000 | 100.000 | 40.000 | 48 | 96 |
| silero-lite-0.4.0 | 100.000 | 100.000 | 40.000 | 48 | 96 |
| agc2 | 100.000 | 100.000 | 40.000 | 48 | 96 |
| ten | 100.000 | 100.000 | 40.000 | 48 | 96 |
| fsmn | 100.000 | 100.000 | 40.000 | 48 | 96 |
| rnnoise | 100.000 | 100.000 | 40.000 | 48 | 96 |
| speex | 100.000 | 100.000 | 40.000 | 48 | 96 |

A positive score floor can also produce an all-positive operating point at a positive threshold (for example, a score floor of 0.1); such a point remains feasible but its 100% FP duration is a degenerate tradeoff, not useful discrimination. Threshold 0 labels every covered frame positive. It can merge multiple reference utterances into one detection, so the one-to-one event recall is not necessarily 100%, and apparent false-event rates do not capture its continuous false-positive duration. EOF-forced endings are excluded from endpoint-delay statistics.

## Reproducibility and host effects

Manifest SHA-256: `73b60d803250b52d2c5cdea7e3a6458a3cf6907a2c171e4610a4b0234cbed52a`. Raw trace checksums, exact thresholds, every development curve point, split metrics, native source/model/package hashes, and run metadata are retained next to this report. Generated WAVs and native/model dependencies stay private/regenerable; no third-party binaries are redistributed.

Current measured CPU: **AMD EPYC 9V74 80-Core Processor**. The historical published-package comparison used Intel Xeon Platinum 8573C. Native binaries compiled with host-specific flags can differ, and probability outputs may drift with runtime/build/hardware. Therefore this new run has its own results directory and provenance; older recorded values are not overwritten or silently combined.

Fixed-reference metrics from this run are compared with the historical comparison in historical-reference-deltas.json. These checks can reveal aggregate differences but cannot establish bitwise score identity when historical raw scores are unavailable.

## Limits

- Four synthetic English TTS voices, with two per split and repeated texts within split, share one Flite engine. The fixed holdout is not evidence of real-microphone or human-speech generalization
- Labels are clean-source activity proxies; uncertain activity collars, internal pauses and reverberation tails are excluded. Generic speech includes background voices
- Different native frame coverage can give slightly different positive/negative denominators. All confusion counts and exposure times are retained rather than assuming identical denominators
- Native frame size/state, causal resampling, score alignment, model provenance and shared endpointing are inherited unchanged. Unknown native score alignment remains uncalibrated
- FP rate here means FP / (FP + TN) over known-negative frames, not false discoveries among positive predictions. FP seconds and event counts are both reported
- False-event rates have limited known-negative exposure and are descriptive, not an assurance of a production rate. Retained Poisson intervals do not model repeated-voice or condition dependence
- The study follows prior observed benchmark results and is not preregistered or blind. Threshold selection uses development only; no claim is made that tuning or repeated analysis was unseen
- Runtime measurements are one shared-host pass with no CPU affinity/frequency control. They are retained for provenance, not a controlled speed comparison with previous hosts
- No new endpoint latency, preroll, ASR, noise corpus, or device-latency study is included

## Reproduce

See [setup and protocol](../../docs/RECALL_FIRST.md). [Independent review](INDEPENDENT_REVIEW.md) and [validation](VALIDATION.md) record checks against the final artifacts.
