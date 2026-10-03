"""Same-runtime v5.1 waveform-context ablation, not execution of lite 0.2.1.

Both arms preserve recurrence. The disabled arm passes only the fresh 32 ms
window, reproducing the pre-fix tensor contract rather than a zero-prefix arm.
The enabled arm prepends the previous 4 ms (zeros for the first window).
"""
import hashlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA256 = '2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f'
BACKENDS = {'context-disabled': False, 'context-enabled': True}


class ContextAblationAdapter:
    def __init__(self, context_enabled, model=None, sample_rate=16000):
        import onnxruntime as ort
        if sample_rate not in (8000, 16000):
            raise ValueError('Expected 8000 or 16000 Hz')
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * 32 // 1000
        self.context_samples = sample_rate * 4 // 1000
        self.context_enabled = bool(context_enabled)
        self.model = Path(model or ROOT / '.deps/silero-vad-lite/0.3.0/packages/silero_vad_lite/data/silero_vad.onnx')
        digest = hashlib.sha256(self.model.read_bytes()).hexdigest()
        if digest != MODEL_SHA256:
            raise ValueError(f'Unexpected v5.1 model hash: {digest}')
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(self.model), sess_options=opts,
                                           providers=['CPUExecutionProvider'])
        self.sr = np.array(self.sample_rate, dtype=np.int64)
        self.metadata = dict(
            name='context-enabled' if self.context_enabled else 'context-disabled',
            model_version='v5.1', model_source='published silero-vad-lite 0.3.0 wheel',
            model_sha256=digest, runtime=ort.__version__, providers=self.session.get_providers(),
            runtime_path='same Python ONNX Runtime CPU adapter for both arms',
            score_kind='probability', score_delay_s=0.0, sample_rate=self.sample_rate,
            frame_samples=self.frame_samples, context_samples=self.context_samples if self.context_enabled else 0,
            input_samples=self.frame_samples + (self.context_samples if self.context_enabled else 0),
            recurrent_state='retained across frames; zeros for each independent stream',
            interpretation='context correction' if self.context_enabled else 'emulated pre-fix missing-context tensor contract; NOT actual 0.2.1 package',
            old_source_commit='216ba7a62f1382b5973d4510637503d8a8a0e490')
        self.reset()

    def reset(self):
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, self.context_samples), dtype=np.float32)

    def process(self, frame):
        frame = np.asarray(frame, dtype=np.float32)
        if frame.ndim != 1 or len(frame) != self.frame_samples:
            raise ValueError(f'Expected exactly {self.frame_samples} fresh mono samples')
        frame = frame.reshape(1, -1)
        inputs = np.concatenate([self.context, frame], axis=1) if self.context_enabled else frame
        probability, self.state = self.session.run(
            ['output', 'stateN'], {'input': inputs, 'state': self.state, 'sr': self.sr})
        # Keep bookkeeping symmetric; only the model input prefix differs.
        self.context = frame[:, -self.context_samples:].copy()
        return float(probability[0, 0])
