import sys, os, time, statistics, json, hashlib
from pathlib import Path
ROOT=str(Path(__file__).resolve().parent)
sys.path[:0]=[ROOT+'/packages',ROOT+'/py-webrtcvad-wheels']
import numpy as np
import webrtcvad
import onnxruntime as ort
root=ROOT
# Avoid overwriting the committed historical results.
output=Path(ROOT)/'results'/'local'
output.mkdir(parents=True,exist_ok=True)
old=root+'/packages/silero_vad_lite/data/silero_vad.onnx'
new=root+'/silero_current.onnx'
class Onnx:
 def __init__(self,path,context=True):
  opt=ort.SessionOptions(); opt.intra_op_num_threads=1; opt.inter_op_num_threads=1
  self.s=ort.InferenceSession(path,sess_options=opt,providers=['CPUExecutionProvider']);self.context=context;self.reset()
 def reset(self): self.state=np.zeros((2,1,128),np.float32);self.prev=np.zeros((1,32),np.float32)
 def process(self,x):
  z=x.reshape(1,-1)
  if self.context:z=np.concatenate([self.prev,z],axis=1)
  p,self.state=self.s.run(None,{'input':z,'state':self.state,'sr':np.array(8000,dtype=np.int64)})
  self.prev=z[:,-32:]
  return float(p[0,0])
raw=np.fromfile(ROOT+'/py-webrtcvad-wheels/test-audio.raw',dtype='<i2')
rng=np.random.default_rng(5)
# 60s each. Fixture is 8kHz in upstream unit test. Repeated input is throughput only, not accuracy.
inputs={'fixture':np.resize(raw,480000),'noise':rng.integers(-3000,3001,480000,dtype=np.int16),'silence':np.zeros(480000,np.int16)}
results=[]
for name,pcm in inputs.items():
 for variant,n in [('classic10',80),('classic20',160),('classic30',240),('onnx51context',256),('onnxCurrentContext',256)]:
  if variant.startswith('classic'):
   frames=[pcm[i:i+n].tobytes() for i in range(0,len(pcm)-n+1,n)]
   factory=lambda:webrtcvad.Vad(2)
   def process(m,f): return m.is_speech(f,8000)
  else:
   frames=[np.ascontiguousarray(pcm[i:i+n],dtype=np.float32)/32768 for i in range(0,len(pcm)-n+1,n)]
   factory=lambda:Onnx(old if variant=='onnx51context' else new)
   def process(m,f):return m.process(f)
  runs=[]; cpus=[]
  for k in range(6):
   m=factory()
   t=time.perf_counter();c=time.process_time()
   for f in frames:process(m,f)
   cpu=time.process_time()-c;wall=time.perf_counter()-t
   if k:runs.append(wall);cpus.append(cpu)
  d={'input':name,'backend':variant,'wall_s_median':statistics.median(runs),'cpu_s_median':statistics.median(cpus),'rtf':statistics.median(runs)/60,'us_call':statistics.median(runs)/len(frames)*1e6,'runs':runs}
  results.append(d);print(json.dumps(d),flush=True)
# Verify context mismatch vs exactly same ONNX with and without context.
a=Onnx(old,False);b=Onnx(old,False);c=Onnx(old,True)
pa=[];pb=[];pc=[]
for i in range(0,len(raw)-256+1,256):
 x=raw[i:i+256].astype(np.float32)/32768
 pa.append(a.process(x));pb.append(b.process(x));pc.append(c.process(x))
print(json.dumps({'context_check_frames':len(pa),'no_context_vs_no_context_max_abs':float(np.max(np.abs(np.array(pa)-pb))),'no_context_vs_context_max_abs':float(np.max(np.abs(np.array(pa)-pc))),'no_context_vs_context_mean_abs':float(np.mean(np.abs(np.array(pa)-pc)))}))
open(output/'bench-results.json','w').write(json.dumps(results,indent=2))
for p in [old,new]:print(p,hashlib.sha256(open(p,'rb').read()).hexdigest())
