#!/usr/bin/env python3
"""Reproducible Linux native builds; dependencies remain private in .deps.

No shell execution of upstream installer scripts. TEN is intentionally excluded.
"""
import argparse
import base64
import tarfile
import urllib.request
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / '.deps'
PINS = {
    'rnnoise': ('https://github.com/xiph/rnnoise.git', '70f1d256acd4b34a572f999a05c87bf00b67730d'),
    'speexdsp': ('https://github.com/xiph/speexdsp.git', '1b28a0f61bc31162979e1f26f3981fc3637095c8'),
    'webrtc_rnnvad': ('https://github.com/daanzu/webrtc_rnnvad.git', '10209d27953cad3affadfdcca968c0066cea0830'),
    'abseil-cpp': ('https://github.com/abseil/abseil-cpp.git', '1e3d25b2657228bd691ee938cfd37d487f48054b'),
}

def run(*args, cwd=None):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)


def checkout(name):
    url, pin = PINS[name]
    target = DEPS / name
    if not target.exists():
        run('git', 'clone', '--no-checkout', url, target)
    run('git', 'checkout', '--detach', pin, cwd=target)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=target, text=True).strip()
    if head != pin:
        raise RuntimeError('Source pin verification failed')
    # Refuse tracked source edits; generated untracked build/config files are OK.
    if subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=target).strip():
        raise RuntimeError(f'Tracked changes in {target}; use a clean checkout')
    return target


def rnnoise():
    src = checkout('rnnoise')
    model_hash = '0a8755f8e2d834eff6a54714ecc7d75f9932e845df35f8b59bc52a7cfe6e8b37'
    if (src/'model_version').read_text().strip() != model_hash:
        raise RuntimeError('Unexpected RNNoise model version')
    archive = src/f'rnnoise_data-{model_hash}.tar.gz'
    if not archive.exists():
        urllib.request.urlretrieve('https://media.xiph.org/rnnoise/models/'+archive.name, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != model_hash:
        raise RuntimeError('RNNoise model archive hash mismatch')
    with tarfile.open(archive) as data:
        data.extractall(src, filter='data')
    files = ['denoise', 'rnn', 'pitch', 'kiss_fft', 'celt_lpc', 'nnet', 'nnet_default',
             'parse_lpcnet_weights', 'rnnoise_data', 'rnnoise_tables']
    run('gcc', '-O3', '-march=native', '-DNDEBUG', '-fPIC', '-shared', '-I'+str(src/'include'), '-I'+str(src/'src'),
        *[src/'src'/f'{f}.c' for f in files], '-lm', '-o', DEPS/'librnnoise.so')


def speex():
    src = checkout('speexdsp')
    (src/'include/speex/speexdsp_config_types.h').write_text(
        '#include <stdint.h>\ntypedef int16_t spx_int16_t; typedef uint16_t spx_uint16_t; '
        'typedef int32_t spx_int32_t; typedef uint32_t spx_uint32_t;\n')
    files = ['preprocess', 'mdf', 'fftwrap', 'filterbank', 'smallft']
    run('gcc', '-O3', '-DNDEBUG', '-fPIC', '-shared', '-DFLOATING_POINT', '-DUSE_SMALLFT', '-DEXPORT=',
        '-I'+str(src/'include'), '-I'+str(src/'libspeexdsp'),
        *[src/'libspeexdsp'/f'{f}.c' for f in files], '-lm', '-o', DEPS/'libspeexdsp.so')


BRIDGE = r'''
#include <array>
#include "modules/audio_processing/agc2/rnn_vad/features_extraction.h"
#include "modules/audio_processing/agc2/rnn_vad/rnn.h"
using namespace webrtc::rnn_vad;
struct VadState { FeaturesExtractor features; RnnBasedVad rnn; };
extern "C" {
void* vadbench_agc2_create() { return new VadState(); }
void vadbench_agc2_destroy(void* p) { delete static_cast<VadState*>(p); }
float vadbench_agc2_process(void* p, const float* x) {
  auto* s = static_cast<VadState*>(p);
  std::array<float, kFeatureVectorSize> f{};
  bool silence = s->features.CheckSilenceComputeFeatures(
    rtc::ArrayView<const float, kFrameSize10ms24kHz>(x, kFrameSize10ms24kHz), f);
  return s->rnn.ComputeVadProbability(f, silence);
}
}
'''


def agc2():
    src = checkout('webrtc_rnnvad')
    absl = checkout('abseil-cpp')
    notices = DEPS/'webrtc-notices'
    notices.mkdir(exist_ok=True)
    for name, expected in {
        'LICENSE': 'ab00a482b6a3902e40211b43c5d0441962ea99b6cc7c25c0f243fa270b78d482',
        'PATENTS': '01462e2068d1a04c2274f3389773014c14ed9bc3446b28303543bd3e3c064145',
    }.items():
        target = notices/name
        if not target.exists():
            raw = urllib.request.urlopen('https://webrtc.googlesource.com/src/+/refs/heads/main/'+name+'?format=TEXT').read()
            target.write_bytes(base64.b64decode(raw))
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise RuntimeError('WebRTC notice changed; review before building')

    build = DEPS/'agc2-build'
    build.mkdir(exist_ok=True)
    (build/'bridge.cc').write_text(BRIDGE)
    flags = ['-O3', '-DNDEBUG', '-fPIC', '-DWEBRTC_POSIX', '-DWEBRTC_LINUX', '-I'+str(src), '-I'+str(absl)]
    sources = sorted((src/'modules/audio_processing/agc2/rnn_vad').glob('*.cc'))
    sources = [p for p in sources if not any(t in p.name for t in ('test', 'tool'))]
    sources += [src/p for p in [
        'modules/audio_processing/agc2/biquad_filter.cc',
        'modules/audio_processing/utility/pffft_wrapper.cc',
        'third_party/rnnoise/src/rnn_vad_weights.cc',
        'rtc_base/checks.cc', 'rtc_base/logging.cc', 'rtc_base/string_utils.cc',
        'rtc_base/string_encode.cc', 'rtc_base/time_utils.cc', 'rtc_base/critical_section.cc',
        'rtc_base/platform_thread_types.cc', 'rtc_base/strings/string_builder.cc',
        'rtc_base/memory/aligned_malloc.cc']]
    objects = []
    for name in ['pffft', 'fftpack']:
        obj = build/f'{name}.o'
        run('gcc', *flags, '-c', src/f'third_party/pffft/src/{name}.c', '-o', obj)
        objects.append(obj)
    run('g++', '-std=c++14', *flags, '-shared', build/'bridge.cc', *sources, *objects,
        '-pthread', '-lm', '-Wl,-z,defs', '-o', DEPS/'libagc2vad.so')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('backends', nargs='*', choices=['rnnoise', 'speex', 'agc2'])
    args = ap.parse_args()
    if not sys.platform.startswith('linux'):
        ap.error('This minimal reproducible builder targets Linux with gcc/g++')
    for tool in ['git', 'gcc', 'g++']:
        if not shutil.which(tool):
            ap.error(f'Missing build tool: {tool}')
    DEPS.mkdir(exist_ok=True)
    for backend in args.backends or ['rnnoise', 'speex', 'agc2']:
        globals()[backend]()
    manifest = {'source_pins': PINS, 'compiler': subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0],
                'rnnoise_model_sha256': '0a8755f8e2d834eff6a54714ecc7d75f9932e845df35f8b59bc52a7cfe6e8b37',
                'rnnoise_compile_flags': '-O3 -march=native -DNDEBUG -fPIC; no runtime CPU dispatch',
                'libraries': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in DEPS.glob('*.so')}}
    (DEPS/'native-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('Built libraries and manifest in', DEPS)

if __name__ == '__main__':
    main()
