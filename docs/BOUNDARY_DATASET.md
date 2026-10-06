# Frozen synthetic boundary stress corpus

## Reproduce

```sh
python -m unittest discover -s tests -p 'test_boundary_dataset.py' -v
python -m vadbench.boundary_dataset --output data/boundary-v1 --seed 20261005
```

Requires the repository's NumPy/SciPy dependencies and FFmpeg with CMU Flite
voices `awb`, `kal`, `rms`, and `slt`. No recordings, human labels, voice cloning,
API calls, or model-generated labels are used. The generator reuses the existing
source synthesizer and mathematical noise helpers from `vadbench.dataset`.
Generated WAVs stay in the ignored `data/` directory; retain the JSON manifests,
freeze record, hashes, generator and environment metadata with experiment results.
Never overwrite a finalized corpus. Use a new output directory/version for a
changed design, even if no model results have yet been viewed.

## Size and construction

272 mono, 16 kHz, PCM16 streams of exactly eight seconds: **36 minutes 16 seconds**.
Development and test each have 136 streams, 120 construction-defined turns, and
16 negative-only streams. The balanced split is deliberate; cases are correlated
synthetic variants, not 272 independent speakers or linguistic examples.

Per split:

- 64 short-word cases: 16 onset phases × four stresses (`clean`, `quiet`, `fade`,
  `synthetic_breath`). The two voices and eight words vary deterministically
  across these cases. They are not a full voice × text × phase factorial
- 56 paired streams: seven pause lengths × four prefix/continuation replicates
  × two branches (`stop`, `resume`). Each replicate uses one voice and one phrase
  pair; it is repeated across the seven pause lengths
- 16 negatives: silence, fan-like noise, typing-like noise and music-like tones,
  each with four replicates. Non-silence RMS settings are −34/−28/−22/−16 dBFS,
  subject to explicitly recorded clipping-prevention gain

Normal speech is set to −23 dBFS before endpoint processing; quiet speech uses
−40 dBFS. Fade cases apply a 240 ms exponential gain decay to the last portion
of the source, ending at −60 dB relative gain. The fade is not subsequently
normalized away. `synthetic_breath` appends 180 ms of seeded, band-passed,
fading noise at a nominal pre-envelope −38 dBFS. This is **artificial breath-like
noise**, not a recorded or synthesized human breath and not labeled speech.
The corpus makes no claim that quiet TTS is a physiological whisper.

Short texts include vowel-, stop-, fricative-, nasal- and glide-like English
word shapes and different endings. These are word choices, not phonetic
annotations or evidence that Flite preserves every real-world articulatory cue.

The nominal acoustic onset is aligned to 640 ms plus each of
0, 10, …, 150 ms, covering the 160 ms least common multiple of 10/20/32 ms
native frame periods. Alternating cases add one 16 kHz sample (62.5 μs).
Each stress covers every 10 ms phase, but the sub-sample offsets are not a full
factorial. The manifest records the exact phase in samples. Alignment subtracts
the source's first RMS-active frame; it does **not** mistake low-energy Flite
leading support for acoustic onset. An individual test of `prepare_source`
can reproduce the separate source placement, support and activity extents.

## Labels: turn intent is separate from acoustic evidence

A known construction decision says whether a prefix has ended or will resume.
That decision defines turn identity. It does not provide human phonetic truth.
Every positive stream has exactly one explicit turn:

```json
{
  "id": "dev-0000-onset_clean-turn-0",
  "onset_s": 0.64,
  "offset_s": 1.2,
  "onset_uncertainty_s": [0.52, 0.66],
  "offset_uncertainty_s": [1.18, 1.25],
  "acoustic_intervals": [[0.64, 0.87], [0.92, 1.2]],
  "internal_pauses": [],
  "construction_support_intervals": [[0.52, 1.25]]
}
```

The numbers above illustrate the schema, not a particular generated sample.
`acoustic_intervals` may contain many spans. **Do not split the turn at each
acoustic gap.** `internal_pauses` contains the intentionally inserted
support-to-support pause in resumed pairs; ordinary source-internal low-energy
gaps remain visible in the acoustic intervals and uncertainty. A stop branch
has no constructed internal pause. A resume branch contains one turn spanning
both the prefix and continuation.

The clean speech after gain, endpoint fading and PCM quantization is normalized
to −20 dBFS RMS solely for labeling. Its 10 ms frame RMS must exceed the greater
of −48 dBFS or peak frame RMS minus 40 dB to be active. The first and last active
frames define nominal turn boundaries. This proxy is independent of every VAD
being evaluated, but can miss weak consonants and retain synthesizer artifacts.

Uncertainty covers all RMS transitions ±20 ms and source support below that
threshold. Boundary uncertainty additionally reaches the exact nonzero support
of the emitted clean PCM when this is broader than the collar. Synthetic
breath-like tails extend offset uncertainty, but not speech labels. Consequently,
uncertainty bands can be substantially wider than 20 ms; source support is a
conservative construction proxy, not asserted phonetic truth.

Existing runner-compatible fields remain:

- `speech_intervals` and `target_intervals`: identical clean-speech proxy spans
- `background_intervals`: empty (this suite does not add competing talkers)
- `uncertain_intervals`: merged half-open exclusion regions for frame scoring
- `duration_s`, relative WAV `path`, SHA-256 and source/noise provenance

Use the explicit turn objects for boundary and interruption scoring, acoustic
intervals for speech-frame scoring, and report uncertainty-sensitive timings.
Exclude uncertain regions from primary frame scoring and report excluded time.
The intentional pause itself is confidently non-speech for frame scoring away
from collars, while still belonging to a single construction-defined turn.

## Paired causal ambiguity

Requested support-to-support pauses are 50/100/150/200/300/500/800 ms. For each
pair, the stop and resume branches contain **byte-identical PCM history up to
but excluding the first nonzero continuation sample**. Stop keeps silence;
resume continues the same labeled turn. Prefix and continuation are separately
synthesized phrases, so this is an intentionally artificial turn construction,
not a claim about natural discourse timing or coarticulation.

`causal_pair` records the unique pair `id`, common `shared_prefix_id`, branch,
requested pause, prefix support-end sample, exact `resume_sample` and
`resume_time_s`, `shared_prefix_end_sample`, and SHA-256 of the raw little-endian
PCM shared history. Pair branches use unique record seeds even though their
shared speech and silence contain no random component. The generator refuses
independent whole-stream gain adjustments that would break history identity.

A deterministic causal controller with equal initial state must behave alike
on these histories until continuation is observed. Ending the stop case early
therefore also splits the resumed case if it commits before the differing
sample is available. Evaluate stop latency and resumed-turn fragmentation
together. The pause parameter is measured from exact emitted prefix support;
latency relative to nominal RMS offset can differ by the prefix's weak tail.

## Split, freeze, and reproducibility

Within this new corpus, dev uses `awb`/`kal` and test uses `rms`/`slt`. Exact texts
and record RNG seeds are disjoint. Both splits share Flite and processing code.
These voices also occur in historical experiments, so this is a freshly frozen
corpus holdout, not a claim that the synthesis voices have never been studied.
Use development only for parameter/threshold selection; report every test
result without tuning to it.

Generation validates every delivered WAV/hash, label bounds and pair prefix,
then writes the test-only manifest first, followed by the full manifest and
`FROZEN.json`. Freeze metadata declares `before_model_scoring_and_selection` and
contains both manifest hashes and an audit summary. It has no changing time or
absolute path fields. The test-only file retains the complete generation design
metadata, including full-corpus count; its `records` list contains test only.
A finalized manifest or freeze record prevents regeneration in that directory.

Bitwise reproduction requires the recorded versions and the same Flite build.
Metadata includes generator/helper SHA-256, Python, NumPy, SciPy and FFmpeg
versions, and retained raw source WAV hashes. Deterministic tests use small
mathematical source fixtures, not a full TTS run. They cover phase alignment,
quiet labeling, fading/breath-tail honesty, paired causal bytes, pause/turn
semantics, split isolation, reproducible manifests and overwrite protection.

Only 128 seconds of negative-only exposure exist per split. Report that
denominator when reporting false starts; sparse or zero observed alarms cannot
support strong claims about rare real-world false-start rates. The corpus is a
controlled stress probe, not an estimate of production conversational quality.

## Executed verification (2026-10-05)

The full corpus was synthesized twice into different directories. Both complete
manifests, the test-only manifests and `FROZEN.json` were byte-identical; all
272 delivered WAV hashes consequently matched. Every WAV format/duration/hash,
ordered label bounds, pause-within-one-turn invariant, and PCM causal-prefix
hash was audited. All 16 actual acoustic onset phases were checked separately
for each stress and split. Six new fixture tests and the six pre-existing
source-generator tests passed.

- Full manifest SHA-256:
  `9fba764ac3692dba68712e5b6ea78904288bc479cf44292c4a8a81ed089a7106`
- Test-only manifest SHA-256:
  `d92496d5f067835f07026989340ccf91b59c3d8157ac0499c426793f739a7154`
- `FROZEN.json` SHA-256:
  `1a59af4dfbf45e8ab07acb020523e8c35fe1a8a0ba063def80c944bcdd47a9cf`
- Median onset uncertainty width: dev 270 ms; test 200 ms
- Median offset uncertainty width: dev 114.9375 ms; test 203.3125 ms
- Uncertain union: dev 67.9473125 seconds; test 76.585625 seconds

These broad source-support uncertainty bands are intentional. Report nominal
proxy timing alongside uncertainty-sensitive timing; do not present a tolerant
uncertainty-adjusted result alone as accurate phonetic boundary detection.
