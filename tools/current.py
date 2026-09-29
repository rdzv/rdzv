"""Check whether the public bootstrap branch already names this source commit."""
import base64
import json
import subprocess
import sys


def current():
    result = subprocess.run(['gh', 'api', 'repos/rdzv/rdzv/contents/manifest.json?ref=release'],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        try:
            status = json.loads(result.stdout).get('status')
        except ValueError:
            status = None
        if str(status) == '404':
            return False
        raise RuntimeError('Unable to check published build: ' + result.stderr)
    manifest = json.loads(base64.b64decode(json.loads(result.stdout)['content']))
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                            check=True, timeout=10).stdout.strip()
    return manifest['source_commit'] == commit


if __name__ == '__main__':
    print('true' if current() else 'false')
