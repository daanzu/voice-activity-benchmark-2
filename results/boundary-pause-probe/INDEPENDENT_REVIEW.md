# Independent hard-gated pause-probe review

Reviewed 2026-10-05. **PASS: no unresolved construction, controller-reuse, or
primary-study preservation blocker found.** All **254 repository tests passed,
with zero skips**, using the configured native runtime and the completed probe
artifacts. The frozen generator and primary scoring implementation were not
edited during this review.

## Scope and independent checks

The reviewer inspected `boundary_pause_probe.py`, its existing tests and protocol,
then added eight independent tests in `tests/test_boundary_pause_probe_review.py`.
Those tests do not import the probe generator, its activity helpers, or the
production evaluator.

- Checked all **112 emitted WAVs** for exact SHA-256 identity, mono PCM16 format,
  16 kHz rate, and eight-second duration
- Recomputed source-local activity from integer PCM with a separate implementation
  of the declared normalization and 10 ms RMS threshold. Every source's first and
  last frame remains active after cropping/tapering; emitted source hashes and all
  retained source/record/turn activity bounds agree
- Reconstructed each stream from its labeled emitted sources and verified there
  is no extra PCM elsewhere
- Independently measured all **56 resumed streams**. Each requested gap has eight
  examples across the two provenance splits, and the minimum and maximum measured
  RMS-frame gap both equal the request: **50, 100, 150, 200, 300, 500, 800 ms**.
  Every inserted gap sample is zero
- Checked all **56 stop/resume PCM pairs** byte-for-byte through the continuation
  acquisition horizon, including the retained prefix hashes
- Verified all 12 raw NPZ/metadata hashes and stream identities. Direct comparison
  of acquisition-aligned rows at or before each resume horizon passed for all
  **672 backend/pair combinations**
- Verified the complete factorial design, exact test-provenance subset, frozen
  manifest/specification/source-snapshot hashes, recorded implementation hashes,
  and primary frozen-selection identity
- Compared every one of the **156 policy references** with its primary frozen row:
  identical labels, backend and controller parameters. Together with 24 shared
  baseline references, these map to **114 unique backend/controllers**. There is
  no diagnostic threshold search, development frontier or reselection
- Checked aggregate denominators of 56 turns and all 336 baseline/pause/branch
  rows with four turns each. Paired-cut events fall in the declared half-open
  interval from prefix RMS offset to resumed RMS onset

## Primary study preservation

The primary scorer remains byte-identical:

`boundary_latency.py`: `e653f90fe1a93352627da4f10fc78263856da0361bf8d2a43cfc40a98e6d94d6`

The primary manifest, frozen selections, and logical bytes of the primary summary,
development curves and per-turn outcomes were verified against the identities
recorded before this supplement. In particular:

- Manifest: `9fba764ac3692dba68712e5b6ea78904288bc479cf44292c4a8a81ed089a7106`
- Summary: `2446067b8461a8f1cb5c3a9c6717e1268850381b8c4b118a00611d5627e13714`
- Curves: `ef6a2caf682e093543b0928c8365d239f7dca978cda7f0a33a36be3e5743dbcd`
- Per-turn outcomes: `85e5dccb505a328d8c1e0a12382ddfeb6e3653ab8ec59f8451ea7b05142769ad`

No primary measurements were replaced or relabeled. Freeze hashes establish
retained identity; they are not an independently attested wall-clock timestamp.

## Interpretation and disclosure

The supplement addresses a specific interpretation gap: the original requested
gap was measured between exact nonzero support, whereas the source-local RMS
activity could have a longer gap. This supplement deliberately excises faint
outer material and places the retained active frame bounds at the requested gap.
It does not retroactively make the primary corpus a short-RMS-gap experiment.

The exact gap claim is about the declared **source-local RMS frame proxy**, not
samplewise phonetic activity. The 1 ms taper includes zero-valued edge samples;
last-nonzero to next-nonzero distance need not equal the RMS-frame gap. The outer
±1 ms bands describe known synthetic gates, not human phonetic precision.

Cropping can remove speech content; hard gating and splicing can affect detector
responses even with a taper. The protocol and findings clearly disclose those
risks. They also correctly disclose that:

- Primary texts and voices are reused; this is not a fresh independent holdout
- Seven stopped rows per family contain identical audio, so 56 reported test turns
  are correlated variants of four prefix families, not 56 independent utterances
- There is no negative-only noise challenge set, so false activity in surrounding
  artificial silence does not establish noise robustness
- Acquisition-clock timing excludes real compute, microphone/device and
  application latency; natural conversational turn completion is not measured

The main findings and duration breakdowns are appropriate as a bounded,
artifact-sensitive diagnostic. They do not establish a universal production
hangover, a natural pause distribution, or a new winner chosen on these results.

## Reproduce

```sh
source .deps/runtime-env.sh
python -m unittest discover -s tests -p test_boundary_pause_probe_review.py -v
python -m unittest discover -s tests -v
```

Runtime WAV/NPZ data are intentionally not distributed in the normal checkout;
their dedicated independent tests skip when those local artifacts are absent.
All were present and checked in this review. Browser rendering, remote CI and
publication are separate verification stages.

Reviewed probe generator/snapshot SHA-256:
`4428ea5f9b78ea3bec22ea1e1a5399035247aef28c1118155b0cda170ad9e693`

Independent review-test SHA-256:
`baa3cc58564a1d992ad8ac945d8426807c7b59aa283f1c6aea65eddfb841c7a3`
