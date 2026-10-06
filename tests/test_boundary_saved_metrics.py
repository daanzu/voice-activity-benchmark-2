"""Independent arithmetic and provenance audit of saved boundary results."""
import hashlib
import gzip
import json
import math
from pathlib import Path
import unittest

import numpy as np

from vadbench.boundary_latency import Controller
from vadbench.run import BACKENDS


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT/'results'/'boundary-latency'


def read_bytes(path):
    if path.is_file():
        return path.read_bytes()
    return gzip.decompress(path.with_name(path.name+'.gz').read_bytes())


def read_json(path):
    def reject(value):
        raise ValueError(f'Nonstandard JSON numeric constant: {value}')
    return json.loads(read_bytes(path), parse_constant=reject)


def sha(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


class BoundaryResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not any((RESULTS/name).is_file() for name in ('summary.json', 'summary.json.gz')):
            raise unittest.SkipTest('Frozen boundary results have not been generated')
        cls.summary = read_json(RESULTS/'summary.json')
        cls.frozen = read_json(RESULTS/'frozen-selections.json')
        cls.inputs = read_json(RESULTS/'frozen-inputs.json')
        cls.manifest = read_json(RESULTS/'dataset-manifest.json')
        cls.details = read_json(RESULTS/'per-turn-test.json')
        cls.curves = read_json(RESULTS/'development-curves.json')

    def test_complete_backend_split_and_shared_controller_coverage(self):
        summary = self.summary
        self.assertEqual(summary['backends'], BACKENDS)
        self.assertEqual(len(summary['shared']), 2*len(BACKENDS))
        self.assertEqual(len(summary['selections']), 13*len(BACKENDS))
        records = self.manifest['records']
        self.assertEqual(len({r['id'] for r in records}), len(records))
        self.assertEqual(summary['dataset']['records'], len(records))
        for split in ('dev', 'test'):
            subset = [r for r in records if r['split'] == split]
            self.assertEqual(summary['dataset'][split+'_records'], len(subset))
            self.assertEqual(summary['dataset'][split+'_turns'], sum(len(r['turns']) for r in subset))
        for backend in BACKENDS:
            shared = [row for row in summary['shared'] if row['backend'] == backend]
            self.assertEqual({row['configuration'] for row in shared}, {'common-0ms', 'common-200ms'})
            for row in shared:
                self.assertEqual(row['controller']['on'], .5)
                self.assertEqual(row['controller']['off'], .5)
                self.assertEqual(row['controller']['start_s'], 0.)

    def test_frozen_choices_hashes_and_published_controller_identity(self):
        manifest_hash = sha(RESULTS/'dataset-manifest.json')
        self.assertEqual(self.summary['manifest_sha256'], manifest_hash)
        self.assertEqual(self.frozen['manifest_sha256'], manifest_hash)
        self.assertEqual(self.inputs['manifest_sha256'], manifest_hash)
        self.assertEqual(self.inputs['mode'], 'frozen_synthetic_stress_test')
        self.assertFalse(self.frozen['test_used_for_selection'])
        frozen = {(row['backend'], row['policy']): row['controller']
                  for row in self.frozen['selections']}
        actual = {(row['backend'], row['policy']): row['controller']
                  for row in self.summary['selections']}
        self.assertEqual(frozen, actual)
        for row in self.summary['shared']+self.summary['selections']:
            for split in ('dev', 'test'):
                self.assertEqual(row['controller'], row[split]['controller'])
                self.assertEqual(Controller(**row['controller']).id, row[split]['controller_id'])
        for backend, extensions in self.inputs['raw_sha256'].items():
            for extension, expected in extensions.items():
                path = RESULTS/'raw'/f'{backend}.{extension}'
                if path.is_file():
                    self.assertEqual(sha(path), expected)
            run = self.summary['inference_metadata'][backend]
            self.assertEqual(run['backend'], backend)
            self.assertEqual(run['status'], 'ok')
            self.assertEqual(run['manifest_sha256'], manifest_hash)

    def test_per_turn_denominators_deadlines_and_quantiles_recompute(self):
        expected_ids = {(r['id'], t['id']) for r in self.manifest['records']
                        if r['split'] == 'test' for t in r['turns']}
        detail_map = {(item['backend'], item['controller_id']): item['turn_results']
                      for item in self.details}
        self.assertEqual(len(detail_map), len(self.details))
        for row in self.summary['shared']+self.summary['selections']:
            metric = row['test']
            turns = detail_map[row['backend'], metric['controller_id']]
            with self.subTest(backend=row['backend'], controller=metric['controller_id']):
                self.assertEqual({(r['record_id'], r['turn_id']) for r in turns}, expected_ids)
                self.assertEqual(len(turns), len(expected_ids))
                self.assertEqual(metric['counts']['turns'], len(turns))
                for side in ('onset', 'end'):
                    latencies = [r[side+'_latency_s'] for r in turns]
                    finite = sorted(x for x in latencies if x is not None)
                    for ms, stored in metric[side]['deadlines_ms'].items():
                        count = sum(x is not None and -1e-9 <= x <= int(ms)/1000+1e-9
                                    for x in latencies)
                        self.assertEqual(stored['successes'], count)
                        self.assertEqual(stored['total'], len(turns))
                        self.assertAlmostEqual(stored['fraction'], count/len(turns))
                    for name, denominator in [('all_turn_quantiles', len(turns)),
                                              ('conditional_quantiles', len(finite))]:
                        stored = metric[side][name]
                        self.assertEqual(stored['denominator'], denominator)
                        self.assertEqual(stored['observations'], len(finite))
                        for quantile in (50, 90, 95):
                            rank = math.ceil(quantile/100*denominator)
                            reached = denominator > 0 and rank <= len(finite)
                            self.assertEqual(stored[f'p{quantile}']['reached'], reached)
                            expected = finite[rank-1] if reached else None
                            self.assertEqual(stored[f'p{quantile}']['seconds'], expected)
                for key, stored in metric['joint_intact_deadlines'].items():
                    start_limit, end_limit = (int(x)/1000 for x in key.split('/'))
                    count = sum(r['intact'] and r['onset_latency_s'] <= start_limit+1e-9
                                and r['end_latency_s'] <= end_limit+1e-9 for r in turns)
                    self.assertEqual(stored['successes'], count)
                    self.assertEqual(stored['total'], len(turns))
                    self.assertAlmostEqual(stored['fraction'], count/len(turns))
                for count_name, field in [('missed_turns', 'missed'),
                                          ('early_active_turns', 'early_active'),
                                          ('premature_end_turns', 'premature_end'),
                                          ('censored_turns', 'censored'),
                                          ('fragmented_turns', 'fragmented')]:
                    self.assertEqual(metric['counts'][count_name], sum(r[field] for r in turns))
                self.assertEqual(metric['counts']['no_distinct_start_turns'],
                                 sum(r['onset_latency_s'] is None for r in turns))

    def test_reference_exposure_and_coverage_arithmetic(self):
        for split in ('dev', 'test'):
            metrics = [row[split] for row in self.summary['shared']+self.summary['selections']]
            self.assertEqual(len({m['negative_hours'] for m in metrics}), 1)
            self.assertEqual(len({m['acoustic_speech_s'] for m in metrics}), 1)
            for metric in metrics:
                self.assertAlmostEqual(metric['false_starts_per_negative_hour'],
                                       metric['counts']['false_starts']/metric['negative_hours'])
                for prefix in ('source_aligned', 'operational'):
                    self.assertAlmostEqual(metric[prefix+'_speech_recall'],
                        1-metric[prefix+'_clipped_s']/metric['acoustic_speech_s'])
                    self.assertGreaterEqual(metric[prefix+'_speech_recall'], -1e-9)
                    self.assertLessEqual(metric[prefix+'_speech_recall'], 1+1e-9)
                    self.assertAlmostEqual(metric[prefix+'_false_positive_fraction'],
                        metric[prefix+'_false_positive_s']/(metric['negative_hours']*3600))
                    self.assertGreaterEqual(metric[prefix+'_false_positive_fraction'], -1e-9)
                    self.assertLessEqual(metric[prefix+'_false_positive_fraction'], 1+1e-9)

    def test_uncertainty_envelope_contains_nominal_in_all_retained_candidates(self):
        metrics = [row['metric'] for row in self.curves]
        metrics += [row[split] for row in self.summary['shared']+self.summary['selections']
                    for split in ('dev', 'test')]
        for metric in metrics:
            for side in ('onset', 'end'):
                for deadline, nominal in metric[side]['deadlines_ms'].items():
                    certain = metric[side]['uncertainty_certain_deadlines_ms'][deadline]
                    possible = metric[side]['uncertainty_possible_deadlines_ms'][deadline]
                    self.assertLessEqual(certain['successes'], nominal['successes'])
                    self.assertLessEqual(nominal['successes'], possible['successes'])

    def test_every_chosen_point_is_optimal_under_its_development_policy(self):
        candidates = {b: [r['metric'] for r in self.curves if r['backend'] == b] for b in BACKENDS}
        for row in self.summary['selections']:
            def key(metric):
                common = (-metric['source_aligned_speech_recall'],
                          metric['operational_false_positive_fraction'],
                          metric['false_starts_per_negative_hour'],
                          metric['counts']['premature_end_turns'],
                          metric['counts']['fragmented_turns'], metric['controller_id'])
                if row['policy'] == 'recall-priority':
                    return common
                deadline = row['policy'].removeprefix('joint-').replace('-', '/')
                return (-metric['joint_intact_deadlines'][deadline]['fraction'], *common)
            best = min(candidates[row['backend']], key=key)
            self.assertEqual(row['dev'], best)

    def test_saved_pareto_flags_match_independent_nondominance(self):
        for backend in BACKENDS:
            rows = [r for r in self.curves if r['backend'] == backend]
            objectives = []
            for row in rows:
                m = row['metric']
                n = m['counts']['turns']
                objectives.append([1-m['onset']['deadlines_ms']['100']['fraction'],
                                   1-m['end']['deadlines_ms']['300']['fraction'],
                                   1-m['source_aligned_speech_recall'],
                                   m['false_starts_per_negative_hour'],
                                   m['operational_false_positive_fraction'],
                                   m['counts']['premature_end_turns']/n,
                                   m['counts']['fragmented_turns']/n])
            values = np.asarray(objectives)
            for i, row in enumerate(rows):
                dominated = any(np.all(other <= values[i]+1e-12)
                                and np.any(other < values[i]-1e-12) for other in values)
                self.assertEqual(row['pareto'], not dominated)


if __name__ == '__main__':
    unittest.main()
