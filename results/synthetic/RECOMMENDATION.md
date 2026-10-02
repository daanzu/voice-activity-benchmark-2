# Recommendation from this experiment

Use **correctly contextualized Silero as the primary baseline for the next implementation decision**, while retaining classic WebRTC as a low-footprint compatibility option. This recommendation is limited to this synthetic corpus and common controller; it is not a universal real-microphone ranking.

At the development-selected strict budget (at most 5 unmatched false activations per known-negative hour and 1% negative-frame false positives), Silero missed 6.46% of known source activity in holdout. It observed 2 unmatched false activations over approximately 0.566 negative hours: 3.53/hour, with a very broad descriptive Poisson 95% interval of 0.43–12.76/hour. That exposure is too small to establish a production false-trigger guarantee.

The alternatives are **not broken or silent detectors**. At fixed reference thresholds, raw FSMN missed about 5.5% of holdout activity and historical AGC2 about 10.7%, but accepted substantially more non-speech frames. Speex and classic can retain nearly all activity while also firing frequently on interference. Their calibrated all-miss points under the severe budget illustrate a tradeoff, not general uselessness. The report includes reference points and the complete development curves for that reason.

The initial coarse threshold grid skipped feasible high-probability points. An independent audit identified that issue; the final common development-only grid includes dense near-one thresholds. Final constrained miss rates are approximately 31.9% TEN, 43.9% current RNNoise, 57.5% historical AGC2, and 87.6% raw FSMN. These high-threshold streams also fragment speech. Short or negative end-notification delays must therefore not be interpreted as faster correct endpointing.

## Integration choice

- **Silero:** strongest source-activity retention at this selected low-false-activation budget. Keep the required waveform context and recurrent state, reset between independent streams, and separately tune the product endpoint policy
- **Classic WebRTC:** keep for compatibility and minimal compute/distribution requirements. Its binary modes cannot emulate arbitrary probability operating points
- **AGC2 RNN:** a small native option worth retaining. This implementation is a historical extraction, not current full WebRTC APM behavior
- **TEN:** useful optional comparator, with extra license restrictions and uncalibrated exact score alignment; its declared lookahead is documented
- **FSMN:** this test uses raw neural posteriors under a common controller. It does not establish the quality of FunASR's complete energy-gated segmentation pipeline
- **RNNoise:** choose primarily when denoising is part of the product requirement; the measured path performs full denoising even when only its VAD score is consumed
- **SpeexDSP:** chiefly a legacy integration option; its documented heuristic and coarse probability output offer limited calibration flexibility here

The synthetic set has two voices per split, repeated texts within each split, one shared synthesis engine, artificial noise, and activity-proxy labels with explicit uncertainty. Before a production decision, evaluate a separately sourced, appropriately licensed natural-audio benchmark and the actual capture pipeline. No human labeling was performed or is required to reproduce this repository's experiment.

See [full results and caveats](REPORT.md), [machine-readable metrics](summary.json), [development curves](development-curves.json), and [artifact sizes](resource-inventory.json). Runtime memory and artifact size are separate measurements.
