# Synthetic streaming benchmark results

**Synthetic-domain experiment, not real-microphone accuracy or human phonetic ground truth.**

240 streams, 1.33 hours; 96 development and 144 fixed holdout streams. Four synthesis voices are split between dev/test. The same synthesis engine is shared, so this is not cross-engine generalization.

Labels come from known source placement plus clean-signal activity proxies, with uncertainty excluded. Generic speech includes background voices. A foreground-only diagnostic is separately reported and is not a fair expectation for speaker-agnostic VAD. See [dataset methodology](../../docs/DATASET.md).

## Frozen operating point

Thresholds and classic aggressiveness are selected only on development data: minimize missed speech subject to at most 5 unmatched activations per negative-audio hour AND at most 1% non-speech frame false positives. The shared grid is dense in the high-probability tail (0.99 through 0.9999 in 0.0001 steps), includes finer near-one values and a never-positive threshold. Its exact values are in summary.json. A source/metrics audit identified that the initial coarse grid skipped feasible development points; this common dev-only grid corrects that issue without selecting thresholds from holdout. This can select an unusable all-miss detector; no feasible useful operating point is a result, not a reason to retune on holdout. Constraints need not transfer to holdout.

| Backend | Threshold | Holdout miss % | Holdout false-positive % | False events/negative hour | Event recall % | Extra fragments |
|---|---:|---:|---:|---:|---:|---:|
| agc2 | 0.999 | 57.516 | 0.003 | 3.533 | 93.333 | 475 |
| classic-0 | 1.001 | 100.000 | 0.000 | 0.000 | 0.000 | 0 |
| fsmn | 0.9981 | 87.587 | 0.003 | 1.771 | 87.500 | 528 |
| rnnoise | 0.9989 | 44.040 | 0.000 | 1.766 | 97.083 | 327 |
| silero-lite-0.3.0 | 0.96 | 21.376 | 0.009 | 3.533 | 87.917 | 22 |
| silero-lite-0.4.0 | 0.8 | 6.463 | 0.004 | 3.533 | 97.500 | 3 |
| silero | 0.8 | 6.463 | 0.004 | 3.533 | 97.500 | 3 |
| speex | 0.9901 | 100.000 | 0.000 | 0.000 | 0.000 | 0 |
| ten | 0.9 | 31.856 | 0.002 | 0.000 | 95.000 | 128 |

## Published Silero packages

The two lite rows execute the actual pinned PyPI CPython 3.12 Linux x86-64 wheels through their public `SileroVAD.process` API. Each version is installed in a separate private target and loaded in a fresh process; neither model is substituted into the direct-ONNX baseline. Context and recurrent state are managed by the package, and the common runner resets each independent stream.

Both 0.3.0 and 0.4.0 already have the corrected 4 ms waveform context and reset behavior. This is **not** a context-fix accuracy experiment. Their native library is byte-identical on the tested platform; the bundled model changes from v5.1 to v6.2 (upstream v6.2.3 release). The 0.4.0 model is byte-identical to the existing direct-ONNX `silero` baseline. Thus 0.3.0 versus 0.4.0 compares the weight/model update, while 0.4.0 versus `silero` compares native wrapper/runtime execution of the same model.

| Package row | Upstream model | Model SHA-256 | Native library SHA-256 |
|---|---|---|---|
| silero-lite-0.3.0 | Silero VAD v5.1 | `2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f` | `0e65d68994ce43439ac1aecd564e3a6ba3f71135c4b77248440e1d3c123d9cf9` |
| silero-lite-0.4.0 | Silero VAD v6.2.3 (v6.2 streaming weights) | `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3` | `0e65d68994ce43439ac1aecd564e3a6ba3f71135c4b77248440e1d3c123d9cf9` |

Paired scores use identical waveform streams, frame clocks, resets, and acquisition timestamps. Model equivalence alone does not imply bitwise runtime equivalence; observed differences are recorded below.

| Pair | Frames | Max absolute score difference | Mean absolute difference | Scores differing by >1e-6 |
|---|---:|---:|---:|---:|
| silero / silero-lite-0.4.0 | 150000 | 0 | 0 | 0 |
| silero-lite-0.3.0 / silero-lite-0.4.0 | 150000 | 0.970263243 | 0.0241015713 | 149873 |

Full wheel URL/hash, package version, model/native-library hashes, runtime and source provenance are retained in `summary.json` and `runs.json`. See [setup and provenance](../../docs/SILERO_LITE.md). Timings include the package API and adapter conversion/validation overhead; they do not isolate ONNX kernels. Startup is construction plus integrity verification, excluding Python process launch.


## Reference points and tradeoffs

The severe calibrated budget above is only one operating point. The following fixed reference points were not optimized on holdout: 0.5 for most probability/binary scores, 0.35 for Speex’s documented entry probability, and 0.8 for FSMN’s approximate raw-posterior equivalent of its speech/noise margin. These are **not complete vendor-default detectors**: the common 200 ms endpoint policy replaces package-specific gates, hysteresis and segmentation. In particular, FSMN’s native energy gate is absent. Classic mode 2 is shown as the normal reference, independent of the calibrated mode choice.

| Backend | Reference threshold | Holdout miss % | False-positive % | False events / negative hour |
|---|---:|---:|---:|---:|
| agc2 | 0.500 | 10.738 | 15.486 | 1411.418 |
| classic-2 | 0.500 | 0.137 | 39.268 | 858.510 |
| fsmn | 0.800 | 5.491 | 11.686 | 329.497 |
| rnnoise | 0.500 | 0.829 | 3.503 | 484.016 |
| silero-lite-0.3.0 | 0.500 | 7.304 | 0.345 | 123.654 |
| silero-lite-0.4.0 | 0.500 | 5.049 | 0.051 | 31.797 |
| silero | 0.500 | 5.049 | 0.051 | 31.797 |
| speex | 0.350 | 0.164 | 42.655 | 651.831 |
| ten | 0.500 | 6.278 | 2.068 | 777.252 |

## False-activation sample uncertainty

| Backend | False events | Known-negative hours | Rate / hour | Descriptive Poisson 95% interval |
|---|---:|---:|---:|---:|
| agc2 | 2 | 0.566 | 3.533 | 0.428 – 12.762 |
| classic-0 | 0 | 0.566 | 0.000 | 0.000 – 6.516 |
| fsmn | 1 | 0.564 | 1.771 | 0.045 – 9.870 |
| rnnoise | 1 | 0.566 | 1.766 | 0.045 – 9.842 |
| silero-lite-0.3.0 | 2 | 0.566 | 3.533 | 0.428 – 12.762 |
| silero-lite-0.4.0 | 2 | 0.566 | 3.533 | 0.428 – 12.762 |
| silero | 2 | 0.566 | 3.533 | 0.428 – 12.762 |
| speex | 0 | 0.566 | 0.000 | 0.000 – 6.516 |
| ten | 0 | 0.566 | 0.000 | 0.000 – 6.516 |

Intervals assume Poisson event arrivals and are descriptive only: the repeated synthetic voices/texts and structured conditions are not independent natural audio. A zero observed count does not establish a zero real-world rate. Inspect the full development curves; do not rank models solely by this severe threshold or by short endpoint delays that can result from clipped/fragmented speech.


![Accuracy plots](accuracy.svg)

## Timing and notification

| Backend | Wall RTF | CPU RTF | Startup s | Peak process MiB | Onset clipping p95 ms | End notification p50 / p95 ms | Matched latency events |
|---|---:|---:|---:|---:|---:|---:|---:|
| agc2 | 0.011 | 0.011 | 0.003 | 122.125 | 2497.500 | -415.000 / 190.000 | 224 |
| classic-0 | 0.001 | 0.001 | 0.002 | 119.438 | n/a | n/a / n/a | 0 |
| fsmn | 0.023 | 0.023 | 0.033 | 143.688 | 3680.000 | -1305.000 / 155.500 | 210 |
| rnnoise | 0.066 | 0.066 | 0.031 | 133.230 | 1683.000 | 50.000 / 190.000 | 233 |
| silero-lite-0.3.0 | 0.006 | 0.006 | 0.287 | 152.855 | 570.000 | 210.000 / 300.000 | 211 |
| silero-lite-0.4.0 | 0.008 | 0.008 | 0.311 | 152.336 | 321.200 | 290.000 / 520.500 | 234 |
| silero | 0.006 | 0.006 | 0.066 | 137.285 | 321.200 | 290.000 / 520.500 | 234 |
| speex | 0.003 | 0.003 | 0.002 | 113.941 | n/a | n/a / n/a | 0 |
| ten | 0.014 | 0.014 | 0.002 | 117.680 | 1738.800 | 180.000 / 346.000 | 228 |

![Performance plots](performance.svg)

## Interpretation and limits

- Unknown native score alignment is left uncompensated and recorded as null. Frame-boundary accuracy for these adapters is not alignment-calibrated; native lookahead is documented separately. AGC2 is a historical extraction; FSMN is raw posterior, not native segmentation.
- Native frame sizes, context, state, and causal FIR resampling are preserved. Input arrives in simulated 10 ms capture blocks. Retrospective score alignment is separate from actual acquisition-time notification.
- A common 200 ms silence endpoint rule is used, with no padding or separate exit threshold. It does not reproduce each vendor’s native endpoint defaults. EOF-forced endings are excluded from latency distributions.
- Event reference intervals merge clean activity gaps up to 200 ms. Matching is globally greedy one-to-one by descending overlap; overlapping extra fragments are counted separately. Long merged detections cannot count as multiple correct events. Delays are conditional on matched events; read them together with recall, premature notifications, source end clipping, fragmentation, and misses in summary.json.
- False activation events are unmatched segments with no reference overlap per known-negative hour; the separate frame false-positive cap prevents a single long activation from gaming event counts. Unmatched events with any known-negative grid support count as false activations; events supported only by uncertainty are separately censored.
- The dataset and split were fixed before execution. Preliminary holdout results were viewed during validation; common metric fixes and the denser shared development-only threshold grid were then audited. This is not a blinded or preregistered study; no thresholds are selected from holdout performance.
- Development has only 32 minutes and holdout 48 minutes, with still less known-negative time. Low false-event rates are quantized and statistically uncertain; this is not evidence of a production 5/hour guarantee.
- Single measured corpus pass after warmup; shared unpinned cloud CPU, no frequency control. RTF includes buffering, resampling, dispatch, and inference; excludes WAV reads and reset. Startup is adapter construction, not a full process import.
- Memory is isolated-backend peak process RSS including Python, dependencies, and stored traces. It is not model-only RAM. File/package size and RSS must not be conflated.
- Notification delays use simulated audio-acquisition time and exclude compute scheduling. They are algorithmic pipeline delays, not measured device-to-application wall latency.
- Synthetic fan, typing, music-like interference and TTS speech do not represent real rooms or microphones. No human labeling was performed. Do not generalize the ranking to natural speech without external validation.
- Historical results and REPORT.md remain unchanged. Machine-readable full metrics, adapter pins, provenance, blocked status, and calibration curves are adjacent.
