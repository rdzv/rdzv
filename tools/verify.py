"""Verify a packaged runtime as an unprivileged user with real Tor sessions."""
import argparse
import json
import subprocess
import time

from tools.assemble import installer
from tools.build import ROOT, PLATFORMS, INPUTS, VERSION, run

TIMEOUTS = (
    'Tor startup timed out after 180 seconds.',
    'Onion service publication timed out; no invitation was issued.',
    'Unable to connect before the connection deadline: Timed out reaching or handshaking with the onion service.',
)


def verify(arch):
    output = ROOT / 'dist' / arch
    entry = json.loads((output / f'manifest-{arch}.json').read_text())
    release = entry['release']
    entries = {target: dict(archive=f'rdzv-{release}-linux-{target}.tar.gz', sha256='0' * 64)
               for target in PLATFORMS}
    entries[arch] = entry
    bootstrap = ROOT / '.build' / arch / 'install.sh'
    bootstrap.write_text(installer(release, entries, 'install'))
    image = f'rdzv-rootless-test:{arch}'
    run('docker', 'build', '--platform', PLATFORMS[arch], '--build-arg', f'BASE_IMAGE={INPUTS["ubuntu"]}',
        '-t', image, '-f', ROOT / 'tests/integration/Dockerfile', ROOT / 'tests/integration')
    command = ['docker', 'run', '--rm', '--platform', PLATFORMS[arch], '--read-only',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--tmpfs', '/home/guest:exec,uid=10001,gid=10001,mode=700', '--tmpfs', '/tmp',
               '-e', f'RDZV_VERSION={VERSION}', '-e', f'RDZV_RELEASE={release}', '-e', f'RDZV_ARCH={arch}',
               '--mount', f'type=bind,src={output},dst=/release,readonly',
               '--mount', f'type=bind,src={bootstrap},dst=/installer,readonly',
               '--mount', f'type=bind,src={ROOT}/tests/integration,dst=/tests,readonly',
               image, 'sh', '/tests/install.sh']
    for attempt in range(3):
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        print(result.stdout, result.stderr, flush=True)
        if not result.returncode:
            return
        if attempt == 2 or not any(message in result.stdout + result.stderr for message in TIMEOUTS):
            result.check_returncode()
        time.sleep(5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=PLATFORMS, required=True)
    verify(parser.parse_args().arch)
