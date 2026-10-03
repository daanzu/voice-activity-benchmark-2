# Independent review: Silero v5.1 waveform-context ablation

Reviewed 2026-10-03 against the six retained inference runs, `summary.json`,
and the generated human-readable report.

## Verdict

**No blocking correctness or fairness issue found in the context-only experiment.**
The disabled arm faithfully emulates the released 0.2.1 model-input contract, and
the enabled arm reproduces the corrected 0.3.0 scores exactly on this corpus.
This supports attributing the measured paired accuracy change to waveform context
under the stated benchmark conditions. It is not a run of the old native wheel,
a measurement of the reset API's benefit, or a real-microphone validation.

## Released-source verification

The exact `v0.2.1` tag resolves to
`a4222a5c2c6ca7b7fb1fbcc2af1d19374772d273`.
Its [C++ source](https://github.com/daanzu/py-silero-vad-lite/blob/a4222a5c2c6ca7b7fb1fbcc2af1d19374772d273/src/silero_vad_lite/silero_vad.cpp#L46-L89)
sets the input tensor to 512 fresh samples at 16 kHz (256 at 8 kHz), without a
waveform prefix. Recurrent state is initially zero with shape `(2, 1, 128)` and
is copied from `stateN` after every inference. The
[Python API](https://github.com/daanzu/py-silero-vad-lite/blob/a4222a5c2c6ca7b7fb1fbcc2af1d19374772d273/src/silero_vad_lite/silero_vad.py)
and C API have no stream-reset operation. A fresh old-package instance starts a
new independent stream; clearing state per frame would not emulate it.

The old C++ blob is `e647a02ec52eda8fa098b5b3d7cd6eea8289f6d6`, identical to the
pre-fix parent `216ba7a62f1382b5973d4510637503d8a8a0e490` recorded by the adapter.
Both exact release tags, old `a4222a5…` and corrected `64837ca…`, contain model
Git blob `b3e3a900c0d70e67b5e2b90a33ad856ee7947930` (2,327,524 bytes).
The corrected release's
[independent fixture generator](https://github.com/daanzu/py-silero-vad-lite/blob/64837cae29c0a920a679f4883f3a186d37de1f86/tests/generate_context_fixture.py)
identifies the model as SHA-256
`2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f`, which is
verified for both experimental arms.

The [official upstream v5.1 wrapper](https://github.com/snakers4/silero-vad/blob/84768cefdf5a3852400e9d8237f7315d14b64a08/src/silero_vad/utils_vad.py#L46-L95)
prepends the preceding 64 samples at 16 kHz (32 at 8 kHz), uses zeros only for
initial context, and retains recurrent state. It advances by the fresh 32 ms
window. This supports the shared score clock used here: no extra 4 ms capture
wait, extra scored interval, or artificial timestamp shift is introduced.

No old executable-stack wheel was loaded for this review.

## Implementation and data checks

- Reviewed `vadbench/context_ablation.py`, adapter dispatch, new contract tests,
  `scripts/report_context_ablation.py`, and the unchanged common runner/metrics
- Disabled feeds `(1, 512)`; enabled feeds `(1, 576)` with the true prior tail.
  Both retain state, reset before each independent recording, use float32,
  Python ONNX Runtime 1.19.0 CPU, one inter/intra-op thread, and full graph
  optimization. Supplying a zero prefix on every disabled call would have been
  a different experiment; this implementation correctly omits it entirely
- The full inherited and new suite independently passes: 59 tests, one skipped
  for the unrelated TEN integration dependency. All ten new contract and result
  tests pass. These cover captured tensor
  contracts and recurrence at both rates, rejected frame shapes, exact
  real-model reset replay, result aggregation, development calibration, timing
  arithmetic, bootstrap pairing, and latency matching. The labeled corpus
  inference itself is at 16 kHz
- All six run manifests match
  `73b60d803250b52d2c5cdea7e3a6458a3cf6907a2c171e4610a4b0234cbed52a`:
  240 streams, 4,800 seconds, with the original 96 development / 144 holdout split.
  Independently read all WAV headers: every file is mono PCM16 at 16 kHz with
  exactly 320,000 samples
- All six recorded adapter, dispatch, runner and metric source hashes match the
  corresponding reviewed files. Runner and metrics are unchanged from the base
- Checked identical paired source/acquisition clocks, frame shapes, incomplete
  tails, resampling delay, clipping counts, runtime/environment settings, and
  finite probability ranges. No final-frame padding is added
- Independently verified all three repeated traces are bitwise identical within
  each arm, and all 150,000 corrected-arm scores and clocks exactly match the
  previous actual native 0.3.0 run. The native run's model and manifest metadata
  also match; that older run is an accuracy oracle, not a timing comparator
- Independently recomputed holdout frame confusion counts from direct interval
  masks, without the benchmark's `evaluate` or `aligned_grid` helpers. Fixed 0.5
  and development-calibrated counts match `summary.json` exactly

## Statistics and interpretation

The fixed 0.5 comparison isolates the effect at a common decision rule. Missed
speech falls from **31.364% to 7.304%** (24.060 percentage points), false-positive
frames from **2.333% to 0.345%**, and extra fragments from **193 to 21**. The
corrected fixed-0.5 arm still produces 70 false activations in 0.566 known-negative
hours, so this threshold does not meet the strict 5/hour budget.

The separate development-calibrated comparison uses the existing shared grid
and budget, selecting 0.94 disabled and 0.96 enabled without holdout optimization.
Holdout missed speech is **77.268% versus 21.376%**; both have two false events.
This measures outcomes after the same calibration procedure, not the effect at
an identical threshold. Cross-threshold results are retained for transparency.

The 5,000-replicate bootstrap correctly resamples paired whole streams within
fixed condition strata and aggregates counts before calculating rates. The
identical-arm null sanity check returned exact zero deltas and intervals. Its
intervals are descriptive corpus-resampling intervals: repeated voices/texts are
dependent, thresholds are held fixed, and neither calibration uncertainty nor
natural-audio generalization is captured. Three inference passes do not create
three independent accuracy datasets.

Paired boundary comparisons use the same matched reference events in both arms
and exclude forced-EOF end notifications. They remain conditional on detection.
Later end notifications can reflect fewer premature cutoffs rather than a harmful
latency regression; onset/end clipping, recall, and fragmentation must accompany
any latency claim. There are no forced-EOF matched endings in these results.

Three sequential timing passes with alternating arm order provide a useful range,
but shared unpinned CPU timing is noisy. In particular, the first corrected pass
is slower than its other two passes. Median wall RTF is approximately 0.00531
versus 0.00553, but this does not establish precise deployment overhead. Timings
include Python and common pipeline work, and do not measure the old native wheel.

The final scope remains synthetic TTS/noise with source-activity proxy labels,
explicit uncertain regions, and a common 200 ms endpoint controller. These
results demonstrate the missing-context defect on this fixed corpus; they do not
establish production false-alarm guarantees or a universal VAD accuracy ranking.

## Final report sign-off

Reviewed the generated `REPORT.md` and `scripts/write_context_report.py` against
the retained summary, including all accuracy, condition, uncertainty and timing
tables. Latency wording correctly distinguishes premature cutoff from beneficial
endpoint speed, and paired reference-event changes from unpaired quantiles.

The report now computes the per-pass overhead range from the recorded passes
(-0.16% to +22.86%) and distinguishes the 4.1% ratio-of-medians result from that
range. CPU demand is expressed as approximately 5–6 ms of CPU time per second of
audio, without claiming measured real-time deployment utilization. The optional
native-oracle row is conditional on actual verification; a regression test
confirms that missing oracle data produces an explicit “not checked” statement.
These review findings are resolved. **Final sign-off: no outstanding blocking
correctness, numerical-reporting or experiment-fairness issue found.**
