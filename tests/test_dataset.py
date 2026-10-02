"""Lightweight generator tests; no network, models, or TTS required."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from vadbench.dataset import (SR, CONDITIONS, TEXTS, VOICES, build_record,
                              generate, intervals, source_activity)


def fake_synth(text, voice, cache):
    # Two voiced spans separated by an actual silent gap.
    t = np.arange(SR)/SR
    x = .1*np.sin(2*np.pi*220*t)
    x[SR//3:SR//2] = 0
    return x, {'voice': voice, 'text': text, 'source_sha256': 'test-fixture'}


class DatasetTests(unittest.TestCase):
    def test_intervals_half_open(self):
        self.assertEqual(intervals(np.array([0,1,1,0,1], bool)), [[.01,.03],[.04,.05]])
        self.assertEqual(intervals(np.zeros(3, bool)), [])

    def test_silence_is_not_speech(self):
        self.assertFalse(source_activity(np.zeros(SR)).any())

    def test_split_assets_are_disjoint(self):
        self.assertTrue(set(VOICES['dev']).isdisjoint(VOICES['test']))
        dev = {s for values in TEXTS['dev'].values() for s in values}
        test = {s for values in TEXTS['test'].values() for s in values}
        self.assertTrue(dev.isdisjoint(test))

    @patch('vadbench.dataset.synthesize', side_effect=fake_synth)
    def test_repeatability_and_quiet_labels(self, _):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'audio').mkdir(); (root/'sources').mkdir()
            a = build_record(4, 123, root, root/'sources')
            b = build_record(4, 123, root, root/'sources')
            q = build_record(6, 123, root, root/'sources')
            self.assertEqual(a, b)
            # Normalization for labels precedes quiet mixing gain.
            self.assertAlmostEqual(sum(y-x for x,y in a['target_intervals']),
                                   sum(y-x for x,y in q['target_intervals']))
            self.assertTrue(q['uncertain_intervals'])

    @patch('vadbench.dataset.synthesize', side_effect=fake_synth)
    def test_background_is_only_generic_speech(self, _):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'audio').mkdir(); (root/'sources').mkdir()
            r = build_record(CONDITIONS.index('background_only'), 1, root, root/'sources')
            self.assertEqual(r['target_intervals'], [])
            self.assertTrue(r['speech_intervals'])
            self.assertEqual(r['speech_intervals'], r['background_intervals'])
            for key in ('speech_intervals','uncertain_intervals'):
                self.assertTrue(all(0 <= a < b <= 20 for a,b in r[key]))

    @patch('vadbench.dataset.subprocess.check_output', return_value='fake ffmpeg\n')
    def test_manifest_refuses_overwrite(self, _):
        with tempfile.TemporaryDirectory() as d:
            a = generate(d, count=1)
            self.assertEqual(a['records'][0]['speech_intervals'], [])
            with self.assertRaises(FileExistsError):
                generate(d, count=1)

if __name__ == '__main__':
    unittest.main()
