# Interactive benchmark explorer

[Open the recall-first interactive notebook in your browser](https://molab.marimo.io/github/daanzu/voice-activity-benchmark-2/blob/recall-first-tradeoffs/notebooks/explore_results.py/wasm?mode=read&show-code=false)

The notebook includes the **recall-first** reconstruction and preserves both historical result sets. The preview targets the `recall-first-tradeoffs` feature branch and reflects only the code published there. You can also run the file below or serve its WebAssembly export.

`explore_results.py` is a standalone [marimo](https://marimo.io/) notebook for the committed benchmark results. It starts with three detectors instead of an overlapping full field. No models, audio, native VAD libraries, benchmark reruns, or credentials are needed.

## Controls

- Start with **Recall-first**, or switch to the historical **Silero Lite comparison** or **synthetic evaluation**. Sets are never combined; historical CPU timings are from different runs/hosts
- In Recall-first, choose a **development speech-frame recall target**: 99%, 99.5%, 99.9%, or the native development recall of classic modes 0–3
- For classic-matched goals, **Include matched classic reference** adds that mode beside your selected detectors for direct FP comparison; uncheck it to show only your subset
- The default plot shows **actual frozen holdout recall versus FP duration**. Switch the x axis to FP seconds, FP minutes per known-negative hour, or false events per known-negative hour
- Inspect the expanded **development tradeoff**, **toward-zero log threshold sweep**, or **selected development points**. Stars mark the stored development selection for the chosen goal
- Use **Classic modes** with the native-reference view to compare all four binary modes; use the separate **Diagnostic only: threshold 0** view to inspect the always-positive boundary case
- Add/remove individual detectors with the searchable multiselect; use Small comparison, Silero family, Neural detectors, Classic modes, All, or None to reset the subset
- Historical sets retain their development, frozen holdout, fixed-reference, and performance views. The selected subset survives plot/metric/target changes
- Zoom by dragging a box or scrolling, pan with the Plotly toolbar, and double-click to reset. Axis bounds can fit the subset or show the full 0–100% range
- Hover for exact values/thresholds; click legend entries to hide, or double-click to isolate. Colors and dash styles stay stable as the subset changes
- Read the visible paired **development / actual holdout** table, including feasibility, frozen threshold, recall, FP duration and false-event rates. Unattainable goals have blank selected metrics, never invented zeroes
- Expand the exact source rows and download the chosen data as JSON; the provenance panel identifies the source files and reconstruction run

The direct ONNX `silero` and native Lite 0.4.0 have identical recorded accuracy curves in the historical package comparison. Their overlapping lines are expected; isolate one in the legend to inspect either. Their runtimes differ.

## Can I adjust it on GitHub?

**GitHub's ordinary `.py` file view is source-only.** A molab `/wasm` URL opens the notebook actually committed at the URL's branch in an interactive WebAssembly preview; the Python runs in your browser. No login is required for this public preview. Initial runtime/package downloads need internet access and may take a moment.

Per the [official GitHub guide](https://docs.marimo.io/guides/publishing/github/), replace `github.com` in the notebook URL with `molab.marimo.io/github` and append `/wasm`. Without `/wasm`, the preview is static. The optional marimo glance browser extension can also render interactive previews inside GitHub.

This file does not enable GitHub Pages or deploy a website. The preview link targets `recall-first-tradeoffs`; local changes and exported artifacts do not update that published branch. If the branch is deleted after merge, use `main` only after verifying the notebook exists there.

## Run locally

With [uv](https://docs.astral.sh/uv/) installed:

```sh
uvx marimo==0.25.1 run --sandbox notebooks/explore_results.py
# Editable notebook:
uvx marimo==0.25.1 edit --sandbox notebooks/explore_results.py
```

Alternatively, install `marimo==0.25.1 plotly==7.1.0` in a virtual environment and run `marimo run notebooks/explore_results.py`.

## Export an interactive HTML app

```sh
uvx marimo==0.25.1 export html-wasm notebooks/explore_results.py -o /tmp/vad-explorer --mode run
python -m http.server --directory /tmp/vad-explorer 8000
```

The exporter also requires uv to resolve imports. Open `http://localhost:8000`. The folder export needs HTTP serving; ordinary static `marimo export html` does **not** rerun Python when inputs change. For one downloadable HTML file, add `--single-file` and use an `.html` output path; CDN/runtime downloads still need internet. See [WebAssembly exports](https://docs.marimo.io/guides/exporting/webassembly_html/).

## Data and interpretation

Only committed `summary.json` and `development-curves.json` are read when generating the embedded snapshot. The notebook itself uses an embedded, lossless compressed JSON snapshot so opening a single `.py` in a browser does not rely on repository file mounting, raw-data downloads, CORS, or a moving `main` branch. Its provenance panel records source-file and dataset hashes.

- Recall-first selects the **highest strictly positive cutoff meeting the development speech-frame recall target** from exact speech-score order statistics. This minimizes FP duration and recall overshoot among feasible tied-FP cutoffs. All equal-score ties are included. The display grid does not limit the selected cutoff
- Classic outputs are binary. Their native 0.5 threshold is the only operational decision; lowering a positive cutoff does not create additional recall choices. Classic-matched targets require **at least the classic development frame recall**, not event recall or holdout recall; equal-score ties can overshoot the goal, so this is not a claim of exactly identical recall
- Targets are goals on development, not promises about holdout. The holdout table and warnings report achieved recall honestly, including target shortfalls. An unattainable positive-cutoff target has no selected threshold and no corresponding holdout point
- Threshold **0 is diagnostic only**, outside operational selection and positive-threshold curves. Its always-positive output can merge detections and reduce the false-event count while marking nearly all known-negative time positive. A legitimate positive cutoff can also produce all-positive output when scores have a positive floor; explicit saturation warnings flag such feasible but uninformative choices. Always read duration alongside event rates
- Threshold curves are **development only**. Stars mark already-frozen dev choices; exploring the display never recalibrates on holdout
- Holdout plots use stored selected or fixed-reference points. There is no holdout threshold sweep
- In the historical budget-first sets, all four classic modes have dev curves and fixed-reference holdout metrics, but only the dev-selected mode has a selected holdout/performance result. Unsupported selections are reported visibly; classic modes are never interpolated
- Fixed-reference thresholds use the benchmark's shared endpoint policy, not complete vendor-default detectors
- Runtime covers the entire corpus, not the selected accuracy split; it is a single warmed pass on a shared CPU without run-to-run uncertainty
- FP seconds equal false-positive scored frames × the dataset frame duration (10 ms). FP minutes per known-negative hour equal 60 × the FP fraction. These are duration metrics; false events count detector segments. Event recall counts matched speech segments and does not replace speech-frame recall
- Missing latency is unavailable, never zero. Signed end delay can be negative; lower can mean early cutoff. Interpret matched-event latency with recall, clipping and fragmentation
- Synthetic TTS and source-activity labels do not establish production microphone accuracy. Zero observed false events do not establish zero real-world rate

## Refresh the embedded results

```sh
python scripts/build_explorer_data.py
python scripts/build_explorer_data.py --check
```

These commands **do not run inference**. They rebuild/check the snapshot against source JSON exactly. To include another compatible result directory, pass repeated `--result-set DIRECTORY_NAME` arguments and update `DEFAULTS`/`LABELS` in the builder when making it the maintained default. A new backend should receive an explicit stable style in `STYLES`.

## Checks

```sh
python scripts/build_explorer_data.py --check
marimo check --strict notebooks/explore_results.py
python -m unittest discover -s tests -p '*explorer.py' -v
marimo export html notebooks/explore_results.py -o /tmp/explorer-static.html
marimo export html-wasm notebooks/explore_results.py -o /tmp/explorer-wasm --mode run
```

Snapshot and schema tests use only the standard library. Recall-first tests verify positive-only selection, frozen holdout thresholds, feasibility, exact target controls, actual holdout shortfalls, duration conversions, diagnostic separation, classic binary points, and unchanged historical sets. Synthetic minimal fixtures exist only inside tests; no fabricated measurements are written into recorded results. Execution/plot tests run when marimo and Plotly are installed; the dedicated CI job installs them and runs both exports. Neither job reruns benchmark inference for this explorer.
