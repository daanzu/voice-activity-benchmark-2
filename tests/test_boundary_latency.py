"""Independent causal-controller and all-turn boundary regression fixtures.

No TTS, model, network, or learned thresholds are needed. Expected event times
are derived by hand from the trace acquisition schedule, not the evaluator.
"""
import copy
import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from vadbench.boundary_latency import (
    Controller, causal_episodes, evaluate_boundaries, prepare_records,
    quantiles, reference_turns, validate_trace,
)


def trace_for(positive=(), duration=2., step=.01, delay=0.):
    count = int(round((duration-delay)/step))
    starts = np.arange(count)*step
    ends = starts+step
    centers = starts+step/2
    scores = np.zeros(count)
    for a, b in positive:
        scores[(centers >= a) & (centers < b)] = 1.
    return np.column_stack((starts, ends, scores, ends+delay))


def record_for(turn_spans=(((.2, .5),),), duration=2., collar=0., uncertain=()):
    turns = []
    speech = []
    for i, spans in enumerate(turn_spans):
        spans = [list(span) for span in spans]
        a, b = spans[0][0], spans[-1][1]
        turns.append(dict(id=f'turn-{i}', onset_s=a, offset_s=b,
            onset_uncertainty_s=[max(0., a-collar), a+collar],
            offset_uncertainty_s=[b-collar, min(duration, b+collar)],
            acoustic_intervals=spans,
            internal_pauses=[[x[1], y[0]] for x, y in zip(spans, spans[1:])]))
        speech.extend(spans)
    return dict(id='fixture', duration_s=duration, turns=turns,
                speech_intervals=speech, target_intervals=speech,
                uncertain_intervals=list(uncertain), condition=dict(name='fixture'))


def measure(record=None, trace=None, controller=None, **kwargs):
    record = record if record is not None else record_for()
    trace = trace if trace is not None else trace_for(((.2, .5),))
    controller = controller if controller is not None else Controller(silence_s=0.)
    return evaluate_boundaries([record], {record['id']: trace}, controller,
                               details=True, **kwargs)


class ControllerTests(unittest.TestCase):
    def test_silence_durations_are_rounded_up_to_available_evidence(self):
        for silence, expected in [(0., .51), (.032, .54), (.064, .57),
                                  (.1, .6), (.15, .65), (.2, .7),
                                  (.3, .8), (.5, 1.)]:
            with self.subTest(silence=silence):
                event = causal_episodes(trace_for(((.2, .5),)),
                                        Controller(silence_s=silence), 2.)[0]
                self.assertAlmostEqual(event['start_s'], .2)
                self.assertAlmostEqual(event['start_available_s'], .21)
                self.assertAlmostEqual(event['end_s'], .5)
                self.assertAlmostEqual(event['end_available_s'], expected)
                self.assertFalse(event['censored'])

    def test_native_frame_and_capture_quantization_are_retained(self):
        trace = trace_for(((.032, .128),), duration=.32, step=.032)
        trace[:, 3] = np.ceil(trace[:, 1]*100-1e-9)/100
        event = causal_episodes(trace, Controller(silence_s=.032), .32)[0]
        self.assertAlmostEqual(event['start_s'], .032)
        self.assertAlmostEqual(event['start_available_s'], .07)
        self.assertAlmostEqual(event['end_s'], .128)
        self.assertAlmostEqual(event['end_available_s'], .16)

    def test_identical_acquisition_times_are_valid(self):
        trace = np.array([[0., .01, 1., .04], [.01, .02, 0., .04]])
        event = causal_episodes(trace, Controller(silence_s=0.), .1)[0]
        self.assertEqual(event['start_available_s'], .04)
        self.assertEqual(event['end_available_s'], .04)
        self.assertEqual(event['end_s'], .01)

    def test_source_delay_does_not_change_event_availability(self):
        original = trace_for(((.2, .5),))
        delayed = original.copy()
        delayed[:, :2] -= .004
        a = causal_episodes(original, Controller(silence_s=.1), 2.)[0]
        b = causal_episodes(delayed, Controller(silence_s=.1), 2.)[0]
        self.assertAlmostEqual(a['start_s']-b['start_s'], .004)
        self.assertAlmostEqual(a['end_s']-b['end_s'], .004)
        self.assertEqual(a['start_available_s'], b['start_available_s'])
        self.assertEqual(a['end_available_s'], b['end_available_s'])

    def test_start_confirmation_restarts_after_interrupted_positive(self):
        trace = trace_for(((.2, .22), (.23, .5)))
        event = causal_episodes(trace, Controller(start_s=.03, silence_s=0.), 2.)[0]
        self.assertAlmostEqual(event['start_s'], .23)
        self.assertAlmostEqual(event['first_evidence_end_s'], .24)
        self.assertAlmostEqual(event['start_available_s'], .26)

    def test_hysteresis_equality_holds_active_but_does_not_start(self):
        trace = np.array([[0., .01, .6, .01], [.01, .02, .4, .02],
                          [.02, .03, .3, .03], [.03, .04, .399, .04]])
        events = causal_episodes(trace, Controller(on=.6, off=.4, silence_s=0.), .04)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['start_s'], 0.)
        self.assertEqual(events[0]['end_s'], .02)
        self.assertEqual(events[0]['end_available_s'], .03)

    def test_gaps_reset_confirmation_and_silence_evidence(self):
        trace = np.array([[0., .01, 1., .01], [.02, .03, 1., .03],
                          [.03, .04, 1., .04], [.04, .05, 0., .05],
                          [.07, .08, 0., .08], [.08, .09, 0., .09]])
        event = causal_episodes(trace, Controller(start_s=.02, silence_s=.02), .09)[0]
        self.assertEqual(event['start_s'], .02)
        self.assertEqual(event['start_available_s'], .04)
        self.assertEqual(event['end_s'], .07)
        self.assertEqual(event['end_available_s'], .09)

    def test_all_silent_and_empty_trace_have_no_events(self):
        self.assertEqual(causal_episodes(trace_for()), [])
        self.assertEqual(causal_episodes(np.empty((0, 4))), [])

    def test_eof_is_censoring_and_never_an_end_notification(self):
        event = causal_episodes(trace_for(((.2, 2.),)), Controller(), 2.)[0]
        self.assertTrue(event['censored'])
        self.assertIsNone(event['end_available_s'])
        self.assertAlmostEqual(event['end_s'], 2.)

    def test_subconfirmation_eof_does_not_invent_start(self):
        events = causal_episodes(trace_for(((1.99, 2.),)), Controller(start_s=.032), 2.)
        self.assertEqual(events, [])

    def test_causal_identical_prefixes_have_identical_notifications(self):
        stop = trace_for(((.2, .5),))
        resume = trace_for(((.2, .5), (.7, 1.)), duration=2.)
        np.testing.assert_array_equal(stop[:70], resume[:70])
        controller = Controller(silence_s=.1)
        before_resume = lambda x: [e for e in causal_episodes(x, controller, 2.)
                                   if e['end_available_s'] is not None
                                   and e['end_available_s'] <= .7]
        self.assertEqual(before_resume(stop), before_resume(resume))

    def test_invalid_controller_parameters_are_rejected(self):
        for kwargs in [dict(on=float('nan')), dict(off=float('inf')), dict(off=0.),
                       dict(on=1.1), dict(on=.4, off=.5), dict(start_s=-.01),
                       dict(silence_s=-.1)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Controller(**kwargs)

    def test_controller_ids_distinguish_adjacent_score_cutoffs(self):
        lower = .5
        upper = float(np.nextafter(lower, 1.))
        self.assertNotEqual(Controller(on=lower, off=lower).id,
                            Controller(on=upper, off=upper).id)


class TraceValidationTests(unittest.TestCase):
    def test_nonfinite_malformed_reversed_and_noncausal_traces_rejected(self):
        bad = [np.zeros((2, 3)), [[0., .01, float('nan'), .01]],
               [[0., .01, 1.1, .01]], [[.01, .01, 1., .01]],
               [[0., .01, 1., .009]], [[0., .01, 1., 2.1]],
               [[0., .02, 1., .02], [.01, .03, 1., .03]],
               [[0., .01, 1., .04], [.01, .02, 1., .03]]]
        for trace in bad:
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                validate_trace(trace, 2.)

    def test_small_negative_source_origin_is_allowed(self):
        trace = [[-.004, .006, .5, .01], [.006, .016, .5, .02]]
        self.assertEqual(validate_trace(trace, .1).shape, (2, 4))


class BoundaryMatchingTests(unittest.TestCase):
    def test_perfect_scores_still_have_acquisition_latency(self):
        result = measure()
        self.assertAlmostEqual(result['onset']['all_turn_quantiles']['p50']['seconds'], .01)
        self.assertAlmostEqual(result['end']['all_turn_quantiles']['p50']['seconds'], .01)
        self.assertEqual(result['joint_intact_deadlines']['50/100']['successes'], 1)
        self.assertAlmostEqual(result['source_aligned_clipped_s'], 0.)
        self.assertAlmostEqual(result['operational_clipped_s'], .01)

    def test_all_silent_retains_every_reference_in_denominator(self):
        result = measure(trace=trace_for())
        self.assertEqual(result['counts']['missed_turns'], 1)
        self.assertEqual(result['counts']['no_distinct_start_turns'], 1)
        for side in ('onset', 'end'):
            self.assertEqual(result[side]['deadlines_ms']['100']['total'], 1)
            self.assertEqual(result[side]['deadlines_ms']['100']['successes'], 0)
            self.assertFalse(result[side]['all_turn_quantiles']['p50']['reached'])

    def test_early_active_start_is_not_clamped_into_success(self):
        result = measure(trace=trace_for(((0., .5),)))
        self.assertEqual(result['counts']['early_active_turns'], 1)
        self.assertEqual(result['counts']['false_starts'], 1)
        self.assertEqual(result['onset']['deadlines_ms']['200']['successes'], 0)
        self.assertIsNone(result['turn_results'][0]['onset_latency_s'])

    def test_delayed_notification_cannot_rescue_early_evidence(self):
        result = measure(trace=trace_for(((0., .5),)),
                         controller=Controller(start_s=.25, silence_s=0.))
        self.assertEqual(result['counts']['early_active_turns'], 1)
        self.assertEqual(result['onset']['deadlines_ms']['200']['successes'], 0)

    def test_first_fragment_owns_turn_even_when_second_is_longer(self):
        record = record_for((((.2, 1.),),))
        result = measure(record, trace_for(((.2, .3), (.4, 1.))))
        row = result['turn_results'][0]
        self.assertEqual(row['matched_episode'], 0)
        self.assertAlmostEqual(row['onset_latency_s'], .01)
        self.assertIsNone(row['end_latency_s'])
        self.assertEqual(result['counts']['fragmented_turns'], 1)
        self.assertEqual(result['counts']['extra_fragments'], 1)
        self.assertEqual(result['counts']['premature_end_turns'], 1)
        self.assertEqual(result['joint_intact_deadlines']['200/500']['successes'], 0)

    def test_one_merged_episode_cannot_recall_two_turn_starts(self):
        record = record_for((((.2, .5),), ((.6, .9),)))
        result = measure(record, trace_for(((.2, .9),)))
        self.assertEqual(result['counts']['merged_episodes'], 1)
        self.assertEqual(result['counts']['merged_turns'], 1)
        self.assertEqual(result['onset']['deadlines_ms']['50']['total'], 2)
        self.assertEqual(result['onset']['deadlines_ms']['50']['successes'], 1)
        self.assertEqual(result['counts']['no_distinct_start_turns'], 1)
        self.assertIsNone(result['turn_results'][1]['matched_episode'])
        self.assertEqual(result['joint_intact_deadlines']['200/500']['successes'], 0)

    def test_short_interturn_gap_is_not_implicitly_merged_in_truth(self):
        record = record_for((((.2, .5),), ((.532, .8),)))
        self.assertEqual(len(reference_turns(record)), 2)
        self.assertEqual(measure(record, trace_for())['counts']['turns'], 2)

    def test_internal_pause_cut_vs_continuity(self):
        record = record_for((((.2, .4), (.6, 1.)),))
        trace = trace_for(((.2, .4), (.6, 1.)))
        cut = measure(record, trace, Controller(silence_s=0.))
        held = measure(record, trace, Controller(silence_s=.3))
        self.assertEqual(cut['counts']['internal_pause_cuts'], 1)
        self.assertEqual(cut['counts']['fragmented_turns'], 1)
        self.assertEqual(held['counts']['internal_pause_cuts'], 0)
        self.assertEqual(held['counts']['fragmented_turns'], 0)
        self.assertAlmostEqual(held['acoustic_speech_s'], .6)

    def test_pause_only_episode_does_not_claim_acoustic_turn(self):
        record = record_for((((.2, .4), (.6, 1.)),))
        result = measure(record, trace_for(((.42, .48),)))
        self.assertEqual(result['counts']['missed_turns'], 1)
        self.assertEqual(result['counts']['false_starts'], 1)
        self.assertIsNone(result['turn_results'][0]['matched_episode'])

    def test_premature_end_is_not_a_negative_latency_success(self):
        result = measure(trace=trace_for(((.2, .4),)))
        self.assertEqual(result['counts']['premature_end_turns'], 1)
        self.assertEqual(result['end']['deadlines_ms']['100']['successes'], 0)
        self.assertFalse(result['end']['all_turn_quantiles']['p95']['reached'])
        self.assertAlmostEqual(result['diagnostic']['source_end_error']['p50']['seconds'], -.1)

    def test_late_notification_does_not_hide_backdated_tail_clipping(self):
        result = measure(trace=trace_for(((.2, .45),)),
                         controller=Controller(silence_s=.1))
        self.assertEqual(result['counts']['premature_end_turns'], 1)
        self.assertEqual(result['end']['deadlines_ms']['100']['successes'], 0)
        self.assertAlmostEqual(result['source_aligned_clipped_s'], .05)

    def test_censored_end_and_dropped_tail_remain_failures(self):
        record = record_for((((.2, 1.),),), duration=1.)
        trace = trace_for(((.2, 1.),), duration=.99)
        result = measure(record, trace)
        self.assertEqual(result['counts']['censored_turns'], 1)
        self.assertEqual(result['end']['deadlines_ms']['500']['successes'], 0)
        self.assertEqual(result['end']['all_turn_quantiles']['denominator'], 1)
        self.assertAlmostEqual(result['score_covered_s'], .99)
        self.assertAlmostEqual(result['source_aligned_clipped_s'], .01)

    def test_empty_trace_does_not_remove_uncertain_reference_turn(self):
        record = record_for(uncertain=((0., 2.),))
        result = measure(record, np.empty((0, 4)))
        self.assertEqual(result['counts']['turns'], 1)
        self.assertEqual(result['onset']['deadlines_ms']['50']['total'], 1)
        self.assertEqual(result['counts']['missed_turns'], 1)
        self.assertIsNone(result['false_starts_per_negative_hour'])

    def test_false_starts_use_initial_evidence_not_eventual_overlap(self):
        result = measure(trace=trace_for(((.1, .6),)))
        self.assertEqual(result['counts']['false_starts'], 1)
        self.assertEqual(result['counts']['missed_turns'], 0)

    def test_uncertain_start_is_separate_from_definite_false_start(self):
        record = record_for(uncertain=((.1, .12),))
        result = measure(record, trace_for(((.1, .6),)))
        self.assertEqual(result['counts']['uncertain_starts'], 1)
        self.assertEqual(result['counts']['false_starts'], 0)

    def test_negative_exposure_is_reference_only(self):
        record = record_for(uncertain=((.1, .12),))
        full = measure(record, trace_for())
        empty = measure(record, np.empty((0, 4)))
        self.assertEqual(full['negative_hours'], empty['negative_hours'])
        self.assertAlmostEqual(full['negative_hours']*3600, 1.68)

    def test_one_long_false_start_cannot_hide_near_constant_false_activity(self):
        always = measure(trace=trace_for(((0., 2.),)))
        brief = measure(trace=trace_for(((0., .01), (.2, .5))))
        self.assertEqual(always['counts']['false_starts'], 1)
        self.assertEqual(brief['counts']['false_starts'], 1)
        self.assertAlmostEqual(always['source_aligned_speech_recall'], 1.)
        self.assertAlmostEqual(brief['source_aligned_speech_recall'], 1.)
        self.assertAlmostEqual(always['source_aligned_false_positive_s'], 1.7)
        self.assertAlmostEqual(always['source_aligned_false_positive_fraction'], 1.)
        self.assertAlmostEqual(always['operational_false_positive_s'], 1.69)
        self.assertAlmostEqual(brief['source_aligned_false_positive_s'], .01)
        self.assertAlmostEqual(brief['operational_false_positive_s'], .02)
        self.assertGreater(always['operational_false_positive_fraction'], .99)

    def test_false_activity_excludes_uncertain_reference_time(self):
        record = record_for(uncertain=((0., .1),))
        metric = measure(record, trace_for(((0., 2.),)))
        self.assertAlmostEqual(metric['source_aligned_false_positive_s'], 1.6)
        self.assertAlmostEqual(metric['operational_false_positive_s'], 1.6)
        self.assertAlmostEqual(metric['source_aligned_false_positive_fraction'], 1.)
        self.assertAlmostEqual(metric['operational_false_positive_fraction'], 1.)
        unknown = measure(record_for(uncertain=((0., 2.),)), trace_for(((0., 2.),)))
        self.assertIsNone(unknown['source_aligned_false_positive_fraction'])
        self.assertIsNone(unknown['operational_false_positive_fraction'])

    def test_onset_and_end_deadlines_include_exact_boundary(self):
        for silence, passes in [(.099, True), (.1, True), (.101, False)]:
            result = measure(controller=Controller(start_s=.05, silence_s=silence))
            self.assertEqual(result['onset']['deadlines_ms']['50']['successes'], 1)
            self.assertEqual(result['end']['deadlines_ms']['100']['successes'], int(passes))

    def test_no_turns_is_undefined_not_perfect_or_failed_recall(self):
        result = measure(record_for(()), trace_for())
        self.assertEqual(result['counts']['turns'], 0)
        self.assertIsNone(result['onset']['deadlines_ms']['50']['fraction'])
        self.assertIsNone(result['source_aligned_speech_recall'])
        self.assertFalse(result['onset']['all_turn_quantiles']['p50']['reached'])

    def test_prepared_reference_cache_is_identical_and_nonmutating(self):
        record = record_for()
        before = copy.deepcopy(record)
        prepared = prepare_records([record])
        self.assertEqual(record, before)
        self.assertNotIn('_boundary_reference', record)
        self.assertEqual(measure(record), measure(prepared[0]))

    def test_result_is_strict_json_including_unreached_quantiles(self):
        result = measure(trace=trace_for())
        encoded = json.dumps(result, allow_nan=False)
        decoded = json.loads(encoded)
        self.assertIsNone(decoded['end']['all_turn_quantiles']['p95']['seconds'])
        self.assertFalse(decoded['end']['all_turn_quantiles']['p95']['reached'])


class UncertaintyTests(unittest.TestCase):
    def test_nominal_start_requires_evidence_compatible_with_nominal_onset(self):
        record = record_for(collar=.02)
        result = measure(record, trace_for(((.19, .5),)),
                         Controller(start_s=.03, silence_s=0.))
        self.assertAlmostEqual(result['turn_results'][0]['event']['start_available_s'], .22)
        self.assertAlmostEqual(result['turn_results'][0]['event']['first_evidence_end_s'], .2)
        self.assertEqual(result['onset']['deadlines_ms']['50']['successes'], 0)
        self.assertEqual(result['onset']['uncertainty_possible_deadlines_ms']['50']['successes'], 1)

    def test_nominal_end_cannot_borrow_lower_uncertainty_endpoint_tolerance(self):
        record = record_for(collar=.02)
        result = measure(record, trace_for(((.2, .49),)))
        self.assertAlmostEqual(result['turn_results'][0]['event']['end_available_s'], .5)
        self.assertAlmostEqual(result['turn_results'][0]['event']['end_s'], .49)
        self.assertEqual(result['end']['deadlines_ms']['100']['successes'], 0)
        self.assertEqual(result['end']['uncertainty_possible_deadlines_ms']['100']['successes'], 1)

    def test_certain_nominal_possible_form_an_ordered_envelope(self):
        for collar in (0., .02):
            record = record_for(collar=collar)
            for start in (.18, .2, .23):
                for end in (.48, .5, .52):
                    trace = trace_for(((start, end),))
                    for confirmation in (0., .03, .064):
                        for silence in (0., .032, .1):
                            controller = Controller(start_s=confirmation, silence_s=silence)
                            with self.subTest(collar=collar, start=start, end=end,
                                              confirmation=confirmation, silence=silence):
                                result = measure(record, trace, controller)
                                for side in ('onset', 'end'):
                                    for deadline, nominal in result[side]['deadlines_ms'].items():
                                        possible = result[side]['uncertainty_possible_deadlines_ms'][deadline]
                                        certain = result[side]['uncertainty_certain_deadlines_ms'][deadline]
                                        self.assertLessEqual(certain['successes'], nominal['successes'])
                                        self.assertLessEqual(nominal['successes'], possible['successes'])
                                        if collar == 0.:
                                            self.assertEqual(certain['successes'], nominal['successes'])
                                            self.assertEqual(nominal['successes'], possible['successes'])

    def test_optimistic_start_can_succeed_when_nominal_start_is_early(self):
        record = record_for(collar=.02)
        result = measure(record, trace_for(((.19, .5),), step=.005))
        self.assertEqual(result['onset']['deadlines_ms']['50']['successes'], 0)
        self.assertEqual(result['onset']['uncertainty_possible_deadlines_ms']['50']['successes'], 1)
        self.assertEqual(result['onset']['uncertainty_certain_deadlines_ms']['50']['successes'], 0)

    def test_optimistic_end_can_succeed_when_nominal_end_is_early(self):
        record = record_for(collar=.02)
        result = measure(record, trace_for(((.2, .49),), step=.005))
        self.assertEqual(result['end']['deadlines_ms']['100']['successes'], 0)
        self.assertEqual(result['end']['uncertainty_possible_deadlines_ms']['100']['successes'], 1)
        self.assertEqual(result['end']['uncertainty_certain_deadlines_ms']['100']['successes'], 0)

    def test_optimistic_start_uses_boundary_compatible_with_first_evidence(self):
        record = record_for(collar=.02)
        result = measure(record, trace_for(((.18, .5),)),
                         Controller(start_s=.07, silence_s=0.))
        self.assertAlmostEqual(result['turn_results'][0]['event']['start_available_s'], .25)
        self.assertAlmostEqual(result['turn_results'][0]['event']['first_evidence_end_s'], .19)
        self.assertEqual(result['onset']['uncertainty_possible_deadlines_ms']['50']['successes'], 0)

    def test_optimistic_end_uses_same_boundary_as_source_endpoint(self):
        record = record_for((((.2, 1.),),), collar=.02)
        result = measure(record, trace_for(((.2, .98),)), Controller(silence_s=.12))
        self.assertAlmostEqual(result['turn_results'][0]['event']['end_available_s'], 1.1)
        self.assertAlmostEqual(result['turn_results'][0]['event']['end_s'], .98)
        self.assertEqual(result['end']['uncertainty_possible_deadlines_ms']['100']['successes'], 0)


class QuantileAndReferenceTests(unittest.TestCase):
    def test_nearest_rank_has_exact_failure_reachability_boundary(self):
        one_failure = quantiles([.1]*19+[None], total=20)
        two_failures = quantiles([.1]*18+[None, None], total=20)
        self.assertTrue(one_failure['p95']['reached'])
        self.assertEqual(one_failure['p95']['seconds'], .1)
        self.assertFalse(two_failures['p95']['reached'])
        self.assertIsNone(two_failures['p95']['seconds'])
        self.assertTrue(two_failures['p90']['reached'])

    def test_single_observation_empty_and_mixed_outcomes(self):
        self.assertEqual(quantiles([.1])['p95']['seconds'], .1)
        self.assertFalse(quantiles([])['p50']['reached'])
        result = quantiles([.1, None], total=2)
        self.assertTrue(result['p50']['reached'])
        self.assertFalse(result['p90']['reached'])
        self.assertEqual(quantiles([.1, None])['denominator'], 1)

    def test_nonresponses_and_infinities_never_serialize_as_numbers(self):
        result = quantiles([float('inf'), float('nan'), None, .2], total=4)
        self.assertEqual(result['observations'], 1)
        self.assertFalse(result['p50']['reached'])
        json.dumps(result, allow_nan=False)

    def test_old_replay_uses_source_placements_not_point_two_second_merge(self):
        record = record_for((((.2, .4), (.6, 1.)), ((1.1, 1.3),)))
        del record['turns']
        record['provenance'] = dict(sources=[dict(inserted_interval=[.2, 1.]),
                                            dict(inserted_interval=[1.1, 1.3])])
        turns = reference_turns(record)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]['internal_pauses'], [[.4, .6]])

    def test_invalid_turn_order_identity_support_and_uncertainty_rejected(self):
        mutations = [lambda r: r['turns'][0].update(onset_s=-.1),
                     lambda r: r['turns'][1].update(id='turn-0'),
                     lambda r: r['turns'][1].update(onset_s=.4),
                     lambda r: r['turns'][0].update(acoustic_intervals=[[.1, .3]]),
                     lambda r: r['turns'][0].update(onset_uncertainty_s=[.21, .22])]
        for mutate in mutations:
            record = record_for((((.2, .5),), ((.6, .9),)))
            mutate(record)
            with self.subTest(record=record), self.assertRaises(ValueError):
                reference_turns(record)


class SelectionIsolationTests(unittest.TestCase):
    def test_confirmatory_mode_rejects_missing_or_tampered_freeze_metadata(self):
        from vadbench import boundary_report
        cases = ('missing', 'stage', 'manifest_hash', 'test_hash', 'test_subset', 'turns')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                records = []
                for split in ('dev', 'test'):
                    record = record_for()
                    record.update(id=split, split=split)
                    records.append(record)
                if case == 'turns':
                    del records[0]['turns']
                manifest = dict(records=records)
                manifest_path = root/'manifest.json'
                manifest_path.write_text(json.dumps(manifest))
                subset = dict(manifest, records=[records[1]])
                if case == 'test_subset':
                    subset = copy.deepcopy(subset)
                    subset['records'][0]['condition']['name'] = 'changed-after-freeze'
                test_path = root/'test-manifest.json'
                test_path.write_text(json.dumps(subset))
                freeze = dict(stage='before_model_scoring_and_selection',
                              manifest_sha256=boundary_report.digest(manifest_path),
                              test_manifest_sha256=boundary_report.digest(test_path))
                if case == 'stage':
                    freeze['stage'] = 'after_test_selection'
                elif case == 'manifest_hash':
                    freeze['manifest_sha256'] = 'incorrect'
                elif case == 'test_hash':
                    freeze['test_manifest_sha256'] = 'incorrect'
                if case != 'missing':
                    (root/'FROZEN.json').write_text(json.dumps(freeze))
                with patch.object(boundary_report, 'load_inputs', return_value=(manifest, {}, {})):
                    with patch.object(boundary_report, 'candidate_controllers') as select:
                        with self.assertRaises(ValueError):
                            boundary_report.analyze(manifest_path, root/'raw', root/'out',
                                                    backends=['fixture'])
                        select.assert_not_called()

    def test_candidate_controller_generation_rejects_holdout_records(self):
        from vadbench.boundary_report import candidate_controllers
        record = record_for()
        record['split'] = 'test'
        with self.assertRaises(ValueError):
            candidate_controllers([record], {'fixture': trace_for(((.2, .5),))})
        with self.assertRaises(ValueError):
            candidate_controllers([], {})

    def test_binary_candidates_keep_native_threshold_and_full_duration_grid(self):
        from vadbench.boundary_report import candidate_controllers, SILENCES, CONFIRMATIONS
        record = record_for()
        record['split'] = 'dev'
        candidates, choices = candidate_controllers(
            [record], {'fixture': trace_for(((.2, .5),))}, binary=True)
        self.assertEqual(len(candidates), len(SILENCES)*len(CONFIRMATIONS))
        self.assertEqual({(c.on, c.off) for c in candidates}, {(.5, .5)})
        self.assertEqual({c.silence_s for c in candidates}, set(SILENCES))
        self.assertEqual({c.start_s for c in candidates}, set(CONFIRMATIONS))
        self.assertTrue(all(choice['feasible'] for choice in choices))

    def test_pareto_dominance_keeps_equivalent_candidates_and_removes_worse(self):
        from vadbench.boundary_report import pareto_indices
        good = measure()
        bad = copy.deepcopy(good)
        equal = copy.deepcopy(good)
        bad['false_starts_per_negative_hour'] += 1
        self.assertEqual(pareto_indices([good, bad, equal]), [0, 2])

    def test_operational_false_activity_breaks_equal_coverage_selection_ties(self):
        from vadbench.boundary_report import choose_points, pareto_indices
        good = measure()
        long_false_activity = copy.deepcopy(good)
        long_false_activity['operational_false_positive_fraction'] += .2
        # Hold event rate, coverage, responsiveness and every other objective fixed.
        self.assertEqual(pareto_indices([long_false_activity, good]), [1])
        self.assertTrue(all(row['index'] == 1 for row in choose_points([long_false_activity, good])))

    def test_selection_objectives_require_reference_negative_exposure(self):
        from vadbench.boundary_report import objectives
        metric = measure()
        metric['negative_hours'] = 0.
        with self.assertRaises(ValueError):
            objectives(metric)

    def test_holdout_changes_cannot_change_selections_and_freeze_precedes_scoring(self):
        from vadbench import boundary_report
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root/'raw'
            raw.mkdir()
            records = []
            for split in ('dev', 'test'):
                record = record_for()
                record.update(id=split, split=split)
                records.append(record)
            manifest_path = root/'manifest.json'
            manifest_path.write_text(json.dumps(dict(records=records)))
            manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            (raw/'fixture.json').write_text(json.dumps(dict(
                backend='fixture', status='ok', manifest_sha256=manifest_hash,
                adapter=dict(score_kind='binary'))))
            frozen = []
            summaries = []
            for number, holdout in enumerate((trace_for(((.2, .5),)), trace_for())):
                np.savez(raw/'fixture.npz', dev=trace_for(((.2, .5),)), test=holdout)
                output = root/f'analysis-{number}'
                original_evaluate = boundary_report.evaluate_boundaries
                observed_splits = []

                def checked_evaluate(subset, *args, **kwargs):
                    split = {r['split'] for r in subset}
                    self.assertEqual(len(split), 1)
                    observed_splits.extend(split)
                    if split == {'test'}:
                        self.assertTrue((output/'frozen-selections.json').is_file())
                        saved = json.loads((output/'frozen-selections.json').read_text())
                        self.assertFalse(saved['test_used_for_selection'])
                        self.assertEqual(len(saved['selections']), 13)
                    return original_evaluate(subset, *args, **kwargs)

                with patch.object(boundary_report, 'evaluate_boundaries', side_effect=checked_evaluate):
                    with redirect_stdout(io.StringIO()):
                        summaries.append(boundary_report.analyze(
                            manifest_path, raw, output, backends=['fixture'], exploratory=True))
                self.assertIn('test', observed_splits)
                first_test = observed_splits.index('test')
                self.assertEqual(set(observed_splits[:first_test]), {'dev'})
                self.assertNotIn('dev', observed_splits[first_test:])
                frozen.append(json.loads((output/'frozen-selections.json').read_text()))
                with self.assertRaises(FileExistsError):
                    boundary_report.analyze(manifest_path, raw, output,
                                            backends=['fixture'], exploratory=True)
            self.assertEqual(frozen[0]['selections'], frozen[1]['selections'])
            self.assertEqual(frozen[0]['threshold_choices'], frozen[1]['threshold_choices'])
            self.assertNotEqual(summaries[0]['shared'][0]['test']['onset'],
                                summaries[1]['shared'][0]['test']['onset'])


if __name__ == '__main__':
    unittest.main()
