# Voice Activity Benchmark 2: detailed comparison

Research and limited measurements, 2026-10-02.

## Executive summary

Keep classic WebRTC VAD when compatibility, tiny footprint, and minimum CPU are the primary requirements. For a modern speech detector, compare a correctly integrated current Silero model with WebRTC's compact AGC2 RNN VAD on the actual target workload. TEN and FSMN are worthwhile additional candidates. RNNoise is most relevant when denoising is also required; Speex is primarily a legacy integration option.

This is a source-informed comparison of seven approaches, supported by a small, reproducible throughput experiment for classic WebRTC and two Silero ONNX models. It is **not** a seven-way measured accuracy ranking. No labeled accuracy evaluation was performed, and the practical recommendation remains conditional on deployment-specific tests.

## 1. Important finding: Silero-lite's model and context handling

The investigated `silero-vad-lite` 0.2.1 package bundled the exact official Silero v5.1 model blob, Git blob SHA `b3e3a900c0d70e67b5e2b90a33ad856ee7947930`, 2,327,524 bytes. The Silero release page inspected during research listed v6.2.3 as the current release. The benchmark's newer model is pinned independently by source commit and SHA-256; the name “current” in retained result rows is a historical label.

The inspected lite C++ implementation feeds only each new chunk. The official v5.1 streaming wrapper prepends the previous 64 samples at 16 kHz or 32 samples at 8 kHz: 4 ms of past waveform context, in addition to recurrent state. New input chunks are 512 or 256 samples respectively. Recurrent state and waveform context are distinct parts of the streaming contract.

A controlled diagnostic held the v5.1 model, ONNX Runtime, and audio constant while enabling or disabling that explicit context. Over 28 chunks of the small fixture:

| Input | Maximum absolute probability difference | Mean absolute difference |
|---|---:|---:|
| 8 kHz fixture | 0.9911231696605682 | 0.3970406587634768 |
| 16 kHz sample-repeated fixture | 0.6065110564231873 | 0.10526469882045474 |

Two independent no-context controls matched exactly. This establishes a material output difference on this fixture. It does **not** establish which output is more accurate, or quantify real-world degradation. There are no labels here, and the 16 kHz signal is simply sample-repeated, not a realistic resampling test.

The native Linux lite 0.2.1 binary could not load because it requested an executable stack (`GNU_STACK RWE`) rejected by the environment. No security setting was relaxed. The diagnostic and timings use a direct NumPy/ONNX wrapper; they are not native-lite measurements.

Sources: [lite C++ implementation](https://github.com/daanzu/py-silero-vad-lite/blob/main/src/silero_vad_lite/silero_vad.cpp), [official v5.1 streaming wrapper](https://github.com/snakers4/silero-vad/blob/v5.1/src/silero_vad/utils_vad.py), [Silero releases](https://github.com/snakers4/silero-vad/releases).

## 2. Classic WebRTC VAD

Classic WebRTC VAD accepts mono signed 16-bit PCM at 8, 16, 32, or 48 kHz, using exactly 10, 20, or 30 ms frames. It returns a Boolean speech decision and offers four aggressiveness modes. It is a small C implementation with no external model or inference framework.

Its classifier uses six-band features and adaptive Gaussian mixture models, with downsampling to the core 8 kHz analysis representation. Aggressiveness changes the operating point; a Boolean API is convenient but gives less threshold control than a continuous score.

The implementation includes state and hangover. Depending on frame size and mode, nominal hangover is roughly 80–150 ms in modes 0/1 and 60–100 ms in modes 2/3. This is trailing behavior, not future lookahead. An application may add further end-of-speech padding or silence duration.

This is the strongest fit when minimal CPU, small distribution size, straightforward native integration, and existing behavior matter most. Its age alone is not evidence of poor performance on a specific workload; compare miss and false-alarm rates using representative audio.

The Python wrapper is MIT-licensed, with WebRTC BSD and other embedded notices requiring preservation.

Source: [pinned WebRTC VAD core](https://webrtc.googlesource.com/src/+/b9d2649d7eaf03f013b07cd9b93db73b1e4921af/common_audio/vad/vad_core.c).

## 3. WebRTC AGC2 RNN VAD

The AGC2 RNN VAD is a separate detector from classic WebRTC VAD. Its analysis path uses 240 floating-point samples at 24 kHz per 10 ms step; the surrounding wrapper handles resampling and channel selection. It produces a probability rather than the classic Boolean mode-based result.

The inspected network uses 42 features, a dense layer of width 24, a GRU of width 24, and one output. Its 4,585 embedded signed 8-bit parameters are scaled for floating-point inference. Compact stored weights should not be mistaken for an integer-only inference path.

The feature extractor uses trailing 20 ms analysis and approximately 36 ms pitch history. That history is not future lookahead. Source reset behavior also needs care: resetting the GRU is not equivalent to resetting the whole frontend. The inspected wrapper periodically resets the GRU every 1.5 seconds, and silence handling also affects recurrent state.

The native implementation has AVX2/SSE2, ARM64 NEON, and scalar paths. It needs no general-purpose inference framework, but extracting it requires internal C++ resampling, pitch, FFT/PFFFT, utilities, and RNNoise-derived dependencies. It is not a stable stand-alone C API. Preserve the applicable BSD, RNNoise, FFT, and other dependency notices.

This is a promising choice for a compact native neural detector when the engineering cost of packaging and maintaining the dependency boundary is acceptable. No runtime or accuracy measurements for this detector were performed in this repository.

Sources: [network](https://webrtc.googlesource.com/src/+/b9d2649d7eaf03f013b07cd9b93db73b1e4921af/modules/audio_processing/agc2/rnn_vad/rnn.cc), [feature extraction](https://webrtc.googlesource.com/src/+/b9d2649d7eaf03f013b07cd9b93db73b1e4921af/modules/audio_processing/agc2/rnn_vad/features_extraction.cc), [build dependencies](https://webrtc.googlesource.com/src/+/b9d2649d7eaf03f013b07cd9b93db73b1e4921af/modules/audio_processing/agc2/rnn_vad/BUILD.gn), [surrounding wrapper](https://webrtc.googlesource.com/src/+/b9d2649d7eaf03f013b07cd9b93db73b1e4921af/modules/audio_processing/agc2/vad_wrapper.cc).

## 4. Silero VAD

The inspected ONNX streaming contract is normalized floating-point mono input at 8 or 16 kHz, with 32 ms of fresh audio per call, 4 ms of past context, and recurrent state of shape `[2, batch, 128]`. Preserve state during one stream and reset both state and context between independent streams. The official wrapper provides `reset_states`; the older lite interface investigated lacked a corresponding reset API.

A model score is not a full endpointing policy. In the inspected official `VADIterator`, defaults include a 0.5 entry threshold, 0.35 exit threshold, at least 100 ms of silence, and 30 ms speech padding. With 32 ms chunks, the end event arrives on the fifth low-scoring chunk, 128 ms after the first low chunk was processed. A backdated boundary timestamp does not make the notification arrive earlier. Likewise, a 32 ms input chunk does not guarantee 32 ms onset detection.

The official Python integration uses Torch, whereas a direct ONNX integration can avoid it. The lite package bundles ONNX Runtime 1.19 and avoids Python inference-runtime dependencies, but that does not mean a tiny binary: the inspected Linux shared library was around 23 MB, and compressed wheels were approximately 6.6 MB on Windows, 10.1 MB on Linux, and 30.8 MB on macOS. The ONNX model itself was about 2.3 MB. File sizes are not runtime memory measurements.

Silero, the lite wrapper, and ONNX Runtime use MIT licenses, with bundled third-party notices still relevant. The official quality page provides useful evaluation context; its published results should not be compared directly against unrelated datasets or thresholds as if they were a controlled ranking.

Sources: [official wrapper](https://github.com/snakers4/silero-vad/blob/master/src/silero_vad/utils_vad.py), [published quality metrics](https://github.com/snakers4/silero-vad/wiki/Quality-Metrics).

## 5. TEN VAD

TEN accepts 16 kHz signed 16-bit PCM and returns a probability plus a flag. Its public interface supports 10 or 16 ms hops, but the internal network operates on 16 ms steps with a 48 ms analysis window and one frame of future lookahead. A small API hop may buffer input or return a previous score. A 10 ms API hop is therefore not evidence of 10 ms detection latency.

The inspected implementation keeps four 64-float recurrent states plus frontend history and resets neural state approximately every 30 seconds. Its create/process/destroy interface does not expose a dedicated reset endpoint. The published Linux library was about 306 KB; the approximately 308 KB ONNX model is a different distribution option that also needs a runtime. Neither number measures resident memory.

The license is Apache-derived with additional Agora competitive-use restrictions. Treat it as source-available with additional conditions, not plain Apache 2.0; evaluate suitability before adoption.

The vendor's comparison uses a pinned Silero V5 baseline. Its plotting code shifts TEN scores for frame alignment, compares differing frame grids, and does not provide a classic WebRTC curve or reproduce full end-notification latency. The plot is useful vendor evidence, not an independently matched seven-way benchmark.

Sources: [API](https://github.com/TEN-framework/ten-vad/blob/main/include/ten_vad.h), [frontend declarations](https://github.com/TEN-framework/ten-vad/blob/main/src/aed.h), [processing](https://github.com/TEN-framework/ten-vad/blob/main/src/aed.cc), [evaluation plotting](https://github.com/TEN-framework/ten-vad/blob/main/examples/plot_pr_curves.py), [license](https://github.com/TEN-framework/ten-vad/blob/main/LICENSE).

## 6. FSMN VAD / FunASR

FSMN supports streaming and offline boundary detection, with 8 and 16 kHz checkpoints. The investigated model is approximately 0.4 million parameters and 1.72 MB of weights. Checkpoint-specific configuration matters; these numbers are not guarantees for every model called FSMN.

The frontend uses a 25 ms feature window and 10 ms shift. Centered stacking of five feature frames introduces two future frames, approximately 20 ms of lookahead, even when the encoder's right-context order is zero. A causal encoder does not make the entire frontend causal.

The inspected endpoint configuration includes a 200 ms decision window, 150 ms transition setting, 800 ms maximum end silence, 200 ms lookback, and 100 ms extension. These values serve different conditions and should not be blindly summed. Retroactive boundary timestamps do not eliminate the time spent waiting to issue the event. Pin and inspect configuration, including dynamic silence handling, before comparing latency.

The encoder cache tensors alone were estimated at approximately 38 KiB. This excludes frontend buffers, endpoint state, framework memory, and all other process overhead, so it is not a RAM estimate. State handling and segmentation behavior make integration more complex than calling a frame classifier.

The framework is MIT-licensed; the cited model is Apache 2.0. FSMN is attractive when a configurable segmentation-oriented frontend is useful, but its endpoint settings need tuning for interactive tasks. No matched runtime or accuracy measurements were performed here.

Sources: [model configuration](https://huggingface.co/funasr/fsmn-vad/raw/main/config.yaml), [model card](https://huggingface.co/funasr/fsmn-vad), [feature frontend](https://github.com/modelscope/FunASR/blob/main/funasr/frontends/wav_frontend.py), [streaming model](https://github.com/modelscope/FunASR/blob/main/funasr/models/fsmn_vad_streaming/model.py).

## 7. RNNoise

RNNoise is a native C denoiser that also exposes a VAD probability. The inspected current implementation processes 480 floating-point samples at 48 kHz per 10 ms step, using int16-like amplitude scaling rather than normalized ±1 input.

The current network uses 65 features, 32 bands, two temporal convolutions, three GRUs, and joint gain/VAD output heads. This is substantially newer than the older RNNoise-derived design embedded in WebRTC AGC2. Do not transfer old 2018 RNNoise size or speed claims to this current implementation.

Analysis uses a 20 ms window. The training-target alignment suggests the score corresponds to the previous feature frame, implying approximately 10 ms lookahead; this is an inference from the source alignment, not an independently measured latency result. Score alignment and denoised-audio output delay must be considered separately.

State includes frontend, neural, and synthesis history. Skipping inference for silence retains recurrent state, unlike AGC2's reset behavior. `rnnoise_init` resets the state. The normal processing path still performs denoising work even when an application consumes only the VAD score.

Weights can be compiled into the native library, avoiding a general ML runtime, although the build obtains model assets. RNNoise is BSD-licensed. Prefer it as a candidate when denoising is also required; it may be unnecessary work for a VAD-only pipeline.

Sources: [pinned network implementation](https://github.com/xiph/rnnoise/blob/70f1d256acd4b34a572f999a05c87bf00b67730d/src/rnn.c), [processing and state](https://github.com/xiph/rnnoise/blob/70f1d256acd4b34a572f999a05c87bf00b67730d/src/denoise.c), [training alignment](https://github.com/xiph/rnnoise/blob/70f1d256acd4b34a572f999a05c87bf00b67730d/torch/rnnoise/train_rnnoise.py#L145-L148), [build documentation](https://github.com/xiph/rnnoise/blob/70f1d256acd4b34a572f999a05c87bf00b67730d/README).

## 8. SpeexDSP preprocessing VAD

SpeexDSP provides a native C preprocessor for signed 16-bit PCM with configurable sample rate and frame size; 10–20 ms frames are recommended. Processing can modify the input buffer. Its VAD is a spectral noise/SNR heuristic rather than a separately distributed learned model.

VAD must be explicitly enabled; otherwise the relevant processing result returns 1. Probability settings are integer percentages, with default start/continue thresholds of 35/20. This threshold hysteresis is not a fixed-duration hangover. The analysis uses previous and current input without explicit future lookahead; audio synthesis delay is a separate consideration.

Noise estimates and other adaptive state persist. Destroying and recreating a preprocessor gives a clean independent stream. The FFT pipeline is still involved when denoising is disabled, so disabling denoising is not equivalent to removing all preprocessing cost.

The upstream source itself states: “The VAD has been replaced by a hack pending a complete rewrite.” This is a reason to treat it as a legacy integration option and validate carefully, rather than a preferred modern baseline. SpeexDSP is BSD-licensed. It was not timed or accuracy-tested here.

Sources: [upstream warning](https://github.com/xiph/speexdsp/blob/7a158783df74efe7c2d1c6ee8363c1e695c71226/libspeexdsp/preprocess.c#L1096-L1100), [decision logic](https://github.com/xiph/speexdsp/blob/7a158783df74efe7c2d1c6ee8363c1e695c71226/libspeexdsp/preprocess.c#L991-L1009), [public interface](https://github.com/xiph/speexdsp/blob/7a158783df74efe7c2d1c6ee8363c1e695c71226/include/speex/speex_preprocess.h).

## 9. What was actually measured

Only classic WebRTC VAD and direct ONNX inference for the two Silero models were measured. The scripts implement Silero's state/context contract with NumPy and ONNX Runtime, not the official Torch-based Python package. The older lite native binary was not run successfully.

Recorded environment: shared Linux x86-64 cloud host reporting AMD EPYC 9V74 80-Core Processor; Python 3.12.14; NumPy 2.3.5; ONNX Runtime 1.19.0 CPU provider; one intra-op and one inter-op thread. No CPU pinning or frequency control. Classic WebRTC used an already-compiled checkout at `e8fb8b736111631ae8aa6f29fc9b7498ce893ccf`; its original compiler invocation was not retained.

Each condition processed 60 seconds of input. Inputs were the repeated upstream 8 kHz fixture, seeded uniform noise, and silence. The 16 kHz fixture was constructed by repeating each 8 kHz sample twice, solely for throughput and output-difference diagnostics. Each run constructed a fresh detector outside the timer; one complete run was discarded, then the median of five measured passes was recorded.

The per-call values are amortized whole-pass timings, not p50/p95 measurements of individual calls. Timings include dispatch, state/context handling, and inference, while excluding startup, input preparation, device capture, realistic resampling, and endpoint policy. No matched RAM, power, or timings for AGC2 RNN, TEN, FSMN, RNNoise, or Speex were measured.

### 16 kHz fixture throughput

| Backend | Fresh input per call | Amortized µs/call | Wall-time RTF |
|---|---:|---:|---:|
| Classic WebRTC mode 2 | 10 ms | 1.61 | 0.0001606 |
| Classic WebRTC mode 2 | 20 ms | 2.20 | 0.0001098 |
| Classic WebRTC mode 2 | 30 ms | 2.74 | 0.0000915 |
| Silero v5.1 with context | 32 ms | 138.68 | 0.0043336 |
| Pinned newer Silero with context | 32 ms | 134.11 | 0.0041911 |

RTF is processing wall time divided by audio duration; lower is faster. These results establish large throughput headroom for these measured cases, not a guarantee of accuracy or latency on another machine. Complete five-run records, including 8 kHz, noise, and silence conditions, are in [results/2026-10-02](results/2026-10-02).

### Reproducibility identifiers

- Classic checkout: `e8fb8b736111631ae8aa6f29fc9b7498ce893ccf`
- Newer Silero source commit: `1e261b036686cd0017d500ee96acd1c4ba572a9d`
- Older model SHA-256: `2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f`
- Newer model SHA-256: `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`

The README gives the pinned reproduction commands. `verify_models.py` checks both model hashes. Binary/model/fixture assets are deliberately fetched from upstream rather than bundled.

## 10. How to interpret the earlier accuracy benchmark

The earlier [voice-activity-benchmark repository at the inspected commit](https://github.com/daanzu/voice-activity-benchmark/tree/ea8710836e9b0b3ecdd17700111483eacc54a554) showed Silero v5.1 ahead of an extracted WebRTC RNN, ahead of classic WebRTC, on that benchmark's dataset. This is dataset-specific evidence, not a general ranking across all speech environments or a current-model comparison.

Its mixing pipeline uses energy-derived labels, excludes ambiguous UNKNOWN regions, inserts 20-second silences, and uses DEMAND noise at 0 dB. This is not a human-annotated boundary test. The engine also caches Silero and precomputed RNN outputs; timing only its processing path does not independently reproduce the plotted end-to-end RTF ratios. Accuracy plots and speed claims therefore need separate provenance checks.

Sources: [mixing and labels](https://github.com/daanzu/voice-activity-benchmark/blob/ea8710836e9b0b3ecdd17700111483eacc54a554/mixer.py), [engine and caching](https://github.com/daanzu/voice-activity-benchmark/blob/ea8710836e9b0b3ecdd17700111483eacc54a554/engine.py).

## 11. Recommended next evaluation

1. Keep classic WebRTC as an independent compatibility backend rather than silently replacing its behavior
2. Establish a correctly integrated, current pinned Silero baseline, including context and state resets
3. Compare AGC2 RNN on target hardware if a compact native neural option is attractive
4. Evaluate TEN only after checking its additional license conditions; tune FSMN's endpoint policy before comparing responsiveness
5. Add RNNoise when denoising is part of the objective; retain Speex primarily for legacy integration requirements

Use untouched held-out recordings from representative microphones and rooms, including fan noise, keyboard input, music, television, other voices, and quiet or short speech. Compare false activations at matched operating points, missed speech, onset clipping, and p50/p95 end-notification delay. Respect each model's frame alignment, scaling, lookahead, and reset contract.

Separate frame-scoring quality from endpoint policy: first compare aligned scores, then apply equivalent segmentation rules where possible, and finally compare the complete product behavior. Report startup, steady-state CPU, resident memory, and power independently, and distinguish event timestamps from the time applications actually receive those events.

## Scope and source caveats

All source observations describe the versions inspected during this research. Some explanatory links point to upstream moving branches and may change; immutable revisions are used where the research retained them. Vendor claims are identified separately from local measurements. Size figures are distribution/model sizes, not RAM. Licensing notes are technical diligence, not legal advice. No private recordings or user-specific personal information are included.
