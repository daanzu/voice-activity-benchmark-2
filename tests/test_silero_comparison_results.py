"""Validate committed nine-backend records without external backend dependencies."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results/silero-lite-comparison'


class SileroComparisonResults(unittest.TestCase):
    def setUp(self):
        if not (RESULTS / 'summary.json').is_file():
            self.skipTest('Comparison has not been recorded yet')
        self.summary = json.loads((RESULTS / 'summary.json').read_text())
        self.runs = json.loads((RESULTS / 'runs.json').read_text())
        self.results = {r['backend']: r for r in self.summary['results']}

    def test_exact_original_dataset_and_complete_runs(self):
        original = (ROOT / 'results/synthetic/dataset-manifest.json').read_bytes()
        current = (RESULTS / 'dataset-manifest.json').read_bytes()
        self.assertEqual(current, original)
        self.assertEqual(self.summary['manifest_sha256'], hashlib.sha256(current).hexdigest())
        expected = {'agc2', 'classic-0', 'fsmn', 'rnnoise', 'silero', 'speex', 'ten',
                    'silero-lite-0.3.0', 'silero-lite-0.4.0'}
        self.assertEqual(set(self.results), expected)
        self.assertEqual(self.summary['blocked'], [])
        self.assertEqual(len(self.runs), 12)  # Classic's four development candidates.
        for run in self.runs.values():
            self.assertEqual(run['status'], 'ok')
            self.assertEqual(run['manifest_sha256'], self.summary['manifest_sha256'])
            self.assertEqual(len(run['timing']), 240)
            self.assertEqual(sum(t['audio_s'] for t in run['timing']), 4800)

    def test_packages_and_equivalent_model_provenance(self):
        old = self.results['silero-lite-0.3.0']['adapter']
        new = self.results['silero-lite-0.4.0']['adapter']
        baseline = self.results['silero']['adapter']
        self.assertEqual(old['package_version'], '0.3.0')
        self.assertEqual(new['package_version'], '0.4.0')
        self.assertEqual(new['model_sha256'], baseline['model_sha256'])
        self.assertNotEqual(old['model_sha256'], new['model_sha256'])
        self.assertEqual(old['library_sha256'], new['library_sha256'])
        for adapter in (old, new):
            self.assertEqual(adapter['context_samples'], 64)
            self.assertEqual(adapter['frame_samples'], 512)
            self.assertEqual(len(adapter['wheel_sha256']), 64)
            self.assertIn('files.pythonhosted.org', adapter['wheel_url'])

    def test_unchanged_development_protocol_and_timing_arithmetic(self):
        original = json.loads((ROOT / 'results/synthetic/summary.json').read_text())
        self.assertEqual(self.summary['calibration'], original['calibration'])
        self.assertEqual(self.summary['dataset'], original['dataset'])
        for name, result in self.results.items():
            self.assertEqual(result['dev']['threshold'], result['test']['threshold'])
            timing = self.runs[name]['timing']
            self.assertAlmostEqual(result['performance']['wall_rtf'],
                                   sum(t['wall_s'] for t in timing) / 4800)
            self.assertAlmostEqual(result['performance']['inference_rtf'],
                                   sum(t['inference_s'] for t in timing) / 4800)

    def test_paired_comparison_uses_all_frames_and_identical_clocks(self):
        comparisons = self.summary['paired_silero_score_comparisons']
        self.assertEqual(len(comparisons), 2)
        for comparison in comparisons:
            self.assertEqual(comparison['frames'], 150000)
            self.assertTrue(comparison['identical_clocks'])
            self.assertGreaterEqual(comparison['maximum_absolute_score_difference'],
                                    comparison['mean_absolute_score_difference'])
        self.assertTrue(comparisons[0]['model_hash_equal'])
        self.assertFalse(comparisons[1]['model_hash_equal'])


if __name__ == '__main__':
    unittest.main()
