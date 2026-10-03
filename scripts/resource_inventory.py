#!/usr/bin/env python3
"""Record artifact bytes separately from process RSS; omit model binaries."""
import hashlib
import argparse
import importlib.util
import json
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
paths={'silero_model':ROOT/'.deps/silero_current.onnx','fsmn_model':ROOT/'.deps/fsmn/model.onnx',
       'rnnoise_native':ROOT/'.deps/librnnoise.so','agc2_native':ROOT/'.deps/libagc2vad.so',
       'speex_native':ROOT/'.deps/libspeexdsp.so'}
if os.environ.get('VADBENCH_TEN_LIB'):paths['ten_native']=Path(os.environ['VADBENCH_TEN_LIB'])
for version in ('0.3.0','0.4.0'):
    paths[f'silero_lite_{version}_installed']=ROOT/'.deps/silero-vad-lite'/version/'packages'
for module,key in [('_webrtcvad','classic_native'),('onnxruntime','onnxruntime_package')]:
    spec=importlib.util.find_spec(module)
    if spec and spec.origin:
        paths[key]=Path(spec.origin) if key=='classic_native' else Path(spec.origin).parent
results={}
for key,path in paths.items():
    if path.is_file():results[key]={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    elif path.is_dir():results[key]={'installed_tree_bytes':sum(p.stat().st_size for p in path.rglob('*') if p.is_file()),'note':'Includes all installed package files, not compressed download size'}
    else:results[key]={'status':'not installed'}
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'results/synthetic/resource-inventory.json')
output=parser.parse_args().output
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps({'artifacts':results,'note':'Artifact sizes only; excludes dependency closure except separately named package. Never interpret as RAM.'},indent=2)+'\n')
print(output)
