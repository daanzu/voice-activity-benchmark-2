"""Audit retained ablation arithmetic and fixed holdout controls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from scripts.report_context_ablation import ARMS, paired_bootstrap, matched_timings
from scripts.write_context_report import main as write_report
from vadbench.metrics import evaluate

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results/context-ablation'


class ContextResultTests(unittest.TestCase):
    def setUp(self):
        if not (RESULTS / 'summary.json').exists():
            self.skipTest('No recorded ablation yet')
        self.summary = json.loads((RESULTS / 'summary.json').read_text())
        self.streams = json.loads((RESULTS / 'per-stream-holdout.json').read_text())

    def test_same_model_runtime_manifest_and_full_clocks(self):
        s = self.summary
        self.assertEqual(s['dataset']['split_counts'], {'dev': 96, 'test': 144})
        self.assertEqual(s['dataset']['duration_s'], 4800)
        a, b = [s['arms'][arm] for arm in ARMS]
        for key in ('model_sha256', 'runtime', 'sample_rate', 'frame_samples', 'providers'):
            self.assertEqual(a[key], b[key])
        self.assertEqual((a['input_samples'], b['input_samples']), (512, 576))
        self.assertEqual(s['paired_trace_checks']['frames'], 150000)
        self.assertTrue(s['paired_trace_checks']['identical_clocks'])
        self.assertTrue(s['paired_trace_checks']['all_three_passes_bitwise_identical'])
        if s['enabled_vs_actual_0_3_0'] is not None:
            self.assertEqual(s['enabled_vs_actual_0_3_0']['maximum_absolute_score_difference'], 0)

    def test_per_stream_totals_conditions_and_thresholds(self):
        for protocol, p in self.summary['protocols'].items():
            for arm in ARMS:
                m = p['holdout'][arm]
                if protocol == 'fixed_0.5':
                    self.assertEqual(m['threshold'], .5)
                else:
                    self.assertEqual(m['threshold'], self.summary['calibration']['selections'][arm]['threshold'])
                for key in ('tp', 'fp', 'fn', 'tn', 'false_activations', 'fragmentation_events', 'reference_events', 'detected_events'):
                    self.assertEqual(m[key], sum(r[key] for r in self.streams[protocol][arm].values()))
                    self.assertEqual(m[key], sum(c[arm][key] for c in p['conditions'].values()))
                self.assertAlmostEqual(m['missed_speech_fraction'], m['fn'] / (m['tp'] + m['fn']))
                self.assertAlmostEqual(m['false_positive_fraction'], m['fp'] / (m['fp'] + m['tn']))

    def test_calibration_only_uses_feasible_development_points(self):
        curves = json.loads((RESULTS / 'development-curves.json').read_text())
        for arm, selected in self.summary['calibration']['selections'].items():
            feasible = [m for m in curves[arm] if m['false_activations_per_negative_hour'] <= 5 and m['false_positive_fraction'] <= .01]
            best = min(feasible, key=lambda m: (m['missed_speech_fraction'], m['false_positive_fraction'], m['threshold']))
            self.assertEqual(selected, best)

    def test_three_pass_timing_arithmetic(self):
        runs = json.loads((RESULTS / 'runs.json').read_text())
        for arm, data in self.summary['timing'].items():
            self.assertEqual(len(data['passes']), 3)
            for r, p in zip(runs[arm], data['passes']):
                self.assertAlmostEqual(p['wall_rtf'], sum(t['wall_s'] for t in r['timing']) / 4800)
            self.assertEqual(data['wall_rtf']['median'], float(np.median([p['wall_rtf'] for p in data['passes']])))

    def test_paired_bootstrap_identical_arms_gives_zero_interval(self):
        manifest = json.loads((RESULTS / 'dataset-manifest.json').read_text())
        records = [r for r in manifest['records'] if r['split'] == 'test']
        one = self.streams['fixed_0.5'][ARMS[0]]
        result = paired_bootstrap(records, {arm: one for arm in ARMS}, repetitions=20)
        for metric in result['metrics'].values():
            self.assertEqual(metric['delta'], 0)
            self.assertEqual(metric['percentile95'], [0, 0])

    def test_latency_matching_matches_shared_evaluator(self):
        record = dict(id='test', duration_s=2., speech_intervals=[[.1, .5], [.8, 1.2]], uncertain_intervals=[])
        trace = np.array([[i/10, (i+1)/10, float(i in (1, 2, 8, 9, 10)), (i+1)/10] for i in range(20)])
        match = matched_timings(record, trace, .5)
        overall = evaluate([record], {'test': trace}, .5)
        self.assertEqual(len(match), overall['detected_events'])
        self.assertAlmostEqual(np.median([m['onset_notification_s'] for m in match.values()]), overall['onset_notification_p50_s'])
        self.assertAlmostEqual(np.median([m['end_notification_s'] for m in match.values()]), overall['end_notification_p50_s'])

    def test_report_does_not_claim_missing_optional_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.summary['enabled_vs_actual_0_3_0'] = None
            (output / 'summary.json').write_text(json.dumps(self.summary))
            with patch('sys.argv', ['write_context_report.py', '--output', tmp]):
                write_report()
            report = (output / 'REPORT.md').read_text()
            self.assertIn('Not checked: optional native trace was not supplied', report)
            self.assertNotIn('scores match the prior actual', report)


if __name__ == '__main__':
    unittest.main()
