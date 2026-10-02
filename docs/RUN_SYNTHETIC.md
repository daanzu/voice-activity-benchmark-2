# Run the synthetic streaming evaluation

The historical `bench.py`, `bench16.py`, `REPORT.md`, and original results are preserved. The new `vadbench` package is a separate, common-interface evaluation. Use Python 3.12 on Linux x86-64 with a C/C++ compiler, git, FFmpeg built with Flite, and network access for official packages/model sources. No paid services or accounts are required. Generated speech is synthetic; no human labeling occurs.

## Set up

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python scripts/setup_primary.py
python scripts/setup_native.py
python scripts/setup_fsmn.py
```

Review [native backend setup](NATIVE_BACKENDS.md) for compiler and TEN details. TEN requires separately accepting its additional license restrictions and providing its library; it is not silently downloaded or redistributed. Other model assets and native dependencies remain under ignored `.deps/`. Review [FSMN](FSMN_BACKEND.md) for exact frontend and raw-score semantics.

## Generate and evaluate

```sh
python -m vadbench.dataset --output data/synthetic --seed 20261002 --count 240
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run --manifest data/synthetic/manifest.json
python -m vadbench.report --manifest data/synthetic/manifest.json
python scripts/resource_inventory.py
python -m unittest discover -s tests -v
```

Generation refuses to overwrite an existing manifest. Preserve the seed, exact source generator, Flite/FFmpeg build, voice identities, and source hashes. Two complete generations matched byte-for-byte in the recorded environment; other Flite builds can synthesize differently and will produce different recorded hashes.

The runner launches each backend in a fresh sequential process. WAV input is read outside measured streaming processing. Every independent stream resets detector and resampler. Ten-millisecond capture blocks pass through a causal stateful FIR resampler if required. FIR interpolation overshoot is clipped to normalized [-1,1] and clipped sample counts are retained in each run. Native frame sizes are preserved; no incomplete final frame is padded. Scores retain source-aligned intervals and separate acquisition-time emissions. The benchmark is not an audio-device loop.

The reporter calibrates thresholds and classic WebRTC aggressiveness only on development data, then evaluates holdout without tuning. It writes `results/synthetic/summary.json`, development curves, exact dataset manifest, SVG plots, and `REPORT.md`. Large WAVs and compressed raw score traces stay ignored and are regenerated locally. A backend initialization failure is recorded as blocked, never a made-up measurement.

## Read the results correctly

- Ground truth is a clean-source activity proxy plus explicit uncertainty, not phonetic annotation
- Generic speech treats background voices as speech; foreground-only scores are a separate diagnostic
- FSMN is its neural posterior under the common controller, not the complete native energy/segmentation logic
- Common endpointing is a threshold and 200 ms trailing silence; package defaults are not equated
- Unknown native score alignment is disclosed; no undocumented lookahead compensation is claimed
- Notification delays use observed input time and are distinct from retrospectively aligned score timestamps
- Single-pass shared-host timings are indicative; no CPU affinity/frequency control or power measurement
- Peak process RSS includes Python/runtime and trace storage; model/package bytes are separate
- Synthetic holdout conclusions do not establish real-microphone generalization

See [DATASET.md](DATASET.md) for synthesis, split, label, uncertainty, license and reproducibility details.
