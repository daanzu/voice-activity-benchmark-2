# Voice Activity Benchmark 2

Reproducible CPU voice-activity experiments: a **nine-backend synthetic streaming comparison**, a controlled Silero context ablation, and a retained historical throughput study. The synthetic tests measure source-activity detection and simulated streaming behavior; they do **not** establish real-microphone accuracy or device-to-application latency.

Start with the [comparison results](results/silero-lite-comparison/REPORT.md), [interactive explorer](notebooks/README.md), or [backend and methodology guide](docs/BACKENDS.md).

## Backends tested

These are the actual execution paths in the synthetic comparison. An available Python package is not necessarily the implementation tested. The original seven backend families plus two published Silero Lite versions produce nine comparison entries; classic WebRTC's four aggressiveness modes are tested separately before development-only selection.

| Backend / result ID | Implementation actually tested | Native input per call | Python package availability and use |
|---|---|---|---|
| Classic WebRTC · `classic-0`…`classic-3` | Source-built `webrtcvad-wheels` 2.0.14 C extension | 10 ms at 16 kHz | Community `webrtcvad` / `webrtcvad-wheels`; pinned source build used |
| Silero · `silero` | Official v6.2 weights, direct NumPy + ONNX Runtime 1.19.0 | 32 ms at 16 kHz + 4 ms past context | Official `silero-vad` exists; its package API was not used |
| Silero Lite 0.3.0 · `silero-lite-0.3.0` | Published native wheel, bundled v5.1 model | 32 ms at 16 kHz + 4 ms past context | Third-party `silero-vad-lite` 0.3.0; actual package API used |
| Silero Lite 0.4.0 · `silero-lite-0.4.0` | Published native wheel, bundled v6.2 model | 32 ms at 16 kHz + 4 ms past context | Third-party `silero-vad-lite` 0.4.0; actual package API used |
| WebRTC AGC2 RNN · `agc2` | Historical extraction, compiled C++ via repo `ctypes` adapter | 10 ms at 24 kHz | Community `py-webrtcrnnvad` exists; not used |
| TEN · `ten` | Upstream prebuilt Linux library via repo `ctypes` adapter | 16 ms at 16 kHz | Official Python wrapper / `ten-vad` exists; wrapper not used |
| FSMN · `fsmn` | Official ONNX model + repo frontend, ONNX Runtime 1.19.2 | 10 ms at 16 kHz; 25 ms analysis window | Official `funasr` / `funasr-onnx` exist; package APIs not used |
| RNNoise · `rnnoise` | Source-built C library via repo `ctypes` adapter | 10 ms at 48 kHz | Third-party `pyrnnoise` exists; not used |
| SpeexDSP · `speex` | Source-built C preprocessor via repo `ctypes` adapter | 20 ms at 16 kHz | Community bindings exist; the documented `speexdsp` EchoCanceller is not this VAD |

Important qualifications:

- AGC2 is a **historical third-party extraction**, not current WebRTC or the full audio-processing pipeline
- FSMN exposes raw neural posteriors with centered feature stacking, not FunASR's energy/SNR gates or native endpointing; its first valid score arrives at 50 ms
- RNNoise timing includes the **full denoising call**; Speex runs with VAD and denoising on, AGC off, using its integer-percent probability
- TEN uses a hash-pinned prebuilt library with additional license restrictions; exact native score alignment is uncalibrated for TEN, AGC2, RNNoise and Speex
- All backends share benchmark endpointing. Frame size, past context, lookahead and notification latency are different quantities

See [exact versions, package sources, adapter caveats and shared methodology](docs/BACKENDS.md) for the details behind this table.

## Experiments and results

The common-interface seven-backend extension is documented in [docs/RUN_SYNTHETIC.md](docs/RUN_SYNTHETIC.md). It generates 80 minutes of split-disjoint synthetic scenarios with known source placement, explicit activity-label uncertainty, development-only calibration, and a held-out evaluation. See [the synthetic results](results/synthetic/REPORT.md). Historical measurements below remain unchanged.

The [published Silero package comparison](results/silero-lite-comparison/REPORT.md) adds actual `silero-vad-lite` **0.3.0 and 0.4.0** native wheels and reruns all seven previous backends on the identical corpus. See [package isolation, model provenance, and reproduction](docs/SILERO_LITE.md). Both new releases already include the context/reset correction; 0.4.0's model is byte-identical to the existing direct-ONNX baseline.

The [v5.1 context-only ablation](results/context-ablation/REPORT.md) isolates the waveform-context correction using the same model, runtime, labeled corpus and controller, with the 64-sample preceding waveform prefix omitted versus enabled and reset behavior held constant. At a fixed 0.5 threshold, synthetic holdout missed speech falls from 31.36% to 7.30%; strict development-calibrated results, paired uncertainty, boundary metrics and three timing passes are also reported. The missing-context arm emulates the old input/state contract; it does not execute the old 0.2.1 native wheel. See the [independent validation](results/context-ablation/INDEPENDENT_REVIEW.md). These results do not establish real-microphone generalization.

## Interactive comparisons

Use the [marimo notebook](notebooks/README.md) to compare a smaller detector subset with searchable selection, presets, stable colors, exact-value tooltips, and zoomable development/holdout/performance graphs. It reads saved results only; no benchmark rerun is needed. [Open the interactive browser preview](https://molab.marimo.io/github/daanzu/voice-activity-benchmark-2/blob/interactive-marimo-explorer/notebooks/explore_results.py/wasm?mode=read&show-code=false). GitHub's ordinary file view is static; this link runs the notebook in your browser.

## Contents

- [docs/BACKENDS.md](docs/BACKENDS.md): tested implementations, Python package options, shared methodology, and limitations
- [REPORT.md](REPORT.md): historical seven-candidate research report and limited throughput measurements
- `bench.py`: 8 kHz throughput and context diagnostic
- `bench16.py`: 16 kHz throughput and context diagnostic
- [`results/2026-10-02`](results/2026-10-02): historical measurements and exact methodology
- `tests/test_results.py`: dependency-free validation of historical results and script syntax
- [THIRD_PARTY.md](THIRD_PARTY.md): dependencies and attribution

## Historical throughput experiment

The original experiment timed only classic WebRTC and two directly loaded Silero ONNX models. It had no labeled accuracy evaluation. Its commands, measurements and methodology remain below; use [RUN_SYNTHETIC.md](docs/RUN_SYNTHETIC.md) for the newer streaming comparison.

### Reproduce

Use Linux x86-64 with Python 3.12 and a C compiler for the closest match to the recorded environment. Commands require network access and install upstream packages; run in an isolated virtual environment. No model binaries, audio fixtures, or third-party compiled code are bundled.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install setuptools

git clone https://github.com/daanzu/py-webrtcvad-wheels.git
git -C py-webrtcvad-wheels checkout e8fb8b736111631ae8aa6f29fc9b7498ce893ccf
(cd py-webrtcvad-wheels && python setup.py build_ext --inplace)
python -m pip install --target packages numpy==2.3.5 onnxruntime==1.19.0 silero-vad-lite==0.2.1
curl --fail --location https://raw.githubusercontent.com/snakers4/silero-vad/1e261b036686cd0017d500ee96acd1c4ba572a9d/src/silero_vad/data/silero_vad.onnx -o silero_current.onnx
python verify_models.py
mkdir -p results/local
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python bench.py | tee results/local/bench-output.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python bench16.py | tee results/local/bench16-output.txt
python -m unittest discover -s tests -v
```

The lite package supplies its bundled model; its native library is neither imported nor executed by these scripts. Verify model hashes before running. These commands reproduce the experiment, not the exact wall-clock values; shared-host scheduling and hardware affect timings. The original compiler invocation was not retained.

### Methodology

Recorded on 2026-10-02: Python 3.12.14, NumPy 2.3.5, ONNX Runtime 1.19.0 CPU provider, one intra-op and one inter-op thread, Linux x86-64, reported AMD EPYC 9V74 80-Core Processor. Shared cloud machine; no CPU affinity or frequency controls.

Each condition processes 60 seconds of one input: repeated upstream `test-audio.raw`, seeded uniform noise, or silence. The fixture is 8 kHz signed little-endian 16-bit PCM. For the 16 kHz run each sample is repeated twice; this is deliberately a throughput-only transformation, not realistic resampling. Classic WebRTC uses mode 2 and 10/20/30 ms frames; Silero uses 32 ms fresh chunks and 4 ms of past waveform context.

Each run creates a fresh detector outside timing. One complete run is discarded, then five runs are recorded. Timings include Python dispatch and state/context handling, but exclude startup, frame preparation, input conversion, audio capture, segmentation, and resampling. Recurrent model state is maintained across each stream.

`rtf` is median wall time / 60 seconds; smaller is faster. `us_call` compares different frame sizes and is not a direct end-to-end latency metric. The diagnostic compares the same older model with/without explicit context, holding inference runtime and input constant; it is not a run of the native lite implementation or an accuracy score. The fixture has no ground-truth labels here.

The retained `onnxCurrentContext` label means the pinned snapshot used on the measurement date, not a floating latest release. Historical logs have only their machine-local model-path prefixes removed. Scripts retain the measured algorithm, with unused/unreachable lite code removed and new JSON outputs redirected to `results/local` to protect the historical results.

## Extending this work

Before claiming a production accuracy winner, validate the integrations on labeled real speech/noise datasets with documented rights and splits. Tune on separate development data and compare false alarms/misses, boundary errors, and downstream behavior at matched operating points. Include complete package-default pipelines where relevant, and run on the intended deployment hardware with repeatability controls, memory and power measurements as needed.
