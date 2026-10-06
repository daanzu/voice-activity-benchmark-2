# Independent boundary-methodology review

Review date: 2026-10-05. Scope: causal controller, turn matching, metric arithmetic,
development selection, failure handling, and the interpretation of simulated
acquisition latency. The reviewer inspected the implementation independently and
wrote the regression fixtures without changing the core implementation.

## Verdict

The implementation supports the stated limited synthetic experiment. No unresolved
core correctness blocker was found. It separates actionable event availability
from backdated source boundaries, retains failed turns in the primary denominator,
and freezes development-only choices before held-out metric evaluation. It does
not establish a production latency/error budget, a globally optimal controller,
real-device latency, or natural-conversation turn-completion accuracy.

## Independently checked

`tests/test_boundary_latency.py` contains **56 passing tests**, with hand-derived
event times and small deterministic traces. Coverage includes:

- Silence thresholds 0/32/64/100/150/200/300/500 ms, interrupted START confirmation,
  hysteresis equality, and missing score-coverage gaps
- Native 32 ms framing on a 10 ms capture clock, equal acquisition timestamps, and
  source-clock compensation that cannot advance event availability
- Silent/empty/all-positive inputs, subconfirmation EOF, active EOF censoring,
  and reference speech extending into an uncovered native tail
- Early-active START rejection, including delayed confirmation of earlier noise;
  first-fragment ownership; one-to-one matching; and merged-turn failures
- Internal-pause cuts, controller continuity, and an event confined to a pause
  that must not claim a turn's acoustic speech
- Premature END rejection, clipped source endpoints whose notifications arrive
  later, operational versus source-aligned clipping, and exact deadline equality
- Coherent nominal/possible/certain uncertainty calculations and strict JSON
  encoding of unavailable quantiles, plus 162 combinations checking ordered
  `certain <= nominal <= possible` envelopes at every deadline
- Nearest-rank failure-aware quantiles: with 20 turns, 19 finite responses reach
  P95, while 18 do not; no interpolation through infinity
- Reference-only negative exposure and uncertainty exclusion; one long false
  activation retaining nearly all negative time cannot hide behind an event count
  of one
- Distinct controller IDs for adjacent representable score thresholds
- Rejection of test records by controller selection, the native binary candidate
  grid, and Pareto/tie-breaking sensitivity to operational false-positive duration
- Rejection of missing, altered, or mismatched freeze metadata before selection
- A complete miniature analysis proving that all 13 selections are persisted
  before the first held-out metric evaluation; changing test scores from perfect
  to all-silent leaves controller selections and threshold choices unchanged

`tests/test_boundary_saved_metrics.py` additionally audits saved-result arithmetic
independently of the evaluator: per-turn coverage, deadline and joint-success
counts, nearest-rank quantiles, frozen-controller identity, exposure and duration
arithmetic, development policy optimality, all seven Pareto objectives, and the
uncertainty envelope over every retained candidate. All **seven saved-result
tests passed** against the corrected 1,632-candidate, 156-selection output.
The separate [result audit](RESULT_AUDIT.md) checks retained artifacts and
independently replays baseline controller events from the raw traces.

## Issues corrected during review

1. Possible uncertainty outcomes were initially gated by nominal success. They
   are now evaluated independently, so a nominally early boundary may still be
   possible within the predeclared uncertainty interval
2. Optimistic timing initially could use a hypothetical boundary incompatible
   with its observed first evidence or source endpoint. Both timing and evidence
   now use compatible bounds; explicit regressions cover the counterexamples
3. Non-exploratory analysis now requires matching frozen full/test manifest hashes,
   the exact held-out subset, the pre-scoring freeze stage, and explicit turn IDs
4. Documentation now distinguishes standalone first-episode END success from
   joint intact-turn success, which also rejects merges and fragmentation
5. False-positive duration complements false-event rate in reporting, development
   tie-breaking, and the frontier, preventing a nearly continuous activation from
   appearing inexpensive merely because it generates few START events
6. The retained-result audit found a further consistency bug: nominal success had
   allowed evidence/source-endpoint tolerance from the uncertainty lower bound,
   while possible/certain outcomes used strict hypothetical boundaries. This could
   make nominal success exceed possible success. Nominal START now requires first
   evidence extending beyond nominal onset; nominal END requires its source end
   to reach nominal offset. The original inconsistent result run was rejected and
   regenerated from unchanged raw inference, corpus, and candidate design. This
   was a metric-consistency correction, not controller tuning on test outcomes

## Interpretation constraints

- START/END times are simulated input-acquisition availability. Compute-completion,
  microphone/device buffering, scheduling, and application integration were not
  measured. Native overhang and undocumented native score alignment remain
- Source-aligned speech coverage describes controller episodes, not unprocessed
  detector-frame recall. Operational coverage begins at actual START availability
- First-episode END is deliberately strict about fragment rescue. A correct final
  END after an earlier cut does not repair that first episode. Standalone END may
  succeed for the first turn of a merge; joint intact-turn success cannot
- `internal_pause_cuts` counts END notifications delivered inside inserted pause
  intervals. A pause-induced END delivered after speech resumes can instead appear
  in premature-END/fragmentation counts
- All-turn latency and joint metrics are primary. Conditional successful-event
  latency alone is insufficient for ranking and can reward missed responses
- Every frontier and selected optimum is restricted to the declared candidate
  grid. No globally optimal threshold/controller or universal cost budget is claimed
- Split-disjoint voices/texts/seeds within this corpus do not make repeated variants
  independent or establish unseen-engine, natural-speech, multilingual, or
  real-microphone generalization. The voices were available in earlier experiments
- Both manifests and reference labels are read for integrity validation before
  selection. Only development observations influence threshold/controller choices

## Reproduce the review checks

```sh
source .deps/runtime-env.sh
python -m unittest discover -s tests -p test_boundary_latency.py -v
python -m unittest discover -s tests -p test_boundary_saved_metrics.py -v
python -m unittest discover -s tests -v
```

Final verification completed 2026-10-05 at 16:26 UTC: **all 229 repository tests
passed with zero skips** against the corrected result artifacts and regenerated
explorer snapshot. This includes the 56 causal/methodology tests and seven
saved-metric tests above. The configured runtime is necessary for optional native
model tests; an initial system-interpreter run lacked ONNX Runtime, which the
configured runtime resolved. The rejected first result run and its uncertainty
bug are documented above and in the independent result audit.

These are local code/data checks. Browser rendering and any remote CI/publication
verification are separate from this review; see the dedicated verification
artifacts for their actual status.

Reviewed core SHA-256:

- `vadbench/boundary_latency.py`: `e653f90fe1a93352627da4f10fc78263856da0361bf8d2a43cfc40a98e6d94d6`
- `vadbench/boundary_report.py`: `72be5bdd24872edc7e7dc4aa9f25253a6501e931cd3145129a20ab0664f31e5c`
- `tests/test_boundary_latency.py`: `65fecc1b9aca085c739a83e6c30f838836187b0317cca9b68431e8d9920cbbf3`
- `tests/test_boundary_saved_metrics.py`: `646ca130f24bc97432934202a41e8c73c8c32415e61d51281d09aa45f1fa45b1`
