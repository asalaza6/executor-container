# Source code, licensing and rebuilding

English | [简体中文](SOURCE.zh-CN.md)

Follow Executor's original application, setup/build tools and original docs are
GPL-3.0-or-later. Read [LICENSE](../LICENSE), [NOTICE](../NOTICE) and
[third-party notices](../THIRD_PARTY_NOTICES.md). You may inspect, modify and
redistribute the software under its license. There is no warranty.

## Customers do not need to compile anything

Continue using the installation archive and [beginner setup guide](SETUP.md).
The Docker image is provided for convenience. Source access does not require
an active signal subscription. Signal-service access is authorized separately;
this software license does not supply a subscription token, provider strategy,
signing key or customer credentials.

The matching application source archive is inside the kit's `sources/` directory.
Its filename and SHA-256 are recorded in `RELEASE.json`; the kit's `SHA256SUMS`
checks it too. It contains the application, wizard, launchers, Dockerfile, build
scripts, dependency pins, tests, docs and license notices. `SOURCE.json` records
individual source-file hashes. It contains no Git history or machine configuration.

For a container kit, also download `follow-executor-0.3.1-dependencies.tar.gz`
from the **same release page as the installation archive**. Its SHA-256 is in
`RELEASE.json` under `third_party_source`. This separate download is for inspection
and rebuilding; normal installation does not need it. It includes the exact
unmodified official IBKR API archive, Python dependency source distributions,
CPython source, and Debian package sources/patches/notices for the supplied image.
Retain this archive when redistributing the container release; an upstream link
alone is not our source-delivery method.

## Build the customer release from source

Use Ubuntu 24.04 ARM64, CPython 3.12 and Docker. Work in a separate development
folder, away from any active installation. Building and offline tests do not
require an IBKR login or a relay token. Do not run setup/start against your real
account to test a build. Commands below run in the extracted application source
folder, which has `pyproject.toml` at its root.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
./scripts/install-ibapi.sh
.venv/bin/ruff check .
.venv/bin/python -m unittest discover -s tests -v
python3.12 scripts/build-bytecode.py
python3.12 scripts/build-executor-container.py
python3.12 scripts/test-executor-container.py
python3.12 scripts/test-executor-isolation.py
curl --fail --location --output /tmp/follow-dependencies.tar.gz https://github.com/quantmnq/executor-container/releases/download/v0.1.12/follow-executor-0.1.12-dependencies.tar.gz
python3.12 scripts/collect-third-party-source.py --image follow-executor:0.3.1 --reuse-archive /tmp/follow-dependencies.tar.gz --reuse-sha256 c2740a33b3f91508c70116d4c0a4389b47fe2fd1748b16b5cf9f480dac0bb769
python3.12 scripts/build-container-kit.py --build dist/executor-container/BUILD.json --third-party dist/third-party/SOURCES.json
```

These scripts download pinned build inputs from their official locations; they
require internet access. The API ZIP's SHA-256 is verified before building, and
Python image dependencies are pinned by version and wheel hashes. The base image
is pinned by digest. The retained dependency archive gives access to the inputs
if upstream downloads later disappear; it is not an automatic offline build cache.

The application wheel remains CPython 3.12 bytecode for compatibility with the
existing installer. Its complete matching source is provided separately. The
wheel records GPL-3.0-or-later and carries LICENSE/NOTICE. `build-bytecode.py`
compiles in a fresh isolated interpreter so previously imported application code
cannot change the wheel bytes. For an identical wheel, use the same CPython patch
version recorded as `build_python_version` in `RELEASE.json`; this is not a claim
that the entire Docker image is bit-for-bit reproducible. The image retains
upstream notices and includes `/usr/share/licenses/ibapi` and
`/usr/share/licenses/follow-executor`.

A modified build must use matching source and notices too. The checksums are
integrity checks, not DRM: regenerate the kit using the supplied build scripts.
See [release instructions](RELEASING.md) for source delivery and publication.

For 0.3.1, runtime pins match 0.1.12, so the commands retain that release's exact
dependency sources using the trusted SHA-256 above. The collector checks archive
and file hashes; the kit builder checks the complete installed image inventory.
If pins change, collect new sources without `--reuse-archive` and review their
provenance. Never substitute newer source versions for installed dependencies.
