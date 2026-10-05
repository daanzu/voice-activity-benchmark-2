"""Recall-first selection tests, independent of native inference assets."""
from fractions import Fraction
import unittest
import numpy as np

from vadbench.recall_first import (DISPLAY_THRESHOLDS, checked_records, choose_threshold,
                                  frame_arrays, metrics, target_definition, audit_trace_coverage)


class RecallFirstTests(unittest.TestCase):
    def fixture(self, positive=(.01, .02, .2, .8), negative=(.005, .015, .05, .9), split='dev'):
        n = len(positive) + len(negative)
        record = dict(id=split+'-a', split=split, duration_s=n*.01,
                      speech_intervals=[[0, len(positive)*.01]], target_intervals=[[0, len(positive)*.01]],
                      uncertain_intervals=[])
        starts = np.arange(n)*.01
        trace = np.c_[starts, starts+.01, np.r_[positive, negative], starts+.01]
        return [record], {record['id']: trace}

    def target(self, numerator, denominator):
        return target_definition('test', 'test', numerator, denominator)

    def test_exact_highest_feasible_cutoff(self):
        records, traces = self.fixture()
        choice = choose_threshold(records, traces, self.target(3, 4))
        self.assertTrue(choice['feasible'])
        self.assertEqual(choice['threshold'], .02)
        m = metrics(records, traces, choice['threshold'])
        self.assertEqual(m['tp'], 3)
        self.assertEqual(m['fp'], 2)
        self.assertEqual(m['speech_frame_recall'], .75)

    def test_score_ties_included_and_do_not_require_randomization(self):
        records, traces = self.fixture(positive=(.2, .2, .2, .8))
        choice = choose_threshold(records, traces, self.target(1, 2))
        self.assertEqual(choice['threshold'], .2)
        self.assertEqual(metrics(records, traces, .2)['speech_frame_recall'], 1.)

    def test_all_positive_cutoffs_exhaustively_minimize_fp(self):
        rng = np.random.default_rng(4)
        for _ in range(20):
            p = rng.choice([0., .000001, .03, .2, .9], 10)
            n = rng.choice([0., .000001, .03, .2, .9], 8)
            records, traces = self.fixture(p, n)
            for count in (1, 5, 9, 10):
                target = self.target(count, 10)
                candidates = sorted(set(np.r_[p, n, 1.001]))
                feasible = [t for t in candidates if t > 0 and np.count_nonzero(p >= t) >= count]
                choice = choose_threshold(records, traces, target)
                self.assertEqual(choice['feasible'], bool(feasible))
                if feasible:
                    self.assertEqual(choice['threshold'], max(feasible))
                    self.assertEqual(np.count_nonzero(n >= choice['threshold']),
                                     min(np.count_nonzero(n >= t) for t in feasible))

    def test_binary_target_unattainable_honestly(self):
        records, traces = self.fixture(positive=(0, 1, 1, 1), negative=(0, 0, 0, 1))
        choice = choose_threshold(records, traces, self.target(99, 100), binary=True)
        self.assertFalse(choice['feasible'])
        self.assertIsNone(choice['threshold'])
        self.assertEqual(choice['max_dev_recall'], .75)
        self.assertEqual(metrics(records, traces, 0)['speech_frame_recall'], 1)
        self.assertEqual(metrics(records, traces, 0)['false_positive_fraction'], 1)

    def test_binary_native_threshold_preserved(self):
        records, traces = self.fixture(positive=(0, 1, 1, 1), negative=(0, 0, 0, 1))
        choice = choose_threshold(records, traces, self.target(3, 4), binary=True)
        self.assertEqual(choice['threshold'], .5)
        self.assertTrue(choice['feasible'])

    def test_zero_is_never_selected_for_probabilities(self):
        records, traces = self.fixture(positive=(0., .01, .3, .8))
        choice = choose_threshold(records, traces, self.target(1, 1))
        self.assertFalse(choice['feasible'])
        self.assertIsNone(choice['threshold'])
        self.assertEqual(choice['max_dev_recall'], .75)

    def test_near_zero_positive_score_is_operational(self):
        records, traces = self.fixture(positive=(1e-20, .01, .3, .8))
        self.assertEqual(choose_threshold(records, traces, self.target(1, 1))['threshold'], 1e-20)

    def test_holdout_records_rejected_by_selector(self):
        records, traces = self.fixture(split='test')
        with self.assertRaisesRegex(ValueError, 'dev-only'):
            choose_threshold(records, traces, self.target(1, 2))

    def test_mixed_split_rejected(self):
        dev, dev_traces = self.fixture()
        test, test_traces = self.fixture(split='test')
        with self.assertRaisesRegex(ValueError, 'dev-only'):
            choose_threshold(dev+test, dev_traces|test_traces, self.target(1, 2))

    def test_holdout_traces_are_not_accessed(self):
        records, traces = self.fixture()
        class DevOnly(dict):
            def __getitem__(self, key):
                if key.startswith('test'):
                    raise AssertionError('Holdout leak')
                return super().__getitem__(key)
        protected = DevOnly(traces | {'test-secret': None})
        self.assertEqual(choose_threshold(records, protected, self.target(3, 4))['threshold'], .02)

    def test_exact_fraction_ceil_for_classic_parity(self):
        records, traces = self.fixture(positive=(.1,)*100, negative=(.01,))
        t = self.target(29, 100)
        self.assertEqual(choose_threshold(records, traces, t)['required_speech_frames'], 29)

    def test_parity_denominators_can_differ(self):
        records, traces = self.fixture(positive=(.1,)*7, negative=(.01,))
        self.assertEqual(choose_threshold(records, traces, self.target(2, 3))['required_speech_frames'], 5)

    def test_invalid_scores_rejected(self):
        for bad in (np.nan, np.inf, -.01, 1.1):
            records, traces = self.fixture(positive=(bad, .1))
            with self.assertRaisesRegex(ValueError, 'finite probabilities'):
                frame_arrays(records, traces)

    def test_binary_metadata_must_match_scores(self):
        records, traces = self.fixture()
        with self.assertRaisesRegex(ValueError, 'non-binary'):
            choose_threshold(records, traces, self.target(1, 2), binary=True)

    def test_uncertainty_does_not_enter_target_denominator(self):
        records, traces = self.fixture()
        records[0]['uncertain_intervals'] = [[0, .02]]
        choice = choose_threshold(records, traces, self.target(1, 2))
        self.assertEqual(choice['known_speech_frames'], 2)
        self.assertEqual(choice['threshold'], .8)

    def test_empty_speech_or_negative_support_rejected(self):
        for p, n in (((), (.1, .2)), ((.1, .2), ())):
            records, traces = self.fixture(p, n)
            with self.assertRaisesRegex(ValueError, 'known speech and non-speech'):
                choose_threshold(records, traces, self.target(1, 2))

    def test_invalid_target_rejected(self):
        for p, q in ((0, 1), (2, 1), (-1, 2)):
            with self.assertRaisesRegex(ValueError, 'in \\(0,1\\]'):
                self.target(p, q)

    def test_curve_extends_to_zero_but_diagnostic_excluded(self):
        self.assertEqual(DISPLAY_THRESHOLDS[0], 1e-12)
        self.assertTrue(np.all(DISPLAY_THRESHOLDS > 0))
        self.assertTrue(np.all(np.diff(DISPLAY_THRESHOLDS) > 0))
        self.assertIn(1.001, DISPLAY_THRESHOLDS)

    def test_raw_manifest_and_coverage_checked(self):
        records, traces = self.fixture()
        with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
            audit_trace_coverage(records, traces, {'status':'ok','manifest_sha256':'bad'}, 'good')
        with self.assertRaisesRegex(ValueError, 'coverage mismatch'):
            audit_trace_coverage(records, traces|{'extra':next(iter(traces.values()))},
                                 {'status':'ok','manifest_sha256':'good'}, 'good')


if __name__ == '__main__':
    unittest.main()
