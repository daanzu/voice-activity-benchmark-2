"""One isolated process per backend, timed streaming inference and raw score traces."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
import wave
import numpy as np
from .adapters import create
from .streaming import StreamResampler

BACKENDS=['classic-0','classic-1','classic-2','classic-3','silero','agc2','ten','fsmn','rnnoise','speex']

def read_audio(path):
    with wave.open(str(path),'rb') as wav:
        if wav.getnchannels()!=1 or wav.getsampwidth()!=2:
            raise ValueError('Expected mono 16-bit PCM')
        return np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768,wav.getframerate()

def worker(manifest_path, output, backend):
    manifest=json.loads(manifest_path.read_text());records=manifest['records']
    output.mkdir(parents=True,exist_ok=True)
    (output/f'{backend}.json').write_text(json.dumps(dict(backend=backend,status='running',error='Run has not completed')))
    pre_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started=time.perf_counter()
    try:
        model=create(backend)
    except Exception as exc:
        result=dict(backend=backend,status='blocked',error=f'{type(exc).__name__}: {exc}')
        (output/f'{backend}.json').write_text(json.dumps(result,indent=2));return
    startup=time.perf_counter()-started
    # Warmup is distinct from measured reset streams and never used as accuracy data.
    for _ in range(10):model.process(np.zeros(model.frame_samples,dtype=np.float32))
    traces={}; timing=[]
    for record in records:
        audio_path=manifest_path.parent/record['path']
        if hashlib.sha256(audio_path.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError(f'Audio hash mismatch: {record["id"]}')
        audio,sr=read_audio(audio_path)
        if abs(len(audio)/sr-record['duration_s'])>1/sr:
            raise ValueError('Audio duration differs from manifest')
        model.reset();resampler=StreamResampler(sr,model.sample_rate)
        buffer=np.zeros(0,dtype=np.float32);native_count=0;trace=[]
        resample_wall=inference_wall=0.;clipped_samples=0;begin=time.perf_counter();cpu=time.process_time()
        quantum=sr//100
        for offset in range(0,len(audio),quantum):
            acquisition=min(offset+quantum,len(audio))/sr
            t=time.perf_counter();converted=resampler.process(audio[offset:offset+quantum]);resample_wall+=time.perf_counter()-t
            clipped_samples+=int(np.count_nonzero(np.abs(converted)>1))
            converted=np.clip(converted,-1,1)
            buffer=np.concatenate([buffer,converted])
            while len(buffer)>=model.frame_samples:
                frame=buffer[:model.frame_samples];buffer=buffer[model.frame_samples:]
                t=time.perf_counter();score=model.process(frame);inference_wall+=time.perf_counter()-t
                if not np.isfinite(score):raise ValueError(f'{backend} nonfinite score')
                start=native_count/model.sample_rate;native_count+=model.frame_samples
                end=native_count/model.sample_rate
                shift=resampler.delay_s+float(model.metadata.get('score_delay_s') or 0.0)
                trace.append([start-shift,end-shift,float(score),acquisition])
        elapsed=time.perf_counter()-begin;cpu=time.process_time()-cpu
        traces[record['id']]=np.asarray(trace,dtype=np.float64)
        timing.append(dict(id=record['id'],audio_s=record['duration_s'],wall_s=elapsed,cpu_s=cpu,
                           inference_s=inference_wall,resampling_s=resample_wall,
                           dropped_tail_samples=len(buffer),resampler_delay_s=resampler.delay_s,resampling_clipped_samples=clipped_samples))
    np.savez_compressed(output/f'{backend}.npz',**traces)
    result=dict(backend=backend,status='ok',adapter=model.metadata,startup_s=startup,
                rss_before_adapter_kib=pre_rss,peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                timing=timing,manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
                environment=dict(python=platform.python_version(),platform=platform.platform(),numpy=np.__version__,
                    cpu_model=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),'unknown')),
                methodology=dict(capture_quantum_s=.01,tail_policy='drop incomplete native frame; exclude uncovered grid',
                    latency='simulated acquisition time, excludes measured computation',timing='includes causal resampling, dispatch, buffering, inference; excludes WAV read/reset; one pass',
                    memory='isolated backend process peak RSS, includes full corpus trace storage; not model-only RAM'))
    (output/f'{backend}.json').write_text(json.dumps(result,indent=2))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('results/synthetic/raw'));parser.add_argument('--backends',nargs='+',default=BACKENDS)
    parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    if args.worker:
        worker(args.manifest,args.output,args.backends[0]);return
    for backend in args.backends:
        print('Running',backend,flush=True)
        env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        subprocess.run([sys.executable,'-m','vadbench.run','--manifest',str(args.manifest.resolve()),'--output',str(args.output.resolve()),'--backends',backend,'--worker'],check=True,env=env)
if __name__=='__main__':main()
