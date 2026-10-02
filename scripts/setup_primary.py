#!/usr/bin/env python3
"""Install pinned primary backends inside the active environment; no credentials."""
import hashlib
from pathlib import Path
import subprocess
import sys
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
DEPS=ROOT/'.deps';DEPS.mkdir(exist_ok=True)
def run(*args):subprocess.run(args,check=True)
run(sys.executable,'-m','pip','install','numpy==2.3.5','scipy==1.17.0','matplotlib==3.10.8','onnxruntime==1.19.0','setuptools')
source=DEPS/'py-webrtcvad-wheels'
if not source.exists():run('git','clone','https://github.com/daanzu/py-webrtcvad-wheels.git',str(source))
run('git','-C',str(source),'checkout','e8fb8b736111631ae8aa6f29fc9b7498ce893ccf')
run(sys.executable,'-m','pip','install','--no-build-isolation',str(source))
url='https://raw.githubusercontent.com/snakers4/silero-vad/1e261b036686cd0017d500ee96acd1c4ba572a9d/src/silero_vad/data/silero_vad.onnx'
data=urllib.request.urlopen(url).read()
if hashlib.sha256(data).hexdigest()!='1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3':raise ValueError('Silero model hash mismatch')
(DEPS/'silero_current.onnx').write_bytes(data)
