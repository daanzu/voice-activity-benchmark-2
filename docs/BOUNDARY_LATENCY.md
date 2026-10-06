# Causal START/END latency protocol

This experiment answers when a streaming application can act on VAD output. It is separate from backdated boundary accuracy, throughput, and semantic turn completion. The previous corpus replay is explicitly exploratory; the new [frozen stress suite](BOUNDARY_DATASET.md) supplies a separate development/test comparison.

## Clocks and controller

Each retained trace row is `[source_start, source_end, score, acquisition_time]`. The existing runner feeds causal 10 ms capture blocks, resamples statefully where needed, and waits for a complete native frame. Acquisition is the time the necessary input has arrived, not a benchmark-loop wall clock. Native processing delays, internal overhang and unknown score alignment remain as observed; unknown lookahead is never guessed or subtracted. Causal resampler delay is compensated in source timestamps only. A Silero 32 ms frame may become available at 40 ms because capture arrives in 10 ms blocks. Multiple native frames can share an acquisition time.

A `Controller(on, off, start_s, silence_s)` has `0 < off <= on <= 1`. START requires contiguous scores at or above `on` for the requested source-time duration. An interruption resets pending confirmation. While active, scores at or above `off` sustain speech. END requires contiguous below-`off` evidence for the requested silence duration. Both decisions occur only when scores arrive, not at unobserved timer ticks. Zero silence still requires one observed negative frame. Source gaps reset pending duration accumulation. Start confirmation may backdate a segment start to its first positive evidence; that never backdates the START notification.

An active stream at EOF is right-censored. No artificial END is emitted. Incomplete native input tails are retained as uncovered time, and reference turns are not removed for having uncovered evidence. Real compute and device latency are outside these simulated acquisition numbers. Existing aggregate inference wall/CPU data are retained as provenance, without fabricating per-frame compute-completion events.

## References and matching

New references have explicit construction-defined turn IDs, nominal clean-PCM RMS-proxy onset/offset, conservative uncertainty bands, acoustic speech intervals, and inserted internal pauses. A pause-resume example is one turn even if its pause is longer than the controller's hangover. Negative acoustic time inside a turn is not mislabeled speech. A “turn” here encodes synthetic construction intent; VAD does not solve natural language turn-completion semantics.

For old-corpus diagnostics, source placements define utterance envelopes. Overlapping speakers are unioned for generic-speech evaluation; internal acoustic gaps do not silently define new turns via a 200 ms merge rule. Those labels and previously inspected old test streams remain exploratory.

Episodes are ordered chronologically. The first episode with positive acoustic overlap claims the earliest unclaimed reference turn; each episode and reference is used at most once. A tiny first fragment cannot be replaced by a later longer fragment to improve latency. Merges and every additional overlapping fragment remain explicit errors. A detector active from earlier noise is not awarded instant onset success: START must be at or after nominal onset, before nominal offset, and its first positive evidence must extend beyond the nominal onset.

Primary END success concerns the matched first episode. Its notification must be at or after nominal offset and its backdated end must reach the nominal offset. Earlier notifications or nominally clipped endpoints fail; possible/certain sensitivity separately shows which failures could be resolved by the frozen uncertainty bands. Final-END timing from a later fragment cannot rescue the first episode. Standalone END can still succeed for a merged first episode; **joint intact-turn success additionally requires a valid START, no fragmentation, and no merge**.

## Metrics and denominators

- Every reference turn appears in START and END deadline denominators, including missed, unmatched, early-active, premature, clipped and censored cases
- START deadline success: 50 / 100 / 200 ms; END: 100 / 200 / 300 / 500 ms; all 12 joint intact-turn combinations
- Failure-aware P50 / P90 / P95 use the inverse empirical CDF, nearest rank, with failed turns at positive infinity. JSON stores `{reached:false, seconds:null}` for unreached quantiles. A separate conditional distribution is diagnostic, never the primary ranking
- Missed turns, no distinct START, early-active turns, first-episode premature/clipped ends, EOF censoring, fragmentation, merges, inserted-pause cuts (END availability falls inside the labeled pause), and false/uncertain START counts. Pause-triggered ENDs delivered after speech resumes are reflected in premature/fragmentation metrics, not that narrower pause count
- Source-aligned lost acoustic milliseconds and operational lost acoustic milliseconds. Operational activity begins only at START availability; a backdated segment may retain audio that the application could not yet act on. Aggregate source coverage and operational coverage therefore answer different questions
- False STARTs are classified by their first positive evidence interval, even when the resulting episode eventually overlaps speech. Evidence overlapping no speech and no uncertainty counts as false; uncertain evidence is separate
- Source-aligned and operational false-positive duration/fraction on definite-negative time accompany event counts, so one continuous false activation cannot appear cheap just because it emits one START
- False START rate denominator is a reference-only 1 ms definite-negative grid, identical for all backends and controllers. Zero exposure is undefined, not zero errors. The small exposure and repeated variants do not support precise real-world event-rate claims
- Frozen-test condition breakdowns and per-turn outcomes retain failures. No subgroup retuning

Nominal source boundaries are proxies, not exact phonetic labels. Possible/certain deadline sensitivity uses each frozen boundary interval. Optimistic and conservative clocks respect the same hypothetical boundary and observed evidence: e.g. optimistic END delay cannot use a boundary later than the actual reported endpoint. Broad exact-support bands deliberately expose uncertainty; do not read a nominal 10 ms proxy as 10 ms ground-truth precision.

## Development-only selection

Baseline comparisons use exactly the same controller across all models: cutoff 0.5, equal on/off, no extra START confirmation, and either 0 or 200 ms added silence. This preserves existing 200 ms behavior as a reference; native overhang remains extra and is not advertised as raw-posterior behavior.

Development candidates combine:

- Cutoff 0.5 plus attainable strictly-positive score cutoffs for 99%, 99.5%, 99.9% development speech-frame recall, using the exact order-statistic selector from the recall-first analysis
- Binary classic modes remain native cutoff 0.5; unattainable recall anchors are recorded
- Off/on ratios 1 and 0.5 for continuous scores, 1 for binary scores
- START confirmation 0 / 32 / 64 ms
- Trailing silence 0 / 32 / 64 / 100 / 150 / 200 / 300 / 500 ms

Durations are seconds, not interchangeable frame counts. Every model has its own acquisition/framing behavior. Threshold zero is excluded from operational choices.

Before test scoring, all candidates are evaluated on development only. A maximum source-coverage reference and a representative maximizing each of the 12 joint deadline successes are frozen to disk. Ties favor source coverage, less operational false-positive time, fewer false STARTs, fewer premature ends, fewer fragmented turns, then stable controller ID. These are illustrative choices, not a universal latency/error budget. The user has not chosen an acceptable production false-positive cost. The development frontier preserves nondominated onset100 failure, end300 failure, source-missed fraction, false-START rate, operational false-positive fraction, premature-END fraction, and fragmentation fraction.

Manifest and trace integrity are validated for both splits before selection; test labels are not used to choose controllers. Non-exploratory analysis requires exact `FROZEN.json`, complete/test manifest hashes, matching held-out records, and explicit turns. Test hashes were frozen before model inference. Both splits share the Flite engine; each has two disjoint voices and disjoint texts/seeds within this suite, but those voices appeared in prior benchmark work. Repeated source/prefix variants are correlated. We do not bootstrap variants as independent observations or claim unseen-engine/human generalization.

## Causal ambiguity experiment

Stop/resume pairs have identical PCM histories through a controlled 50 / 100 / 150 / 200 / 300 / 500 / 800 ms support-to-support gap. All pre-divergence acquisition-aligned scores and END decisions must match. An early correct stop decision before the unseen continuation is necessarily also a cut in the paired resumed turn. This demonstrates why VAD speed and pause tolerance trade off; it does not prescribe a natural-conversation pause distribution.

## Reproduce

Use the existing [native setup](RUN_SYNTHETIC.md), including approved TEN license requirements. No human labeling or paid service is used. Do not overwrite the frozen dataset or analysis output.

```sh
python -m vadbench.boundary_dataset --output data/boundary-v1 --seed 20261005
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m vadbench.run \
  --manifest data/boundary-v1/manifest.json --output results/boundary-latency/raw
python -m vadbench.boundary_report --manifest data/boundary-v1/manifest.json \
  --raw results/boundary-latency/raw --output results/boundary-latency
PYTHONPATH=. python scripts/report_boundary_findings.py --results results/boundary-latency
python scripts/package_boundary_results.py
python scripts/package_boundary_results.py --check
python scripts/build_boundary_explorer_data.py
python -m unittest discover -s tests -v
```

Source/model pins, hashes, native binaries and inference environment are recorded. The WAVs and native/model binaries remain regenerable rather than redistributed. Complete raw-score recovery is retained separately. View [findings](../results/boundary-latency/FINDINGS.md) and the [boundary explorer](../notebooks/explore_boundaries.py); the recall-first explorer and historical results are unchanged.

## Audit correction before publication

Independent arithmetic review caught an inconsistency in the first metric pass: nominal evidence/endpoint rules tolerated the lower uncertainty collar, while the possible/certain rules required a compatible hypothetical boundary. This could make nominal success exceed possible success. Before publication, nominal START was tightened to require first evidence reaching nominal onset and nominal END to reach nominal offset. All development candidates, frozen choices and test metrics were recomputed from unchanged cached raw traces under the same predeclared candidate grid. Regression/property checks and the independent result audit require `certain <= nominal <= possible` for every deadline. The superseded metric pass is not a reported result. This is a correctness repair, not controller tuning on test performance.

The three bulk metric artifacts are committed as deterministic `.json.gz` files to keep the repository and publication requests manageable. Decompression restores the exact original pretty-printed JSON bytes; `packaged-results.json` records both compressed and uncompressed hashes. Loaders/audits/explorer checks work in a compressed-only checkout. The local recovery bundle also retains the original JSON and all raw `.npz` traces.

## Measured gaps and short-pause supplement

The original preserved-source corpus uses 50–800 ms between nonzero source supports. Flite's faint tails mean its measured test RMS-activity gaps are 401.6–508.4 ms for a 50 ms insertion and 1151.6–1258.4 ms for an 800 ms insertion. Those are not 50 ms and 800 ms gaps between RMS-active speech. Exact per-family evidence is in [`pause-gap-audit.json`](../results/boundary-latency/pause-gap-audit.json) and the main findings table.

The separate [hard-gated pause probe](BOUNDARY_PAUSE_PROBE.md) tests actual RMS-active gaps of 50–800 ms with the original frozen controllers, without retuning or replacing the original study. It deliberately crops/fades source boundaries, so artificial splices and truncated low-energy phonetics are limitations. Reused text/voice families make it a controlled diagnostic, not a newly independent holdout.
