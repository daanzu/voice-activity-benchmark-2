# Silero v5.1 missing context ablation

Recorded 2026-10-03 UTC. Same model, same runtime, same streams; only the preceding waveform prefix is enabled or omitted.

**The missing-context bug materially harms this synthetic benchmark.** At the fixed 0.5 threshold, correcting it reduces missed speech from **31.36% to 7.30%** (76.7% relative reduction), non-speech false-positive frames from **2.333% to 0.345%**, and extra speech fragments from **193 to 21**. This isolates waveform context, without a model upgrade.

Under the unchanged development-only strict budget, the thresholds are 0.94 without context and 0.96 with context. Holdout missed speech falls from **77.27% to 21.38%**, while both produce two false activations in 0.566 known-negative hours. The fixed 0.5 detector still produces 70 false activations with context, so the fix alone does not meet that strict budget at 0.5.

**Scope:** 240 synthetic 20-second streams (80 minutes), with 96 development and 144 fixed holdout streams. All audio is 16 kHz. Accuracy labels are clean-source activity proxies with uncertainty excluded, not human phonetic annotations. These results do not establish real-microphone or production generalization.

## Exact experiment

| Control | Value |
|---|---|
| Model in both arms | Exact v5.1 ONNX bytes bundled in published silero-vad-lite 0.3.0 |
| Model SHA-256 | `2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f` |
| Runtime in both arms | Python ONNX Runtime 1.19.0, CPUExecutionProvider, graph optimization ALL, one intra/inter-op thread |
| Missing-context arm | 512 fresh float32 samples; no waveform prefix; recurrent state retained |
| Corrected arm | Same 512 fresh samples plus previous 64 samples; first prefix zero-filled; recurrent state retained |
| Independent stream reset | Zero recurrent state and context in both arms |
| Capture and endpoint controller | Unchanged 10 ms acquisition blocks, 32 ms native frames, common 200 ms trailing-silence rule; no hysteresis or padding |
| Manifest SHA-256 | `73b60d803250b52d2c5cdea7e3a6458a3cf6907a2c171e4610a4b0234cbed52a` |
| Trace verification | 150,000 paired frames, identical source/acquisition clocks; three runs per arm yield bitwise-identical scores |
| Corrected-arm oracle | All 150,000 scores match the prior actual 0.3.0 native-package run bit-for-bit |

The missing-context arm is an **emulation of the old input/state contract**, not execution of the old 0.2.1 wheel. No executable-stack security setting was disabled. The old native wrapper fed exactly the 32 ms window, kept its recurrent state, and had no reset API. A fresh old object is the state-reset equivalent used here. This experiment isolates missing waveform context; it does not measure accidental state leakage across streams or the reset API addition. The Python adapter updates context bookkeeping in both arms; only the ONNX input prefix changes.

Verified source references:
- [Released v0.2.1 native source](https://github.com/daanzu/py-silero-vad-lite/blob/a4222a5c2c6ca7b7fb1fbcc2af1d19374772d273/src/silero_vad_lite/silero_vad.cpp#L46-L89)
- [Released v0.3.0 corrected source](https://github.com/daanzu/py-silero-vad-lite/blob/64837cae29c0a920a679f4883f3a186d37de1f86/src/silero_vad_lite/silero_vad.cpp)
- [Official v5.1 wrapper contract](https://github.com/snakers4/silero-vad/blob/84768cefdf5a3852400e9d8237f7315d14b64a08/src/silero_vad/utils_vad.py#L46-L95)
- [v0.3.0 reference fixture and model hash](https://github.com/daanzu/py-silero-vad-lite/blob/64837cae29c0a920a679f4883f3a186d37de1f86/tests/generate_context_fixture.py)

Both released tags contain the same model Git blob `b3e3a900c0d70e67b5e2b90a33ad856ee7947930` (2,327,524 bytes). The run metadata names pre-fix commit `216ba7a62f1382b5973d4510637503d8a8a0e490`; its old C++/Python source is byte-identical to released v0.2.1. The exact released tag is recorded in summary.json and the independent review.

## Accuracy on the fixed holdout

Generic speech includes foreground and background voices. The holdout contains 240 merged reference events, 605.31 seconds of labeled speech and 2,037.95 seconds (0.5661 hours) of known non-speech. Another 236.74 seconds are excluded as uncertain or uncovered.

| Protocol | Context | Threshold | Missed speech % | Non-speech FP % | False events | False events / negative hour | Event recall % | Extra fragments |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Fixed | disabled | 0.50 | 31.36 | 2.3327 | 123 | 217.28 | 96.25 | 193 |
| Fixed | enabled | 0.50 | 7.30 | 0.3450 | 70 | 123.65 | 97.50 | 21 |
| Dev-calibrated | disabled | 0.94 | 77.27 | 0.0093 | 2 | 3.53 | 66.25 | 227 |
| Dev-calibrated | enabled | 0.96 | 21.38 | 0.0088 | 2 | 3.53 | 87.92 | 22 |

The unchanged calibration grid minimizes development missed speech subject to at most five false activation events per known-negative hour and at most 1% false-positive frames. Thresholds are selected separately for each arm on the same 96 development streams, then frozen. Both chosen thresholds have one development false activation; development misses are 64.33% without context and 27.51% with context. The grid and every development result are retained in development-curves.json. No threshold is selected from holdout.

The fixed 0.5 comparison is the clean same-threshold effect. The dev-calibrated comparison includes the different optimal thresholds under the same rule. Cross-applying each selected threshold confirms that the gain is not only a threshold artifact:

| Shared threshold | Missing-context miss % | Corrected miss % | Missing / corrected false events |
|---|---:|---:|---:|
| 0.94 | 77.27 | 18.95 | 2 / 4 |
| 0.96 | 83.07 | 21.38 | 0 / 2 |

## Paired uncertainty

All deltas below are corrected minus missing context. Intervals are the 2.5th/97.5th percentiles of 5,000 paired whole-stream bootstrap resamples, keeping the 12 conditions and their sample counts fixed. The same resampled stream IDs are used in both arms; thresholds remain frozen. These are descriptive within-corpus intervals: repeated TTS voices/texts violate population independence, and development calibration uncertainty is not included.

| Protocol | Metric | Change | Descriptive paired 95% interval |
|---|---|---:|---:|
| Fixed 0.5 | Missed speech, percentage points | -24.060 | -29.195 to -18.662 |
| Fixed 0.5 | False-positive frames, percentage points | -1.988 | -2.966 to -1.076 |
| Fixed 0.5 | False events per negative hour | -93.623 | -144.285 to -44.082 |
| Fixed 0.5 | Event recall, percentage points | 1.250 | -0.417 to 2.917 |
| Fixed 0.5 | Extra fragments per reference | -0.717 | -0.896 to -0.533 |
| Dev-calibrated | Missed speech, percentage points | -55.892 | -61.066 to -50.383 |
| Dev-calibrated | False-positive frames, percentage points | -0.000 | -0.019 to 0.018 |
| Dev-calibrated | False events per negative hour | 0.000 | -7.059 to 7.072 |
| Dev-calibrated | Event recall, percentage points | 21.667 | 16.250 to 27.083 |
| Dev-calibrated | Extra fragments per reference | -0.854 | -1.067 to -0.646 |

At fixed 0.5, the event-recall change is small and its interval includes zero, even though speech-frame misses and fragmentation improve strongly. At the calibrated operating points both arms have two false events: the descriptive Poisson 95% rate interval is 0.43–12.76 events per negative hour. Observing 3.53/hour here does not establish a production five/hour guarantee.

## Onset and end timing

Times below are relative to synthetic clean-source proxy boundaries and use simulated input acquisition time, excluding compute scheduling. Quantiles include matched events only; missed events and different matching populations can bias the comparison. The one-to-one maximum-overlap greedy matcher is unchanged.

| Protocol | Context | Matched events | Onset notification p50 / p95 ms | End notification p50 / p95 ms | Onset clipping p95 ms | End clipping p95 ms | Premature end % |
|---|---|---:|---:|---:|---:|---:|---:|
| Fixed 0.5 | disabled | 231 | 140 / 2360 | 210 / 325 | 2324 | 2950 | 25.54 |
| Fixed 0.5 | enabled | 234 | 70 / 317 | 290 / 477 | 285 | 62 | 3.42 |
| Dev-calibrated | disabled | 159 | 290 / 3453 | -550 / 220 | 3417 | 4448 | 64.78 |
| Dev-calibrated | enabled | 211 | 200 / 605 | 210 / 300 | 570 | 1797 | 9.48 |

Corrected end notifications can be later because the detector stops cutting speech off early. At fixed 0.5, premature notifications fall from 25.54% to 3.42% and p95 end clipping falls from 2,950 ms to 62 ms; a shorter signed end delay would not by itself be an improvement. At the strict threshold, missing context yields a negative median end notification (550 ms before the true proxy end) and 64.78% premature ends.

For a paired reference-event check, 230 reference events are matched in both arms at fixed 0.5: the median per-event onset notification change is -40 ms and end notification change is +70 ms. At the calibrated points, 153 are matched in both: median onset change -30 ms, end change +760 ms. Full distributions and unmatched-side counts are in summary.json. No EOF-forced event is included in end-delay quantiles.

## Results by condition

Each condition has 12 holdout streams (four minutes). `n/a` means the condition has no speech references or no matched event; it is not zero. Music conditions use synthetic music-like tones rather than recordings. Every speech-bearing condition has fewer missed speech frames with corrected context at fixed 0.5. Corrected fixed-threshold false activations remain concentrated in music-like conditions (41 music-only, 29 speech-plus-music).

### Fixed threshold 0.5

| Condition | Context | Miss % | FP % | False events | Recall % | Extra fragments | Onset p95 ms | End p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| background_only | disabled | 23.69 | 0.000 | 0 | 100.00 | 24 | 1720 | 249 |
| background_only | enabled | 1.36 | 0.000 | 0 | 100.00 | 0 | 175 | 299 |
| background_overlap | disabled | 28.48 | 0.155 | 0 | 100.00 | 42 | 4184 | 300 |
| background_overlap | enabled | 0.25 | 0.000 | 0 | 100.00 | 0 | 90 | 299 |
| clean_long | disabled | 29.73 | 0.000 | 0 | 100.00 | 33 | 2853 | 277 |
| clean_long | enabled | 1.19 | 0.000 | 0 | 100.00 | 1 | 339 | 417 |
| clean_short | disabled | 34.32 | 0.000 | 0 | 93.75 | 1 | 360 | 310 |
| clean_short | enabled | 11.48 | 0.000 | 0 | 100.00 | 0 | 166 | 560 |
| fan_only | disabled | n/a | 0.137 | 3 | n/a | 0 | n/a | n/a |
| fan_only | enabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| fan_speech | disabled | 52.20 | 0.129 | 3 | 79.17 | 26 | 2708 | 271 |
| fan_speech | enabled | 29.15 | 0.081 | 0 | 75.00 | 10 | 1449 | 439 |
| music_only | disabled | n/a | 5.133 | 66 | n/a | 0 | n/a | n/a |
| music_only | enabled | n/a | 1.654 | 41 | n/a | 0 | n/a | n/a |
| music_speech | disabled | 21.63 | 27.899 | 51 | 100.00 | 26 | 2166 | 2102 |
| music_speech | enabled | 9.34 | 2.387 | 29 | 100.00 | 8 | 564 | 584 |
| quiet | disabled | 22.39 | 0.000 | 0 | 97.92 | 0 | 187 | 327 |
| quiet | enabled | 11.71 | 0.000 | 0 | 100.00 | 1 | 183 | 413 |
| silence | disabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| silence | enabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| typing_only | disabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| typing_only | enabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| typing_speech | disabled | 35.04 | 0.000 | 0 | 100.00 | 41 | 2207 | 285 |
| typing_speech | enabled | 2.26 | 0.000 | 0 | 100.00 | 1 | 286 | 462 |

### Development calibrated thresholds

| Condition | Context | Miss % | FP % | False events | Recall % | Extra fragments | Onset p95 ms | End p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| background_only | disabled | 68.86 | 0.000 | 0 | 83.33 | 30 | 1758 | -246 |
| background_only | enabled | 7.83 | 0.000 | 0 | 100.00 | 0 | 340 | 250 |
| background_overlap | disabled | 75.18 | 0.000 | 0 | 83.33 | 40 | 5499 | 88 |
| background_overlap | enabled | 6.48 | 0.000 | 0 | 100.00 | 4 | 448 | 250 |
| clean_long | disabled | 78.76 | 0.000 | 0 | 87.50 | 39 | 3220 | 130 |
| clean_long | enabled | 7.04 | 0.000 | 0 | 100.00 | 0 | 570 | 327 |
| clean_short | disabled | 86.36 | 0.000 | 0 | 37.50 | 0 | 306 | 186 |
| clean_short | enabled | 48.77 | 0.000 | 0 | 83.33 | 0 | 442 | 501 |
| fan_only | disabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| fan_only | enabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| fan_speech | disabled | 79.20 | 0.000 | 0 | 50.00 | 37 | 2095 | -184 |
| fan_speech | enabled | 53.32 | 0.000 | 0 | 54.17 | 0 | 776 | 260 |
| music_only | disabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| music_only | enabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| music_speech | disabled | 83.37 | 0.153 | 2 | 75.00 | 40 | 3282 | 89 |
| music_speech | enabled | 25.87 | 0.145 | 2 | 91.67 | 8 | 1583 | 328 |
| quiet | disabled | 65.59 | 0.000 | 0 | 64.58 | 1 | 435 | 245 |
| quiet | enabled | 58.82 | 0.000 | 0 | 83.33 | 0 | 543 | 261 |
| silence | disabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| silence | enabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| typing_only | disabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| typing_only | enabled | n/a | 0.000 | 0 | n/a | 0 | n/a | n/a |
| typing_speech | disabled | 79.83 | 0.000 | 0 | 79.17 | 40 | 3539 | 84 |
| typing_speech | enabled | 15.54 | 0.000 | 0 | 100.00 | 10 | 1068 | 238 |

## Runtime cost

Three complete 80-minute corpus passes per arm were measured in fresh sequential processes after ten warmup frames, in order disabled/enabled, enabled/disabled, disabled/enabled. All three passes are retained; no best-run selection. CPU affinity/frequency was uncontrolled on a shared Intel Xeon Platinum 8573C host. WAV reading and resets are outside streaming timing; buffering, dispatch, conversion, inference, and context bookkeeping are inside. This measures the same Python runtime path in both arms, not the old-versus-new native wheel speed.

| Context | Wall seconds per 80 min, median [range] | Wall RTF, median [range] | CPU RTF median | Adapter inference RTF median | Peak process MiB range |
|---|---:|---:|---:|---:|---:|
| disabled | 25.50 [25.44–26.59] | 0.005312 [0.005299–0.005539] | 0.005311 | 0.004215 | 134.9–138.9 |
| enabled | 26.55 [26.19–31.25] | 0.005530 [0.005455–0.006510] | 0.005527 | 0.004381 | 136.6–137.8 |

The corrected arm has 4.1% higher median wall RTF in these runs; its per-pass overhead ranges from -0.16% to +22.86% when paired by pass. The broad shared-host variability prevents a precise overhead claim. Both median CPU RTFs are roughly 0.005–0.006, meaning roughly 5–6 ms of CPU time per second of audio under this benchmark. Real-time deployment utilization and device scheduling costs were not measured. Peak RSS includes Python/runtime and retained traces, not just model RAM. A 64-sample prefix is past audio and introduces no extra future-audio wait.

## Limits and validation

- Main accuracy and throughput use 16 kHz only. Contract tests cover 8 kHz shapes (256 fresh + 32 context); no 8 kHz corpus accuracy result is claimed.
- Synthetic fan, typing, music-like tones, TTS voices, echo and filtering cover specific constructed conditions. Only two held-out TTS voices and repeated within-split texts are present. No human voice, real room, microphone or phonetic annotation was evaluated.
- The corpus/split and calibration grid are inherited unchanged. This ablation was requested after prior model-comparison results were observed; it is not a preregistered or blind study.
- A matched event needs positive overlap, not complete utterance capture. A detector can therefore have high event recall while missing much of each utterance. Inspect miss fraction, fragmentation and clipping together.
- The false-event metric counts unmatched segments with known-negative support. Overlapping extra fragments are tracked separately. Non-speech false-positive frames prevent long activations from hiding behind low event counts.
- The known-negative exposure is short, and bootstrap resampling does not estimate between-speaker, between-engine, natural-audio or threshold-selection uncertainty. Timing repeats capture this host only.
- Full contract, arithmetic, result and inherited tests were run; see tests.log and INDEPENDENT_REVIEW.md. The unrelated TEN integration test requires its separately licensed runtime and is skipped in this run.

## Reproduce and inspect

Start from repository commit `a0f9e600dfdba202d9d960ea4679f3eed7a37328` plus the supplied source changes. Follow the existing setup to install pinned 0.3.0 assets and generate or reuse the exact corpus. No old native wheel is needed.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run --manifest data/synthetic/manifest.json --output results/context-ablation/raw/pass1 --backends context-disabled context-enabled
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run --manifest data/synthetic/manifest.json --output results/context-ablation/raw/pass2 --backends context-enabled context-disabled
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run --manifest data/synthetic/manifest.json --output results/context-ablation/raw/pass3 --backends context-disabled context-enabled
python scripts/report_context_ablation.py --native-raw results/silero-lite-comparison/raw/silero-lite-0.3.0.npz
python scripts/write_context_report.py
python -m unittest discover -s tests -v
```

The optional `--native-raw` oracle points at a completed actual native 0.3.0 package trace. `summary.json` contains both protocols, all condition scores, descriptive uncertainty, paired-reference timing, cross-threshold checks and performance. `per-stream-holdout.json` and `development-curves.json` support independent re-analysis. `runs.json` and raw per-pass metadata retain environment, code/model/audio hashes and stream timings; compressed traces remain local generated assets. The exact manifest is copied to `dataset-manifest.json`. Historical benchmark results are unchanged.

**Conclusion:** keep the corrected waveform context. On this controlled v5.1 test it substantially reduces missed speech, false positives, fragmentation and premature endpointing. Validate the intended thresholds on representative real recordings before drawing production conclusions.
