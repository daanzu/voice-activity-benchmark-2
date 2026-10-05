"""Retained recall-first result invariants; no native backend is imported."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT/'results/recall-first'
BACKENDS = {'classic-0', 'classic-1', 'classic-2', 'classic-3', 'silero',
            'silero-lite-0.3.0', 'silero-lite-0.4.0', 'agc2', 'ten', 'fsmn', 'rnnoise', 'speex'}


class RecallResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RESULTS/'summary.json').exists():
            raise unittest.SkipTest('No completed recall-first results yet')
        cls.summary = json.loads((RESULTS/'summary.json').read_text())

    def test_full_cross_product_and_manifest(self):
        s = self.summary
        self.assertEqual(s['analysis_type'], 'recall_first')
        targets = {t['id'] for t in s['targets']}
        self.assertEqual(targets, {'recall-99', 'recall-99.5', 'recall-99.9'} |
                         {f'match-classic-{i}' for i in range(4)})
        self.assertEqual(len(s['selections']), 84)
        self.assertEqual({(r['backend'],r['target_id']) for r in s['selections']},
                         {(b,t) for b in BACKENDS for t in targets})
        self.assertEqual(s['manifest_sha256'], hashlib.sha256((RESULTS/'dataset-manifest.json').read_bytes()).hexdigest())
        self.assertEqual(s['dataset']['split_counts'], {'dev':96, 'test':144})

    def test_frozen_choices_are_identical_to_reported_choices(self):
        s = self.summary
        path = RESULTS/'frozen-thresholds.json'
        frozen = json.loads(path.read_text())
        self.assertEqual(s['frozen_thresholds_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(frozen['split'], 'dev')
        self.assertEqual(frozen['targets'], s['targets'])
        self.assertEqual(len(frozen['selections']), len(s['selections']))
        for fixed, row in zip(frozen['selections'],s['selections']):
            self.assertEqual(fixed, {key:row[key] for key in fixed})

    def test_targets_use_exact_classic_development_counts(self):
        targets = {t['id']:t for t in self.summary['targets']}
        for row in self.summary['classic_references']:
            self.assertEqual(row['threshold'], .5)
            m = row['dev']
            t = targets['match-'+row['backend']]
            self.assertEqual(Fraction(t['numerator'],t['denominator']),Fraction(m['tp'],m['tp']+m['fn']))
            self.assertEqual(t['reference_backend'],row['backend'])

    def test_feasibility_and_positive_cutoffs(self):
        targets = {t['id']:t for t in self.summary['targets']}
        for row in self.summary['selections']:
            with self.subTest(backend=row['backend'],target=row['target_id']):
                t = targets[row['target_id']]
                num, den, n = t['numerator'],t['denominator'],row['known_speech_frames']
                required = (num*n+den-1)//den
                self.assertEqual(row['required_speech_frames'],required)
                self.assertEqual(row['target_recall'],num/den)
                if row['feasible']:
                    self.assertGreater(row['threshold'],0.)
                    self.assertLessEqual(row['threshold'],1.)
                    self.assertIsNone(row['reason'])
                    self.assertGreaterEqual(row['dev']['tp'],required)
                    self.assertEqual(row['dev']['tp']+row['dev']['fn'],n)
                    for split in ('dev','test'):
                        self.assertEqual(row[split]['threshold'],row['threshold'])
                    if row['backend'].startswith('classic-'):
                        self.assertEqual(row['threshold'],.5)
                else:
                    self.assertIsNone(row['threshold'])
                    self.assertIsNone(row['dev'])
                    self.assertIsNone(row['test'])
                    self.assertIsNotNone(row['reason'])

    def test_zero_is_diagnostic_and_all_positive(self):
        s = self.summary
        self.assertEqual({r['backend'] for r in s['diagnostics']},BACKENDS)
        self.assertTrue(all(t>0 for t in s['calibration']['display_threshold_grid']))
        for row in s['diagnostics']:
            self.assertEqual(row['threshold'],0.)
            for split in ('dev','test'):
                self.assertEqual(row[split]['fn'],0)
                self.assertEqual(row[split]['tn'],0)
                self.assertEqual(row[split]['speech_frame_recall'],1.)
                self.assertEqual(row[split]['false_positive_fraction'],1.)
        for row in s['max_positive_points']:
            self.assertGreater(row['threshold'],0.)
            self.assertIsNone(row['test'])

    def test_all_retained_metric_arithmetic(self):
        s = self.summary
        for section in ('selections','classic_references','diagnostics','max_positive_points','fixed_references'):
            for row in s[section]:
                for split in ('dev','test'):
                    m = row.get(split)
                    if m is None:
                        continue
                    with self.subTest(section=section,backend=row['backend'],split=split):
                        self.assertAlmostEqual(m['speech_frame_recall'],m['tp']/(m['tp']+m['fn']))
                        self.assertAlmostEqual(m['missed_speech_fraction'],m['fn']/(m['tp']+m['fn']))
                        self.assertAlmostEqual(m['false_positive_fraction'],m['fp']/(m['fp']+m['tn']))
                        self.assertAlmostEqual(m['false_positive_seconds'],m['fp']*.01)
                        self.assertAlmostEqual(m['speech_seconds'],(m['tp']+m['fn'])*.01)
                        self.assertAlmostEqual(m['negative_hours'],(m['fp']+m['tn'])*.01/3600)
                        self.assertAlmostEqual(m['false_activations_per_negative_hour'],m['false_activations']/m['negative_hours'])
                        self.assertAlmostEqual(m['event_recall'],m['detected_events']/m['reference_events'])
                        self.assertEqual(m['latency_matched_event_count']+m['forced_eof_events'],m['detected_events'])


if __name__ == '__main__':
    unittest.main()
