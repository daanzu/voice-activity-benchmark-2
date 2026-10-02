# Synthetic source-activity benchmark

## Reproduce

Run from the repository root:

```sh
python -m vadbench.dataset --output data/synthetic --seed 20261002 --count 240
```

Requires Python, NumPy, SciPy and FFmpeg compiled with the `flite` filter and the
`awb`, `kal`, `rms`, `slt` voices. Check `ffmpeg -hide_banner -h filter=flite`.
No API, account, downloaded recordings, personal voice clone, or human labeling
is used. FFmpeg and CMU Flite were already installed in the execution environment.
Original English prompt text is embedded in the generator. Noise is synthesized
mathematically. The musical distractor is **music-like tones**, not real music.

Upstream references:
- [CMU Flite official repository](https://github.com/festvox/flite)
- [FFmpeg Flite filter documentation](https://www.ffmpeg.org/ffmpeg-filters.html#flite)

The generator uses installed software rather than redistributing binaries or
voice models. Flite's upstream licensing applies to that software; see its
COPYING and installed distribution copyright notices. Generated assets are local,
ignored data, with source hashes and retained source WAVs for inspection.

## Size and split

Default: 240 mono PCM16 WAV streams, each 20 seconds at 16 kHz: **80 minutes**.
There are 20 streams in each of 12 named strata:

- silence
- fan-only, typing-only, music-like-only
- clean short commands, clean long sentences, quiet commands
- speech plus fan, typing, or music-like noise
- background voice alone, foreground/background voice overlap

Each stratum has 8 development and 12 test streams: 96 dev (32 minutes), 144 test
(48 minutes). Synthetic speakers are **strictly split**: awb/kal in dev,
rms/slt in test. The kal16 alias is never used. Exact texts and noise seeds are
also split-disjoint. Phrases intentionally repeat *within* a split; 240 streams
are not 240 independent speakers or independent linguistic examples. Each split
has only two TTS voices, 8 short prompts, 4 long prompts and 2 background texts.
They share a synthesis engine, and this cannot establish generalization to human
speech, languages, microphones, accents or natural background conversations.

Speech/noise mixtures vary nominal dry-source RMS SNR (20, 10, 0, -5 dB), sparse
causal echo tails (0, 120, 350 ms), and full-band or 300–3400 Hz channel filtering.
Quiet speech is mixed at -38 dBFS source RMS; ordinary foreground is -23 dBFS;
background voices -31 dBFS. Non-speech-only noise is -28 dBFS RMS. SNR is a
**nominal dry utterance RMS / full-stream noise RMS** setting, not an assertion
of measured active-speech post-channel SNR. Echoes and filtering change it.
Channel variations are deterministic rather than a complete Cartesian factorial.
A documented whole-mixture gain prevents clipping. No automatic gain restores
quiet speech to normal loudness.

## What the labels mean (important)

We know which source signals were inserted and when. That is not the same as
knowing exact human phonetic speech boundaries. Neither insertion extent nor
sample-nonzero amplitude is claimed as human speech truth.

Each dry TTS source is normalized to -20 dBFS RMS **for labeling only**, independently
of the quiet/noisy mixing gain. Its 10 ms frame RMS is compared with the greater
of -48 dBFS and its peak frame RMS minus 40 dB. Above-threshold frames form a
**clean-source activity proxy**. No evaluated VAD creates these labels. The proxy
can still miss weak consonants or include synthesizer artifacts, so it is not
an unbiased replacement for annotated real speech.

Explicit `uncertain_intervals` cover:
- subthreshold frames *within* each inserted source, including internal pauses
- ±20 ms around every activity transition
- the synthetic reverberant tail after each source

Exclude uncertain frames from primary frame metrics; report excluded duration.
Any event timings relative to this proxy must be labeled synthetic/proxy timings.
Do not call them validated human endpoint latency. The inserted dry source extents,
texts, voices and source hashes are separately preserved under provenance.

Two distinct tasks are available:
- `speech_intervals`: union of foreground **and background** source activity, the
  appropriate primary target for generic VAD
- `target_intervals`: foreground-only activity, a separate command-source task

A generic VAD firing on background speech is correct for the first task. Report
foreground rejection descriptively and never reinterpret it as universal VAD
error. Background-only cases intentionally have empty target intervals and
nonempty generic-speech intervals. Masks can overlap uncertainty; consumers must
apply uncertainty exclusion rather than assuming the lists are disjoint.

## Manifest schema and integrity

`manifest.json` is an object with `schema_version: 1`, `generation` metadata and
`records`. Every record contains:

| Field | Meaning |
| --- | --- |
| id, split | Stable stream ID; dev/test |
| path | WAV path relative to manifest directory |
| duration_s | Exactly 20 |
| target_intervals | Foreground activity intervals |
| speech_intervals | Union of all source activity |
| background_intervals | Background-only activity |
| uncertain_intervals | Exclusion regions for primary frame scoring |
| condition | Name, noise, nominal SNR, source/noise RMS, echo, bandwidth, gain |
| provenance | Unique noise seed and list of source metadata |
| sha256 | SHA-256 of the delivered PCM WAV file |

All interval lists are sorted, disjoint within a list, half-open `[start,end)`
seconds. Source metadata includes role, exact text, voice, engine, raw source WAV
path/hash, inserted interval after exact outer-silence trimming and clean mix RMS.
`generation` records seed, generator version/hash, Python/NumPy/SciPy/FFmpeg versions,
label policy, split voices and provenance links. `manifest.sha256` protects the
manifest. There are no changing timestamps or absolute paths in the manifest.

A finalized manifest is immutable: a second generation into the same output
raises an error. Use a fresh directory for another run. Bitwise reproducibility
requires the same generator and synthesis/numeric environment; version metadata
and audio hashes expose drift. Test threshold selection belongs on dev only;
once chosen, freeze configuration before inspecting test performance. Do not
retune on this test set or imply that repeated variants are independent samples.

## Executed verification

The default 240-stream dataset was built twice in this environment. The complete
manifests (including every WAV/source SHA-256) were byte-identical. Every WAV was
checked for 16 kHz mono PCM16, exactly 320,000 samples, matching hash, and valid
bounded ordered interval lists. Speaker/text/seed split disjointness was checked.
Six lightweight generator unit tests pass.

- Manifest SHA-256: `73b60d803250b52d2c5cdea7e3a6458a3cf6907a2c171e4610a4b0234cbed52a`
- Foreground proxy activity: 874.22 seconds
- Generic speech proxy activity: 1106.10 seconds
- Uncertainty union: 393.13 seconds (8.19% of the 4800-second dataset)

Activity totals above include portions overlapping uncertainty; primary scored
positive time is smaller after exclusions. These statistics describe generated
signals and are not a human annotation audit.
