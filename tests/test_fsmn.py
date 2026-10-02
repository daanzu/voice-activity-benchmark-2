"""Optional integration tests; run setup_fsmn.py first. No network in tests."""
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vadbench.fsmn import FSMNVAD

@unittest.skipUnless((ROOT / '.deps/fsmn/model.onnx').exists(), 'run scripts/setup_fsmn.py')
class FSMNTests(unittest.TestCase):
    def test_warmup_reset_and_input(self):
        v = FSMNVAD()
        x = np.zeros(160, np.float32)
        first = [v.process(x) for _ in range(10)]
        self.assertEqual(first[:4], [0.0] * 4)
        self.assertEqual(v.processed_frames, 6)
        v.reset()
        self.assertFalse(v.score_valid)
        self.assertEqual(first, [v.process(x) for _ in range(10)])
        for bad in (np.zeros(161), np.ones(160)*1.01, np.full(160, np.nan)):
            with self.assertRaises(ValueError):
                v.process(bad)

    def test_streaming_matches_batched_canonical_frontend(self):
        v = FSMNVAD()
        rng = np.random.default_rng(73)
        audio = (rng.normal(size=16000) * 0.03).astype(np.float32)
        streamed = np.asarray([v.process(f) for f in audio.reshape(-1, 160)])[4:]
        # Independent offline computation of exactly the fully observed LFR contexts.
        fbank = v.knf.OnlineFbank(self._options(v))
        fbank.accept_waveform(16000, (audio*32768).tolist())
        feats = np.asarray([fbank.get_frame(i) for i in range(fbank.num_frames_ready)], np.float32)
        padded = np.concatenate([np.repeat(feats[:1], 2, axis=0), feats])
        contexts = np.asarray([padded[i:i+5].reshape(-1) for i in range(len(feats)-2)])
        normalized = ((contexts+v.cmvn[0])*v.cmvn[1]).astype(np.float32)[None]
        inputs = {'speech': normalized}
        inputs.update({f'in_cache{i}':np.zeros((1,128,19,1), np.float32) for i in range(4)})
        expected = 1-v.session.run(None, inputs)[0][0,:,0]
        np.testing.assert_allclose(streamed, expected, atol=3e-6, rtol=1e-5)

    def _options(self, v):
        opts = v.knf.FbankOptions()
        opts.frame_opts.samp_freq = 16000
        opts.frame_opts.dither = 0
        opts.frame_opts.window_type = 'hamming'
        opts.frame_opts.frame_length_ms = 25
        opts.frame_opts.frame_shift_ms = 10
        opts.frame_opts.snip_edges = True
        opts.mel_opts.num_bins = 80
        opts.energy_floor = 0
        return opts

    def test_future_independence_and_bounded_cache(self):
        a, b = FSMNVAD(), FSMNVAD()
        rng = np.random.default_rng(19)
        prefix = rng.uniform(-0.03,0.03,32000).astype(np.float32)
        self.assertEqual([a.process(f) for f in prefix.reshape(-1,160)],
                         [b.process(f) for f in prefix.reshape(-1,160)])
        self.assertLessEqual(len(a.features), 4)
        self.assertEqual([c.shape for c in a.cache], [(1,128,19,1)]*4)
        self.assertTrue(a.score_valid)

if __name__ == '__main__':
    unittest.main()
