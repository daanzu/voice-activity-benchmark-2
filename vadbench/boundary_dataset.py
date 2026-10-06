"""Frozen synthetic turn-boundary stress corpus; no human phonetic labels."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import wave
from pathlib import Path

import numpy as np
import scipy
from scipy import signal

from .dataset import SR, FRAME, digest, noise, rms_normalize, source_activity, synthesize

VERSION = 'boundary-flite-v1'
DURATION = 8
PHASES_MS = tuple(range(0, 160, 10))
PAUSES_MS = (50, 100, 150, 200, 300, 500, 800)
STRESSES = ('clean', 'quiet', 'fade', 'synthetic_breath')
VOICES = {'dev': ('awb', 'kal'), 'test': ('rms', 'slt')}
# Original prompts. No exact text, voice, or random seed is shared across splits.
TEXTS = {
    'dev': {
        'short': ('Hush', 'Fine', 'Take', 'Okay', 'Zoom', 'Mend', 'Ship', 'Voice'),
        'prefix': ('Place the red folder', 'Bring a warm jacket',
                   'Choose the small cup', 'Read the first line'),
        'continuation': ('beside the window', 'before the evening walk',
                         'and fill it slowly', 'with a softer voice'),
    },
    'test': {
        'short': ('Help', 'See', 'Pick', 'Easy', 'Wave', 'Name', 'Fish', 'Breathe'),
        'prefix': ('Leave the silver key', 'Find a green notebook',
                   'Lift the narrow box', 'Count the final row'),
        'continuation': ('under the wooden shelf', 'after the morning train',
                         'and carry it outside', 'at a steady pace'),
    },
}
NEGATIVES = ('silence', 'fan_only', 'typing_only', 'music_only')
BASE_ONSET_SAMPLES = 64 * FRAME  # 640 ms, a multiple of native-frame LCM 160 ms.
COLLAR = 2 * FRAME


def _json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def _sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _merge(spans, limit=SR * DURATION):
    """Merge half-open integer sample intervals, preserving sub-frame phase."""
    result = []
    for a, b in sorted((max(0, int(a)), min(limit, int(b))) for a, b in spans):
        if a >= b:
            continue
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return result


def _seconds(spans):
    return [[a / SR, b / SR] for a, b in spans]


def _activity_samples(pcm):
    # Label the actually emitted, transformed and quantized clean speech,
    # normalized solely for labeling so quiet gain does not erase speech truth.
    normalized = rms_normalize(pcm.astype(float) / 32768, .1)
    mask = source_activity(normalized)
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    return [[int(a) * FRAME, min(int(b) * FRAME, len(pcm))]
            for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]


def prepare_source(text, voice, cache, stress='clean'):
    """Return emitted clean PCM and separate RMS-proxy / exact-support bounds."""
    raw, metadata = synthesize(text, voice, cache)
    dbfs = -40 if stress == 'quiet' else -23
    audio = rms_normalize(raw, 10 ** (dbfs / 20))
    if stress == 'fade':
        count = min(len(audio), int(.24 * SR))
        audio[-count:] *= np.geomspace(1., .001, count)
    peak_gain = min(1., .8 / max(float(np.max(np.abs(audio))), 1e-12))
    pcm = np.round(audio * peak_gain * 32767).astype('<i2')
    support = np.flatnonzero(pcm != 0)
    activity = _activity_samples(pcm)
    if not len(support) or not activity:
        raise ValueError('Source has no nonzero support or clean-source RMS activity')
    metadata = dict(metadata, role='foreground', clean_rms_dbfs=dbfs,
                    source_peak_gain=peak_gain, endpoint_transform=stress,
                    prepared_pcm_sha256=_sha_bytes(pcm.tobytes()),
                    prepared_samples=len(pcm),
                    label_policy='RMS proxy of transformed PCM normalized to -20 dBFS')
    return {'pcm': pcm, 'activity': activity,
            'support': [int(support[0]), int(support[-1]) + 1], 'metadata': metadata}


def _shift(spans, offset):
    return [[a + offset, b + offset] for a, b in spans]


def _place(audio, source, offset):
    if offset < 0 or offset + len(source['pcm']) > len(audio):
        raise ValueError('Source does not fit; never truncate a source to fit')
    audio[offset:offset + len(source['pcm'])] += source['pcm'].astype(np.int32)
    return dict(source['metadata'],
                inserted_interval=[offset / SR, (offset + len(source['pcm'])) / SR],
                emitted_support_interval=_seconds(_shift([source['support']], offset))[0],
                activity_intervals=_seconds(_shift(source['activity'], offset)))


def _labels(parts, rid, explicit_pauses=(), extra_uncertainty=()):
    """One construction-defined turn can contain multiple acoustic intervals."""
    activity, uncertain, supports = [], list(extra_uncertainty), []
    for source, offset in parts:
        spans = _shift(source['activity'], offset)
        activity.extend(spans)
        support = _shift([source['support']], offset)[0]
        supports.append(support)
        # Subthreshold support and every proxy transition are uncertain.
        previous = support[0]
        for a, b in spans:
            uncertain.append([previous, a])
            uncertain.extend(([a - COLLAR, a + COLLAR], [b - COLLAR, b + COLLAR]))
            previous = b
        uncertain.append([previous, support[1]])
    activity = _merge(activity)
    onset, offset = activity[0][0], activity[-1][1]
    onset_band = [max(0, min(onset - COLLAR, supports[0][0])), onset + COLLAR]
    offset_band = [max(0, offset - COLLAR),
                   min(DURATION * SR, max(offset + COLLAR, supports[-1][1],
                       max((b for _, b in extra_uncertainty), default=0)))]
    uncertain.extend((onset_band, offset_band))
    turn = {'id': rid + '-turn-0', 'onset_s': onset / SR, 'offset_s': offset / SR,
            'onset_uncertainty_s': [a / SR for a in onset_band],
            'offset_uncertainty_s': [a / SR for a in offset_band],
            'acoustic_intervals': _seconds(activity),
            'internal_pauses': _seconds(explicit_pauses),
            'construction_support_intervals': _seconds(supports)}
    return [turn], _seconds(activity), _seconds(_merge(uncertain))


def record_specs(seed=20261005):
    """Stable complete design, independent of synthesis and model outcomes."""
    if seed < 0:
        raise ValueError('seed must be nonnegative')
    specs = []
    for split_number, split in enumerate(('dev', 'test')):
        for stress_number, stress in enumerate(STRESSES):
            for phase_number, phase_ms in enumerate(PHASES_MS):
                specs.append(dict(split=split, family='onset', stress=stress,
                                  phase_ms=phase_ms,
                                  sample_offset=(phase_number + stress_number) % 2,
                                  voice_index=(phase_number // 4 + stress_number) % 2,
                                  text_index=(phase_number + 3 * stress_number) % 8))
        for replicate in range(4):
            for pause_ms in PAUSES_MS:
                for branch in ('stop', 'resume'):
                    specs.append(dict(split=split, family='pause', replicate=replicate,
                                      voice_index=replicate % 2, text_index=replicate,
                                      pause_ms=pause_ms, branch=branch))
        for replicate in range(4):
            for kind in NEGATIVES:
                specs.append(dict(split=split, family='negative', kind=kind,
                                  replicate=replicate))
    for index, spec in enumerate(specs):
        spec['index'] = index
        # Unique random stream, including records that happen not to consume it.
        spec['noise_seed'] = seed * 1000000 + index
    return specs


def build_record(spec, output, cache):
    output, cache = Path(output), Path(cache)
    split, family = spec['split'], spec['family']
    condition_name = ('onset_' + spec['stress'] if family == 'onset' else
                      'pause_' + spec['branch'] if family == 'pause' else spec['kind'])
    rid = f"{split}-{spec['index']:04d}-{condition_name}"
    audio = np.zeros(DURATION * SR, dtype=np.int32)
    rng = np.random.default_rng(spec['noise_seed'])
    condition = {'name': condition_name, 'family': family, 'noise_type': 'none',
                 'reverb_tail_s': 0., 'bandwidth': 'fullband',
                 'peak_normalization_gain': 1.}
    provenance = {'noise_seed': spec['noise_seed'], 'sources': [],
                  'label_type': 'synthetic_clean_pcm_rms_and_support_proxy'}
    turns, activity, uncertain, extra = [], [], [], {}
    if family == 'onset':
        stress = spec['stress']
        voice = VOICES[split][spec['voice_index']]
        source = prepare_source(TEXTS[split]['short'][spec['text_index']], voice, cache, stress)
        nominal_onset = BASE_ONSET_SAMPLES + spec['phase_ms'] * SR // 1000 + spec['sample_offset']
        placement = nominal_onset - source['activity'][0][0]
        provenance['sources'].append(_place(audio, source, placement))
        tail_intervals = []
        if stress == 'synthetic_breath':
            begin = placement + source['support'][1]
            count = int(.18 * SR)
            synthetic = signal.sosfilt(signal.butter(2, [900, 5000], btype='bandpass',
                                                     fs=SR, output='sos'), rng.normal(size=count))
            synthetic = rms_normalize(synthetic, 10 ** (-38 / 20))
            synthetic *= np.linspace(1., .01, count)
            if begin + count > len(audio):
                raise ValueError('Synthetic breath-like tail does not fit')
            audio[begin:begin + count] += np.round(synthetic * 32767).astype(np.int32)
            tail_intervals = [[begin, begin + count]]
            provenance['synthetic_breath_like_tail'] = {
                'interval': _seconds(tail_intervals)[0],
                'description': 'Filtered seeded noise; not a human breath or speech annotation',
                'speech_label': False, 'scoring': 'uncertain endpoint region'}
        turns, activity, uncertain = _labels([(source, placement)], rid,
                                            extra_uncertainty=tail_intervals)
        condition.update(onset_phase_ms=spec['phase_ms'],
                         onset_sample_offset=spec['sample_offset'],
                         onset_phase_samples=nominal_onset % int(.16 * SR),
                         endpoint_stress=stress, target_rms_dbfs=-40 if stress == 'quiet' else -23)
    elif family == 'pause':
        voice = VOICES[split][spec['voice_index']]
        text_index = spec['text_index']
        prefix = prepare_source(TEXTS[split]['prefix'][text_index], voice, cache)
        continuation = prepare_source(TEXTS[split]['continuation'][text_index], voice, cache)
        placement = BASE_ONSET_SAMPLES - prefix['activity'][0][0]
        prefix_end = placement + prefix['support'][1]
        resume_sample = prefix_end + spec['pause_ms'] * SR // 1000
        continuation_placement = resume_sample - continuation['support'][0]
        provenance['sources'].append(_place(audio, prefix, placement))
        parts = [(prefix, placement)]
        pauses = []
        if spec['branch'] == 'resume':
            provenance['sources'].append(_place(audio, continuation, continuation_placement))
            parts.append((continuation, continuation_placement))
            pauses = [[prefix_end, resume_sample]]
        turns, activity, uncertain = _labels(parts, rid, pauses)
        pair_id = f"{split}-pair-{spec['replicate']:02d}-{spec['pause_ms']:03d}"
        # All seven pauses share the identical prefix speech for this replicate.
        shared_prefix_id = f"{split}-prefix-{spec['replicate']:02d}"
        shared_pcm = audio[:resume_sample].astype('<i2').tobytes()
        extra['causal_pair'] = {'id': pair_id, 'branch': spec['branch'],
                                'shared_prefix_id': shared_prefix_id,
                                'requested_pause_s': spec['pause_ms'] / 1000,
                                'prefix_support_end_sample': prefix_end,
                                'resume_sample': resume_sample, 'resume_time_s': resume_sample / SR,
                                'shared_prefix_end_sample': resume_sample,
                                'shared_prefix_pcm_sha256': _sha_bytes(shared_pcm),
                                'identical_history_interval_s': [0., resume_sample / SR]}
        condition.update(pause_s=spec['pause_ms'] / 1000, target_rms_dbfs=-23)
    else:
        kind = spec['kind'].removesuffix('_only')
        if kind != 'silence':
            samples = noise(kind, rng, len(audio))
            dbfs = (-34, -28, -22, -16)[spec['replicate']]
            samples *= 10 ** (dbfs / 20)
            gain = min(1., .95 / max(float(np.max(np.abs(samples))), 1e-12))
            audio = np.round(samples * gain * 32767).astype(np.int32)
            condition.update(noise_type=kind, noise_rms_dbfs=dbfs, peak_normalization_gain=gain)
        condition['negative_description'] = ('Mathematical music-like tones, not real music'
                                              if kind == 'music' else 'Synthetic ' + kind)
    if np.max(np.abs(audio)) > 32767:
        raise ValueError('Unexpected clipping; cannot independently normalize causal pair branches')
    pcm = audio.astype('<i2')
    path = output / 'audio' / (rid + '.wav')
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(pcm.tobytes())
    return {'id': rid, 'split': split, 'path': 'audio/' + path.name,
            'duration_s': DURATION, 'turns': turns, 'speech_intervals': activity,
            'target_intervals': activity, 'background_intervals': [],
            'uncertain_intervals': uncertain, 'condition': condition,
            'provenance': provenance, 'sha256': digest(path), **extra}


def validate_manifest(manifest, root=None):
    """Audit construction labels, split leakage, phase coverage and pair bytes."""
    records = manifest['records']
    assets = {s: {'voices': set(), 'texts': set(), 'seeds': set()} for s in VOICES}
    pairs = {}
    for record in records:
        split = record['split']
        assets[split]['seeds'].add(record['provenance']['noise_seed'])
        for source in record['provenance']['sources']:
            assets[split]['voices'].add(source['voice'])
            assets[split]['texts'].add(source['text'])
        for key in ('speech_intervals', 'target_intervals', 'uncertain_intervals'):
            intervals = record[key]
            if any(not 0 <= a < b <= record['duration_s'] for a, b in intervals):
                raise ValueError('Invalid interval bounds: ' + record['id'])
            if any(left[1] > right[0] for left, right in zip(intervals, intervals[1:])):
                raise ValueError('Unsorted or overlapping intervals: ' + record['id'])
        for turn in record['turns']:
            if not 0 <= turn['onset_s'] < turn['offset_s'] <= record['duration_s']:
                raise ValueError('Invalid turn bounds')
            for boundary in ('onset', 'offset'):
                lo, hi = turn[boundary + '_uncertainty_s']
                if not 0 <= lo <= turn[boundary + '_s'] <= hi <= record['duration_s']:
                    raise ValueError('Invalid boundary uncertainty')
            for a, b in turn['internal_pauses']:
                if not turn['onset_s'] < a < b < turn['offset_s']:
                    raise ValueError('Pause not internal to one turn')
        if record['condition']['family'] == 'negative' and record['turns']:
            raise ValueError('Negative-only stream contains a turn')
        if 'causal_pair' in record:
            pair = record['causal_pair']
            pairs.setdefault(pair['id'], {})[pair['branch']] = record
            if len(record['turns']) != 1:
                raise ValueError('Each causal pair branch must have exactly one turn')
        if root is not None:
            path = Path(root) / record['path']
            if digest(path) != record['sha256']:
                raise ValueError('WAV hash mismatch')
            with wave.open(str(path), 'rb') as wav:
                if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) != (SR, 1, 2, DURATION * SR):
                    raise ValueError('WAV format or duration mismatch')
                pcm = wav.readframes(wav.getnframes())
            if 'causal_pair' in record:
                end = record['causal_pair']['shared_prefix_end_sample']
                if _sha_bytes(pcm[:2 * end]) != record['causal_pair']['shared_prefix_pcm_sha256']:
                    raise ValueError('Causal shared-prefix hash mismatch')
    for key in ('voices', 'texts', 'seeds'):
        if not assets['dev'][key].isdisjoint(assets['test'][key]):
            raise ValueError('Split leakage: ' + key)
    for branches in pairs.values():
        if set(branches) != {'stop', 'resume'}:
            raise ValueError('Incomplete causal pair')
        stop, resume = branches['stop'], branches['resume']
        if stop['causal_pair']['shared_prefix_pcm_sha256'] != resume['causal_pair']['shared_prefix_pcm_sha256']:
            raise ValueError('Causal histories differ')
        if stop['turns'][0]['internal_pauses'] or len(resume['turns'][0]['internal_pauses']) != 1:
            raise ValueError('Incorrect stop/resume turn pause labels')
    return {'records': len(records), 'minutes': sum(r['duration_s'] for r in records) / 60,
            'turns': sum(len(r['turns']) for r in records), 'causal_pairs': len(pairs),
            'negative_only_records': sum(not r['turns'] for r in records),
            'negative_only_seconds': sum(r['duration_s'] for r in records if not r['turns'])}


def generate(output, seed=20261005):
    output = Path(output).resolve()
    if any((output / p).exists() for p in ('manifest.json', 'test-manifest.json', 'FROZEN.json')):
        raise FileExistsError('Immutable corpus exists; choose a fresh output directory')
    cache = output / 'sources'
    cache.mkdir(parents=True, exist_ok=True)
    records = [build_record(spec, output, cache) for spec in record_specs(seed)]
    generation = {
        'generator': VERSION, 'seed': seed, 'count': len(records), 'sample_rate': SR,
        'duration_s': DURATION, 'frame_s': .01, 'speaker_split': VOICES,
        'text_split': TEXTS, 'onset_phases_ms': PHASES_MS, 'sample_offsets': [0, 1],
        'pause_durations_ms': PAUSES_MS, 'label_type': 'synthetic_clean_pcm_rms_and_support_proxy',
        'label_threshold': 'Transformed emitted clean PCM normalized to -20 dBFS RMS; max(-48 dBFS, peak 10 ms frame RMS minus 40 dB)',
        'turn_policy': 'Construction intent defines turn identity; one resumed turn spans the inserted internal pause. RMS proxy defines nominal acoustic boundaries.',
        'uncertainty': '20 ms RMS-transition collars, subthreshold emitted support, conservative exact PCM support bounds; artificial breath-like tail uncertain and not labeled speech',
        'split_policy': 'Disjoint voices, exact texts and record RNG seeds within this corpus; same Flite engine in both splits',
        'selection_policy': 'Entire design and test manifest frozen before any model scoring or development selection',
        'numpy_version': np.__version__, 'scipy_version': scipy.__version__,
        'python_version': platform.python_version(),
        'ffmpeg_version': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
        'generator_sha256': digest(__file__), 'dataset_helpers_sha256': digest(Path(__file__).with_name('dataset.py')),
        'provenance_urls': ['https://github.com/festvox/flite', 'https://www.ffmpeg.org/ffmpeg-filters.html#flite'],
        'limitations': 'Synthetic English TTS only. No human labels or natural breaths. Repeated phase variants and paired prefixes are correlated; two voices per split do not establish human, language or microphone generalization.',
    }
    manifest = {'schema_version': 2, 'generation': generation, 'records': records}
    audit = validate_manifest(manifest, output)
    # Freeze held-out identities, bytes and labels first, before writing the runnable manifest.
    test_manifest = dict(manifest, records=[r for r in records if r['split'] == 'test'])
    test_bytes = _json_bytes(test_manifest)
    (output / 'test-manifest.json').write_bytes(test_bytes)
    (output / 'test-manifest.sha256').write_text(_sha_bytes(test_bytes) + '  test-manifest.json\n')
    manifest_bytes = _json_bytes(manifest)
    (output / 'manifest.json').write_bytes(manifest_bytes)
    (output / 'manifest.sha256').write_text(_sha_bytes(manifest_bytes) + '  manifest.json\n')
    frozen = {'generator': VERSION, 'stage': 'before_model_scoring_and_selection',
              'manifest_sha256': _sha_bytes(manifest_bytes),
              'test_manifest_sha256': _sha_bytes(test_bytes),
              'generator_sha256': generation['generator_sha256'], 'audit': audit,
              'policy': 'Do not overwrite audio, labels, split, or test manifest; use a new dataset version for changes.'}
    (output / 'FROZEN.json').write_bytes(_json_bytes(frozen))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='data/boundary-v1')
    parser.add_argument('--seed', type=int, default=20261005)
    args = parser.parse_args()
    manifest = generate(args.output, args.seed)
    print(json.dumps(dict(validate_manifest(manifest), manifest=str(Path(args.output) / 'manifest.json'))))


if __name__ == '__main__':
    main()
