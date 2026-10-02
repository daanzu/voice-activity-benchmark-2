"""Causal stateful resampling and frame delivery; no whole-stream lookahead."""
from math import gcd
import numpy as np
from scipy.signal import firwin, lfilter

class StreamResampler:
    def __init__(self, source_rate, target_rate):
        factor = gcd(source_rate, target_rate)
        self.up, self.down = target_rate // factor, source_rate // factor
        self.source_rate = source_rate
        self.target_rate = target_rate
        self.position = 0
        self.identity = source_rate == target_rate
        self.taps = np.array([1.]) if self.identity else firwin(32*max(self.up,self.down)+1, 1/max(self.up,self.down))*self.up
        self.state = np.zeros(len(self.taps)-1)
        self.delay_s = (len(self.taps)-1)/(2*source_rate*self.up)
    def process(self, samples):
        if self.identity:
            return np.asarray(samples, dtype=np.float32)
        expanded = np.zeros(len(samples)*self.up)
        expanded[::self.up] = samples
        filtered, self.state = lfilter(self.taps, [1.], expanded, zi=self.state)
        offset = (-self.position) % self.down
        self.position += len(expanded)
        return filtered[offset::self.down].astype(np.float32)
