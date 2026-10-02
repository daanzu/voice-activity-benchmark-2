"""Causal, delayed frame-posterior adapter for FunASR's official FSMN ONNX export."""
from collections import deque
import hashlib
from pathlib import Path
import re
import sys
import numpy as np

REVISION = 'f6e9fbb4cefa7397216c763f21307993f147f585'
HASHES = {
    'model.onnx': '756887ce01695a9bb00dd85ca0f743653de03b18ba54d2e9ef4f4bb9b3edbf9f',
    'vad.mvn': '6820fef9687708c4fc3fab2530179c8fcea6262daa25514380056cd8f6eb1754',
    'vad.yaml': 'db524c680b80b0ea0a617110f6a269019da9fe4db1c38500f7552aeb6fad08b4',
}

class FSMNVAD:
    sample_rate = 16000
    frame_samples = 160

    def __init__(self, model_dir=None):
        self.model_dir = Path(model_dir or Path(__file__).resolve().parents[1] / '.deps/fsmn')
        packages = self.model_dir / 'packages'
        if packages.exists():
            sys.path.insert(0, str(packages))
        try:
            import kaldi_native_fbank as knf
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError('Run python scripts/setup_fsmn.py to install the FSMN backend') from exc
        for name, expected in HASHES.items():
            if hashlib.sha256((self.model_dir / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f'FSMN artifact integrity failure: {name}')
        self.knf = knf
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(self.model_dir / 'model.onnx'), options,
                                           providers=['CPUExecutionProvider'])
        text = (self.model_dir / 'vad.mvn').read_text()
        vectors = re.findall(r'<LearnRateCoef>\s+0\s+\[([^\]]+)\]', text)
        self.cmvn = np.asarray([np.fromstring(v, sep=' ') for v in vectors], dtype=np.float64)
        if self.cmvn.shape != (2, 400):
            raise ValueError(f'Unexpected CMVN dimensions: {self.cmvn.shape}')
        self.metadata = {
            'backend': 'FSMN', 'model_repository': 'https://huggingface.co/funasr/fsmn-vad-onnx',
            'model_revision': REVISION, 'model_sha256': HASHES['model.onnx'],
            'model_license': 'Apache-2.0', 'onnxruntime_version': ort.__version__,
            'kaldi_native_fbank_version': knf.__version__,
            'score_kind': '1 minus silence posterior (class 0), before native segment rules',
            'feature_window_ms': 25, 'feature_hop_ms': 10, 'lfr_context_frames': 5,
            'right_context_ms': 20, 'first_score_available_ms': 50,
            'score_delay_vs_frame_end_ms': 40, 'score_delay_s': 0.04,
            'valid_after_s': 0.05, 'warmup_frames': 4, 'warmup_output': 0.0,
            'timing_policy': 'Score is emitted when available; never backdated in live evaluation',
            'end_policy': 'No future-padding or flush; final four input hops have no own posterior',
        }
        self.reset()

    def reset(self):
        opts = self.knf.FbankOptions()
        opts.frame_opts.samp_freq = self.sample_rate
        opts.frame_opts.dither = 0.0
        opts.frame_opts.window_type = 'hamming'
        opts.frame_opts.frame_length_ms = 25
        opts.frame_opts.frame_shift_ms = 10
        opts.frame_opts.snip_edges = True
        opts.mel_opts.num_bins = 80
        opts.mel_opts.debug_mel = False
        opts.energy_floor = 0
        self.fbank = self.knf.OnlineFbank(opts)
        self.features = deque()
        self.feature_count = 0
        self.next_feature = 0
        self.processed_frames = 0
        self.last_score = 0.0
        self.score_valid = False
        self.score_frame_index = None
        self.cache = [np.zeros((1, 128, 19, 1), np.float32) for _ in range(4)]

    def process(self, frame):
        frame = np.asarray(frame, dtype=np.float32)
        if frame.shape != (self.frame_samples,):
            raise ValueError(f'FSMN requires mono shape ({self.frame_samples},), got {frame.shape}')
        if not np.all(np.isfinite(frame)) or np.any(np.abs(frame) > 1):
            raise ValueError('FSMN requires finite normalized [-1, 1] samples')
        self.fbank.accept_waveform(self.sample_rate, (frame * 32768).tolist())
        for idx in range(self.next_feature, self.fbank.num_frames_ready):
            feat = np.asarray(self.fbank.get_frame(idx), dtype=np.float32).copy()
            if self.feature_count == 0:
                self.features.extend([feat.copy(), feat.copy()])  # canonical left edge replication
            self.features.append(feat)
            self.feature_count += 1
        count = self.fbank.num_frames_ready - self.next_feature
        self.next_feature += count
        if count:
            self.fbank.pop(count)  # bounded online feature storage; absolute indices remain valid
        while len(self.features) >= 5:
            spliced = np.concatenate(list(self.features)[:5])
            normalized = ((spliced + self.cmvn[0]) * self.cmvn[1]).astype(np.float32)
            inputs = {'speech': normalized.reshape(1, 1, 400)}
            inputs.update({f'in_cache{i}': c for i, c in enumerate(self.cache)})
            outputs = self.session.run(None, inputs)
            probs = outputs[0]
            self.cache = outputs[1:]
            self.last_score = float(np.clip(1.0 - probs[0, 0, 0], 0.0, 1.0))
            self.score_valid = True
            self.score_frame_index = self.processed_frames
            self.processed_frames += 1
            self.features.popleft()
        return self.last_score

FsmnVAD = FSMNVAD
FsmnAdapter = FSMNVAD
