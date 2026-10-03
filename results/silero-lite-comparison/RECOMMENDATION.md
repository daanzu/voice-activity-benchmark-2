# Recommendation from the published-package comparison

**Prefer silero-vad-lite 0.4.0 over 0.3.0 as the native package baseline for the
next product evaluation.** This recommendation is limited to the fixed synthetic
corpus and common endpoint controller. It does not establish a real-microphone
accuracy ranking or guarantee a production false-trigger rate.

## What changed

Both published releases already include the correct 4 ms waveform context and
reset handling. Their Python wrapper and native library are byte-identical on
the tested platform; the bundled model changes from v5.1 to v6.2 weights from
upstream v6.2.3. The measured accuracy difference is a **model-update comparison**,
not evidence of an additional context fix between these releases.

The 0.4.0 package and the existing direct-ONNX `silero` baseline contain the
same model and produced **bit-for-bit identical probabilities on all 150,000
frames**, with identical stream resets and acquisition timestamps. Their
accuracy, calibration and common-controller endpoint results therefore match
exactly. The direct baseline remains useful as a correctness reference.

## Accuracy and endpoint tradeoff

| Measure, fixed holdout | Lite 0.3.0 | Lite 0.4.0 / direct baseline |
|---|---:|---:|
| Development-selected threshold | 0.96 | 0.80 |
| Missed source activity, strict budget | 21.376% | 6.463% |
| Non-speech frame false positives, strict budget | 0.009% | 0.004% |
| False activations, strict budget | 2 | 2 |
| False activations / known-negative hour | 3.533 | 3.533 |
| Event recall | 87.917% | 97.500% |
| Extra speech fragments | 22 | 3 |
| Onset clipping p95 | 570 ms | 321.2 ms |
| End notification p95, matched events only | 300 ms | 520.5 ms |
| Premature notifications among measured matches | 9.479% | 0.855% |
| Missed activity at fixed threshold 0.5 | 7.304% | 5.049% |
| Non-speech frame false positives at 0.5 | 0.345% | 0.051% |

Thresholds were selected independently on the unchanged development set under
the same severe budget: no more than 5 false events per known-negative hour and
1% negative-frame false positives. No holdout retuning occurred. The different
thresholds are intentional; using 0.96 unchanged after upgrading would not
reproduce the calibrated 0.4.0 operating point.

The apparently shorter 0.3.0 end-notification delay is not evidence of better
endpointing: it misses more speech/events, clips more onsets, creates more
fragments, and ends prematurely more often. Latency is conditional on matched
events and uses synthetic activity proxies, not human phonetic boundaries.

The two false events span only approximately 0.566 known-negative hours. Each
Silero row's descriptive Poisson 95% rate interval is about 0.43–12.76/hour.
Identical event counts do not establish identical generalization, and this
exposure cannot validate a production 5/hour guarantee.

All previous backends remain in the [full nine-backend report](REPORT.md).
Their severe-budget misses in this run are approximately TEN 31.9%, RNNoise
44.0%, historical AGC2 57.5%, raw FSMN 87.6%, and classic/Speex 100%. The latter
are constrained all-miss operating points, not general failure of those
implementations. Reference thresholds and all development curves remain
available to show the tradeoffs.

## Performance on this host

| Path | Wall RTF | Timed adapter-call RTF | Wall seconds / 80-minute corpus |
|---|---:|---:|---:|
| Direct ONNX baseline | 0.005582 | 0.004430 | 26.791 |
| Published lite 0.3.0 | 0.006200 | 0.005106 | 29.760 |
| Published lite 0.4.0 | 0.007745 | 0.006391 | 37.178 |

All three are substantially faster than real time here. The native package path
was **not faster than the direct ONNX adapter** in this measured pass. Timed
adapter calls include validation, conversion/copies and the actual package API;
they are not isolated ONNX kernels. Model equivalence does not imply equivalent
runtime builds or call overhead. Single-pass shared-host timings cannot establish
a stable percentage speed difference or predict the target application's CPU.

Lite startup was about 0.29–0.31 seconds versus 0.066 seconds for the direct
baseline, but startup includes checksum validation of the complete lite wheel
and installed payload. This is not a package import/startup-only comparison.
Lite peak process RSS was about 152 MiB versus 137 MiB for direct ONNX; these peaks
include interpreter/runtime, integrity-verification allocations and retained
corpus traces, not model-only RAM. See [artifact inventory](resource-inventory.json)
for separate installed/model sizes.

The current host is an Intel Xeon Platinum 8573C; the original seven-backend
record used an AMD EPYC 9V74. All nine rows in this report were rerun on the
current host; original files remain unchanged. RNNoise's newly built,
CPU-specific `-march=native` path has a small accuracy difference from the
original run (43.930% versus 44.040% strict-budget miss), despite unchanged
source/model pins. This flags native build/environment sensitivity; the specific
cause was not isolated. Do not mix old-host timings with this run.

## Next decision

Use the 0.4.0 package as the native integration candidate and the equivalent
ONNX adapter as the regression oracle. Recalibrate the product's operating
threshold and endpoint policy on development audio from the intended capture
pipeline, then validate on separately sourced natural speech/noise. Keep 0.3.0
only where its older-model behavior is an intentional compatibility choice.

No human labeling, real microphone testing, power measurement, or deployment-hardware
benchmark was performed in this extension. The retained [methodology and caveats](REPORT.md),
[package provenance](../../docs/SILERO_LITE.md), and [validation](VALIDATION.md)
are part of the result.
