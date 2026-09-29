# Rendezvous

Temporary shell access over Tor. Single-use invitations, no open ports, and no persistent enrollment.

## Start a session

On the machine to share:

```sh
curl -fsSL https://raw.githubusercontent.com/rdzv/rdzv/release/host.sh | sh
```

On the machine joining:

```sh
curl -fsSL https://raw.githubusercontent.com/rdzv/rdzv/release/join.sh | sh
```

The host prints a single-use invitation. Paste it into the joining terminal. Exit the remote shell or press uppercase `D` on the host to end access. A disconnected invitation cannot be reused.

These commands work for both the first session and subsequent sessions. The bootstrap downloads a self-contained runtime from this repository's GitHub Releases, verifies its pinned SHA-256, and quietly reuses a matching local copy.

Supported platforms: Linux x86_64, ARM64, and ARMv7 hard-float, with glibc 2.34 or newer. Base utilities `curl`, `tar`, `sha256sum`, and `mktemp` must be present. Python and Tor are bundled; no administrator access or endpoint package installation is needed.

## Agent sessions

```sh
curl -fsSL https://raw.githubusercontent.com/rdzv/rdzv/release/join.sh | sh -s -- \
  --agent --invitation 'rv1.…'
```

Agent mode prints local commands for executing remote commands over its single persistent connection. Each command runs in a fresh shell and returns its stdout, stderr, and exit status. Use `--invitation-file /private/path` to avoid putting the invitation in command arguments.

To require approval of agent commands, start the host with:

```sh
curl -fsSL https://raw.githubusercontent.com/rdzv/rdzv/release/host.sh | sh -s -- --approve
```

Press `a` to approve, `d` to deny, or `A` to approve subsequent requests. Approval mode requires a host terminal and agent-mode joining.

## Direct download

Download the archive for your platform from [Releases](https://github.com/rdzv/rdzv/releases), verify it against that release's `SHA256SUMS`, extract it, and run:

```sh
./bin/rdzv host
./bin/rdzv join
./bin/rdzv --help
```

Each release includes `host.sh`, `join.sh`, `install.sh`, platform archives, the exact source snapshot, Tor source, `manifest.json`, and captured CLI help. The `release` branch contains generated bootstraps for the latest successfully published build. Version-specific installers remain available on each release.

GitHub build attestations can be checked with:

```sh
gh attestation verify ./rdzv-VERSION-linux-x86_64.tar.gz --repo rdzv/rdzv
```

## Access model

The remote shell runs as the host user, with that user's access. It is not a sandbox. Protect the invitation as a credential. By default, invitations expire after ten minutes and sessions after twelve hours; `--invite-timeout` and `--session-timeout` adjust those bounds. The first successful authentication consumes the invitation.

The website and this repository distribute software. They are not session brokers and do not receive invitations. Sessions use authenticated Tor onion services and SSH; ending a session removes its temporary service state.

## Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

The application is in `src/`, tests in `tests/`, portable packaging in `packaging/`, and build/update tools in `tools/`. See [BUILD.md](BUILD.md) for release details.
