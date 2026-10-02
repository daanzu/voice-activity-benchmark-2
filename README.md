# Voice Activity Benchmark 2

A reproducible, **limited CPU-throughput experiment** for classic WebRTC VAD and two Silero ONNX models, plus a detailed seven-candidate research report in [REPORT.md](REPORT.md).

This is not a seven-backend accuracy benchmark. Only classic WebRTC and direct Silero ONNX inference were timed. No real-world VAD accuracy, boundary accuracy, power consumption, or end-to-end application latency was measured.

## Contents

- [REPORT.md](REPORT.md): full comparison, source references, measured results, and limitations
- `bench.py`: 8 kHz throughput and context diagnostic
- `bench16.py`: 16 kHz throughput and context diagnostic
- [`results/2026-10-02`](results/2026-10-02): historical measurements and exact methodology
- `tests/test_results.py`: dependency-free validation of historical results and script syntax
- [THIRD_PARTY.md](THIRD_PARTY.md): dependencies and attribution

## Reproduce

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

## Methodology

Recorded on 2026-10-02: Python 3.12.14, NumPy 2.3.5, ONNX Runtime 1.19.0 CPU provider, one intra-op and one inter-op thread, Linux x86-64, reported AMD EPYC 9V74 80-Core Processor. Shared cloud machine; no CPU affinity or frequency controls.

Each condition processes 60 seconds of one input: repeated upstream `test-audio.raw`, seeded uniform noise, or silence. The fixture is 8 kHz signed little-endian 16-bit PCM. For the 16 kHz run each sample is repeated twice; this is deliberately a throughput-only transformation, not realistic resampling. Classic WebRTC uses mode 2 and 10/20/30 ms frames; Silero uses 32 ms fresh chunks and 4 ms of past waveform context.

Each run creates a fresh detector outside timing. One complete run is discarded, then five runs are recorded. Timings include Python dispatch and state/context handling, but exclude startup, frame preparation, input conversion, audio capture, segmentation, and resampling. Recurrent model state is maintained across each stream.

`rtf` is median wall time / 60 seconds; smaller is faster. `us_call` compares different frame sizes and is not a direct end-to-end latency metric. The diagnostic compares the same older model with/without explicit context, holding inference runtime and input constant; it is not a run of the native lite implementation or an accuracy score. The fixture has no ground-truth labels here.

The retained `onnxCurrentContext` label means the pinned snapshot used on the measurement date, not a floating latest release. Historical logs have only their machine-local model-path prefixes removed. Scripts retain the measured algorithm, with unused/unreachable lite code removed and new JSON outputs redirected to `results/local` to protect the historical results.

## Extending this work

Before claiming an accuracy winner, implement each backend's canonical streaming contract, obtain labeled speech/noise datasets with documented rights and splits, tune thresholds on a separate development set, and compare false alarms/misses, boundary errors, and downstream behavior at matched operating points. Run native implementations on the intended deployment hardware, with warmup, repeatability controls, memory and power measurements as needed.
