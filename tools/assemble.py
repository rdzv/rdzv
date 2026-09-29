"""Assemble a complete release and its mode-specific bootstrap scripts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from tools.build import ROOT, PLATFORMS


def installer(release, platforms, mode):
    if not re.fullmatch(r'\d+\.\d+\.\d+-build\.\d+', release):
        raise ValueError('Invalid release identifier')
    if mode not in {'host', 'join', 'install'} or set(platforms) != set(PLATFORMS):
        raise ValueError('Incomplete installer inputs')
    cases = []
    for arch, entry in platforms.items():
        if not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
            raise ValueError('Invalid artifact digest')
        if entry['archive'] != f'rdzv-{release}-linux-{arch}.tar.gz':
            raise ValueError('Unexpected artifact filename')
        cases.append(f"    {arch}) RELEASE_SHA256='{entry['sha256']}'; RELEASE_ARCHIVE='{entry['archive']}' ;;")
    return ((ROOT / 'packaging/install.sh.in').read_text().replace('__VERSION__', release)
            .replace('__DEFAULT_MODE__', mode).replace('__PLATFORM_RELEASES__', '\n'.join(cases)))


def assemble(source, output):
    entries = {}
    helps = []
    for arch in PLATFORMS:
        entry = json.loads((source / f'manifest-{arch}.json').read_text())
        if entry['platform'] != 'linux-' + arch:
            raise ValueError('Platform mismatch')
        if entry['archive'] != f'rdzv-{entry["release"]}-linux-{arch}.tar.gz':
            raise ValueError('Invalid archive path')
        archive = source / entry['archive']
        if hashlib.sha256(archive.read_bytes()).hexdigest() != entry['sha256'] or archive.stat().st_size != entry['bytes']:
            raise ValueError('Artifact checksum mismatch')
        entries[arch] = entry
        helps.append(json.loads((source / f'help-{arch}.json').read_text()))
    if len({(e['release'], e['version'], e['source_commit']) for e in entries.values()}) != 1:
        raise ValueError('Mixed release inputs')
    if any(help_text != helps[0] for help_text in helps):
        raise ValueError('Packaged CLI help differs between architectures')
    release = entries['x86_64']['release']
    output.mkdir(parents=True, exist_ok=True)
    for arch, entry in entries.items():
        shutil.copy2(source / entry['archive'], output / entry['archive'])
    for archive in source.glob('*-source.tar.gz'):
        shutil.copy2(archive, output / archive.name)
    manifest = dict(release=release, version=entries['x86_64']['version'],
                    source_commit=entries['x86_64']['source_commit'], platforms=entries)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'cli-help.json').write_text(json.dumps(helps[0], indent=2) + '\n')
    for mode in ['host', 'join', 'install']:
        (output / (mode + '.sh')).write_text(installer(release, entries, mode))
    (output / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
        for path in sorted(output.iterdir()) if path.is_file() and path.name != 'SHA256SUMS'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'dist/incoming')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/release')
    args = parser.parse_args()
    assemble(args.input, args.output)
