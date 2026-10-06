# Controlled hard-gated short-pause diagnostic

## Purpose and limits

The original frozen corpus inserts 50–800 ms gaps between exact nonzero PCM support. Its faint Flite leading/trailing speech produces longer gaps between its RMS-active regions. This separate supplement isolates short **RMS-activity gaps** without changing the original corpus, primary metrics, frozen choices, or their interpretation.

This is **artificially hard-gated speech**, not a preserved full utterance or human phonetic annotation. Cropping removes faint phonetic content and may create gating/splice artifacts. A 1 ms taper reduces endpoint clicks but cannot prove artifact neutrality. This is a controlled diagnostic reusing primary Flite texts/voices, **not a fresh independent holdout** or natural-conversation result.

## Frozen construction

- 112 deterministic mono 16 kHz PCM16 streams, eight seconds each
- Both primary provenance splits, four prefix/continuation families per split, two voices per split, seven pauses, two paired branches
- Requested gaps: 50, 100, 150, 200, 300, 500, 800 ms
- The clean prepared source is cropped to its first/last RMS-active frame bounds, then tapered for 1 ms at each edge. Source-local activity is recomputed after the crop/taper. If normalization or taper makes an outer frame inactive, the original prepared PCM is cropped further and freshly tapered, until both outer frames are active. Tapers are never accumulated
- RMS activity is the original source-local 10 ms proxy: normalize the emitted source PCM to −20 dBFS, then use max(−48 dBFS, peak frame RMS −40 dB). The normalization convention is per emitted source, so a later continuation cannot change the earlier prefix labels
- Gated prefixes start at 640 ms. Continuations begin exactly the requested number of samples after the last prefix RMS-active frame. All gap samples are zero
- Validation rereads every WAV, checks hashes, remeasures source-local activity from emitted PCM, checks first/last active frames, checks source/turn labels, measures each real inserted gap, checks zero gap samples and exact prefix bytes
- Outer gate uncertainty is ±1 ms, describing the known synthetic edge/taper. Internal RMS transitions retain ±10 ms uncertainty. Neither collar implies human phonetic accuracy. Strict nominal scoring remains unchanged
- A resumed branch is one construction-defined turn spanning an internal pause. A stopped branch ends at the prefix gate
- `specification.json`, the generator source snapshot, all labels/audio hashes, the test-provenance manifest and primary frozen-selections hash are committed to `FROZEN.json` before inference

## Inference and controller reuse

All 12 already-installed backends use the existing acquisition-clock runner, with one inference pass per backend/stream. No model download, new license acceptance, new model, or diagnostic parameter tuning is performed. The approved TEN native library is reused through `.deps/runtime-env.sh`.

The two common baselines have cutoff 0.5, no added start confirmation or hysteresis, and 0/200 ms added trailing silence. All 156 primary frozen policy references retain exactly their saved parameters. Identical backend/controller tuples are deduplicated for aggregate replay. No diagnostic development sweep or new frontier is constructed. Only `split == "test"` provenance rows enter reported metrics; both splits are inferred and validated.

Stop/resume bytes match until the resume sample. Raw four-column traces must match exactly for **every acquisition time ≤ that horizon**, including an output exactly at the horizon before the next sample has been acquired. Causal-cut rows count END availability in `[prefix RMS end, resume RMS onset)`, strictly before continuation. An END exactly at resume is excluded from this cut measure and remains covered by ordinary strict scoring.

## Metrics and dependence

`boundary_latency.py` is unchanged: strict first-overlapping-episode matching, all-turn denominators, nominal clipping/premature failures, censored EOF, fragments, merges, false activity, recall, and nominal/possible/certain deadlines. Failure-aware quantiles retain unsuccessful turns in their denominators.

Each baseline/pause/branch row contains four turns, one per test prefix family. The aggregate test denominator is 56; stopped audio is repeated seven times for its seven paired pause horizons. Do not treat these as independent phrases, speakers, or uncertainty samples. This diagnostic has no negative-only challenge set; definite-negative regions are artificial silence around/within speech. False activity here does not characterize noise robustness.

## Stable result schema

`results/boundary-pause-probe/summary.json` or `summary.json.gz` (gzip when the uncompressed compact JSON exceeds 1 MB):

- `baseline_by_pause`: 336 rows with `backend`, `configuration` (`common-0ms` or `common-200ms`), `branch` (`stop` or `resume`), numeric `pause_ms`, `actual_rms_gap_ms: {min, max}`, and the full `evaluate_boundaries` result in `metric`
- For stop rows, `actual_rms_gap_ms` describes that row’s paired resumed branch, not an observed continuation in stopped PCM
- `shared`: 24 baseline references with controller values and `metric_key`
- `frozen_selections`: 156 unchanged policy references and `metric_key`; no duration-specific policy fitting
- `aggregate_metrics`: full test metric by unique `backend|controller-id`, stored once
- `causal_by_controller`: paired test causal cuts by the same key, with actual gap, prefix/resume times and exact END availability values
- `dataset`, `methodology`, `limitations`, `split_policy`, `frozen_inputs`, `inference_audit`

`per-turn-test.json`/`.gz` stores strict outcomes once per unique backend/controller. `causal-trace-audit.json` records every raw paired-prefix equality check. Compact JSON uses sorted keys and forbids nonfinite floats; gzip has `mtime=0`, so byte output is deterministic. WAV/NPZ runtime files remain local under `runtime-output/`, ignored by version control. No duplicate primary audio or multi-megabyte policy repetition is packaged.

## Reproduce

From the repository root, using a fresh output directory for a new immutable run:

```bash
source .deps/runtime-env.sh
python -m unittest discover -s tests -p 'test_boundary_pause_probe.py' -v
python -m vadbench.boundary_pause_probe generate --output results/boundary-pause-probe
python -m vadbench.run --manifest results/boundary-pause-probe/manifest.json \
  --output results/boundary-pause-probe/runtime-output/raw
python -m vadbench.boundary_pause_probe analyze --output results/boundary-pause-probe
python -m vadbench.boundary_pause_probe validate --output results/boundary-pause-probe
```

Source provenance retains the original `sources/*.wav` paths, relative to the primary corpus root `data/boundary-v1`; those original WAVs are identified by source hashes and are not copied. Generation defaults to that existing `data/boundary-v1/sources` cache and reads `results/boundary-latency/frozen-selections.json`. Generation and analysis each reject existing completed output rather than silently overwriting the frozen diagnostic. All inference metadata and original NPZ traces are retained locally for audit.
