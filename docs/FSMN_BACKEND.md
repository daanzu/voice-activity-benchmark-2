# FSMN frame-posterior backend

## Run

```sh
python scripts/setup_fsmn.py
python -m unittest discover -s tests -p test_fsmn.py -v
```

`vadbench.fsmn.FsmnAdapter` (also `FSMNVAD`) exposes `sample_rate=16000`,
`frame_samples=160`, `process(float32_mono_frame) -> float`, `reset()`, and
`metadata`. Pass `model_dir=` to use another location containing the same pinned
artifacts. Invalid shapes, NaN/Inf and out-of-range normalized samples raise errors.
No account, paid API, GPU, PyTorch, model export, or FunASR install is needed.
Only the setup script accesses the network. Runtime validates all three model files.

## Model and source provenance

- Official model: [funasr/fsmn-vad-onnx](https://huggingface.co/funasr/fsmn-vad-onnx/tree/f6e9fbb4cefa7397216c763f21307993f147f585), revision `f6e9fbb4cefa7397216c763f21307993f147f585`. The official model card labels this model Apache-2.0. The full float model is used, not the quantized variant.
- Canonical frontend: [FunASR frontend.py](https://github.com/modelscope/FunASR/blob/66d7a4c264a5993a2a63ed00c1f402c296ee521a/runtime/python/onnxruntime/funasr_onnx/utils/frontend.py), source revision `66d7a4c264a5993a2a63ed00c1f402c296ee521a` (MIT). This adapter independently implements the small streaming orchestration around Kaldi features and ONNX inference.
- Posterior interpretation: [FunASR e2e_vad.py, GetFrameState](https://github.com/modelscope/FunASR/blob/66d7a4c264a5993a2a63ed00c1f402c296ee521a/runtime/python/onnxruntime/funasr_onnx/utils/e2e_vad.py). The supplied configuration sets `sil_pdf_ids: [0]`; native code computes speech mass as `1 - sum(silence_pdf_scores)`.
- Kaldi native features: `kaldi-native-fbank==1.22.3`, Apache-2.0; [official source](https://github.com/csukuangfj/kaldi-native-fbank). CPython 3.12 Linux x86-64 wheel SHA-256: `f16e74372fe9e20abb4183f98a8e2288d5ee4c48d04d94b6160311170e007661`.
- Runtime: `onnxruntime==1.19.2`, MIT; NumPy `1.26.4`, BSD-3-Clause. The setup script pins these direct versions and records the actual platform-specific PyPI wheel URLs, SHA-256 hashes, and transitive dependencies in `.deps/fsmn/pip-install-report.json`. Transitive dependencies are resolved by pip rather than a cross-platform lock.

Pinned artifacts, verified before loading:

| File | SHA-256 |
|---|---|
| model.onnx | 756887ce01695a9bb00dd85ca0f743653de03b18ba54d2e9ef4f4bb9b3edbf9f |
| vad.mvn | 6820fef9687708c4fc3fab2530179c8fcea6262daa25514380056cd8f6eb1754 |
| vad.yaml | db524c680b80b0ea0a617110f6a269019da9fe4db1c38500f7552aeb6fad08b4 |

## Frontend, cache and timing contract

The model's own configuration requires 16 kHz audio, 80-bin log filterbanks,
25 ms Hamming windows every 10 ms, zero dither, snipped edges, 32768 PCM scaling,
a centered five-frame stack with stride one, and its supplied 400-dimensional
mean/variance transform. Two copies of the first feature pad the left edge.
Two genuinely observed future feature frames supply right context; they are
never synthesized during streaming. Four 128-by-19 FSMN caches persist between
calls and are zeroed on reset. The network itself has `rorder=0`.

The first feature stack needs the first 45 ms of audio. With this adapter's
10 ms input chunks, its first posterior becomes available at 50 ms, on call 5.
That posterior belongs to the nominal [0,10) ms model hop. Each following score
is emitted every 10 ms with the same **40 ms delay relative to its hop's end**.
Metadata therefore supplies `score_delay_s=0.04`, `valid_after_s=0.05`, and
`warmup_frames=4`. Calls 1–4 return a sentinel 0.0; they are not network scores.
Use `score_valid` or warmup metadata to exclude these values from quality metrics.
`score_frame_index` identifies the latest valid zero-based model hop.

Retrospective frame metrics may align scores to nominal model hops, but live
notification/latency must use the actual input-acquisition time. Reporting only
neural compute time would hide 40 ms of frontend/chunk delay. The 25 ms analysis
window itself is not a causal [0,10) ms classifier: it observes beyond that hop.
There is no end flush: four final input hops have no own model posterior before
end-of-stream. No retrospective padding is used to create live decisions.
Feature storage is popped incrementally, and the remaining context queue stays
at four vectors. Reset discards frontend audio, features, counters and model state.

## What is, and is not, measured

This is a real streaming **neural frame speech posterior**, `1 - p(class 0)`.
It intentionally omits FunASR's native energy/SNR gates, adaptive noise statistics,
200 ms vote window, 150 ms transitions, 800 ms silence termination, and boundary
extension rules. A shared benchmark threshold/controller therefore compares raw
model scores under shared endpointing, not each package's out-of-the-box detector.
The native configuration's `speech_noise_thres=0.6` compares speech mass with
noise mass plus 0.6 (approximately a speech threshold of 0.8), not a simple
speech-probability threshold of 0.6. Thresholds need calibration on held-out speech.
In particular, all-zero audio initially produces raw scores around 0.6, which the
native energy gate would suppress. Do not present this backend as native FunASR
segmentation or interpret a common 0.5 threshold as equally calibrated.

## Executed verification

On the Linux CPU workspace, 2026-10-02:

- Three integration tests passed: exact reset reproducibility and warmup/input
  validation; per-hop cached ONNX scores versus batched inference on independently
  constructed fully observed features (absolute tolerance 3e-6); deterministic
  common-prefix processing and bounded feature/model cache dimensions
- Official model example `asr_example.wav`, SHA-256
  `a1bd32dc78493c123f9625a66deee562aed2895f53fbc39f2cca3be7e6f4f20f`:
  5.54 seconds / 554 input hops, ORT 1.19.2; valid raw scores ranged from 0.20348
  to 0.999989. A single untuned smoke run took 0.0700 seconds (RTF 0.01264).
  This is a functionality check, not a rigorous cross-backend speed result.
- No ground-truth labels are claimed for that example; these checks establish
  inference, timing/state behavior and streaming/batch consistency, not accuracy.
- A separate cross-check loaded the actual pinned official `WavFrontend` source,
  ran its `fbank` plus `lfr_cmvn`, cast features to float32 as the official ONNX
  wrapper does, and compared the common fully observed prefix against this
  adapter. Maximum score difference was exactly 0.0 on a seeded one-second
  input. This excludes offline right-edge replicated frames from the comparison.
