import unittest
import numpy as np
from vadbench.metrics import aligned_grid,endpoint,evaluate,calibrate
from vadbench.streaming import StreamResampler

class StreamingTests(unittest.TestCase):
    def test_resampling_chunk_independence(self):
        x=np.random.default_rng(1).normal(size=3200).astype(np.float32)
        for rate in (16000,24000,48000):
            expected=StreamResampler(16000,rate).process(x)
            model=StreamResampler(16000,rate)
            actual=np.concatenate([model.process(x[i:i+137]) for i in range(0,len(x),137)])
            np.testing.assert_allclose(actual,expected,atol=1e-6)
    def test_no_future_resampling(self):
        a=np.zeros(1600,dtype=np.float32);b=a.copy();b[1000:]=1
        for rate in (24000,48000):
            y=StreamResampler(16000,rate).process(a)
            z=StreamResampler(16000,rate).process(b)
            np.testing.assert_array_equal(y[:int(1000*rate/16000)],z[:int(1000*rate/16000)])

class MetricsTests(unittest.TestCase):
    def trace(self):
        ends=np.arange(.01,1.001,.01);score=((ends>.2)&(ends<=.5)).astype(float)
        return np.c_[ends-.01,ends,score,ends+.03]
    def record(self):
        return dict(id='a',duration_s=1,speech_intervals=[[.2,.5]],target_intervals=[[.2,.5]],uncertain_intervals=[])
    def test_perfect_frames(self):
        m=evaluate([self.record()],{'a':self.trace()},.5)
        self.assertEqual(m['fp'],0);self.assertEqual(m['fn'],0)
        self.assertEqual(m['event_recall'],1)
        self.assertAlmostEqual(m['end_notification_p50_s'],.23)
    def test_unknown_excluded(self):
        r=self.record();r['uncertain_intervals']=[[0,1]]
        _,_,_,valid=aligned_grid(r,self.trace());self.assertFalse(valid.any())
    def test_endpoint_waits_full_silence(self):
        event=endpoint(self.trace(),.5)[0]
        self.assertAlmostEqual(event['end'],.5)
        self.assertAlmostEqual(event['end_notification'],.73)
    def test_never_positive_is_explicit(self):
        trace=self.trace();trace[:,2]=1
        chosen,_=calibrate([self.record()],{'a':trace})
        self.assertEqual(chosen['threshold'],1.001)
        self.assertEqual(chosen['missed_speech_fraction'],1)
    def test_eof_censored(self):
        trace=self.trace();trace[50:,2]=1
        m=evaluate([self.record()],{'a':trace},.5)
        self.assertEqual(m['forced_eof_events'],1)
        self.assertIsNone(m['end_notification_p95_s'])
if __name__=='__main__':unittest.main()
