"""Refresh pinned stable upstream inputs; unchanged inputs do not create a release."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(url):
    if not url.startswith(('https://api.github.com/repos/astral-sh/python-build-standalone/',
                           'https://dist.torproject.org/', 'https://pypi.org/pypi/cffi/')):
        raise ValueError('Unexpected update origin')
    headers = {'User-Agent': 'Rendezvous-Update-Checker'}
    if url.startswith('https://api.github.com/') and os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    request = urllib.request.Request(url, headers=headers)
    # Only the fixed upstream origins above are permitted.
    with urllib.request.urlopen(request, timeout=180) as response:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        return response.read()


def refresh_python(inputs, release):
    if not re.fullmatch(r'\d{8}', release['tag_name']):
        raise ValueError('Unexpected standalone Python release')
    selected = {}
    versions = set()
    for arch, old in inputs['python'].items():
        pattern = re.compile(r'cpython-(' + re.escape(inputs['python_series']) + r'\.\d+)\+' +
                             re.escape(release['tag_name']) + '-' + re.escape(old['triple']) +
                             r'-install_only_stripped\.tar\.gz')
        matches = [(asset, pattern.fullmatch(asset['name'])) for asset in release['assets']]
        matches = [(asset, match) for asset, match in matches if match]
        if len(matches) != 1:
            raise ValueError(f'Missing or ambiguous Python asset: {arch}')
        asset, match = matches[0]
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', asset.get('digest') or ''):
            raise ValueError('Python release does not publish an asset digest')
        selected[arch] = dict(triple=old['triple'], sha256=asset['digest'].split(':')[1])
        versions.add(match[1])
    if len(versions) != 1:
        raise ValueError('Python architectures use different versions')
    inputs.update(python=selected, python_version=versions.pop(), python_release=release['tag_name'])


def include_cffi_source(lock):
    """ARMv7 compiles CFFI; resolve metadata without running an upstream sdist."""
    match = re.search(r'^cffi==(\d+(?:\.\d+)+) \\$', lock, re.MULTILINE)
    if not match:
        raise ValueError('CFFI is missing from the resolved runtime')
    version = match[1]
    metadata = json.loads(fetch(f'https://pypi.org/pypi/cffi/{version}/json'))
    sources = [item for item in metadata['urls'] if item['packagetype'] == 'sdist' and
               item['filename'] == f'cffi-{version}.tar.gz']
    if len(sources) != 1 or not re.fullmatch('[a-f0-9]{64}', sources[0]['digests']['sha256']):
        raise ValueError('Missing CFFI source digest')
    digest = sources[0]['digests']['sha256']
    if '--hash=sha256:' + digest in lock:
        return lock
    return lock.replace(match[0] + '\n', match[0] + '\n    --hash=sha256:' + digest + ' \\\n', 1)


def main():
    path = ROOT / 'packaging/inputs.json'
    original = json.loads(path.read_text())
    inputs = json.loads(path.read_text())
    release = json.loads(fetch('https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest'))
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('Expected stable Python release')
    refresh_python(inputs, release)
    listing = fetch('https://dist.torproject.org/').decode()
    versions = set(re.findall(r'href="tor-(\d+\.\d+\.\d+\.\d+)\.tar\.gz"', listing))
    if not versions:
        raise ValueError('No stable upstream Tor release found')
    latest = max(versions, key=lambda value: tuple(map(int, value.split('.'))))
    if tuple(map(int, latest.split('.'))) < tuple(map(int, inputs['tor']['version'].split('.'))):
        raise ValueError('Refusing Tor downgrade')
    if latest != inputs['tor']['version']:
        source = fetch(f'https://dist.torproject.org/tor-{latest}.tar.gz')
        inputs['tor'] = dict(version=latest, sha512=hashlib.sha512(source).hexdigest())
    # Full transitive resolution, retaining hashes for target wheels and ARMv7 sdist.
    environment = {k: v for k, v in os.environ.items() if k not in {'GH_TOKEN', 'GITHUB_TOKEN'}}
    environment['CUSTOM_COMPILE_COMMAND'] = 'python -m tools.update'
    subprocess.run(['pip-compile', '--upgrade', '--generate-hashes', '--strip-extras',
                    '--no-emit-index-url', '--no-emit-trusted-host', '--index-url', 'https://pypi.org/simple',
                    '--pip-args=--only-binary=:all:', '--output-file', 'requirements.lock',
                    'pyproject.toml'], cwd=ROOT, env=environment, check=True, timeout=600)
    lock = ROOT / 'requirements.lock'
    lock.write_text(include_cffi_source(lock.read_text()))
    if inputs != original:
        path.write_text(json.dumps(inputs, indent=2) + '\n')


if __name__ == '__main__':
    main()
