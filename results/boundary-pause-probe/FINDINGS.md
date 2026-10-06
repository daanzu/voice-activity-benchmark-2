# Hard-gated short-pause diagnostic

This separate controlled diagnostic reuses the primary study’s Flite texts and voices. It is **not a fresh independent holdout**. It artificially removes faint outer speech, then applies 1 ms edge fades. Hard gating/splicing can create artifacts and remove phonetic content. The full-utterance primary study is unchanged.

112 eight-second streams: both provenance splits, four prefix families, seven pause durations, stop/resume branches. All 56 emitted resumed streams were remeasured; actual source-local RMS gaps are exactly 50, 100, 150, 200, 300, 500, and 800 ms. All 12 backends have exact-equal raw acquisition outputs before each paired continuation. The table below uses only the 56 test-provenance streams, with four correlated phrase families per pause.

## Shared baselines: causal premature cuts

Each cell counts paired histories with an END notification inside the artificial pause, strictly before continuation. A stopped-phrase END this early must also cut the byte-identical resumed history.

| Detector / added silence | 50 ms | 100 ms | 150 ms | 200 ms | 300 ms | 500 ms | 800 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| classic-0 / 0 ms | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| classic-0 / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 |
| classic-1 / 0 ms | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| classic-1 / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 |
| classic-2 / 0 ms | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| classic-2 / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 |
| classic-3 / 0 ms | 0/4 | 1/4 | 3/4 | 3/4 | 3/4 | 3/4 | 3/4 |
| classic-3 / 200 ms | 0/4 | 1/4 | 1/4 | 1/4 | 4/4 | 4/4 | 4/4 |
| silero / 0 ms | 1/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| silero / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 |
| silero-lite-0.3.0 / 0 ms | 1/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| silero-lite-0.3.0 / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 |
| silero-lite-0.4.0 / 0 ms | 1/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| silero-lite-0.4.0 / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 |
| agc2 / 0 ms | 2/4 | 2/4 | 2/4 | 2/4 | 2/4 | 2/4 | 2/4 |
| agc2 / 200 ms | 0/4 | 0/4 | 0/4 | 1/4 | 3/4 | 3/4 | 3/4 |
| ten / 0 ms | 1/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| ten / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 |
| fsmn / 0 ms | 0/4 | 0/4 | 0/4 | 2/4 | 4/4 | 4/4 | 4/4 |
| fsmn / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 |
| rnnoise / 0 ms | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 |
| rnnoise / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 4/4 |
| speex / 0 ms | 0/4 | 0/4 | 0/4 | 1/4 | 1/4 | 4/4 | 4/4 |
| speex / 200 ms | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 | 3/4 | 4/4 |

## Aggregate shared-baseline outcomes

All 56 test-provenance turns stay in each denominator. Stop branches are repeated at the seven pause values for causal matching. These correlated variants are not 56 independent utterances. START/END are acquisition availability, not backdated boundaries.

| Detector / silence | Recall | START ≤100 ms | END ≤300 ms | Premature first END | Fragmented | False START / negative hour |
|---|---:|---:|---:|---:|---:|---:|
| classic-0 / 0 ms | 99.86% | 100.0% | 64.3% | 20/56 | 20/56 | 0.0 |
| classic-0 / 200 ms | 99.86% | 100.0% | 1.8% | 8/56 | 8/56 | 0.0 |
| classic-1 / 0 ms | 99.86% | 100.0% | 64.3% | 20/56 | 20/56 | 0.0 |
| classic-1 / 200 ms | 99.86% | 100.0% | 1.8% | 8/56 | 8/56 | 0.0 |
| classic-2 / 0 ms | 99.13% | 100.0% | 55.4% | 25/56 | 24/56 | 0.0 |
| classic-2 / 200 ms | 99.16% | 100.0% | 71.4% | 16/56 | 12/56 | 0.0 |
| classic-3 / 0 ms | 93.58% | 100.0% | 12.5% | 49/56 | 49/56 | 0.0 |
| classic-3 / 200 ms | 96.79% | 100.0% | 53.6% | 26/56 | 15/56 | 0.0 |
| silero / 0 ms | 98.84% | 100.0% | 42.9% | 32/56 | 25/56 | 0.0 |
| silero / 200 ms | 98.89% | 100.0% | 64.3% | 20/56 | 13/56 | 0.0 |
| silero-lite-0.3.0 / 0 ms | 98.74% | 100.0% | 51.8% | 27/56 | 26/56 | 0.0 |
| silero-lite-0.3.0 / 200 ms | 98.91% | 100.0% | 66.1% | 19/56 | 13/56 | 0.0 |
| silero-lite-0.4.0 / 0 ms | 98.84% | 100.0% | 42.9% | 32/56 | 25/56 | 0.0 |
| silero-lite-0.4.0 / 200 ms | 98.89% | 100.0% | 64.3% | 20/56 | 13/56 | 0.0 |
| agc2 / 0 ms | 85.97% | 100.0% | 0.0% | 56/56 | 56/56 | 0.0 |
| agc2 / 200 ms | 93.40% | 100.0% | 30.4% | 39/56 | 19/56 | 0.0 |
| ten / 0 ms | 99.98% | 100.0% | 51.8% | 27/56 | 27/56 | 0.0 |
| ten / 200 ms | 99.99% | 100.0% | 78.6% | 12/56 | 12/56 | 0.0 |
| fsmn / 0 ms | 100.00% | 0.0% | 71.4% | 16/56 | 16/56 | 1606.9 |
| fsmn / 200 ms | 100.00% | 0.0% | 0.0% | 8/56 | 8/56 | 1252.2 |
| rnnoise / 0 ms | 99.09% | 100.0% | 37.5% | 35/56 | 35/56 | 73.0 |
| rnnoise / 200 ms | 99.32% | 100.0% | 71.4% | 16/56 | 16/56 | 0.0 |
| speex / 0 ms | 99.95% | 100.0% | 37.5% | 11/56 | 11/56 | 0.0 |
| speex / 200 ms | 99.96% | 100.0% | 0.0% | 8/56 | 8/56 | 0.0 |

## Frozen-policy reuse

All 156 primary development-selected policy references were reused unchanged. Along with 24 shared baseline references, they map to 114 unique backend/controllers; cached raw traces were replayed once per unique controller. No threshold selection, frontier fitting, or tuning used this diagnostic. The full aggregate metrics, nominal/possible/certain deadlines, all-turn and successful-only quantiles, recall, false activity, and error counts are retained once per unique controller. Baseline duration/branch breakdowns are in baseline_by_pause; causal cuts are retained per unique controller.

## Reproduction and evidence

- [Protocol and schema](../../docs/BOUNDARY_PAUSE_PROBE.md)
- [Pre-inference freeze](FROZEN.json), [design](specification.json), [manifest](manifest.json), [test provenance](test-manifest.json)
- Summary: summary.json.gz
- Per-turn outcomes and causal trace audit use compact JSON, deterministically gzipped above 1 MB
- Raw traces/audio are local runtime artifacts; no second copy of primary corpus or its results is made
