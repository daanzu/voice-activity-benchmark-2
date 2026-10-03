# Validation: published Silero comparison

Executed on 2026-10-03, CPython 3.12.14, Linux x86-64, Intel Xeon Platinum 8573C.

- Rebuilt the 240-stream corpus. Manifest bytes, every source/audio hash, labels,
  and 96/144 development/holdout split match the original recorded manifest
- All 12 configurations completed: nine backend rows plus three additional
  classic aggressiveness candidates selected only on development
- Actual PyPI wheels for silero-vad-lite 0.3.0 and 0.4.0 installed in separate
  targets; wheel and every original installed payload file verified by SHA-256
- Both native package APIs executed in separate fresh processes, with no IPC
  added inside the measured frame loop
- Native ONNX Runtime version queried as 1.19.0 for both wheels. Model, wrapper,
  native binary and upstream source identities retained in the run metadata
- Both pinned native libraries have a read/write, non-executable GNU_STACK
- All **49 tests passed, zero skipped**, with all existing optional backend
  dependencies present, including TEN's explicitly supplied library
- Twelve dedicated lite tests include input contracts, conflicting imports,
  corrupted artifact/version rejection, native API parity, independent-instance
  and reset reproducibility, and an independent correctly contextualized ONNX oracle
- Four recorded-result regression tests validate the exact original dataset,
  complete nine-backend/twelve-configuration coverage, pinned package provenance,
  unchanged calibration protocol, paired clocks and timing arithmetic
- `python -m compileall -q vadbench scripts` and `git diff --check` passed
- Independent read-only review found and fixed a documentation command that
  would overwrite the old result directory; no remaining code/isolation blocker
- Both plots were generated from the new machine-readable results

The original adapters and metric/threshold code remain unchanged in behavior.
Some early workers' recorded source snapshots predate the new lite/report module
versions; these unused files do not alter those existing inference paths. The
per-worker hashes are preserved rather than replaced with post-hoc hashes.

Original historical and seven-backend result files are unchanged. New results,
including full per-stream wall/CPU/inference/resampling timings and provenance,
are retained in this directory. Large WAV and raw-score NPZ files remain ignored.
No model, wheel, compiled library, or third-party audio is redistributed.

CI now installs both checksum-pinned published wheels and ONNX Runtime before
unit tests, so the native package/context oracle checks run there. CI does not
rebuild every older optional backend or rerun the 80-minute corpus; those full
executions are established by the local run records, not by CI status alone.
