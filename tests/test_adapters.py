import importlib.util
from pathlib import Path
import unittest
import numpy as np
from vadbench.adapters import ClassicAdapter,SileroAdapter,ROOT

class AdapterTests(unittest.TestCase):
    def reset_matches(self,adapter):
        rng=np.random.default_rng(71)
        frames=[rng.uniform(-.1,.1,adapter.frame_samples).astype(np.float32) for _ in range(20)]
        first=[adapter.process(f) for f in frames]
        adapter.reset()
        self.assertEqual(first,[adapter.process(f) for f in frames])
        self.assertTrue(all(0<=p<=1 for p in first))
    @unittest.skipUnless(importlib.util.find_spec('webrtcvad'),'optional classic dependency')
    def test_classic_reset(self):self.reset_matches(ClassicAdapter())
    @unittest.skipUnless(importlib.util.find_spec('onnxruntime') and (ROOT/'.deps/silero_current.onnx').exists(),'optional Silero dependencies')
    def test_silero_context_reset(self):self.reset_matches(SileroAdapter())
if __name__=='__main__':unittest.main()
