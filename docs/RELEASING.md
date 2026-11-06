# GPL customer releases

English | [简体中文](RELEASING.zh-CN.md)

The owner has selected GPL-3.0-or-later for the customer executor. The signal
service and provider strategy remain separate and private. Publish the reviewed
public export, never this VM's entire checkout, Git history, home directory,
release evidence, credentials or journal. [Source/build details](SOURCE.md).

## Build and validate

Version 0.3.1 is a maintenance release of 0.3.0 (balance sizing: a leverage
fraction of the leader's band, the weight each signal carries and an NQ + MNQ
book). It does not change trading behavior. `follow-stack upgrade` accepts 0.3.0
(identical compatibility digests), the reviewed 0.2.0 migration and the reviewed
0.1.12 Gateway bytecode pair in `maintenance.REVIEWED_GATEWAY_MIGRATIONS`. The
journal, Gateway and Gateway-docker modules must therefore stay byte-identical to
0.2.0/0.3.0; confirm with `follow_executor.release.verify_release` on every kit.
0.3.0's own config/local digests are not a reviewed migration, so changing any of
those modules would also block 0.3.0 upgrades until a reviewed entry is added.
Use CPython 3.12 on Ubuntu 24.04 ARM64 with Docker. Set the version in
`pyproject.toml`, the default image tag in the launcher/tests, and bilingual
versioned examples together. Old release archives are immutable.

```bash
.venv/bin/ruff check .
bash -n follow follow-container follow-stack install.sh deploy/install-bytecode.sh scripts/*.sh
.venv/bin/python -m unittest discover -s tests -v
python3.12 scripts/build-executor-container.py
python3.12 scripts/test-executor-container.py
python3.12 scripts/test-executor-isolation.py
curl --fail --location --output /tmp/follow-dependencies.tar.gz https://github.com/quantmnq/executor-container/releases/download/v0.1.12/follow-executor-0.1.12-dependencies.tar.gz
python3.12 scripts/collect-third-party-source.py --image follow-executor:0.3.1 --reuse-archive /tmp/follow-dependencies.tar.gz --reuse-sha256 c2740a33b3f91508c70116d4c0a4389b47fe2fd1748b16b5cf9f480dac0bb769
python3.12 scripts/build-container-kit.py --build dist/executor-container/BUILD.json --third-party dist/third-party/SOURCES.json
python3.12 scripts/build-source.py --output dist/source --export dist/public-repository
```

The source export reads only the explicit `deploy/public-files.txt` allowlist.
It excludes Git history, local settings, `vendor/`, `dist/`, private release
handoffs and all provider services. Add new application modules to that allowlist;
the builder refuses to omit a module. Review every newly allowlisted file.
Never use `git add .` in the working VM checkout to prepare a public repository.

The image build uses a small allowlisted context. It adds the application's
license metadata and preserves the official IBKR archive's LICENSE, NOTICE and
THIRD_PARTY_LICENSES in the final image. Do not strip dependencies' own notices.
The dependency collector uses a disposable container, mounts only its output
folder, and downloads exact Debian source versions plus Python/API sources.
It does not log into IBKR, access a relay, or alter host services.

The combined-kit builder refuses a stale image context, mismatched wheel, wrong
architecture, changed dependency archive or mismatched installed dependency
versions. Each kit includes its matching application source archive. The wheel
and source must be built from the same reviewed tree. Test from the extracted
source as well as the working checkout, and compare the rebuilt wheel hash.

Run real Docker isolation/lifecycle checks with synthetic fixtures, then repeat
isolation using the final kit's launcher. Verify all archive checksums, matching
source hashes, English/Chinese guide links and private-state preservation.
Automated tests do not establish profitability or validate an unobserved login.

## Publish the reviewed source

The customer repository is
[quantmnq/executor-container](https://github.com/quantmnq/executor-container).
Update it with the reviewed `public-repository/` export for this version,
preserving its existing public history. GitHub Desktop can copy/commit these
files in a clone of the public repository; it does not need access to this VM's
secrets. Include hidden public files such as `.github/` and `.gitignore`, but
never copy the working VM's `.git/` history. No repository URL is assumed by the code.

Create a release/tag matching version 0.3.1 and attach all of these from the
reviewed release output:

- `follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz`
- Its `.tar.gz.sha256` checksum file
- `follow-executor-0.3.1-source.tar.gz` (also included inside the kit)
- `follow-executor-0.3.1-dependencies.tar.gz`
- `SHA256SUMS` covering these release assets

Offer the source downloads beside the binary download at no additional charge.
Do not condition access to source for an existing recipient on renewing the
signal subscription. Do not add a software NDA, no-modification or no-resale
restriction that contradicts the GPL. Service access remains separately
authorized; source publication does not supply a relay token or strategy code.

Retain every published binary and its exact source/dependency archives, license
notices and hashes. If changing download hosts, preserve source availability.
A checksum proves integrity only when obtained through a trusted channel.

The dependency source archive is larger than the installer and is optional for
normal installation. It belongs in GitHub Release assets, not the Git source
tree. Review the release's source and checksum links before inviting customers.
Supply personal relay tokens privately and confirm the provider fingerprint.

## Customer downloads and Discord

Use the public GitHub repository for source and a **v0.3.1 Release** for the
five assets above. In GitHub, open **Releases → Draft a new release**, choose the
matching source commit/tag, attach the assets and use the release notes. For the
initial paper cohort, mark it as a pre-release. Review the actual published
downloads before posting the link.

Pin the release link in Discord alongside links to `docs/SETUP.md` (English)
and `docs/SETUP.zh-CN.md` (简体中文) at that same tag. For existing customers,
also link `docs/UPGRADE.md` and `docs/UPGRADE.zh-CN.md`. Normal customers download
only the `follow-stack` archive and its `.sha256`, then follow their language's
SETUP guide. GitHub's automatic “Source code” downloads are not the installer.
All the guides and screenshots are also inside the kit.

If attaching the installer directly to Discord, attach its matching checksum
and link the corresponding application/dependency source downloads in the same
post. Check the channel's attachment limit first; the dependency source archive
is much larger than the installer. Prefer one GitHub Release link to avoid
splitting a version's files across multiple messages.

`START_HERE` and `AGENT_SETUP` are the primary Codex/Claude Code setup path;
`CONTAINER_SETUP` covers maintenance/recovery; `EXECUTOR` explains trade and
safety behavior. Each has a Chinese counterpart. `DISCORD` configures personal
trade notifications; it is not the installation guide. Customers using this
combined container kit should not begin with `SETUP_NATIVE` or `RELEASING`.

## Rollout and maintenance

Use the English/Chinese beginner setup guides. Start with two or three paper
customers, including first-time terminal users. Their own readiness checks must
pass; setup never starts trading. Review mode, instrument and size before their
explicit start. Customers begin in Codex or Claude Code with START_HERE. Existing installations require a
stopped-and-flat migration that preserves their journals and regenerates the
service to obtain the credential-isolation mounts. A new image alone is not enough.

Publication does not deploy to the running pilot or authorize live trading.
The native Gateway path remains available for existing installations; AMD64 is
not a supported customer target. Changing the upstream Gateway pin requires its
own login/recovery acceptance, independent of source-release packaging.

For 0.3.1, runtime pins match 0.1.12, so the commands retain that release's exact
dependency sources using the trusted SHA-256 above. The collector checks archive
and file hashes; the kit builder checks the complete installed image inventory.
If pins change, collect new sources without `--reuse-archive` and review their
provenance. Never substitute newer source versions for installed dependencies.
