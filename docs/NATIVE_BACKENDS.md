# Native VAD backends

These adapters accept exactly one normalized, finite, mono float32 frame in
`[-1,1]` and return a native speech score. They recreate **all native state** on
`reset()`. No third-party source, model, library, or sample audio is redistributed
in this repository. `.deps/` is private and ignored.

## Reproduce on Linux

Requirements: Python 3.12+, NumPy, Git, GCC/G++, and network access to the source
and model hosts. CMake and autotools are not needed. From the repository root:

```sh
python scripts/setup_native.py
python -m unittest discover -s tests -p test_native.py -v
```

The default builds RNNoise, SpeexDSP and historical AGC2. Sources are checked out
at immutable commits; tracked source modifications cause a failure. The model
archive is SHA-256 verified. The script does not run upstream install scripts or
modify system paths. Results and their hashes are in `.deps/native-manifest.json`.
`python scripts/setup_native.py rnnoise speex` builds a subset. RNNoise uses
`-O3 -march=native`; rebuild on each benchmark CPU, and do not copy that library
to a machine with a different instruction set. Speex and AGC2 use `-O3`; AGC2's
upstream CPU dispatch chooses its available implementation. These are build
configurations for this comparison, not a claim of best possible throughput.

Library paths can be overridden with `VADBENCH_RNNOISE_LIB`,
`VADBENCH_SPEEX_LIB`, and `VADBENCH_AGC2_LIB`. The actual loaded binary hash is
always recorded. Overrides are the user's responsibility and may not correspond
to the reference source pin; do not represent an arbitrary replacement library
as the pinned build.

## Exact implementations

| Adapter | Native input/hop | Source pin | Native score |
|---|---|---|---|
| RNNoise | 48 kHz, 480 float PCM samples (10 ms) | [xiph/rnnoise `70f1d256`](https://github.com/xiph/rnnoise/tree/70f1d256acd4b34a572f999a05c87bf00b67730d) | Probability returned by full denoising call |
| AGC2 RNN | 24 kHz, 240 float PCM samples (10 ms) | [daanzu/webrtc_rnnvad `10209d27`](https://github.com/daanzu/webrtc_rnnvad/tree/10209d27953cad3affadfdcca968c0066cea0830) | RNN output after AGC2 feature extraction |
| SpeexDSP | 16 kHz, 320 int16 samples (20 ms) | [xiph/speexdsp `1b28a0f6`](https://github.com/xiph/speexdsp/tree/1b28a0f61bc31162979e1f26f3981fc3637095c8) | `SPEEX_PREPROCESS_GET_PROB / 100` |
| TEN | 16 kHz, 256 int16 samples (16 ms) | [TEN-framework/ten-vad `22a3bcd4`](https://github.com/TEN-framework/ten-vad/tree/22a3bcd4509d0faaa8eef4881e8af5f39c178950) | `ten_vad_process` probability |

RNNoise's default full model comes from the official Xiph archive
`rnnoise_data-0a8755f8e2d834eff6a54714ecc7d75f9932e845df35f8b59bc52a7cfe6e8b37.tar.gz`.
Its SHA-256 is the hash in its filename and is checked against the pinned source's
`model_version`. This is the current larger convolution/GRU model, **not** the
older RNNoise 0.1.1 network. Denoised output is discarded, but its computation is
included in timing. The adapter does not isolate just the VAD head.

AGC2 is an explicitly **historical third-party extraction** of WebRTC, not current
upstream WebRTC and not the full APM/AGC2 pipeline. It retains the extraction's
own feature/high-pass processing. Its Abseil dependency is pinned to
`1e3d25b2657228bd691ee938cfd37d487f48054b`. This source identity must stay visible
in results; do not generalize its accuracy or speed to every WebRTC release.

Speex enables preprocessor VAD and denoising, disables AGC, and reports the
integer-percent probability rather than the preprocessor's hysteretic binary
return. Upstream prints “The VAD has been replaced by a hack pending a complete
rewrite”; this is an upstream warning, not a failed build. Its coarse score
resolution and preprocessor adaptation are relevant to interpretation.

RNNoise and AGC2 receive normalized samples multiplied by 32768. Speex and TEN
receive rounded, saturated int16 PCM (`-1 -> -32768`, `+1 -> 32767`). No input is
resampled inside the adapters; the common runner owns resampling and frame clocks.

## Timing semantics

`score_delay_s=None` means exact acoustic target alignment has **not** been
calibrated. Never turn that into a claim of zero algorithmic latency. The runner
may retain emission-time intervals without compensation, but must label them as
unaligned. Callback availability, analysis-window center, trained label offset,
and denoised-audio delay are different quantities.

- AGC2 and Speex only consume current/past input, so declared additional future
  lookahead is zero. Their overlapping analysis/history does not establish an
  exact score target timestamp
- Current RNNoise uses streaming convolutions and delayed denoising spectra.
  Its output-audio delay must not be applied blindly to its returned VAD score;
  score alignment/lookahead are left unknown
- TEN reference source `src/aed_st.h` declares one lookahead frame and
  `src/aed.cc` uses a 256-sample internal hop at 16 kHz: **16 ms declared model
  lookahead**. That is recorded for the known binary hash below. Its 768-sample
  analysis window and prebuilt implementation still require separate end-to-end
  alignment validation; no automatic score-clock shift is asserted here

## TEN: separately obtained, explicitly opt-in

[TEN's license](https://github.com/TEN-framework/ten-vad/blob/22a3bcd4509d0faaa8eef4881e8af5f39c178950/LICENSE)
adds noncompetition and own-application/direct-end-user restrictions to Apache
2.0. It is **not plain Apache-2.0**. Review and accept the applicable terms before
obtaining/running it. The default setup neither downloads TEN nor accepts terms.
Do not redistribute its source, binary, model, or example audio through this repo.

After your own license review, a Linux x86-64 reference installation is:

```sh
git clone https://github.com/TEN-framework/ten-vad.git .deps/ten-vad
git -C .deps/ten-vad checkout --detach 22a3bcd4509d0faaa8eef4881e8af5f39c178950
export VADBENCH_TEN_LIB="$PWD/.deps/ten-vad/lib/Linux/x64/libten_vad.so"
sha256sum "$VADBENCH_TEN_LIB"
# Install libc++1 through your OS package manager if it is missing
python -m unittest discover -s tests -p test_native.py -v
```

The tested library reports version `2.1.0` and SHA-256
`5abfe6bf6e9a4fcea6b440240f0a9a0f431ab5006e48a4e16465ebe681ffd90f`.
The adapter accepts only an explicitly supplied path; a missing library or runtime
fails clearly. It records library version/hash; external libraries are not assumed
to have the reference source provenance.

For environments without a system package manager, this comparison privately
extracted official Debian LLVM 14 runtime packages using `dpkg-deb -x` and set
`LD_LIBRARY_PATH` to their `usr/lib/llvm-14/lib` directory. No system installation
was performed. Packages came from
`https://deb.debian.org/debian/pool/main/l/llvm-toolchain-14/`:

| Package | SHA-256 |
|---|---|
| `libc++1-14_14.0.6-12_amd64.deb` | `e25732a2aeb5ea0a3b0e069dfefac201659a9b96ad572693c1e22fd85c90abbf` |
| `libc++abi1-14_14.0.6-12_amd64.deb` | `36f947832ba07ae944543dcab6f5a6c1cc1b02741aad2a2165834f35121b88fb` |
| `libunwind-14_14.0.6-12_amd64.deb` | `a3d11439ce2560c0e3314a8f08daeaa901513b560fb4c2fd5a908d04dc3a7657` |

## Attribution and redistribution

Keep every upstream notice with any separately built/distributed dependency.
RNNoise and Speex retain `COPYING` in their checkouts; RNNoise additionally has
per-source notices. Abseil retains its Apache license. The AGC2 extraction lacks
a root WebRTC license, so setup downloads checksum-verified official WebRTC
`LICENSE` and `PATENTS` to `.deps/webrtc-notices`; PFFFT/FFTPACK license text is
in its source headers, and RNNoise-derived weights require their upstream notices.
The wrapper and build script do not relicense these dependencies. The private
build tree is not a redistribution-ready third-party package.

## Validation

`tests/test_native.py` checks PCM boundary conversion, finite bounded scores,
exact reset reproducibility, malformed/nonfinite/out-of-range input rejection,
metadata, and repeated cleanup. Optional absent dependencies are skipped; a
present broken native library fails rather than silently skipping. All four
backends were exercised, including TEN with explicit license approval. These
smoke tests validate execution/contracts, not speech-detection quality.
