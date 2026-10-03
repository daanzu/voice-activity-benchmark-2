# Published silero-vad-lite package comparison

This extension adds **two distinct backends** to the original seven-candidate
synthetic suite: `silero-lite-0.3.0` and `silero-lite-0.4.0`. It executes the
published native PyPI wheels through their Python package API. The direct ONNX
`silero` adapter remains unchanged as a separate baseline.

## Set up and run

Use the existing [synthetic setup](RUN_SYNTHETIC.md), then install both packages:

```sh
. .venv/bin/activate
python scripts/setup_silero_lite.py
python -m vadbench.dataset --output data/synthetic --seed 20261002 --count 240
# Skip generation if this immutable dataset already exists.
# Set VADBENCH_TEN_LIB and any private runtime library path as documented for TEN.
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run \
  --manifest data/synthetic/manifest.json --output results/silero-lite-comparison/raw
python -m vadbench.report --manifest data/synthetic/manifest.json \
  --raw results/silero-lite-comparison/raw --output results/silero-lite-comparison
python scripts/resource_inventory.py \
  --output results/silero-lite-comparison/resource-inventory.json
python -m unittest discover -s tests -v
```

The published comparison used CPython 3.12.14 on Linux x86-64. Wheels and model
assets remain ignored under `.deps/`; no native binary is redistributed. Each
package version has its own installation target. Every backend runs in a fresh,
sequential Python process. A single-version guard prevents accidentally loading
both lite native implementations into one process. This avoids Python import
cache and shared-library symbol collisions without adding per-frame IPC to the
measured path.

## Model and runtime provenance

| Path | Model | Model SHA-256 |
|---|---|---|
| Existing direct ONNX `silero` | Pinned newer Silero | `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3` |
| Published lite 0.3.0 | v5.1 | `2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f` |
| Published lite 0.4.0 | v6.2, from upstream v6.2.3 | `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3` |

Both tested CPython 3.12 manylinux x86-64 wheels contain the same native-library
SHA-256: `0e65d68994ce43439ac1aecd564e3a6ba3f71135c4b77248440e1d3c123d9cf9`.
The wheel SHA-256 values are:

- 0.3.0: `da7798f61ea453b3880d7002d45ab8745a6850697c68ac71e880f81f4e42fe8a`
- 0.4.0: `bc2e57848ea923aff771df720a3155f41c89696ca85014303398dcb881d1a287`

The installed package metadata, wheel origin, hashes, model and native runtime
provenance are retained in each run. Both lite native libraries were built with
ONNX Runtime 1.19.0; the direct `silero` row uses the Python ONNX Runtime 1.19.0
CPU provider. This version agreement does not imply identical runtime builds or
call overhead. FSMN separately uses ONNX Runtime 1.19.2 and is not conflated with
the Silero runtime comparison.

Sources: [0.3.0 on PyPI](https://pypi.org/project/silero-vad-lite/0.3.0/),
[0.4.0 on PyPI](https://pypi.org/project/silero-vad-lite/0.4.0/),
[package source](https://github.com/daanzu/py-silero-vad-lite), and
[existing model source pin](https://github.com/snakers4/silero-vad/tree/1e261b036686cd0017d500ee96acd1c4ba572a9d).

## Fairness and interpretation

- Both releases already contain the 4 ms waveform-context and reset correction.
  **No context-fix accuracy improvement can be inferred from this comparison**
- 0.3.0 versus 0.4.0 compares the changed model with an identical native library
  on the tested platform; 0.4.0 versus direct `silero` compares the wrapper/runtime
  path using an identical model
- All three Silero paths consume normalized float32 mono at 16 kHz, with 512
  fresh samples per inference. Lite itself supplies the 64 past-context samples;
  the adapter must not prepend another 64
- The common runner owns 10 ms input capture, buffering, resampling, score clocks,
  a 200 ms endpoint controller, and per-stream resets. Package endpoint defaults
  are not compared. No extra padding or future waveform context is introduced
- All thresholds use the unchanged development-only grid and budget. The exact
  96/144 split, every audio/source hash, and all labels match the original 240
  streams, manifest SHA `73b60d803250b52d2c5cdea7e3a6458a3cf6907a2c171e4610a4b0234cbed52a`
- All original backends are rerun on the same current host. Timings are a single
  warmed corpus pass, sequential and unpinned; do not compare the new rows against
  old-run timing as though they ran together
- `inference_s` includes the complete Python adapter and package API, validation,
  conversion/copies, native inference, and state management. Wall RTF also
  includes the common buffering/resampler. Neither number is pure neural-kernel
  time; acquisition-time endpoint latency excludes compute scheduling
- The report retains paired score differences for model-equivalent paths instead
  of presuming bitwise equality. RSS includes Python/runtime and accumulated
  traces; downloaded wheel size, installed size and model bytes are different
  measures

See the [new nine-backend report](../results/silero-lite-comparison/REPORT.md).
The [original seven-backend results](../results/synthetic/REPORT.md) and older
throughput experiments are retained unchanged.
