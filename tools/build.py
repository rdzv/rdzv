"""Build one self-contained Linux runtime from checked-in, hash-pinned inputs."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {'x86_64': 'linux/amd64', 'aarch64': 'linux/arm64', 'armv7l': 'linux/arm/v7'}
INPUTS = json.loads((ROOT / 'packaging/inputs.json').read_text())
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']


def run(*args, timeout=3600, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, timeout=timeout, **kwargs)


def download(url, target, expected, algorithm='sha256'):
    """Only trusted upstream HTTPS origins, followed by pinned-content verification."""
    if not url.startswith(('https://github.com/astral-sh/python-build-standalone/releases/download/',
                           'https://dist.torproject.org/tor-')):
        raise ValueError('Unexpected upstream origin')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.download')
    if not target.exists():
        # URL origin is restricted above and content is checked against committed input.
        with urllib.request.urlopen(url, timeout=180) as response, temporary.open('wb') as out:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            shutil.copyfileobj(response, out)
        temporary.replace(target)
    actual = hashlib.new(algorithm, target.read_bytes()).hexdigest()
    if actual != expected:
        target.unlink()
        raise ValueError(f'Upstream checksum mismatch: {url}')


def cli(arch, bundle, command='rdzv'):
    return ['docker', 'run', '--rm', '--platform', PLATFORMS[arch], '--network', 'none',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--user', '10001:10001', '-e', 'COLUMNS=80', '-e', 'NO_COLOR=1',
            '--mount', f'type=bind,src={bundle},dst=/bundle,readonly', INPUTS['ubuntu'],
            '/bundle/bin/' + command]


def pack(bundle, archive):
    with archive.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as output:
            for file in sorted(bundle.rglob('*')):
                relative = file.relative_to(bundle)
                if '__pycache__' in relative.parts or file.suffix == '.pyc':
                    continue
                info = output.gettarinfo(str(file), str(relative))
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                if file.is_file() and not file.is_symlink():
                    with file.open('rb') as source:
                        output.addfile(info, source)
                else:
                    output.addfile(info)


def build(arch, release):
    if not re.fullmatch(r'\d+\.\d+\.\d+-build\.\d+', release):
        raise ValueError('Expected release identifier VERSION-build.NUMBER')
    work = ROOT / '.build' / arch
    bundle = work / 'bundle'
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    output = ROOT / 'dist' / arch
    output.mkdir(parents=True, exist_ok=True)
    config = INPUTS['python'][arch]
    url = ('https://github.com/astral-sh/python-build-standalone/releases/download/'
           f'{INPUTS["python_release"]}/cpython-{INPUTS["python_version"]}%2B{INPUTS["python_release"]}-'
           f'{config["triple"]}-install_only_stripped.tar.gz')
    python_archive = work / 'python.tar.gz'
    download(url, python_archive, config['sha256'])
    with tarfile.open(python_archive) as archive:
        archive.extractall(bundle, filter='data')
    tor_archive = work / 'tor.tar.gz'
    download(f'https://dist.torproject.org/tor-{INPUTS["tor"]["version"]}.tar.gz',
             tor_archive, INPUTS['tor']['sha512'], 'sha512')
    run('docker', 'run', '--rm', '--platform', PLATFORMS[arch],
        '--mount', f'type=bind,src={bundle},dst=/out',
        '--mount', f'type=bind,src={tor_archive},dst=/inputs/tor.tar.gz,readonly',
        '--mount', f'type=bind,src={ROOT}/packaging/tor.sh,dst=/build.sh,readonly',
        '-e', f'OUT_UID={os.getuid()}', '-e', f'OUT_GID={os.getgid()}',
        INPUTS['alpine'], 'sh', '/build.sh', timeout=14400)
    image = 'rdzv-python-builder:' + arch
    run('docker', 'build', '--platform', PLATFORMS[arch], '--build-arg', f'BASE_IMAGE={INPUTS["ubuntu"]}',
        '-f', ROOT / 'packaging/python.Dockerfile', '-t', image, ROOT / 'packaging')
    run('docker', 'run', '--rm', '--platform', PLATFORMS[arch], '--user', f'{os.getuid()}:{os.getgid()}',
        '-e', 'HOME=/tmp', '-e', f'RDZV_ARCH={arch}', '--mount', f'type=bind,src={bundle},dst=/out',
        '--mount', f'type=bind,src={ROOT},dst=/src,readonly', image, 'sh', '/src/packaging/python-deps.sh')
    (bundle / 'app').mkdir()
    for name in ['rendezvous.py', 'agent_session.py']:
        shutil.copy2(ROOT / 'src' / name, bundle / 'app' / name)
    (bundle / 'bin').mkdir()
    (bundle / 'bin/rdzv').write_text('''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PATH="$ROOT/bin:$PATH"
exec "$ROOT/python/bin/python3" -I "$ROOT/app/rendezvous.py" "$@"
''')
    musl = 'armhf' if arch == 'armv7l' else arch
    (bundle / 'bin/tor').write_text('''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$ROOT/tor/lib/ld-musl-''' + musl + '''.so.1" --library-path "$ROOT/tor/lib" "$ROOT/tor/bin/tor" "$@"
''')
    for name in ['rdzv', 'tor']:
        (bundle / 'bin' / name).chmod(0o755)
    result = run(*cli(arch, bundle), '--version', capture_output=True, text=True)
    if result.stdout.strip() != f'Rendezvous {VERSION}':
        raise ValueError('Packaged CLI version disagrees with project version')
    tor_result = run(*cli(arch, bundle, 'tor'), '--version', capture_output=True, text=True)
    if f'Tor version {INPUTS["tor"]["version"]}.' not in tor_result.stdout:
        raise ValueError('Unexpected Tor version')
    help_output = {}
    for args in [[], ['host'], ['join'], ['session'], ['session', 'exec'], ['session', 'help'], ['session', 'close']]:
        help_output[' '.join(['rdzv', *args])] = run(*cli(arch, bundle), *args, '--help', capture_output=True, text=True).stdout
    (output / f'help-{arch}.json').write_text(json.dumps(help_output, indent=2) + '\n')
    metadata = dict(version=VERSION, release=release, platform='linux-' + arch,
                    minimum_glibc='2.34', inputs=INPUTS,
                    source_commit=os.environ.get('SOURCE_COMMIT', run('git', 'rev-parse', 'HEAD', cwd=ROOT, capture_output=True, text=True).stdout.strip()),
                    requirements_sha256=hashlib.sha256((ROOT / 'requirements.lock').read_bytes()).hexdigest())
    (bundle / 'BUILD.json').write_text(json.dumps(metadata, indent=2) + '\n')
    archive = output / f'rdzv-{release}-linux-{arch}.tar.gz'
    pack(bundle, archive)
    manifest = dict(release=release, version=VERSION, platform='linux-' + arch,
                    archive=archive.name, sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                    bytes=archive.stat().st_size, source_commit=metadata['source_commit'])
    (output / f'manifest-{arch}.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if arch == 'x86_64':
        shutil.copy2(tor_archive, output / f'tor-{INPUTS["tor"]["version"]}-source.tar.gz')
    print(json.dumps(manifest), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=PLATFORMS, required=True)
    parser.add_argument('--release', required=True)
    args = parser.parse_args()
    build(args.arch, args.release)
