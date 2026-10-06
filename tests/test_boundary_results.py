"""Dependency-free retained audit plus hand-derived alternate-oracle fixtures.

No raw archives, learned models, TTS, NumPy, or production scorer are imported.
The retained audit test skips only when the summary has not been generated.
"""
import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.audit_boundary_results import (
    audit_results, baseline_episodes, check_deadline, check_quantiles,
    controller_id, expected_quantiles, grid_indices, independent_choices,
    independent_pareto, oracle_turn_rows, raw_oracle, reference_exposure,
    read_json, sha256,
)


ROOT = Path(__file__).resolve().parents[1]


def record(turns=((.2, .5),), duration=1., pauses=None):
    result = dict(id='fixture', split='test', duration_s=duration,
                  speech_intervals=[], uncertain_intervals=[],
                  condition=dict(name='fixture'), turns=[])
    for i, (a, b) in enumerate(turns):
        spans = [[a, b]] if pauses is None else pauses
        result['speech_intervals'] += spans
        result['turns'].append(dict(id=f't{i}', onset_s=a, offset_s=b,
            onset_uncertainty_s=[a, a], offset_uncertainty_s=[b, b],
            acoustic_intervals=spans, internal_pauses=[[x[1], y[0]] for x, y in zip(spans, spans[1:])]))
    return result


def trace(positives, duration=1., step=.1):
    return [[i*step, (i+1)*step, float(any(a <= (i+.5)*step < b for a, b in positives)),
             (i+1)*step] for i in range(round(duration/step))]


def candidate(name='a', recall=.9, false_rate=1., false_fraction=.1, joint=.4):
    return dict(controller_id=name, source_aligned_speech_recall=recall,
                false_starts_per_negative_hour=false_rate, operational_false_positive_fraction=false_fraction,
                counts=dict(turns=10, premature_end_turns=2, fragmented_turns=1),
                onset=dict(deadlines_ms={'100': dict(fraction=.6)}),
                end=dict(deadlines_ms={'300': dict(fraction=.5)}),
                joint_intact_deadlines={f'{a}/{b}':dict(fraction=joint)
                    for a in (50,100,200) for b in (100,200,300,500)})


class AuditArithmeticTests(unittest.TestCase):
    def test_gzip_only_json_hashes_original_bytes(self):
        data = b'{"x": [1, 2, 3]}\n'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'data.json'
            path.with_suffix('.json.gz').write_bytes(gzip.compress(data, mtime=0))
            self.assertEqual(read_json(path), {'x':[1,2,3]})
            self.assertEqual(sha256(path), hashlib.sha256(data).hexdigest())

    def test_full_denominator_quantiles_are_not_conditional(self):
        all_turn = expected_quantiles([.01, .02, None, None], 4)
        conditional = expected_quantiles([.01, .02, None, None])
        self.assertEqual(all_turn['p50'], dict(reached=True, seconds=.02))
        self.assertEqual(conditional['p50'], dict(reached=True, seconds=.01))
        self.assertEqual(all_turn['p90'], dict(reached=False, seconds=None))
        check_quantiles(all_turn, 'full')
        check_quantiles(conditional, 'conditional')

    def test_empty_quantiles_and_bad_reachability(self):
        q = expected_quantiles([])
        check_quantiles(q, 'empty')
        q['p50'] = dict(reached=True, seconds=0.)
        with self.assertRaisesRegex(AssertionError, 'reachability'):
            check_quantiles(q, 'wrong')

    def test_deadline_denominator_or_fraction_corruption_fails(self):
        check_deadline(dict(successes=3, total=120, fraction=.025), 120, 'valid')
        for entry in (dict(successes=3, total=3, fraction=1.),
                      dict(successes=3, total=120, fraction=1.),
                      dict(successes=-1, total=120, fraction=-1/120)):
            with self.assertRaises(AssertionError):
                check_deadline(entry, 120, 'corrupt')

    def test_signed_alignment_error_is_distinct_from_response_delay(self):
        q = expected_quantiles([-.05])
        check_quantiles(q, 'source_error', nonnegative=False)
        with self.assertRaisesRegex(AssertionError, 'negative'):
            check_quantiles(q, 'response_delay')

    def test_exposure_union_does_not_double_count_uncertainty(self):
        r = record()
        r['uncertain_intervals'] = [[.1,.25], [.45,.6]]
        e = reference_exposure([r])
        self.assertAlmostEqual(e['negative_hours']*3600, .5)
        self.assertAlmostEqual(e['acoustic_speech_s'], .3)
        self.assertEqual(len(grid_indices([[0,.1], [.05,.2]], 1.)), 200)

    def test_independent_selection_priority_and_duration_fp_tie_break(self):
        low_duration = candidate('low-duration', false_rate=100., false_fraction=.01)
        low_event_rate = candidate('low-events', false_rate=1., false_fraction=.2)
        choices = independent_choices([low_event_rate, low_duration])
        self.assertEqual(len(choices), 13)
        self.assertTrue(all(m['controller_id'] == 'low-duration' for m in choices.values()))
        high_joint = candidate('joint', recall=.8, joint=.6)
        choices = independent_choices([low_duration, high_joint])
        self.assertEqual(choices['recall-priority']['controller_id'], 'low-duration')
        self.assertEqual(choices['joint-100-300']['controller_id'], 'joint')

    def test_pareto_keeps_tradeoff_and_equal_points(self):
        first = candidate('a')
        duplicate = candidate('b')
        dominated = candidate('c', recall=.8, false_rate=2.)
        tradeoff = candidate('d', recall=.95, false_fraction=.9)
        self.assertEqual(independent_pareto([first, duplicate, dominated, tradeoff]), {0,1,3})

    def test_controller_id_keeps_float_distinctions(self):
        import math
        a = dict(on=.5, off=.5, start_s=0., silence_s=.2)
        b = dict(a, on=math.nextafter(.5, 1.))
        self.assertNotEqual(controller_id(a), controller_id(b))


class AlternateRawOracleTests(unittest.TestCase):
    def test_zero_silence_needs_negative_evidence_and_clock_is_not_backdated(self):
        events = baseline_episodes(trace([(.2,.5)]), 0.)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0]['start_s'], .2)
        self.assertAlmostEqual(events[0]['start_available_s'], .3)
        self.assertAlmostEqual(events[0]['end_s'], .5)
        self.assertAlmostEqual(events[0]['end_available_s'], .6)

    def test_silence_quantization_and_short_pause_do_not_close_early(self):
        rows = trace([(.2,.4), (.5,.6)])
        events = baseline_episodes(rows, .2)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0]['end_s'], .6)
        self.assertAlmostEqual(events[0]['end_available_s'], .8)

    def test_coverage_gap_cannot_confirm_silence(self):
        rows = [[0,.1,1,.1], [.1,.2,0,.2], [.4,.5,0,.5], [.5,.6,0,.6]]
        event = baseline_episodes(rows, .2)[0]
        self.assertAlmostEqual(event['end_s'], .4)
        self.assertAlmostEqual(event['end_available_s'], .6)

    def test_early_active_missed_and_forced_eof_stay_failures(self):
        r = record()
        early = baseline_episodes(trace([(0., .7)]), 0.)
        rows, _, _ = oracle_turn_rows(r, early)
        self.assertTrue(rows[0]['early_active'])
        self.assertIsNone(rows[0]['onset_latency_s'])
        self.assertFalse(rows[0]['intact'])
        missed, _, _ = oracle_turn_rows(r, [])
        self.assertTrue(missed[0]['missed'])
        self.assertIsNone(missed[0]['end_latency_s'])
        eof, _, _ = oracle_turn_rows(r, baseline_episodes(trace([(.2, 1.)]), 0.))
        self.assertTrue(eof[0]['censored'])
        self.assertIsNone(eof[0]['end_latency_s'])
        self.assertIsNone(eof[0]['event']['end_available_s'])

    def test_later_fragment_cannot_rescue_premature_first_end(self):
        r = record(turns=((.2,.8),), pauses=[[.2,.4], [.6,.8]])
        events = baseline_episodes(trace([(.2,.4), (.6,.8)]), 0.)
        rows, _, _ = oracle_turn_rows(r, events)
        self.assertEqual(rows[0]['matched_episode'], 0)
        self.assertTrue(rows[0]['premature_end'])
        self.assertTrue(rows[0]['fragmented'])
        self.assertIsNone(rows[0]['end_latency_s'])
        self.assertFalse(rows[0]['intact'])

    def test_nominal_evidence_must_reach_actual_boundary_not_lower_uncertainty(self):
        r = record()
        r['turns'][0]['onset_uncertainty_s'] = [.1,.25]
        r['turns'][0]['offset_uncertainty_s'] = [.4,.6]
        event = dict(start_s=.1, first_evidence_end_s=.15, start_available_s=.22,
                     end_s=.45, end_available_s=.55, censored=False)
        rows, _, _ = oracle_turn_rows(r, [event])
        self.assertTrue(rows[0]['early_active'])
        self.assertTrue(rows[0]['premature_end'])
        self.assertIsNone(rows[0]['onset_latency_s'])
        self.assertIsNone(rows[0]['end_latency_s'])

    def test_merged_episode_has_single_turn_owner(self):
        r = record(turns=((.2,.4), (.6,.8)))
        events = baseline_episodes(trace([(.2,.8)]), 0.)
        rows, touching, owners = oracle_turn_rows(r, events)
        self.assertEqual(owners, {0:0})
        self.assertEqual(touching, {0:[0,1]})
        self.assertFalse(rows[0]['intact'])
        self.assertIsNone(rows[1]['matched_episode'])
        self.assertFalse(rows[1]['missed'])
        self.assertIsNone(rows[1]['onset_latency_s'])

    def test_false_starts_and_duration_fp_use_negative_only_exposure(self):
        r = record()
        counts, rows, sums = raw_oracle([r], {'fixture': trace([(0.,1.)])}, 0.)
        self.assertEqual(counts['false_starts'], 1)
        self.assertEqual(counts['early_active_turns'], 1)
        self.assertAlmostEqual(sums['source_aligned_false_positive_s'], .7)
        self.assertAlmostEqual(sums['operational_false_positive_s'], .6)
        self.assertAlmostEqual(sums['source_aligned_clipped_s'], 0.)


class RetainedBoundaryResultTests(unittest.TestCase):
    @unittest.skipUnless(any((ROOT/'results/boundary-latency'/name).is_file()
                            for name in ('summary.json', 'summary.json.gz')),
                         'Frozen boundary summary has not been generated')
    def test_retained_json_without_raw_npz_or_production_imports(self):
        result = audit_results(ROOT/'results/boundary-latency', raw=False)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['selection_count'], 156)
        self.assertEqual(result['turns_per_split'], dict(dev=120, test=120))


if __name__ == '__main__':
    unittest.main()
