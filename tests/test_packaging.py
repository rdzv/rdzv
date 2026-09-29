import hashlib
import json
import subprocess

import pytest

from tools.assemble import assemble, installer
from tools.build import INPUTS, PLATFORMS
from tools.update import refresh_python


def fixture_assets(path):
    release = '0.2.8-build.1'
    for arch in PLATFORMS:
        name = f'rdzv-{release}-linux-{arch}.tar.gz'
        content = arch.encode()
        (path / name).write_bytes(content)
        (path / f'manifest-{arch}.json').write_text(json.dumps(dict(release=release, version='0.2.8',
            platform='linux-' + arch, archive=name, sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content), source_commit='a' * 40)))
        (path / f'help-{arch}.json').write_text(json.dumps({'rdzv': 'Usage: rdzv'}))


def test_assembly_verifies_all_artifacts_before_generating_bootstrap(tmp_path):
    source = tmp_path / 'input'
    source.mkdir()
    fixture_assets(source)
    output = tmp_path / 'output'
    assemble(source, output)
    assert "MODE='host'" in (output / 'host.sh').read_text()
    assert "MODE='join'" in (output / 'join.sh').read_text()
    for mode in ['host', 'join', 'install']:
        subprocess.run(['dash', '-n', str(output / (mode + '.sh'))], check=True, timeout=10)
    assert '__' not in (output / 'host.sh').read_text()
    assert len(json.loads((output / 'manifest.json').read_text())['platforms']) == 3
    (source / 'rdzv-0.2.8-build.1-linux-armv7l.tar.gz').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='checksum'):
        assemble(source, tmp_path / 'rejected')
    assert not (tmp_path / 'rejected').exists()


def test_mixed_cli_help_blocks_release(tmp_path):
    fixture_assets(tmp_path)
    (tmp_path / 'help-armv7l.json').write_text('{"rdzv": "different"}')
    with pytest.raises(ValueError, match='CLI help differs'):
        assemble(tmp_path, tmp_path / 'output')


def test_installer_rejects_injected_metadata():
    entries = {arch: dict(archive=f'rdzv-0.2.8-build.1-linux-{arch}.tar.gz', sha256='a' * 64)
               for arch in PLATFORMS}
    entries['armv7l']['archive'] = "x';touch /tmp/injected;#"
    with pytest.raises(ValueError, match='filename'):
        installer('0.2.8-build.1', entries, 'host')


def python_release():
    return dict(tag_name='20260925', assets=[dict(
        name=f'cpython-3.12.15+20260925-{entry["triple"]}-install_only_stripped.tar.gz',
        digest='sha256:' + 'b' * 64) for entry in INPUTS['python'].values()])


def test_python_update_requires_all_architectures_and_published_hashes():
    inputs = json.loads(json.dumps(INPUTS))
    release = python_release()
    refresh_python(inputs, release)
    assert inputs['python_version'] == '3.12.15'
    assert inputs['python_release'] == '20260925'
    release['assets'].pop()
    with pytest.raises(ValueError, match='Missing'):
        refresh_python(inputs, release)
    release = python_release()
    release['assets'][0]['digest'] = None
    with pytest.raises(ValueError, match='digest'):
        refresh_python(inputs, release)
