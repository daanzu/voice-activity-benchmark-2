# Tested backends and benchmark methodology

[Back to the overview table](../README.md#backends-tested) ·
[Comparison results](../results/silero-lite-comparison/REPORT.md) ·
[Interactive explorer](../notebooks/README.md) ·
[Reproduction](RUN_SYNTHETIC.md)

This guide distinguishes the **implementation that ran** from Python packages
that could be used in an application. All inference was local CPU inference.
Package availability does not establish identical weights, frontend behavior,
state handling, segmentation, performance or licensing.

## Which experiment answers which question?

| Experiment | Execution and purpose | Results |
|---|---|---|
| Historical throughput study | Classic WebRTC plus direct ONNX v5.1/newer Silero; repeated short fixture, noise and silence at 8/16 kHz; no accuracy labels | [Original report](../REPORT.md) and [retained timings](../results/2026-10-02) |
| Seven-backend synthetic study | Classic, Silero, AGC2, TEN, FSMN, RNNoise and Speex under a shared streaming runner/controller | [Original synthetic results](../results/synthetic/REPORT.md) |
| Nine-backend package comparison | Actual PyPI Silero Lite 0.3.0/0.4.0 wheels plus fresh runs of the original seven backends on the identical corpus | [Package comparison](../results/silero-lite-comparison/REPORT.md) |
| Silero v5.1 context-only ablation | Same model, ONNX Runtime, corpus and controller; preceding waveform context omitted versus enabled | [Ablation and independent validation](../results/context-ablation/REPORT.md) |

The historical `silero-vad-lite` 0.2.1 native library could not load because of
its executable-stack requirement; security settings were not relaxed. The old
throughput scripts used its model through direct ONNX inference. The context
ablation emulates the old input/state contract; **it is not an execution of the
old 0.2.1 wheel**. In contrast, the 0.3.0 and 0.4.0 comparison really executes
those published packages. Both already contain the context/reset correction.

## Implementation notes

The [runner](../vadbench/run.py) supplies normalized float32 mono frames.
Adapters convert to their native formats, preserve state within a stream and
reset between independent streams. The README gives the actual frame durations
and sample rates, rather than every format an upstream project might support.

### Classic WebRTC

- Tested `webrtcvad-wheels` 2.0.14 built from the pinned
  [daanzu/py-webrtcvad-wheels checkout](https://github.com/daanzu/py-webrtcvad-wheels/tree/e8fb8b736111631ae8aa6f29fc9b7498ce893ccf)
  using its Python C extension, not an independently downloaded wheel
- The [adapter](../vadbench/adapters.py) converts to signed int16 PCM and calls
  `Vad.is_speech` on 160 samples at 16 kHz; the score is Boolean, not a probability
- All four aggressiveness modes are run. Development calibration selects the
  mode/operating point; mode 2 also has a fixed reference result. Native hangover
  remains in the classifier before the shared endpoint controller
- Source and dependency pins: [setup_primary.py](../scripts/setup_primary.py)

### Silero direct ONNX

- Official v6.2 streaming weights, byte-identical to the model in the tested
  Lite 0.4.0 release (from upstream v6.2.3); pinned source commit
  [`1e261b03`](https://github.com/snakers4/silero-vad/tree/1e261b036686cd0017d500ee96acd1c4ba572a9d)
- Repo NumPy wrapper calls ONNX Runtime 1.19.0 CPU directly, with one intra-op
  and one inter-op thread. The official `silero-vad` Python API is not used
- Each call consumes 512 fresh 16 kHz samples and prepends 64 past samples.
  Recurrent state and waveform context are distinct and both reset per stream
- The 4 ms prefix is **past context, not future lookahead**. No official
  `VADIterator` endpoint settings are applied
- Code: [SileroAdapter](../vadbench/adapters.py); model hash and comparison:
  [SILERO_LITE.md](SILERO_LITE.md#model-and-runtime-provenance)

### Silero Lite 0.3.0 and 0.4.0

- Two separately installed, hash-pinned CPython 3.12 Linux x86-64 PyPI wheels,
  executed through their public `SileroVAD.process` API in fresh processes
- 0.3.0 bundles v5.1; 0.4.0 bundles v6.2. The tested native library is identical
  in both wheels and bundles ONNX Runtime 1.19.0
- Both consume 512 fresh samples at 16 kHz. The package supplies the 64-sample
  past prefix and resets context/state; the repo adapter does not prepend it again
- 0.3.0 versus 0.4.0 compares the model update. 0.4.0 versus direct `silero`
  compares execution paths using identical weights, not different model quality
- Code: [silero_lite.py](../vadbench/silero_lite.py); exact wheel, model and native
  hashes, isolation and runtime validation: [SILERO_LITE.md](SILERO_LITE.md)

### WebRTC AGC2 RNN

- Historical third-party [daanzu/webrtc_rnnvad extraction at `10209d27`](https://github.com/daanzu/webrtc_rnnvad/tree/10209d27953cad3affadfdcca968c0066cea0830),
  compiled as C++ with a small repo C interface and called through `ctypes`
- 240 samples at 24 kHz per call, with normalized input scaled to float PCM
- Retains this extraction's feature/high-pass processing; neither current
  upstream WebRTC nor the complete APM/AGC2 pipeline is tested
- The `py-webrtcrnnvad` Python package is an alternative integration, not the
  executed wrapper. No calibrated acoustic score timestamp is claimed
- Build pins, notices and reset behavior: [NATIVE_BACKENDS.md](NATIVE_BACKENDS.md)

### TEN

- Upstream prebuilt Linux x86-64 `libten_vad.so`, obtained from repository
  revision [`22a3bcd4`](https://github.com/TEN-framework/ten-vad/tree/22a3bcd4509d0faaa8eef4881e8af5f39c178950),
  called directly through the repo's `ctypes` adapter; reports library version 2.1.0
- 256 int16 samples at 16 kHz. The probability is used, not the API's flag;
  the upstream Python wrapper / PyPI package is not the measured integration
- The binary hash is retained, but binary-to-source correspondence is not
  independently established. Source declares 16 ms lookahead and a 48 ms
  analysis window; exact acoustic score alignment is uncalibrated
- Its license adds restrictions to Apache 2.0. Setup is explicitly opt-in after
  license review; see [license, binary hash and runtime](NATIVE_BACKENDS.md#ten-separately-obtained-explicitly-opt-in)

### FSMN / FunASR

- Official full-float [FSMN ONNX export at `f6e9fbb4`](https://huggingface.co/funasr/fsmn-vad-onnx/tree/f6e9fbb4cefa7397216c763f21307993f147f585),
  run with ONNX Runtime 1.19.2, `kaldi-native-fbank` 1.22.3 and repo streaming orchestration
- 16 kHz input in 10 ms hops, 25 ms filterbank windows, centered five-frame
  stacking, supplied mean/variance transform and persistent FSMN caches
- Two observed future feature frames are needed. First valid posterior arrives
  at 50 ms; each score is delayed 40 ms relative to its nominal hop's end.
  Initial sentinels are excluded from quality metrics; there is no padded end flush
- Reports `1 - p(silence)`. FunASR's energy/SNR gates, adaptive noise statistics,
  voting, transitions and boundary extensions are omitted. This is **raw neural
  posterior with shared endpointing**, not full native FunASR segmentation
- The official `funasr` / `funasr-onnx` package APIs are not used. Frontend parity,
  timing contract and hashes: [FSMN_BACKEND.md](FSMN_BACKEND.md)

### RNNoise

- Official [xiph/rnnoise at `70f1d256`](https://github.com/xiph/rnnoise/tree/70f1d256acd4b34a572f999a05c87bf00b67730d),
  source-built C with the default full model and called through repo `ctypes`
- 480 samples at 48 kHz, scaled to float PCM; uses the probability returned by
  the **full denoising call**. Denoised audio is discarded, but its cost is included
- This is the larger convolution/GRU architecture, not the older RNNoise 0.1.1
  network. Build uses `-O3 -march=native`; rebuild for the target CPU
- `pyrnnoise` is a third-party Python integration, not the path tested here.
  VAD score alignment is not calibrated; output-audio delay is not substituted
  for it. Details: [NATIVE_BACKENDS.md](NATIVE_BACKENDS.md)

### SpeexDSP

- Official [xiph/speexdsp at `1b28a0f6`](https://github.com/xiph/speexdsp/tree/1b28a0f61bc31162979e1f26f3981fc3637095c8)
  (1.2.1), source-built C preprocessor called through repo `ctypes`
- 320 int16 samples at 16 kHz. VAD and denoising enabled, AGC disabled
- Uses `SPEEX_PREPROCESS_GET_PROB / 100`, with 0.01 score resolution, rather
  than the preprocessor's hysteretic Boolean return. Adaptive preprocessing
  remains part of this backend
- The documented `speexdsp` Python package API is an echo canceller, not evidence
  of a binding for this preprocessing VAD. It was not used
- Upstream warns its VAD is a temporary heuristic; exact score alignment remains
  uncalibrated. Details: [NATIVE_BACKENDS.md](NATIVE_BACKENDS.md)

## Python package options

Availability checked 2026-10-03. **Official** means maintained under the model or
library project's upstream organization; **community / third-party** means a
separate wrapper project. These are integration options, not additional benchmark
rows, package recommendations or guarantees for every OS/Python version. Only
the source-built classic extension and the two pinned Lite package APIs above
were used as VAD Python-package integrations.

| Family | Available Python integration | Relation to this benchmark |
|---|---|---|
| Classic WebRTC | Community [webrtcvad](https://pypi.org/project/webrtcvad/) and [webrtcvad-wheels](https://pypi.org/project/webrtcvad-wheels/); [wheels source](https://github.com/daanzu/py-webrtcvad-wheels) | Uses the pinned wheels-project source build, not an arbitrary latest PyPI wheel |
| Silero | Official [silero-vad](https://pypi.org/project/silero-vad/) / [upstream](https://github.com/snakers4/silero-vad) | Available but not used; direct ONNX path instead |
| Silero Lite | Third-party [silero-vad-lite 0.3.0](https://pypi.org/project/silero-vad-lite/0.3.0/) and [0.4.0](https://pypi.org/project/silero-vad-lite/0.4.0/) / [source](https://github.com/daanzu/py-silero-vad-lite) | Both actual native package APIs used; one row per release |
| AGC2 RNN | Third-party [py-webrtcrnnvad](https://pypi.org/project/py-webrtcrnnvad/) / [source](https://github.com/jzi040941/py-webrtcrnnvad) | Not used; separate from the tested historical extraction and repo wrapper |
| TEN | Official [upstream Python wrapper](https://github.com/TEN-framework/ten-vad#python-usage) and [ten-vad on PyPI](https://pypi.org/project/ten-vad/) | Not used; repo adapter calls the upstream prebuilt library directly |
| FSMN | Official [funasr](https://pypi.org/project/funasr/) and [funasr-onnx](https://pypi.org/project/funasr-onnx/); [ONNX VAD examples](https://github.com/modelscope/FunASR/tree/main/runtime/python/onnxruntime) | Neither package API used; official model and repo frontend instead |
| RNNoise | Third-party [pyrnnoise](https://pypi.org/project/pyrnnoise/) / [source](https://github.com/pengzhendong/pyrnnoise) | Not used; repo adapter calls the source-built Xiph library |
| SpeexDSP | Third-party [speexdsp](https://pypi.org/project/speexdsp/) / [binding interface](https://github.com/xiongyihui/speexdsp-python/blob/master/src/speexdsp.i) | Not used; documented EchoCanceller API does not expose this preprocessing VAD |

The existence of other Python bindings is not ruled out. Package links describe
the independently published options as of the check date; the benchmark's pinned
versions and hashes remain the source of truth for its measurements.

## Shared synthetic experiment

- **Data:** 240 twenty-second mono streams at 16 kHz, 80 minutes total.
  Flite TTS plus synthetic fan, typing and music-like signals; 96 development
  streams (32 minutes), 144 holdout streams (48 minutes). Voices, exact texts and
  noise seeds are split-disjoint, but the synthesis engine is shared
- **Labels:** known source placement plus a clean-source energy/activity proxy.
  Uncertain regions are excluded. Primary generic speech includes background
  voices; foreground-only scoring is a separate diagnostic. There are no human
  phonetic annotations. See [DATASET.md](DATASET.md)
- **Streaming:** simulated 10 ms capture blocks, causal stateful FIR resampling
  where needed, native frame sizes, per-stream detector/resampler resets, no
  padding of incomplete final frames. Past context is preserved. Retrospective
  score intervals are separate from acquisition-time emissions
- **Endpointing:** shared threshold plus 200 ms trailing silence, no added
  padding or separate exit threshold. It replaces package-specific endpoint
  policies; inherent backend smoothing/hangover remains
- **Calibration:** choose thresholds and classic aggressiveness on development
  only, minimizing missed speech subject to at most 5 false activations per
  known-negative hour and at most 1% non-speech frame false positives. Freeze
  for holdout; fixed reference thresholds and development curves are also shown.
  An all-miss operating point is possible under this severe budget
- **Timing:** fresh sequential process per backend; warmup then one measured
  corpus pass. Wall RTF includes resampling, buffering, dispatch, adapter/API
  conversion and inference; excludes WAV reads and resets. Startup is adapter
  construction/integrity checks, not Python process launch. RSS includes Python,
  runtimes and retained traces, not just model memory
- **Provenance:** the nine-backend rerun used Python 3.12.14 on a shared Linux
  x86-64 Intel Xeon Platinum 8573C host. Runtime/build versions differ across
  adapters; this is not a common-kernel microbenchmark. Exact recorded metadata:
  [experiment.json](../results/silero-lite-comparison/experiment.json),
  [runs.json](../results/silero-lite-comparison/runs.json),
  [resource inventory](../results/silero-lite-comparison/resource-inventory.json)

### Limits that matter when reading a result

This is a small synthetic-domain comparison, not evidence of a universal VAD
winner or a production false-activation guarantee. Two TTS voices per split,
repeated phrases and less than an hour of holdout negative audio limit inference.
Preliminary holdout results were seen during validation before shared metric/grid
corrections; this was not a blinded or preregistered study.

Native score alignment is unknown for some backends and is left uncompensated;
that does not mean zero algorithmic latency. Notification delays use simulated
acquisition time and exclude compute scheduling. Read matched-event delays with
recall, missed speech, clipping, premature endings and fragmentation; a clipped
utterance can appear to end quickly. EOF-forced endings are excluded from latency.

The shared cloud CPU was not pinned or frequency-controlled. The main synthetic
comparison has one warmed timing pass, so it does not estimate run-to-run timing
uncertainty; the context ablation separately retains three passes. Do not mix
old/new timing rows as though they ran together. No power or live audio-device
measurements were made, and peak RSS is not model-only RAM.

For setup, run the relevant [synthetic instructions](RUN_SYNTHETIC.md) and
[Lite package setup](SILERO_LITE.md); retain the pinned assets and manifest.
Saved results and metric definitions are unchanged by this guide.
