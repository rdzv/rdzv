# Building Rendezvous

Official runtime bundles are built on standard GitHub-hosted runners. The source repository has no dependency on the website or Cloudflare.

## Release workflow

`.github/workflows/release.yml` runs on product changes to `main`, manual dispatch, and a daily dependency check at 09:37 UTC. A scheduled check with unchanged inputs and a current published build does not rebuild.

1. Check for stable upstream updates and commit changed input pins.
2. Run product and bootstrap regression tests and Semgrep.
3. Build x86_64 and ARM64 natively, and ARMv7 under QEMU in a separate Linux job.
4. Execute each packaged CLI, capture help, and verify rootless installation plus real interactive, agent, and host-control sessions over Tor.
5. Require all platforms to pass and their CLI help to agree.
6. Assemble and attest the complete release, upload into a draft, download and verify every asset, then publish.
7. Advance the generated `release` branch to the newly published bootstrap scripts.

When a dependency check creates a commit, it dispatches a fresh build workflow at that commit. This keeps the attested source identity aligned with the files actually built.

Build identifiers are `APP_VERSION-build.RUN_NUMBER`. A dependency-only refresh receives a new build identifier and a separate runtime cache; the application version changes when the application changes. Published bundles are never overwritten. A failed build does not advance the public bootstrap scripts.

GitHub schedules are best-effort and may be disabled after 60 days of repository inactivity. Check the Actions page for failed or disabled runs; manual dispatch is available for recovery.

## Inputs

- `packaging/inputs.json`: standalone Python release, platform hashes, Tor source version/hash, and base image digests.
- `requirements.lock`: hashed runtime dependencies, including AsyncSSH and its transitive dependencies.
- `packaging/build-requirements.lock`: ARMv7 CFFI build tools.
- `pyproject.toml`: supported application dependency ranges.

The updater tracks stable standalone Python builds in the selected Python series, stable upstream Tor tarballs, and Python dependencies within the project's supported ranges. Python major/minor changes and base-image changes are explicit packaging changes. The updater rejects incomplete Python platform sets and missing published digests.

Tor is compiled in Alpine with private musl libraries. Python comes from upstream standalone builds. ARMv7 CFFI is compiled against a privately bundled libffi; other Python dependencies use upstream wheels. Endpoint machines perform no compilation.

The bundle contains upstream metadata and documentation unchanged. Tor source accompanies every release. Build records include the source commit and exact declared inputs. Base-image digests and downloaded runtime inputs are pinned; build packages from signed OS repositories can change, so this is not a claim of byte-for-byte reproducibility.

## Local builds

Requirements: Linux, Docker, Python 3.12+, and execution support for the selected target architecture. On an x86_64 builder, register the pinned binfmt image in `packaging/inputs.json` for `arm` before building ARMv7; register `arm64` for emulated ARM64 builds.

```sh
python3 -m tools.build --arch x86_64 --release 0.2.8-build.1
python3 -m tools.verify --arch x86_64
```

Repeat for `aarch64` and `armv7l` as needed. Build work stays in `.build/`, and release outputs in `dist/`; neither is committed. The GitHub matrix assembles the three outputs automatically. Maintainer Docker containers install build tools; the rootless endpoint tests deliberately have no system Python, Tor, or sudo.

Local dependency refresh:

```sh
.venv/bin/python -m pip install pip-tools==7.5.1
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m tools.update
```
