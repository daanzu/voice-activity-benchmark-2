# Interactive benchmark explorer

[Open the interactive notebook in your browser](https://molab.marimo.io/github/daanzu/voice-activity-benchmark-2/blob/interactive-marimo-explorer/notebooks/explore_results.py/wasm?mode=read&show-code=false)

`explore_results.py` is a standalone [marimo](https://marimo.io/) notebook for the committed benchmark results. It starts with three detectors instead of an overlapping full field. No models, audio, native VAD libraries, benchmark reruns, or credentials are needed.

## Controls

- Pick the latest **Silero Lite comparison** or the earlier **synthetic evaluation**. Sets are never combined; their CPU timings are from different runs/hosts
- Add/remove individual detectors with the searchable multiselect; use Small comparison, Silero family, Neural detectors, Classic modes, All, or None to reset the subset
- Switch among development curves, threshold sensitivity, frozen holdout accuracy, fixed references, and performance plots. The selected subset survives plot/metric changes
- Zoom by dragging a box or scrolling, pan with the Plotly toolbar, and double-click to reset. Axis bounds can fit the subset or show the full 0–100% range
- Hover for exact values/thresholds; click legend entries to hide, or double-click to isolate. Colors and dash styles stay stable as the subset changes
- Expand the exact source rows and download the chosen data as JSON

The direct ONNX `silero` and native Lite 0.4.0 have identical recorded accuracy curves in the package comparison. Their overlapping lines are expected; isolate one in the legend to inspect either. Their runtimes differ.

## Can I adjust it on GitHub?

**GitHub's ordinary `.py` file view is source-only.** The link above opens the same GitHub-hosted notebook in molab's interactive WebAssembly preview; the Python runs in your browser. No login is required for this public preview. Initial runtime/package downloads need internet access and may take a moment.

Per the [official GitHub guide](https://docs.marimo.io/guides/publishing/github/), replace `github.com` in the notebook URL with `molab.marimo.io/github` and append `/wasm`. Without `/wasm`, the preview is static. The optional marimo glance browser extension can also render interactive previews inside GitHub.

This PR does not enable GitHub Pages or deploy a website. The preview link targets the PR branch so it works before merge. If that branch is deleted after merge, replace `interactive-marimo-explorer` with `main` in the link.

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

- Threshold curves are **development only**. Stars mark already-frozen dev choices; exploring the display never recalibrates on holdout
- Holdout plots use stored selected or fixed-reference points. There is no holdout threshold sweep
- All four classic modes have dev curves and fixed-reference holdout metrics, but only the dev-selected mode has a selected holdout/performance result. Unsupported selections are reported visibly; classic modes are never interpolated
- Fixed-reference thresholds use the benchmark's shared endpoint policy, not complete vendor-default detectors
- Runtime covers the entire corpus, not the selected accuracy split; it is a single warmed pass on a shared CPU without run-to-run uncertainty
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
python -m unittest discover -s tests -p test_explorer.py -v
marimo export html notebooks/explore_results.py -o /tmp/explorer-static.html
marimo export html-wasm notebooks/explore_results.py -o /tmp/explorer-wasm --mode run
```

Snapshot tests use only the standard library. Execution/plot tests run when marimo and Plotly are installed; the dedicated CI job installs them and runs both exports. Neither job reruns benchmark inference for this explorer.
