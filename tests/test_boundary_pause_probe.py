"""Hard-gated diagnostic tests use deterministic synthetic PCM, no VAD models."""
import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from vadbench.boundary_pause_probe import (EDGE_FADE_SAMPLES, SR, audit_causal_traces,
    build_record, controller_plan, gate_source, generate, json_bytes, paired_cuts,
    read_pcm, specs, validate_manifest, write_result)
from vadbench.boundary_latency import Controller, evaluate_boundaries
from vadbench.boundary_dataset import TEXTS, VOICES, _activity_samples
from vadbench.run import BACKENDS


def fake_synth(text, voice, cache):
    t = np.arange(16000) / SR
    pcm = np.full(len(t), .00003)
    pcm[1600:12000] = .15*np.sin(2*np.pi*(170+len(text))*t[1600:12000])
    pcm[6400:7040] = 0
    return pcm, dict(text=text, voice=voice, source_sha256='fixture', source_path='fixture.wav', engine='fixture')


class PauseProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        with patch('vadbench.boundary_dataset.synthesize', side_effect=fake_synth):
            cls.sources = {(split, rep, role):gate_source(TEXTS[split][role][rep], VOICES[split][rep%2], cls.root)
                for split in VOICES for rep in range(4) for role in ('prefix', 'continuation')}
        cls.records = [build_record(s, cls.root, cls.sources) for s in specs()]
        cls.manifest = dict(records=cls.records)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_complete_design(self):
        self.assertEqual(len(specs()),112)
        self.assertEqual(sum(s['split']=='test' for s in specs()),56)
        self.assertEqual({s['replicate'] for s in specs()},set(range(4)))

    def test_gates_are_active_after_fade(self):
        for source in self.sources.values():
            pcm=source['pcm']; active=_activity_samples(pcm)
            self.assertEqual(active[0][0],0)
            self.assertEqual(active[-1][1],len(pcm))
            self.assertEqual(pcm[0],0); self.assertEqual(pcm[-1],0)
            self.assertEqual(source['metadata']['edge_fade_samples'],EDGE_FADE_SAMPLES)
            self.assertLess(len(pcm),source['metadata']['original_prepared_samples'])

    def test_actual_pcm_gap_and_pair_audit(self):
        audit=validate_manifest(self.manifest,self.root)
        self.assertEqual(audit['causal_pairs'],56)
        for pause, row in audit['actual_rms_gap_ms'].items():
            self.assertEqual(row,dict(min=float(pause),max=float(pause),resume_streams=8))

    def test_reject_false_gap_metadata(self):
        bad=copy.deepcopy(self.manifest)
        bad['records'][1]['causal_pair']['measured_rms_gap_samples']+=1
        with self.assertRaisesRegex(ValueError,'gap'):
            validate_manifest(bad,self.root)

    def test_reject_false_rms_labels(self):
        bad=copy.deepcopy(self.manifest)
        bad['records'][1]['provenance']['sources'][0]['activity_intervals'][0][0]+=.01
        with self.assertRaisesRegex(ValueError,'activity'):
            validate_manifest(bad,self.root)

    def test_stop_bytes_identical_across_pause_durations(self):
        stop=[r for r in self.records if r['split']=='test' and r['condition']['replicate']==0 and r['condition']['branch']=='stop']
        reference=read_pcm(self.root,stop[0])
        for r in stop[1:]:
            np.testing.assert_array_equal(read_pcm(self.root,r),reference)

    def test_acquisition_equality_includes_exact_horizon(self):
        records=self.records[:2]; t=records[0]['causal_pair']['resume_time_s']
        trace=np.array([[0.,.01,.1,.01],[t-.01,t,.2,t],[t,t+.01,.3,t+.01]])
        traces={'fixture':{r['id']:trace.copy() for r in records}}
        traces['fixture'][records[1]['id']][-1,2]=.9
        self.assertEqual(len(audit_causal_traces(records,traces)),1)
        traces['fixture'][records[1]['id']][-2,2]=.9
        with self.assertRaisesRegex(ValueError,'acquisition'):
            audit_causal_traces(records,traces)

    def test_paired_cut_strictly_before_resume(self):
        records=self.records[:2]; r=records[0]; p=r['causal_pair']
        end=p['prefix_activity_end_sample']/SR; horizon=p['resume_time_s']
        base=np.array([[.64,.65,1.,.65],[end-.01,end,1.,end],[end,end+.01,0.,end+.01]])
        traces={r['id']:base for r in records}
        cut=paired_cuts(records,traces,Controller(silence_s=0))[0]
        self.assertTrue(cut['cuts_resume_before_future_speech'])
        base[-1]=[end,horizon,0.,horizon]
        cut=paired_cuts(records,traces,Controller(silence_s=0))[0]
        self.assertFalse(cut['cuts_resume_before_future_speech'])

    def test_frozen_plan_reuses_values_and_deduplicates(self):
        primary=dict(selections=[dict(backend=b,policy=f'p{i}',controller=dict(on=.3,off=.2,start_s=.032,silence_s=.15))
                                 for b in BACKENDS for i in range(13)])
        plan,controllers=controller_plan(primary)
        self.assertEqual(len(plan),180);self.assertEqual(len(controllers),36)
        frozen=[p for p in plan if p['kind']=='frozen']
        self.assertEqual(len(frozen),156)
        self.assertEqual(frozen[0]['controller'],primary['selections'][0]['controller'])

    def test_strict_scoring_counts_pause_cut(self):
        record=self.records[1]; p=record['causal_pair']; end=p['prefix_activity_end_sample']/SR
        resume=p['resume_time_s']; offset=record['turns'][0]['offset_s']
        # One complete source episode, a cut in the pause, and a resumed fragment.
        t=np.arange(.65,8.001,.01); score=np.where(((t>.64)&(t<=end))|((t>resume)&(t<=offset)),1.,0.)
        trace=np.column_stack([t-.01,t,score,t])
        m=evaluate_boundaries([record],{record['id']:trace},Controller(silence_s=0))
        self.assertEqual(m['counts']['turns'],1)
        self.assertEqual(m['counts']['premature_end_turns'],1)
        self.assertEqual(m['counts']['fragmented_turns'],1)
        self.assertEqual(m['end']['deadlines_ms']['300']['successes'],0)

    def test_compaction_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); value={'x':'a'*1_000_001}
            a=write_result(root/'a.json',value);b=write_result(root/'b.json',value)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            self.assertEqual(gzip.decompress(a.read_bytes()),json_bytes(value))
            self.assertFalse((root/'a.json').exists())

    @patch('vadbench.boundary_dataset.synthesize', side_effect=fake_synth)
    def test_generation_freezes_before_inference_and_refuses_overwrite(self, _):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); primary=root/'primary.json'
            primary.write_text(json.dumps(dict(manifest_sha256='original',selections=[{}]*156)))
            output=root/'probe'; result=generate(output,root,primary)
            self.assertEqual(result['stage'],'before_model_inference')
            self.assertFalse((output/'runtime-output/raw').exists())
            self.assertTrue((output/'generator-frozen.py.txt').exists())
            self.assertEqual(len(json.loads((output/'test-manifest.json').read_text())['records']),56)
            with self.assertRaises(FileExistsError):
                generate(output,root,primary)


if __name__=='__main__':
    unittest.main()
