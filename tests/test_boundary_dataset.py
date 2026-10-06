"""Deterministic unit fixtures: no FFmpeg, downloaded model, or full corpus synthesis."""
import hashlib
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from vadbench.boundary_dataset import (
    BASE_ONSET_SAMPLES, DURATION, PAUSES_MS, PHASES_MS, SR, STRESSES, TEXTS,
    VOICES, build_record, generate, prepare_source, record_specs, validate_manifest,
)


def fake_synth(text, voice, cache):
    n = int(.66 * SR)
    t = np.arange(n) / SR
    frequency = 170 + sum(map(ord, text + voice)) % 90
    # Long tiny synthesizer support precedes/follows voiced energy; these
    # samples must widen uncertainty, never become nominal acoustic onset.
    audio = np.full(n, 5e-5)
    voiced = .12 * np.sin(2 * np.pi * frequency * t)
    audio[int(.12 * SR):int(.56 * SR)] = voiced[int(.12 * SR):int(.56 * SR)]
    audio[int(.27 * SR):int(.32 * SR)] = 0
    return audio, {'voice': voice, 'text': text, 'source_sha256': 'fixture',
                   'source_path': 'sources/fixture.wav', 'engine': 'deterministic fixture'}


def read_pcm(root, record):
    with wave.open(str(root / record['path']), 'rb') as wav:
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')


class BoundaryDatasetTests(unittest.TestCase):
    def test_design_and_split_assets(self):
        specs = record_specs()
        self.assertEqual(len(specs), 272)
        self.assertEqual(len({s['noise_seed'] for s in specs}), 272)
        self.assertTrue(set(VOICES['dev']).isdisjoint(VOICES['test']))
        dev = {text for group in TEXTS['dev'].values() for text in group}
        test = {text for group in TEXTS['test'].values() for text in group}
        self.assertTrue(dev.isdisjoint(test))
        for split in VOICES:
            selected = [s for s in specs if s['split'] == split]
            self.assertEqual(len(selected), 136)
            for stress in STRESSES:
                phases = [s['phase_ms'] for s in selected if s.get('stress') == stress]
                self.assertEqual(phases, list(PHASES_MS))
            self.assertEqual({s['pause_ms'] for s in selected if s['family'] == 'pause'}, set(PAUSES_MS))
            self.assertEqual({s['sample_offset'] for s in selected if s['family'] == 'onset'}, {0, 1})
        with self.assertRaises(ValueError):
            record_specs(-1)

    @patch('vadbench.boundary_dataset.synthesize', side_effect=fake_synth)
    def test_onset_phase_is_acoustic_proxy_not_source_placement(self, _):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            specs = [s for s in record_specs() if s['family'] == 'onset' and s['split'] == 'dev']
            for spec in specs:
                record = build_record(spec, root, root / 'sources')
                turn = record['turns'][0]
                desired = BASE_ONSET_SAMPLES + spec['phase_ms'] * 16 + spec['sample_offset']
                self.assertEqual(round(turn['onset_s'] * SR), desired)
                self.assertEqual(len(record['turns']), 1)
                self.assertEqual(turn['internal_pauses'], [])
                self.assertEqual(turn['acoustic_intervals'], record['speech_intervals'])
                self.assertGreaterEqual(len(turn['acoustic_intervals']), 2)
            clean = build_record(specs[0], root, root / 'sources')
            turn = clean['turns'][0]
            support_start = clean['provenance']['sources'][0]['emitted_support_interval'][0]
            self.assertLess(support_start, turn['onset_s'] - .02)
            self.assertLessEqual(turn['onset_uncertainty_s'][0], support_start)

    @patch('vadbench.boundary_dataset.synthesize', side_effect=fake_synth)
    def test_pairs_have_identical_causal_histories_and_one_resumed_turn(self, _):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for pause in PAUSES_MS:
                specs = [s for s in record_specs() if s['family'] == 'pause'
                         and s['split'] == 'dev' and s['replicate'] == 0 and s['pause_ms'] == pause]
                stop, resumed = [build_record(s, root, root / 'sources') for s in specs]
                records.extend((stop, resumed))
                pair = resumed['causal_pair']
                endpoint = pair['resume_sample']
                before = read_pcm(root, stop)
                after = read_pcm(root, resumed)
                np.testing.assert_array_equal(before[:endpoint], after[:endpoint])
                self.assertNotEqual(before[endpoint:].tobytes(), after[endpoint:].tobytes())
                self.assertEqual(hashlib.sha256(before[:endpoint].tobytes()).hexdigest(),
                                 pair['shared_prefix_pcm_sha256'])
                self.assertEqual(stop['causal_pair']['shared_prefix_pcm_sha256'],
                                 pair['shared_prefix_pcm_sha256'])
                self.assertEqual(len(resumed['turns']), 1)
                self.assertEqual(stop['turns'][0]['internal_pauses'], [])
                gap = resumed['turns'][0]['internal_pauses'][0]
                self.assertAlmostEqual(gap[1] - gap[0], pause / 1000)
                self.assertLess(gap[1], resumed['turns'][0]['offset_s'])
            audit = validate_manifest({'records': records}, root)
            self.assertEqual(audit['causal_pairs'], 7)

    @patch('vadbench.boundary_dataset.synthesize', side_effect=fake_synth)
    def test_quiet_fade_and_synthetic_breath_are_honest(self, _):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean = prepare_source('Hush', 'awb', root)
            quiet = prepare_source('Hush', 'awb', root, 'quiet')
            faded = prepare_source('Hush', 'awb', root, 'fade')
            self.assertLess(np.sqrt(np.mean(quiet['pcm'].astype(float) ** 2)),
                            np.sqrt(np.mean(clean['pcm'].astype(float) ** 2)) / 5)
            self.assertEqual(quiet['activity'], clean['activity'])
            self.assertLessEqual(faded['activity'][-1][1], clean['activity'][-1][1])
            spec = next(s for s in record_specs() if s.get('stress') == 'synthetic_breath')
            record = build_record(spec, root, root / 'sources')
            tail = record['provenance']['synthetic_breath_like_tail']
            self.assertFalse(tail['speech_label'])
            self.assertGreaterEqual(record['turns'][0]['offset_uncertainty_s'][1], tail['interval'][1])
            self.assertLessEqual(record['speech_intervals'][-1][1], tail['interval'][0])

    def test_negative_streams_have_no_turns_and_reproducible_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for spec in [s for s in record_specs() if s['family'] == 'negative' and s['replicate'] == 0]:
                first = build_record(spec, root, root / 'sources')
                second = build_record(spec, root, root / 'sources')
                self.assertEqual(first, second)
                for field in ('turns', 'speech_intervals', 'target_intervals', 'uncertain_intervals'):
                    self.assertEqual(first[field], [])
                if spec['kind'] == 'silence':
                    self.assertFalse(read_pcm(root, first).any())

    @patch('vadbench.boundary_dataset.subprocess.check_output', return_value='fixture ffmpeg\n')
    @patch('vadbench.boundary_dataset.synthesize', side_effect=fake_synth)
    def test_generation_freezes_test_and_refuses_overwrite(self, _, __):
        chosen = [record_specs()[i] for i in (0, 64, 65, 120, 136, 200, 201, 256)]
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as other:
            root = Path(directory)
            with patch('vadbench.boundary_dataset.record_specs', return_value=chosen):
                manifest = generate(root)
                generate(other)
                with self.assertRaises(FileExistsError):
                    generate(root)
            frozen = json.loads((root / 'FROZEN.json').read_text())
            self.assertEqual(frozen['stage'], 'before_model_scoring_and_selection')
            test = json.loads((root / 'test-manifest.json').read_text())
            self.assertTrue(all(r['split'] == 'test' for r in test['records']))
            self.assertEqual(frozen['test_manifest_sha256'],
                             hashlib.sha256((root / 'test-manifest.json').read_bytes()).hexdigest())
            self.assertEqual(frozen['manifest_sha256'],
                             hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest())
            self.assertEqual((root / 'manifest.json').read_bytes(),
                             (Path(other) / 'manifest.json').read_bytes())
            self.assertEqual(validate_manifest(manifest, root)['records'], 8)
            # Verify metadata tampering is detected rather than trusting a stored hash.
            manifest['records'][1]['causal_pair']['shared_prefix_pcm_sha256'] = 'bad'
            with self.assertRaisesRegex(ValueError, 'prefix hash'):
                validate_manifest(manifest, root)


if __name__ == '__main__':
    unittest.main()
