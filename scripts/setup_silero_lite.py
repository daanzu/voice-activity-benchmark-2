#!/usr/bin/env python3
"""Install both checksum-pinned PyPI wheels into independent version targets."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vadbench.silero_lite import (DEFAULT_INSTALL_ROOT, RELEASES, require_supported_platform,
                                 sha256_file, verify_installation)


def install(version, destination):
    spec = RELEASES[version]
    directory = destination / version
    directory.mkdir(parents=True, exist_ok=True)
    wheel = directory / spec['wheel_filename']
    if wheel.exists() and sha256_file(wheel) != spec['wheel_sha256']:
        raise ValueError(f'Existing wheel checksum mismatch: {wheel}')
    if not wheel.exists():
        with tempfile.TemporaryDirectory(prefix='download-', dir=directory) as temp:
            temporary = Path(temp) / spec['wheel_filename']
            with urllib.request.urlopen(spec['wheel_url'], timeout=120) as source, temporary.open('wb') as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            if sha256_file(temporary) != spec['wheel_sha256']:
                raise ValueError(f'Downloaded wheel checksum mismatch: {version}')
            temporary.replace(wheel)
    packages = directory / 'packages'
    if not packages.exists():
        with tempfile.TemporaryDirectory(prefix='install-', dir=directory) as temp:
            staging = Path(temp) / 'packages'
            report = directory / 'pip-install-report.json'
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index',
                '--only-binary=:all:', '--no-compile', '--report', str(report),
                '--target', str(staging), str(wheel),
            ], check=True)
            verify_installation(version, destination, packages=staging)
            staging.rename(packages)
    provenance = verify_installation(version, destination)
    (directory / 'manifest.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(f'Verified silero-vad-lite=={version}: {packages}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--versions', nargs='+', choices=RELEASES, default=list(RELEASES))
    parser.add_argument('--destination', type=Path, default=DEFAULT_INSTALL_ROOT)
    args = parser.parse_args()
    require_supported_platform()
    for version in args.versions:
        install(version, args.destination.resolve())


if __name__ == '__main__':
    main()
