"""Common normalized-float frame interface, with native contracts retained."""
from pathlib import Path
import hashlib
import os
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

class ClassicAdapter:
    sample_rate = 16000
    frame_samples = 160
    def __init__(self, mode=2):
        import webrtcvad
        self._module = webrtcvad
        self.mode = mode
        self.metadata = dict(name='classic', mode=mode, score_kind='binary',
                             score_delay_s=0.0, sample_rate=self.sample_rate,
                             frame_samples=self.frame_samples)
        self.reset()
    def reset(self):
        self.detector = self._module.Vad(self.mode)
    def process(self, frame):
        if len(frame) != self.frame_samples:
            raise ValueError('Classic requires exactly 160 samples')
        pcm = np.clip(np.rint(frame * 32768), -32768, 32767).astype('<i2')
        return float(self.detector.is_speech(pcm.tobytes(), self.sample_rate))

class SileroAdapter:
    sample_rate = 16000
    frame_samples = 512
    def __init__(self, model=None):
        import onnxruntime as ort
        self.model = Path(model or os.environ.get('VADBENCH_SILERO_MODEL', ROOT / '.deps/silero_current.onnx'))
        expected = '1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3'
        digest = hashlib.sha256(self.model.read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError(f'Unexpected pinned Silero model hash: {digest}')
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(self.model), sess_options=opts,
                                           providers=['CPUExecutionProvider'])
        self.metadata = dict(name='silero', model_sha256=digest, runtime=ort.__version__,
                             score_kind='probability', score_delay_s=0.0,
                             sample_rate=self.sample_rate, frame_samples=self.frame_samples,
                             context_samples=64, source_commit='1e261b036686cd0017d500ee96acd1c4ba572a9d')
        self.reset()
    def reset(self):
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)
    def process(self, frame):
        if len(frame) != self.frame_samples:
            raise ValueError('Silero requires exactly 512 fresh samples')
        frame = np.asarray(frame, dtype=np.float32).reshape(1, -1)
        inputs = np.concatenate([self.context, frame], axis=1)
        probability, self.state = self.session.run(None, {'input':inputs, 'state':self.state,
                                                         'sr':np.array(self.sample_rate, dtype=np.int64)})
        self.context = frame[:, -64:].copy()
        return float(probability[0, 0])

def create(name):
    if name in ('context-enabled', 'context-disabled'):
        from .context_ablation import BACKENDS, ContextAblationAdapter
        return ContextAblationAdapter(BACKENDS[name])
    if name == 'classic':
        return ClassicAdapter()
    if name.startswith('classic-'):
        return ClassicAdapter(int(name.split('-')[1]))
    if name == 'silero':
        return SileroAdapter()
    if name.startswith('silero-lite-'):
        from .silero_lite import BACKEND_VERSIONS, SileroLiteAdapter
        return SileroLiteAdapter(BACKEND_VERSIONS[name])
    if name == 'fsmn':
        from .fsmn import FsmnAdapter
        return FsmnAdapter()
    from .native import Agc2Adapter, RNNoiseAdapter, SpeexAdapter, TenAdapter
    return {'agc2':Agc2Adapter, 'rnnoise':RNNoiseAdapter,
            'speex':SpeexAdapter, 'ten':TenAdapter}[name]()
