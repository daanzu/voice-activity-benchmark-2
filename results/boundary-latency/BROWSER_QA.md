# Boundary explorer browser QA

Date: 2026-10-05 UTC. Target: cloud browser; the user's computer was not used.

## Exact artifact and attempted URL

- Local URL: `http://localhost:2720`
- Repository base: PR #6 at `ab45ad3831769c07a0aa1451ce26ab7d34396c2f`; the new uncommitted notebook is identified by its source hash below
- Notebook: `notebooks/explore_boundaries.py`
- Notebook SHA-256: `26dca138d63c80874c5ec98a2bfe2084958e6c7e81adf0d09582b38d61444267`
- Completed source `summary.json` SHA-256: `2446067b8461a8f1cb5c3a9c6717e1268850381b8c4b118a00611d5627e13714`
- Packaged `summary.json.gz` SHA-256: `6baeada74cd1f268a2574f4f41da7cfd48aabb23993e944d57d32c098972ce71`

## Browser result: blocked before rendering

The attempted navigation was to the local notebook server shown above.
The cloud browser returned: `Browser Use cannot open http://localhost:2720 in tab 3. Browser reported: net::ERR_BLOCKED_BY_CLIENT`.
No alternate address, inspection route, or browser was used to bypass that block.
No page rendering or interactive browser assertion passed. Desktop/mobile screenshots, interactive START/END and policy controls, subset search/presets/all/none, view navigation, Plotly behavior, and source/download rendering remain **not browser-verified**.

## Independent non-browser checks: passed

Run from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_boundary_explorer.py' -v
.venv/bin/python scripts/build_boundary_explorer_data.py --check
```

The 23 explorer/snapshot tests passed, and the builder reported `Boundary snapshot matches completed source results`.
Coverage includes the actual 15 operating choices (13 frozen policies plus 2 shared baselines), START/END all-turn denominators, frozen dev/test controllers, uncertainty bands, unreachable versus undefined quantiles, conditional-view caveats, development-only frontier and operational-FP axes, per-condition rows, empty/single/all/repeated selections, stable colors, exact source hashing, and gzip/plain identity.
These assertions exercise notebook Python and Plotly objects, not browser event handling or visual layout. Execution emitted read-only user-cache/fontconfig warnings, but no test failed or notebook Python exception occurred.

Strict Marimo checking, static HTML export, and HTML-WASM export passed against the corrected embedding. Those export checks are separate from live browser interaction.

## Pre-publication supplemental snapshot

The notebook was subsequently extended with the controlled hard-gated pause view and the original corpus's measured-gap caveat. This new snapshot was not opened through another local route after the navigation block.

- Notebook SHA-256: `bf99016d885a9e74895549c41a0e2069dfc43fb6154b08fce61e962f39ec9320`
- Pause-probe logical summary SHA-256: `79e46c335d7be38861f33d4d4552b3270d000c301c6806536dcf7fcf978467e7`
- All 56 existing/new explorer tests, strict Marimo check, static/WASM exports and snapshot checks passed
- Public live-browser verification remains pending

## Remaining verification

When an authorized, verified public WASM URL is available, inspect the exact published commit in the cloud browser and append its URL/commit and observed checks here. Check desktop and narrow layouts if supported, repeated view/control/navigation flows, zero-selection and undefined-condition displays, and source/download controls. Do not treat successful static/WASM export alone as live browser QA.
