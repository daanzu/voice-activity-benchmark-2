# Recall-first validation

This records checks against the reconstructed October 5, 2026 work, based on main `5bf4ae0f9d33ccb2375b0af2dd327d5b0959ad5d`. Remote commit verification, browser verification of the published WebAssembly preview, and exact-head GitHub Actions outcomes are recorded in the accompanying pull request after publication; this file does not pre-claim those outcomes.

## Input and inference

- All 240 generated stream WAVs and 56 source WAVs independently hash-match the original corpus
- Complete generated manifest byte-identical, SHA-256 `73b60d803250b52d2c5cdea7e3a6458a3cf6907a2c171e4610a4b0234cbed52a`
- 96 development streams, 144 holdout streams, 4,800 seconds total
- All 12 backend configurations completed fresh sequential inference, 05:39:51–05:46:49 UTC
- All 2,880 stream/backend pairs validated, with 4,350,000 finite probability/binary score frames in [0,1]
- Pinned source/model/wheel integrity verified; native contract tests passed, including TEN
- Actual inference modules stayed byte-identical to the base commit; no score alignment, endpoint, label or resampling change
- Direct Silero and Lite 0.4 exactly equal across all 150,000 frames and clocks; Lite 0.3 model differences reported separately
- AMD host, native rebuild hashes, and fresh runtime measurements retained in provenance; no lost October 4 measurements reused

## Selection and numeric audit

- 84 development-only backend/target choices, 72 feasible and 12 explicitly unattainable binary combinations
- Exact rational required speech counts and positive-score order statistics tested, including ties, zero scores, mixed/holdout rejection, near-zero positives, and exhaustive minimum-FP comparisons
- All thresholds frozen before holdout metrics were computed; threshold-zero diagnostics never selected
- Independent audit imports neither the selector nor benchmark metric functions
- All 84 choices and 168 unique dev/holdout metric points passed 17,946 independent comparisons with zero discrepancies
- Audit includes confusion counts, event matching, false-event rates and intervals, fragmentation, latency quantiles, diagnostics, fixed/native references, and exact classic target fractions
- See [independent review](INDEPENDENT_REVIEW.md) and its machine-readable audit output

## Tests and notebook

- Full repository suite: **112 tests passed, zero skipped** with all pinned optional backends and notebook dependencies installed
- All 28 explorer tests passed, covering historical data plus seven targets across six recall views and all twelve detector configurations
- Snapshot generation exactly matches committed source JSON and hashes
- `marimo check --strict` passed
- Static HTML and interactive WebAssembly exports passed
- `compileall` and `git diff --check` passed
- 52 historical result/inference/metric files checked byte-identical to the base commit

The independent audit can be repeated after restoring raw `.npz` traces from the recovery bundle:

```sh
python scripts/audit_recall_first.py
```

The bundle retains the full source and computed results, including raw traces, without redistributing models/native binaries or synthetic WAVs. The raw arrays remain ignored in Git. Local exported notebook files are verification artifacts; the Python notebook and embedded payload are the portable source.
