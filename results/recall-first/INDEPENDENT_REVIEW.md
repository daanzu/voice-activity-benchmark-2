# Independent recall-first review

Reviewed October 5, 2026 against the completed reconstruction, including every retained raw score file. No native inference was rerun for this review.

**Result: passed.** All 84 backend/target choices agree with an independent raw-score calculation: 72 feasible and 12 infeasible. There were **zero discrepancies** across 17,946 checks, including 168 distinct development/holdout metric points and 2,880 raw traces.

Audited `summary.json` SHA-256:

```text
8461f2b1ec21efc29f3b94630f015bac742d87b19bf34262c9e991262312a072
```

## Independent numerical method

[`scripts/audit_recall_first.py`](../../scripts/audit_recall_first.py) imports neither the benchmark selector nor its metrics implementation. It:

- Verifies the manifest and raw-trace hashes, completed backend status, record identities, finite bounded scores, ordered nonoverlapping intervals, and native binary values
- Reconstructs the specified 10 ms center grid and maps raw score intervals using Python binary search rather than the benchmark's NumPy alignment function
- Separately recomputes speech/non-speech labels, uncertainty exclusions, and coverage for each backend and split
- Sorts development speech scores rather than using the selector's partition operation, computes exact rational target counts, and checks every selected threshold with exact floating-point equality
- Verifies all 12 infeasible records, all 72 feasible records, classic reference target fractions, and identity between frozen and reported selections
- Independently recomputes every feasible selection's development and holdout confusion counts, recall, FP duration/fraction, known-negative exposure, and excluded time
- Independently reimplements the published 200 ms endpoint controller and descending-overlap one-to-one event assignment, checking false events, fragmentation, ambiguous events, event recall, conditional latency quantiles, premature notifications, forced EOF counts, rates, and Poisson intervals
- Rechecks zero diagnostics, maximum-positive-recall development points, classic native references, and fixed reference points

Counts, feasibility, hashes, and selected thresholds agree exactly. Derived floating-point metrics are compared with absolute and relative tolerance 1e-12. The audit deliberately preserves the benchmark's floating-point grid representation; it does not substitute a different boundary-rounding convention.

The full development display sweep is not independently rescored by this audit. Exact selection is checked directly from all development speech scores and therefore does not depend on that sweep.

## Mathematical selection review

Let `N` be the number of known, covered development speech frames and let the rational recall target be `a/b`. The required positive count is `k = ceil(a*N/b)`, computed with integers.

For probability scores sorted from largest to smallest, the kth score is the greatest threshold that can retain at least k speech frames under `score >= threshold`. Any strictly greater threshold retains fewer than k. Equal-score ties are included together; randomized tie splitting and recall interpolation are not used.

FP duration is nonincreasing as the threshold increases. Consequently, this greatest feasible threshold minimizes FP duration over all strictly positive cutoffs and also gives the least speech-recall overshoot among equal-FP solutions. It does not minimize false-event counts, which need not be monotonic.

A positive-cutoff solution exists exactly when at least k speech frames have positive scores. The selector correctly rejects targets requiring exact-zero speech scores. Binary classic modes use their explicitly restricted native 0.5 operating point. All 12 infeasible choices in this run are binary classic-mode choices; every requested target is feasible for each of the eight probability-score configurations.

The smallest selected positive threshold in this run is approximately 0.0003534555435180664. Selection is not limited by the display sweep's 1e-12 floor. Tests also cover positive scores below that display floor, exact zeros, tied scores, exact rational ceilings, mixed/holdout split rejection, and absent label support.

## Development/holdout separation

Source review confirms that the selector requires development-only records and indexes only those records' traces. All targets and thresholds are frozen before holdout metric evaluation; frozen selections and final selections are identical. Raw-file coverage/validity checking includes both splits, but no holdout score or metric determines a threshold.

These controls establish development-only numerical selection, not a claim that the study was blind or preregistered. Prior results were already observed, and the repeated synthetic benchmark remains a limited evaluation.

Holdout target shortfalls are real and retained. For each fixed target, direct Silero, both silero-lite versions, FSMN, and Speex achieve less holdout recall than the corresponding development target. The report must continue showing achieved holdout recall alongside FP cost.

## Exact support and comparison caveats

All twelve configurations have identical known speech support in this run: **37,187 development frames (371.87 seconds)** and **60,531 holdout frames (605.31 seconds)**. No backend loses a known speech frame through incomplete coverage.

| Support | Development | Holdout |
|---|---:|---:|
| Total stream duration | 1,920 seconds | 2,880 seconds |
| Uncertain label time | 156.39 seconds | 236.74 seconds |
| Known-negative time, all except FSMN | 1,391.74 seconds | 2,037.95 seconds |
| Known-negative time, FSMN | 1,387.90 seconds | 2,032.19 seconds |
| Additional uncovered known-negative time, FSMN | 3.84 seconds | 5.76 seconds |

FSMN's source-aligned shifted tail causes its additional uncovered negative time. All other configurations have zero uncovered known speech or known-negative frames on the evaluation grid. Thus speech-recall denominators are directly comparable here, while FSMN's negative denominator differs slightly. Raw FP seconds and the corresponding denominator should both remain visible.

“Classic parity” means **meeting or exceeding a classic mode's development recall**. It does not mean exact equality when scores tie, equal holdout recall, equal false-event rate, or a holdout-optimized minimum-FP comparison. Compare achieved holdout recall and FP duration together before making a model preference claim.

Threshold zero is always-positive on covered frames and remains excluded from selection. An always-positive stream can merge multiple reference utterances into one event, so perfect frame recall does not imply perfect one-to-one event recall or acceptable false-positive duration. Positive cutoffs can also be uninformative if all scores exceed them; a positive threshold alone is not evidence of useful discrimination.

## Tests and scope

The 19 selector tests plus six retained-result invariant tests pass: **25 tests, no failures or skips**. The retained tests are in [`tests/test_recall_results.py`](../../tests/test_recall_results.py).

From the repository root, with the documented dependencies installed and raw score bundle restored:

```sh
python scripts/audit_recall_first.py --results results/recall-first
python -m unittest tests.test_recall_first tests.test_recall_results -v
```

This review validates the retained measurements and stated selector objective. It does not independently validate human phonetic ground truth, unknown native score alignment, the statistical independence of synthetic streams, real-world generalization, historical bitwise score identity, or shared-host runtime comparability. Endpoint timing remains conditional on the published matching convention and excludes forced EOF endings from endpoint-delay statistics.
