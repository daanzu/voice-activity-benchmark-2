# Independent retained-result audit

Executed 2026-10-05T16:21:36+00:00. Status: **PASS**.

Command: `python scripts/audit_boundary_results.py results/boundary-latency --raw`

The audit imports no production evaluator, controller, selector, or Pareto implementation.

## Verified

- Exact corpus manifest SHA-256: `9fba764ac3692dba68712e5b6ea78904288bc479cf44292c4a8a81ed089a7106`
- Exact test manifest SHA-256: `d92496d5f067835f07026989340ccf91b59c3d8157ac0499c426793f739a7154`
- Frozen references, code hashes, raw JSON metadata hashes and complete 12-backend status/record coverage
- 272 records; 120 development and 120 test turns. All full-test rows retain all 120 turns
- Integer nonnegative error counts, clipped-speech identities, false START exposure denominators, deadline fractions and monotonicity
- All-turn versus conditional quantile population/reachability, and exact quantiles/deadline numerators from retained per-turn outcomes
- Independently sorted all 156 development-only choices; exact frozen/dev/test controller identity
- Independently recomputed seven-objective Pareto membership for every development candidate
- All 1560 condition rows: no subgroup retuning, reference exposure, additive counts and deadline numerators
- 79 committed historical result/core-source files match historical-preservation.json
- 12 separately retained historical NPZ archives checked in raw-audit mode

## Independent raw replay

- All 12 NPZ hashes and all 272 trace identities per backend verified; source/acquisition clocks and score bounds checked
- Alternate sign-run oracle replayed both 0 ms and 200 ms common controllers on both splits: 5,760 turn evaluations
- All event/matching/count/deadline/quantile outcomes agreed; retained test events compared exactly
- Missed turns, early-active starts, premature first ends, fragmented turns and EOF censoring cannot become successful intact turns

## Candidate/frontier sizes

| Backend | Candidates | Pareto |
|---|---:|---:|
| classic-0 | 24 | 8 |
| classic-1 | 24 | 8 |
| classic-2 | 24 | 16 |
| classic-3 | 24 | 24 |
| silero | 192 | 169 |
| silero-lite-0.3.0 | 192 | 125 |
| silero-lite-0.4.0 | 192 | 169 |
| agc2 | 192 | 101 |
| ten | 192 | 122 |
| fsmn | 192 | 115 |
| rnnoise | 192 | 132 |
| speex | 192 | 65 |

## Audited result identities

- Original `summary.json` bytes: `2446067b8461a8f1cb5c3a9c6717e1268850381b8c4b118a00611d5627e13714`
- Original `development-curves.json` bytes: `ef6a2caf682e093543b0928c8365d239f7dca978cda7f0a33a36be3e5743dbcd`
- Original `per-turn-test.json` bytes: `85e5dccb505a328d8c1e0a12382ddfeb6e3653ab8ec59f8451ea7b05142769ad`

- Compressed storage `summary.json.gz` bytes: `6baeada74cd1f268a2574f4f41da7cfd48aabb23993e944d57d32c098972ce71`
- Compressed storage `development-curves.json.gz` bytes: `7552270668a045e8fe8484882d41c8442f3cf35c5775b6305cdd570effdced90`
- Compressed storage `per-turn-test.json.gz` bytes: `c5464ebe3e35ec2f16f6f83f756040529061a2f49c98c22b152f2241b9dc1f4b`

## Scope limits

Arithmetic agreement does not validate synthetic labels as human phonetic truth, native model alignment as ground truth, or transfer to natural speech. Selected-controller per-turn JSON is checked for consistency; raw replay independently covers the shared 0.5/no-confirmation/no-hysteresis controls, not the entire development grid. Signed source-alignment errors may legitimately be negative; response delays and clipping may not. Freeze-file contents establish retained input identity, not independently attested wall-clock chronology. Historical provenance checks cover result files and core source, not intentionally edited documentation, CI or ignore rules.

## Invariant failure found and corrected

The first result-generation attempt failed this independent audit because nominal boundary successes could exceed the claimed possible-band successes. For example, the development classic-0 controller with 64 ms START confirmation and zero trailing silence reported 24/120 nominal START-within-50-ms successes but 0/120 possible successes. The nominal calculation had used lower uncertainty limits for evidence eligibility while sensitivity calculations used a stricter hypothetical-boundary family.

The corrected implementation requires START first-evidence end after the nominal onset and END source endpoint at or after the nominal offset. Uncertainty alternatives use the same boundary family. The corpus, raw inference, development grid and declared selection priorities were unchanged; development selection and test scoring were regenerated after the correction. The final audit retains the original certain ≤ nominal ≤ possible assertion and passes it for all retained metric rows. This is a post-outcome implementation correction, not evidence that the final analysis was never inspected.

## Dependency-light packaging validation

`python -S -m unittest tests.test_boundary_results -v`: all 18 tests passed, including the retained full-result audit. Python site-package initialization was disabled.

A temporary clean audit input tree was also verified using only the three compressed large JSON files, the required small metadata/source files, and the 79 historical committed files. It contained no `.npz` archives, no uncompressed summary/curve/per-turn JSON, and no recovery-only manifest. The retained audit passed and reconstructed exactly the original logical artifact SHA-256 hashes listed above. The final in-place gzip artifacts were separately checked for byte-identical decompression and zero creation timestamps.
