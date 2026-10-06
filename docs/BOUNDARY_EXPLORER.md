# Rapid speech-boundary results explorer

`notebooks/explore_boundaries.py` is a separate, standalone Marimo notebook for
`results/boundary-latency/summary.json.gz` (or the identical uncompressed
`summary.json`). It does not modify the historical
recall-first explorer. Its embedded, compressed JSON contains completed result
rows and their uncompressed-source SHA-256; opening it needs no models, audio, credentials,
repository filesystem, or benchmark rerun.

## Run and export

```sh
uvx marimo==0.25.1 run --sandbox notebooks/explore_boundaries.py
uvx marimo==0.25.1 edit --sandbox notebooks/explore_boundaries.py
uvx marimo==0.25.1 export html-wasm notebooks/explore_boundaries.py \
  -o /tmp/boundary-explorer-wasm --mode run
python -m http.server --directory /tmp/boundary-explorer-wasm 8000
```

Alternatively install `marimo==0.25.1 plotly==7.1.0` into a virtual environment.
WASM exports must be served over HTTP and download a browser runtime/packages.
A static `marimo export html` is a readable snapshot but cannot rerun Python when
controls change. This work does not publish a site or change any public preview.

## Explore

1. Choose the shared `common-200ms` or `common-0ms` baseline, or a stored frozen
   development policy. Policy labels come from the data, not a hard-coded ranking
2. Start with the small detector subset; add/remove detectors with the searchable
   multiselect or reset to All, None, Silero family, or Classic modes
3. The default plot shows held-out all-turn deadline success. Switch between START
   and first-episode END, failure-aware quantiles, joint intact success, or the
   boundary-uncertainty view with stored possible / nominal / certain success
4. The development error-versus-latency view shows evaluated controllers and the
   stored multi-objective Pareto markers. Stars show the chosen point on
   development. The plotted two-axis projection may not itself be Pareto-optimal
5. The condition view uses held-out subsets and the same frozen policy. It lists
   unreachable quantiles explicitly, including the number of reference turns
6. Paired development and frozen-test tables retain all-turn p50/p90/p95,
   successful observations, controller settings, and both source-aligned and
   operational speech recall. The error table retains raw counts, known-negative
   hours, false-start rates, and operational/source-aligned false-positive duration
7. Expand the exact-source panel to download selected raw metrics. Zoom, pan,
   hover, or isolate a detector in the Plotly legend

## Main-corpus gap caveat and supplementary controlled probe

The primary corpus's “50–800 ms pause” setting is an inserted gap between
**nonzero sample support**, not a gap between RMS speech-activity edges. Low-energy
Flite tails extend the activity-to-activity gap. In frozen test, inserted 50 ms
means measured RMS gaps of **401.625–508.4375 ms**; inserted 800 ms means
**1151.625–1258.4375 ms**. Development uses different voices and has different
ranges. The notebook shows the full development/test audit from
`results/boundary-latency/pause-gap-audit.json`, with its own source hash and a
verified primary-manifest identity. Do not interpret nominal onset failures from
early RMS-relative activity, including classic mode 0, as slow or wholly missed
responses; inspect early-active counts and boundary-uncertainty bands.

The **Supplementary diagnostic · actual short pauses** view reads completed rows
from `results/boundary-pause-probe/summary.json` (or `.json.gz`). It keeps the
primary study unchanged and separate. Choose an actual RMS-gap duration, STOP or
RESUME branch, the common 0/200 ms silence baseline, and the existing detector
subset. The figure shows all-turn deadline success; the table preserves actual
gap bounds, reference-turn counts, failure-aware quantiles, errors, and exposure.
The main operating-point dropdown does not apply to this view. Aggregate frozen
policy data, when present in the supplementary source, is never presented as
pause-specific data.

This controlled probe reuses the primary texts and voices. It is **not a new
independent holdout**, and no controllers are retuned on it. Speech is hard-gated
with artificial 1 ms transitions to create exact short activity gaps; gating and
splice artifacts limit realism. Four examples per subgroup make percentages
coarse. A STOP branch has no speech continuation: its duration label and gap bounds
refer to its paired RESUME horizon, not a next activity edge in STOP. The same four
stopped phrases repeat across pause settings. RESUME tests continuity across the
requested gap. Do not combine these diagnostic values with the primary
frozen-study metrics or treat either as a production ranking.

## Stored operating points

The notebook discovers every policy and its full display label from the completed
summary. The current analysis stores two shared baselines (`common-200ms` and
`common-0ms`) and 13 development-frozen selections per detector:

- `recall-priority`: maximum source-aligned speech coverage
- `joint-50-100`, `joint-50-200`, `joint-50-300`, `joint-50-500`
- `joint-100-100`, `joint-100-200`, `joint-100-300`, `joint-100-500`
- `joint-200-100`, `joint-200-200`, `joint-200-300`, `joint-200-500`

Each joint label gives the START and END deadline in milliseconds. It maximizes
intact-turn success on development at those deadlines, then uses the recorded
coverage/error tie-breaks. These are exploratory, predeclared design points, not
production error budgets. The held-out plots show the actual results of each
frozen choice; switching controls never recomputes or selects a controller on test.

## Interpretation

Every turn stays in the main deadline and failure-aware quantile denominators.
For example, p95 is unreachable if fewer than 95% of turns have a valid response;
it is never replaced by zero or the successful-subset p95. The explicitly labeled
conditional plot is diagnostic only.

The boundary-uncertainty view shows optimistic possible and conservative certain
success around strict nominal success. These are reference-timing sensitivity
bounds, not confidence intervals. Early-active START can fail the strict nominal
rule without being a slow response or wholly missed speech; inspect early-active
counts and these bands before interpreting low nominal success.

The first overlapping episode owns each turn. A premature END cannot be rescued
by a later fragment; END success therefore includes continuity, not just a final
offset timing comparison. Joint intact success also rejects fragmentation and
merging. Errors can overlap and are not a partition of all turns. Operational false-positive
duration also matters: one long false-active episode can hide behind a low false-START
event count. Select operational FP percentage or seconds as the frontier error axis.

A source boundary can be backdated. Its availability cannot: notifications use
causal input-acquisition time. Source-aligned recall and operational recall are
separate measurements. This is not measured wall-clock compute latency. The
shared baselines use score 0.5, no hysteresis, zero start confirmation, and
200 ms or 0 ms silence; 0 ms still requires negative evidence. They are not
complete vendor-default detectors. EOF never invents an END notification.

Development chooses controllers; frozen holdout only evaluates them. There is
no holdout controller sweep. Synthetic source-activity labels, reference-boundary
uncertainty, short negative exposure, and condition sample sizes limit inference.
These graphs do not establish a universal winner or production-microphone accuracy.

## Refresh and verify

```sh
python scripts/build_boundary_explorer_data.py
python scripts/build_boundary_explorer_data.py --check
marimo check --strict notebooks/explore_boundaries.py
python -m unittest discover -s tests -p 'test_boundary_explorer.py' -v
marimo export html notebooks/explore_boundaries.py -o /tmp/boundary-static.html
marimo export html-wasm notebooks/explore_boundaries.py \
  -o /tmp/boundary-wasm --mode run
```

The builder transparently reads plain JSON or a `.json.gz` fallback and hashes
the exact uncompressed JSON bytes. Its generated snapshot is identical whether
the source is compressed or not. The primary gap audit and completed controlled
probe are separately embedded and hashed; main metrics remain unchanged. It validates all-turn denominators, quantile reachability, false-start
exposure rates, and equal development/test controller settings. Unit tests contain
minimal synthetic fixtures only inside the test module; fixtures never become
recorded benchmark measurements or notebook snapshot data.
