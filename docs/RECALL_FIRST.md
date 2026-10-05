# Recall-first analysis

This is a separate analysis of the same 240-stream synthetic corpus. Historical strict false-event-budget results are retained unchanged. The [findings](../results/recall-first/FINDINGS.md) and standalone [Marimo explorer](../notebooks/README.md) report false-positive duration while pursuing 99%, 99.5%, 99.9%, and each classic mode's native development speech-frame recall.

## Reproduce the fresh run

Follow [the pinned setup](RUN_SYNTHETIC.md), including the separately accepted TEN terms and checksum-pinned runtime. Set `LD_LIBRARY_PATH` as documented for private native runtimes where required. Do not alter executable-stack or other security settings.

```sh
python -m vadbench.dataset --output data/recall-first --seed 20261002 --count 240
# Compare the entire regenerated manifest and every WAV/source hash to the committed corpus.
cmp data/recall-first/manifest.json results/silero-lite-comparison/dataset-manifest.json
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run \
  --manifest data/recall-first/manifest.json --output results/recall-first/raw
python -m vadbench.recall_first \
  --manifest data/recall-first/manifest.json --raw results/recall-first/raw \
  --output results/recall-first
python scripts/report_recall_first.py
python scripts/build_explorer_data.py
python -m unittest discover -s tests -v
```

Use a new output location for a new experiment rather than overwriting the committed results. Record the run date, host, toolchain, dependency/source hashes and dataset identity in `provenance.json`. The analyzer copies this file into `summary.json`. Verify every backend reports `status=ok`; missing runs fail rather than becoming fabricated measurements. Inference processes run sequentially to reduce self-contention. The reconstruction retained all twelve configurations, including all four binary classic modes.

## Selection protocol

1. Score each backend once and retain every trace. Use generic speech labels, excluding uncertainty and uncovered native-frame time, exactly as in the original metrics.
2. Compute each classic mode's native 0.5 development speech-frame recall. These four reference values plus the three fixed targets form seven target definitions. Store targets as exact rational counts.
3. For a probability backend, choose the highest strictly-positive score cutoff that captures the required number of development speech frames. This minimizes known-negative FP duration over **all positive cutoffs**, not only the plotted grid. Equal-score ties remain included. The highest feasible threshold gives the least speech-recall overshoot among equal-FP choices. False-event counts are not the optimization objective.
4. Classic binary backends retain only their native 0.5 point. A missed target is unattainable. For continuous scores, a target requiring exact-zero positive scores is also unattainable without the separate always-positive diagnostic.
5. Write all frozen thresholds before evaluating any holdout point. Apply each threshold unchanged to holdout. Report actual recall, raw FP fraction, FP seconds, false-event counts/rates, event recall, fragmentation and conditional endpoint metrics; never imply the development target was guaranteed on holdout.
6. Draw development curves on the historical grid extended down to 1e-12, plus each exact selected threshold. The display sweep does not constrain the optimizer. No holdout threshold sweep or holdout retuning is performed.

A positive score floor can also make a positive cutoff always-positive; the reported FP duration exposes this degeneracy. At threshold 0 all supported nonnegative scores are positive, giving 100% speech-frame recall and 100% FP time. This is a separately labeled diagnostic, excluded from operational selection and curves. One long detection can cover several utterances and still count as only one match, so frame recall and event recall differ substantially.

## Artifact contract

- `summary.json`: target definitions, 84 backend/target feasibility records, dev and frozen-holdout metrics, classic native references, zero diagnostics, fixed reference points, protocol and provenance
- `frozen-thresholds.json`: development-only choices written before holdout scoring
- `development-curves.json`: development frame/event metrics on the expanded positive sweep and selected thresholds
- `runs.json`, `raw/*.json`: measured startup/timing, adapters, hashes, host and streaming methodology
- `raw/*.npz`: retained score traces in the recovery bundle, ignored in Git to avoid bloating the repository
- `dataset-manifest.json`: exact original manifest; synthetic audio remains regenerable
- `historical-reference-deltas.json`: aggregate comparison of fixed-reference points to the old published-package run, without claims of bitwise score equality
- `INDEPENDENT_REVIEW.md`, `VALIDATION.md`: independent numerical and implementation checks

No distributions, native libraries, model binaries or real audio are redistributed. The original dataset and native/backend limitations apply, especially synthetic labels, limited voices and negative exposure, uncalibrated alignment for some adapters, and one-pass shared-host timing.
