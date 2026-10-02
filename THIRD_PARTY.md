# Third-party attribution

The small NumPy ONNX wrappers in `bench.py` and `bench16.py` follow Silero's official state/past-waveform-context algorithm. Silero Team's MIT notice is preserved in [licenses/SILERO-MIT.txt](licenses/SILERO-MIT.txt). See [the pinned official implementation](https://github.com/snakers4/silero-vad/blob/1e261b036686cd0017d500ee96acd1c4ba572a9d/src/silero_vad/utils_vad.py).

Other dependencies and data are obtained separately, not vendored:

- [py-webrtcvad-wheels](https://github.com/daanzu/py-webrtcvad-wheels/tree/e8fb8b736111631ae8aa6f29fc9b7498ce893ccf): Python wrapper and classic WebRTC VAD, plus the repository's `test-audio.raw` fixture. Preserve its [license and embedded WebRTC notices](https://github.com/daanzu/py-webrtcvad-wheels/blob/e8fb8b736111631ae8aa6f29fc9b7498ce893ccf/LICENSE) when redistributing. No audio fixture is copied into this repository.
- [silero-vad-lite 0.2.1](https://pypi.org/project/silero-vad-lite/0.2.1/): source of the older bundled ONNX model, MIT-licensed package. The benchmark does not execute its native library.
- [Silero VAD](https://github.com/snakers4/silero-vad): newer ONNX model and streaming reference algorithm, MIT license.
- [ONNX Runtime](https://github.com/microsoft/onnxruntime): inference runtime, MIT license and bundled third-party notices.
- [NumPy](https://numpy.org/): arrays and seeded input generation, BSD license and bundled third-party notices.

The repository owner selected the license in [LICENSE](LICENSE) when creating this repository. It is preserved unchanged. Upstream components retain their respective licenses and required notices.
