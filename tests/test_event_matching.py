"""Regression cases for event matching, uncertainty, and endpoint interpretation."""
import unittest

import numpy as np

from vadbench.metrics import evaluate


class EventMatchingTests(unittest.TestCase):
    def measure(self, truth, detections, uncertain=(), duration=4.0):
        # Grid centers select exact 10 ms frames without boundary-roundoff effects.
        starts = np.arange(round(duration * 100)) / 100
        ends = starts + .01
        centers = starts + .005
        scores = np.zeros(len(starts))
        for begin, end in detections:
            scores[(centers >= begin) & (centers < end)] = 1
        trace = np.column_stack((starts, ends, scores, ends))
        record = dict(id='example', duration_s=duration,
                      speech_intervals=truth, target_intervals=truth,
                      uncertain_intervals=list(uncertain))
        return evaluate([record], {'example': trace}, .5)

    def test_fragments_are_counted_and_longest_overlap_supplies_latency(self):
        result = self.measure([[.2, 2]], [[.2, .8], [1.2, 2]])
        self.assertEqual(result['detected_events'], 1)
        self.assertEqual(result['fragmentation_events'], 1)
        self.assertEqual(result['fragmentation_per_reference'], 1)
        self.assertEqual(result['false_activations'], 0)
        self.assertEqual(result['latency_matched_event_count'], 1)
        self.assertAlmostEqual(result['onset_clipping_p50_s'], 1)
        self.assertAlmostEqual(result['end_notification_p50_s'], .2)

    def test_global_assignment_can_use_an_alternative_reference(self):
        # The first event overlaps reference 2 most, but the later event has
        # greater overlap with it. Reference 1 must remain available to event 1.
        result = self.measure([[.2, .6], [.9, 2.5]],
                              [[.2, 1.4], [1.7, 2.5]])
        self.assertEqual(result['reference_events'], 2)
        self.assertEqual(result['detected_events'], 2)
        self.assertEqual(result['fragmentation_events'], 0)

    def test_one_long_detection_cannot_recall_multiple_references(self):
        result = self.measure([[.2, .6], [.9, 2.5]], [[.2, 2.5]])
        self.assertEqual(result['reference_events'], 2)
        self.assertEqual(result['detected_events'], 1)
        self.assertEqual(result['event_recall'], .5)

    def test_unknown_sliver_does_not_hide_known_negative_activation(self):
        result = self.measure([], [[.2, 2]], uncertain=[[.5, .51]])
        self.assertEqual(result['false_activations'], 1)
        self.assertEqual(result['ambiguous_events'], 0)

    def test_entirely_unknown_activation_is_ambiguous(self):
        result = self.measure([], [[.2, .8]], uncertain=[[.2, .8]])
        self.assertEqual(result['false_activations'], 0)
        self.assertEqual(result['ambiguous_events'], 1)

    def test_source_clipping_is_distinct_from_premature_notification(self):
        result = self.measure([[.2, 1]], [[.2, .85]])
        self.assertAlmostEqual(result['end_clipping_p50_s'], .15)
        self.assertAlmostEqual(result['end_notification_p50_s'], .05)
        self.assertEqual(result['premature_notification_fraction'], 0)

    def test_early_notification_remains_signed(self):
        result = self.measure([[.2, 1]], [[.2, .5]])
        self.assertAlmostEqual(result['end_notification_p50_s'], -.3)
        self.assertEqual(result['premature_notification_fraction'], 1)

    def test_forced_eof_is_excluded_from_notification_latency(self):
        result = self.measure([[.2, 4]], [[.2, 4]])
        self.assertEqual(result['forced_eof_events'], 1)
        self.assertEqual(result['latency_matched_event_count'], 0)
        self.assertIsNone(result['end_notification_p50_s'])
        self.assertIsNone(result['premature_notification_fraction'])


if __name__ == '__main__':
    unittest.main()
