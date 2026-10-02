"""Deterministic source-activity synthetic benchmark (not phonetic annotation)."""
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

SR = 16000
FRAME = 160
DURATION = 20
VERSION = 'synthetic-flite-v1'
CONDITIONS = ('silence', 'fan_only', 'typing_only', 'music_only', 'clean_short',
              'clean_long', 'quiet', 'fan_speech', 'typing_speech', 'music_speech',
              'background_only', 'background_overlap')
VOICES = {'dev': ('awb', 'kal'), 'test': ('rms', 'slt')}
TEXTS = {
 'dev': {
 'short': ('Go', 'Pause', 'Resume', 'Next', 'Stop now', 'Go back', 'Turn left', 'Confirm'),
 'long': ('Please set the kitchen timer for twenty minutes and let me know when it rings',
          'The blue bicycle is waiting beside the garden gate near the old stone wall',
          'Tomorrow morning we will review the project notes before the weekly planning session',
          'I would like to hear the weather forecast before deciding whether to take an umbrella'),
 'background': ('The radio announced a new exhibition at the museum on Friday afternoon',
                'Several visitors were talking about the photographs in the upstairs gallery')},
 'test': {
 'short': ('Yes', 'No', 'Cancel', 'Again', 'Open that', 'Move right', 'Answer me', 'Close it'),
 'long': ('Could you check whether the package arrived and put it on the desk in the study',
          'A little yellow boat crossed the lake while clouds gathered above the distant hills',
          'After lunch the team will discuss the budget and prepare a summary for the meeting',
          'Remember to switch off the hallway lights when you leave the apartment this evening'),
 'background': ('The television presenter described the final result of the afternoon football match',
                'Two passengers discussed their journey while waiting near the station entrance')}
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def intervals(mask, frame_s=0.01):
    """Sorted half-open intervals covering true frames."""
    changes = np.diff(np.r_[False, mask, False].astype(np.int8))
    return [[round(int(a)*frame_s, 6), round(int(b)*frame_s, 6)]
            for a, b in zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1))]


def source_activity(audio):
    """10 ms source RMS proxy; no learned VAD and no mixture-derived labels."""
    padded = np.pad(audio, (0, (-len(audio)) % FRAME))
    rms = np.sqrt(np.mean(padded.reshape(-1, FRAME)**2, axis=1))
    threshold = max(10**(-48/20), float(rms.max(initial=0))*10**(-40/20))
    return rms >= threshold


def synthesize(text, voice, cache):
    key = hashlib.sha256((voice+'\0'+text).encode()).hexdigest()[:24]
    wav_path = cache / (key+'.wav')
    if not wav_path.exists():
        text_path = cache / (key+'.txt')
        text_path.write_text(text, encoding='utf-8')
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        f'flite=textfile={text_path}:voice={voice}', '-ar', str(SR),
                        '-ac', '1', '-c:a', 'pcm_s16le', '-y', str(wav_path)], check=True)
    with wave.open(str(wav_path), 'rb') as f:
        if (f.getframerate(), f.getnchannels(), f.getsampwidth()) != (SR, 1, 2):
            raise ValueError('Invalid synthesis format')
        x = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2').astype(float)/32768
    # Trim only exact outer silence; keep internal pauses in provenance and uncertainty.
    nz = np.flatnonzero(np.abs(x) > 1/32768)
    if not len(nz):
        raise ValueError('Synthesizer produced silence')
    x = x[nz[0]:nz[-1]+1]
    return x, {'engine': 'CMU Flite via FFmpeg', 'voice': voice, 'text': text,
               'source_sha256': digest(wav_path), 'source_path': 'sources/'+wav_path.name}


def rms_normalize(x, amplitude):
    return x * amplitude / max(float(np.sqrt(np.mean(x*x))), 1e-12)


def noise(kind, rng, n):
    t = np.arange(n)/SR
    if kind == 'fan':
        x = signal.sosfilt(signal.butter(2, 900, fs=SR, output='sos'), rng.normal(size=n))
        x += .2*np.sin(2*np.pi*120*t) + .08*np.sin(2*np.pi*240*t)
    elif kind == 'typing':
        x = np.zeros(n)
        for start in rng.integers(0, n-1600, size=70):
            pulse = rng.normal(size=1600)*np.exp(-np.arange(1600)/160)
            x[start:start+1600] += pulse
    elif kind == 'music':
        x = np.zeros(n)
        for i in range(40):
            start, end = i*n//40, (i+1)*n//40
            note = float(rng.choice([130.81, 164.81, 196, 261.63, 329.63, 392]))
            u = np.arange(end-start)/SR
            envelope = np.minimum(1, u/.02)*np.exp(-u*2)
            x[start:end] += envelope*(np.sin(2*np.pi*note*u)+.3*np.sin(4*np.pi*note*u))
        x += .1*np.sin(2*np.pi*65.4*t)*(0.5+0.5*np.sin(2*np.pi*2*t))
    else:
        return np.zeros(n)
    return rms_normalize(x, 1)


def build_record(index, seed, output, cache):
    condition_name = CONDITIONS[index % len(CONDITIONS)]
    replicate = index // len(CONDITIONS)
    split = 'dev' if replicate % 5 < 2 else 'test'
    # Unique per-stream seed, split is recorded explicitly and never shared.
    noise_seed = seed*1000000 + index
    rng = np.random.default_rng(noise_seed)
    n, nf = SR*DURATION, SR*DURATION//FRAME
    foreground, background = np.zeros(n), np.zeros(n)
    fg_mask, bg_mask, uncertain = np.zeros(nf, bool), np.zeros(nf, bool), np.zeros(nf, bool)
    sources = []
    voice_pair = VOICES[split]
    primary_voice = voice_pair[replicate % 2]
    variant = replicate // 2
    target_dbfs = -38 if condition_name == 'quiet' else -23
    reverb_s = [0., .12, .35][replicate % 3] if condition_name not in CONDITIONS[:4] else 0.
    bandwidth = 'telephone_300_3400' if replicate % 4 == 3 else 'fullband'

    def insert(role, text, voice, start, dbfs):
        x, info = synthesize(text, voice, cache)
        activity = source_activity(rms_normalize(x, .1))
        x = rms_normalize(x, 10**(dbfs/20))
        offset = int(round(start*100))*FRAME
        # Never truncate words. A source that cannot fit is an implementation error.
        if offset+len(x) > n:
            raise ValueError(f'Source does not fit: {text}')
        # Labels use normalized dry source before channel filtering and mixing.
        k = offset//FRAME
        m = fg_mask if role == 'foreground' else bg_mask
        m[k:k+len(activity)] |= activity
        uncertain[k:k+len(activity)] |= ~activity
        # A 20 ms collar on both sides of all source-activity transitions.
        edges = np.flatnonzero(np.diff(np.r_[False, activity, False].astype(int)))
        for edge in edges:
            uncertain[max(0,k+edge-2):min(nf,k+edge+2)] = True
        target = foreground if role == 'foreground' else background
        target[offset:offset+len(x)] += x
        end = (offset+len(x))/SR
        if reverb_s:
            uncertain[int(end*100):min(nf,int(np.ceil((end+reverb_s)*100)))] = True
        info.update(role=role, inserted_interval=[offset/SR, end], clean_rms_dbfs=dbfs)
        sources.append(info)

    if condition_name not in CONDITIONS[:4] and condition_name != 'background_only':
        if condition_name in ('clean_short', 'quiet'):
            for j, start in enumerate((1., 5., 10., 15.)):
                text = TEXTS[split]['short'][(variant+j) % len(TEXTS[split]['short'])]
                insert('foreground', text, primary_voice, start+float(rng.uniform(0,.35)), target_dbfs)
        else:
            for j, start in enumerate((1., 11.)):
                text = TEXTS[split]['long'][(variant+j) % len(TEXTS[split]['long'])]
                insert('foreground', text, primary_voice, start, target_dbfs)
    if condition_name.startswith('background_'):
        for j, start in enumerate((3., 12.)):
            insert('background', TEXTS[split]['background'][j], voice_pair[1-replicate%2], start, -31)

    # Sparse causal echo channel; direct path is retained. Tail is uncertain.
    if reverb_s:
        for stream in (foreground, background):
            dry = stream.copy()
            for delay, gain in ((reverb_s*.2,.3),(reverb_s*.55,.15),(reverb_s,.07)):
                d = int(delay*SR)
                stream[d:] += gain*dry[:-d]
    kind = next((k for k in ('fan','typing','music') if condition_name.startswith(k)), None)
    snr = [20, 10, 0, -5][replicate % 4] if kind and 'speech' in condition_name else None
    noise_dbfs = target_dbfs-snr if snr is not None else -28
    nonvoice = noise(kind, rng, n)*10**(noise_dbfs/20)
    mixed = foreground + background + nonvoice
    if bandwidth != 'fullband':
        mixed = signal.sosfilt(signal.butter(4, [300,3400], btype='bandpass', fs=SR, output='sos'), mixed)
    # Leave headroom deterministically, with the exact gain documented.
    peak = float(np.max(np.abs(mixed)))
    gain = min(1., .95/max(peak, 1e-12))
    pcm = np.round(np.clip(mixed*gain, -1, 1)*32767).astype('<i2')
    rid = f'{split}-{index:04d}-{condition_name}'
    path = output/'audio'/f'{rid}.wav'
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes(pcm.tobytes())
    return {'id': rid, 'split': split, 'path': 'audio/'+path.name, 'duration_s': DURATION,
            'target_intervals': intervals(fg_mask), 'speech_intervals': intervals(fg_mask|bg_mask),
            'uncertain_intervals': intervals(uncertain), 'background_intervals': intervals(bg_mask),
            'condition': {'name': condition_name, 'noise_type': kind or 'none', 'snr_db': snr,
                          'target_rms_dbfs': target_dbfs if fg_mask.any() else None,
                          'noise_rms_dbfs': noise_dbfs if kind else None,
                          'reverb_tail_s': reverb_s, 'bandwidth': bandwidth,
                          'peak_normalization_gain': gain},
            'provenance': {'noise_seed': noise_seed, 'sources': sources}, 'sha256': digest(path)}


def generate(output, seed=20261002, count=240):
    output = Path(output).resolve()
    if count < 1 or seed < 0:
        raise ValueError('count must be positive and seed nonnegative')
    if (output/'manifest.json').exists():
        raise FileExistsError('Immutable dataset already exists; choose a new output directory')
    (output/'audio').mkdir(parents=True, exist_ok=True)
    cache = output/'sources'; cache.mkdir(exist_ok=True)
    records = [build_record(i, seed, output, cache) for i in range(count)]
    manifest = {'schema_version': 1, 'generation': {
        'generator': VERSION, 'seed': seed, 'count': count, 'sample_rate': SR,
        'duration_s': DURATION, 'frame_s': .01, 'label_type': 'clean_source_rms_activity_proxy',
        'label_threshold': 'On dry source normalized to -20 dBFS RMS: max(-48 dBFS, peak 10 ms frame RMS minus 40 dB)',
        'uncertainty': 'Source-internal subthreshold frames, 20 ms activity collars, reverb tails',
        'speaker_split': VOICES, 'numpy_version': np.__version__, 'scipy_version': scipy.__version__,
        'python_version': platform.python_version(),
        'ffmpeg_version': subprocess.check_output(['ffmpeg','-version'], text=True).splitlines()[0],
        'generator_sha256': digest(__file__),
        'provenance_urls': ['https://github.com/festvox/flite', 'https://www.ffmpeg.org/ffmpeg-filters.html#flite'],
        'limitations': 'Synthetic English TTS only; labels are source-activity proxies, not human phonetic truth. No human labels.'},
        'records': records}
    p = output/'manifest.json'
    p.write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    (output/'manifest.sha256').write_text(digest(p)+'  manifest.json\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='data/synthetic')
    parser.add_argument('--seed', type=int, default=20261002)
    parser.add_argument('--count', type=int, default=240)
    args = parser.parse_args()
    m = generate(args.output, args.seed, args.count)
    print(json.dumps({'records':len(m['records']), 'minutes':len(m['records'])*DURATION/60,
                      'manifest':str(Path(args.output)/'manifest.json')}))

if __name__ == '__main__':
    main()
