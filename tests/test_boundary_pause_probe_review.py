"""Independent retained/PCM audit of the bounded hard-gated pause supplement.

This file does not import the pause generator, its activity helpers, or the
production metric evaluator. Runtime-only checks skip when WAV/NPZ data are not
present in a normal checkout.
"""
import gzip
import hashlib
import json
from pathlib import Path
import unittest
import wave

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT/'results'/'boundary-pause-probe'
PRIMARY = ROOT/'results'/'boundary-latency'
PAUSES = (50, 100, 150, 200, 300, 500, 800)
SR, FRAME = 16000, 160
PRIMARY_HASHES = {
    'dataset-manifest.json': '9fba764ac3692dba68712e5b6ea78904288bc479cf44292c4a8a81ed089a7106',
    'summary.json': '2446067b8461a8f1cb5c3a9c6717e1268850381b8c4b118a00611d5627e13714',
    'development-curves.json': 'ef6a2caf682e093543b0928c8365d239f7dca978cda7f0a33a36be3e5743dbcd',
    'per-turn-test.json': '85e5dccb505a328d8c1e0a12382ddfeb6e3653ab8ec59f8451ea7b05142769ad',
}
CORE_HASH = 'e653f90fe1a93352627da4f10fc78263856da0361bf8d2a43cfc40a98e6d94d6'


def logical_bytes(path):
    return path.read_bytes() if path.is_file() else gzip.decompress(Path(str(path)+'.gz').read_bytes())


def read(path):
    return json.loads(logical_bytes(path), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def emitted_rms_spans(pcm):
    """Independent integer-PCM formulation of the declared source-local proxy."""
    x = pcm.astype(np.float64)
    scale = np.sqrt(np.dot(x, x)/len(x))
    normalized = .1*x/scale
    padded = np.zeros(((len(x)+FRAME-1)//FRAME)*FRAME)
    padded[:len(x)] = normalized
    rms = np.sqrt(np.mean(padded.reshape(-1, FRAME)**2, axis=1))
    active = rms >= max(10**(-48/20), np.max(rms)*10**(-40/20))
    result = []
    start = None
    for index, positive in enumerate(list(active)+[False]):
        if positive and start is None:
            start = index*FRAME
        elif not positive and start is not None:
            result.append([start, min(index*FRAME, len(x))])
            start = None
    return result


class PauseProbeRetainedReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (PROBE/'manifest.json').is_file():
            raise unittest.SkipTest('Supplement has not been generated')
        cls.manifest = read(PROBE/'manifest.json')
        cls.frozen = read(PROBE/'FROZEN.json')
        cls.primary = read(PRIMARY/'frozen-selections.json')

    def test_frozen_input_source_and_primary_identities(self):
        names = {'manifest.json': 'manifest_sha256', 'test-manifest.json': 'test_manifest_sha256',
                 'specification.json': 'specification_sha256', 'generator-frozen.py.txt': 'generator_snapshot_sha256'}
        for filename, key in names.items():
            self.assertEqual(digest(logical_bytes(PROBE/filename)), self.frozen[key])
        for filename, expected in self.frozen['source_sha256'].items():
            self.assertEqual(digest((ROOT/'vadbench'/filename).read_bytes()), expected)
        self.assertEqual((PROBE/'generator-frozen.py.txt').read_bytes(),
                         (ROOT/'vadbench'/'boundary_pause_probe.py').read_bytes())
        self.assertEqual(digest((ROOT/'vadbench'/'boundary_latency.py').read_bytes()), CORE_HASH)
        self.assertEqual(self.frozen['primary_frozen_selections_sha256'],
                         digest(logical_bytes(PRIMARY/'frozen-selections.json')))
        self.assertEqual(self.frozen['stage'], 'before_model_inference')
        self.assertEqual(self.frozen['primary_manifest_sha256'], PRIMARY_HASHES['dataset-manifest.json'])
        for filename, expected in PRIMARY_HASHES.items():
            self.assertEqual(digest(logical_bytes(PRIMARY/filename)), expected)

    def test_complete_factorial_design_and_exact_provenance_subset(self):
        records = self.manifest['records']
        self.assertEqual(len(records), 112)
        self.assertEqual(len({r['id'] for r in records}), 112)
        actual = {(r['split'], r['condition']['replicate'], r['condition']['pause_ms'],
                   r['condition']['branch']) for r in records}
        expected = {(split, rep, pause, branch) for split in ('dev', 'test')
                    for rep in range(4) for pause in PAUSES for branch in ('stop', 'resume')}
        self.assertEqual(actual, expected)
        self.assertEqual(read(PROBE/'test-manifest.json'),
                         dict(self.manifest, records=[r for r in records if r['split'] == 'test']))
        for record in records:
            self.assertEqual(len(record['turns']), 1)
            self.assertTrue(record['provenance']['reused_primary_texts_and_voices'])

    def test_repeated_stops_and_splice_risk_are_not_independent_holdout_claims(self):
        for split in ('dev', 'test'):
            for rep in range(4):
                stops = [r for r in self.manifest['records'] if r['split'] == split
                         and r['condition']['replicate'] == rep and r['condition']['branch'] == 'stop']
                self.assertEqual(len(stops), 7)
                self.assertEqual(len({r['sha256'] for r in stops}), 1)
        generation = self.manifest['generation']
        self.assertIn('not a fresh independent holdout', generation['split_policy'])
        self.assertIn('excises faint speech', generation['limitation'])
        self.assertIn('splice', generation['limitation'])
        self.assertIn('no diagnostic fitting', generation['selection_policy'])


class PauseProbePCMReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (PROBE/'manifest.json').is_file():
            raise unittest.SkipTest('Supplement has not been generated')
        cls.records = read(PROBE/'manifest.json')['records']
        if not all((PROBE/r['path']).is_file() for r in cls.records):
            raise unittest.SkipTest('Runtime WAVs intentionally not bundled')
        cls.audio = {}
        for record in cls.records:
            path = PROBE/record['path']
            if digest(path.read_bytes()) != record['sha256']:
                raise AssertionError('WAV byte hash mismatch')
            with wave.open(str(path), 'rb') as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) != (1, 2, SR, SR*8):
                    raise AssertionError('WAV format mismatch')
                cls.audio[record['id']] = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')

    def test_independently_remeasured_emitted_activity_and_actual_gaps(self):
        measured = {pause: [] for pause in PAUSES}
        for record in self.records:
            pcm = self.audio[record['id']]
            bounds = []
            reconstructed = np.zeros_like(pcm)
            all_spans = []
            for source in record['provenance']['sources']:
                a, b = source['inserted_interval_samples']
                chunk = pcm[a:b]
                self.assertEqual(digest(chunk.tobytes()), source['gated_pcm_sha256'])
                spans = emitted_rms_spans(chunk)
                self.assertEqual((spans[0][0], spans[-1][1]), (0, len(chunk)))
                self.assertEqual((int(chunk[0]), int(chunk[-1])), (0, 0))
                self.assertEqual(source['edge_fade_samples'], 16)
                shifted = [[a+x, a+y] for x, y in spans]
                expected = [[round(x*SR), round(y*SR)] for x, y in source['activity_intervals']]
                self.assertEqual(shifted, expected)
                all_spans.extend(shifted)
                bounds.append((shifted[0][0], shifted[-1][1]))
                reconstructed[a:b] = chunk
            np.testing.assert_array_equal(pcm, reconstructed)
            self.assertEqual(all_spans, [[round(a*SR), round(b*SR)] for a, b in record['speech_intervals']])
            turn = record['turns'][0]
            self.assertEqual(round(turn['onset_s']*SR), bounds[0][0])
            self.assertEqual(round(turn['offset_s']*SR), bounds[-1][1])
            if record['condition']['branch'] == 'resume':
                self.assertEqual(len(bounds), 2)
                gap = bounds[1][0]-bounds[0][1]
                pause = record['condition']['pause_ms']
                self.assertEqual(gap, pause*SR//1000)
                self.assertFalse(pcm[bounds[0][1]:bounds[1][0]].any())
                self.assertEqual(gap, record['causal_pair']['measured_rms_gap_samples'])
                self.assertEqual(bounds[1][0], record['causal_pair']['resume_sample'])
                measured[pause].append(gap*1000/SR)
        for pause, values in measured.items():
            self.assertEqual(values, [float(pause)]*8)

    def test_every_pair_has_exact_pcm_history_through_horizon(self):
        pairs = {}
        for record in self.records:
            pairs.setdefault(record['causal_pair']['id'], {})[record['condition']['branch']] = record
        self.assertEqual(len(pairs), 56)
        for branches in pairs.values():
            stop, resume = branches['stop'], branches['resume']
            horizon = stop['causal_pair']['resume_sample']
            prefix = self.audio[stop['id']][:horizon]
            np.testing.assert_array_equal(prefix, self.audio[resume['id']][:horizon])
            self.assertEqual(digest(prefix.tobytes()), stop['causal_pair']['shared_prefix_pcm_sha256'])
            self.assertEqual(stop['causal_pair']['shared_prefix_pcm_sha256'],
                             resume['causal_pair']['shared_prefix_pcm_sha256'])


class PauseProbeFrozenReplayReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not any((PROBE/name).is_file() for name in ('summary.json', 'summary.json.gz')):
            raise unittest.SkipTest('Supplement analysis has not completed')
        cls.summary = read(PROBE/'summary.json')
        cls.primary = read(PRIMARY/'frozen-selections.json')

    def test_every_primary_policy_is_reused_exactly_without_selection(self):
        actual = self.summary['frozen_selections']
        self.assertEqual(len(actual), 156)
        stripped = [{k: v for k, v in row.items() if k not in ('kind', 'metric_key')} for row in actual]
        self.assertEqual(stripped, self.primary['selections'])
        self.assertEqual(len(self.summary['shared']), 24)
        keys = {row['metric_key'] for row in actual+self.summary['shared']}
        self.assertEqual(keys, set(self.summary['aggregate_metrics']))
        for row in actual+self.summary['shared']:
            self.assertEqual(row['controller'], self.summary['aggregate_metrics'][row['metric_key']]['controller'])

    def test_all_turn_denominators_and_duration_breakdowns(self):
        self.assertEqual(len(self.summary['baseline_by_pause']), 336)
        for metric in self.summary['aggregate_metrics'].values():
            self.assertEqual(metric['counts']['turns'], 56)
            for side in ('onset', 'end'):
                for row in metric[side]['deadlines_ms'].values():
                    self.assertEqual(row['total'], 56)
                    self.assertAlmostEqual(row['fraction'], row['successes']/56)
        for row in self.summary['baseline_by_pause']:
            self.assertEqual(row['metric']['counts']['turns'], 4)
            self.assertEqual(row['actual_rms_gap_ms'], dict(min=float(row['pause_ms']), max=float(row['pause_ms'])))
        for rows in self.summary['causal_by_controller'].values():
            self.assertEqual(len(rows), 28)
            for row in rows:
                self.assertEqual(row['actual_rms_gap_ms'], row['pause_ms'])
                for instant in row['pre_resume_end_available_s']:
                    self.assertGreaterEqual(instant, row['prefix_end_s']-1e-9)
                    self.assertLess(instant, row['resume_s']-1e-9)

    def test_all_raw_hashes_identities_and_pre_resume_acquisition_rows(self):
        raw = PROBE/'runtime-output'/'raw'
        backends = self.summary['backends']
        if not all((raw/f'{backend}.npz').is_file() for backend in backends):
            self.skipTest('Runtime NPZ traces intentionally not bundled')
        records = read(PROBE/'manifest.json')['records']
        ids = {r['id'] for r in records}
        pairs = {}
        for record in records:
            pairs.setdefault(record['causal_pair']['id'], {})[record['condition']['branch']] = record
        checked = 0
        for backend in backends:
            run = read(raw/f'{backend}.json')
            self.assertEqual(run['status'], 'ok')
            self.assertEqual(run['manifest_sha256'], self.summary['frozen_inputs']['manifest_sha256'])
            for suffix, expected in self.summary['inference_audit']['raw_sha256'][backend].items():
                self.assertEqual(digest((raw/f'{backend}.{suffix}').read_bytes()), expected)
            with np.load(raw/f'{backend}.npz', allow_pickle=False) as traces:
                self.assertEqual(set(traces.files), ids)
                for pair in pairs.values():
                    horizon = pair['stop']['causal_pair']['resume_time_s']
                    stop, resume = traces[pair['stop']['id']], traces[pair['resume']['id']]
                    np.testing.assert_array_equal(stop[stop[:, 3] <= horizon+1e-9],
                                                  resume[resume[:, 3] <= horizon+1e-9])
                    checked += 1
        self.assertEqual(checked, 672)


if __name__ == '__main__':
    unittest.main()
