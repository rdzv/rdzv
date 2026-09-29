"""Publish complete tested artifacts, then advance the public bootstrap branch."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPO = 'rdzv/rdzv'


def gh(*args, data=None):
    command = ['gh', *args]
    if data is not None:
        command += ['--input', '-']
    result = subprocess.run(command, input=json.dumps(data) if data is not None else None,
                            capture_output=True, text=True, check=True, timeout=900)
    return result.stdout


def api(path, method='GET', data=None):
    return json.loads(gh('api', f'repos/{REPO}/{path}', '--method', method, data=data))


def main():
    output = ROOT / 'dist/release'
    manifest = json.loads((output / 'manifest.json').read_text())
    release = manifest['release']
    if not re.fullmatch(r'\d+\.\d+\.\d+-build\.\d+', release):
        raise ValueError('Invalid release identifier')
    commit = manifest['source_commit']
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Invalid source commit')
    tag = 'v' + release
    existing = api('releases?per_page=100')
    matches = [item for item in existing if item['tag_name'] == tag]
    if matches:
        draft = matches[0]
        if not draft['draft']:
            raise ValueError('Release already published; use a new workflow run')
    else:
        draft = api('releases', 'POST', dict(tag_name=tag, target_commitish=commit, name='Rendezvous ' + release,
                    draft=True, prerelease=False, body='Self-contained Linux runtimes built and tested by GitHub Actions.\n\n'
                    f'Source: {commit}\nBuild: https://github.com/{REPO}/actions/runs/{os.environ["GITHUB_RUN_ID"]}'))
    # Resume a draft only when existing bytes match; never overwrite an asset.
    remote = {asset['name']: asset for asset in api(f'releases/{draft["id"]}/assets?per_page=100')}
    with tempfile.TemporaryDirectory() as directory:
        for path in sorted(output.iterdir()):
            if not path.is_file():
                continue
            if path.name not in remote:
                gh('release', 'upload', tag, str(path), '--repo', REPO)
            gh('release', 'download', tag, '--repo', REPO, '--pattern', path.name, '--dir', directory)
            downloaded = Path(directory) / path.name
            if hashlib.sha256(downloaded.read_bytes()).digest() != hashlib.sha256(path.read_bytes()).digest():
                raise ValueError('Uploaded release content differs: ' + path.name)
    api(f'releases/{draft["id"]}', 'PATCH', dict(draft=False, make_latest='true'))
    refs = api('git/matching-refs/heads/release')
    previous = next((ref['object']['sha'] for ref in refs if ref['ref'] == 'refs/heads/release'), None)
    tree = []
    for name in ['host.sh', 'join.sh', 'install.sh', 'manifest.json', 'SHA256SUMS', 'cli-help.json']:
        blob = api('git/blobs', 'POST', dict(content=base64.b64encode((output / name).read_bytes()).decode(), encoding='base64'))
        tree.append(dict(path=name, mode='100644', type='blob', sha=blob['sha']))
    tree_sha = api('git/trees', 'POST', dict(tree=tree))['sha']
    generated = api('git/commits', 'POST', dict(message='Publish Rendezvous ' + release, tree=tree_sha,
                                             parents=[previous] if previous else []))['sha']
    if previous:
        api('git/refs/heads/release', 'PATCH', dict(sha=generated, force=False))
    else:
        api('git/refs', 'POST', dict(ref='refs/heads/release', sha=generated))


if __name__ == '__main__':
    main()
