# Follow Executor

Run the follower on **your own OCI Ampere ARM instance**, connect **your own
IBKR account**, and choose a **leverage fraction** of the leader's balance
sizing (NQ plus an MNQ remainder), or a fixed MNQ/NQ quantity. The executor
receives signed targets from a signal provider and trades at your chosen size.

**Upgrading from 0.1.12, 0.2.0 or 0.3.0?** Follow [UPGRADE.md](docs/UPGRADE.md) /
[升级指南](docs/UPGRADE.zh-CN.md) while flat.

This repository contains only the follower. A running signal provider and a
personal relay token are required; cloning the repository does not grant signal
access. The default provider is `relay.quantmnq.com`, stream `sessioncycle.mnq`.
Get your token and confirm the public-key fingerprint with your provider.

## Set up once

New customers use **Codex or Claude Code** with the combined **Gateway + executor
container kit**. Start with [START_HERE](START_HERE.md) or
[从这里开始](START_HERE.zh-CN.md), open the extracted package as the assistant's
workspace, and paste the supplied setup prompt. The assistant guides you from
Oracle signup and IBKR account preparation through installation and verification.
[The beginner English guide](docs/SETUP.md) and [零基础中文指南](docs/SETUP.zh-CN.md)
cover first-time terminal use, laptop versus Ubuntu commands, file transfer,
private wizard prompts, reboot/resume, readiness and explicit paper-trading start.
The recommended new VM uses US West (San Jose), Pay As You Go before VCN creation,
and 2 OCPUs / 12 GB RAM. [IBKR preparation](docs/IBKR_ACCOUNT_SETUP.md) covers an
additional account and a secondary Gateway username to keep phone trading separate.

The kit targets Ubuntu 24.04 ARM64 / Python 3.12. Docker Engine comes from Docker's
official Ubuntu repository; Gateway comes from its pinned upstream registry image;
the executor image is included. No Git checkout, host Java or host venv is needed.
The [container reference](docs/CONTAINER_SETUP.md) covers maintenance/recovery;
[release notes](docs/RELEASE_NOTES.md) record the completed pilot and its limits.

Existing native installations use [their retained guide](docs/SETUP_NATIVE.md)
and require a reviewed migration. The [agent guide](docs/AGENT_SETUP.md) chooses
commands by package type. Customer AGENTS.md/CLAUDE.md files are packaged from
`deploy/customer/`; they do not configure this development checkout.
Maintainers use [release instructions](docs/RELEASING.md).

The following steps are for installation from a development checkout.

Use **Ubuntu 24.04 LTS on OCI Ampere A1 / ARM64**, an SSH login with sudo, and an
IBKR account with the required futures permissions. Start with a paper account.
IBC initiates IB Gateway login using credentials stored privately on your VM;
you approve two-factor authentication in IBKR Mobile. Credentials are not sent
to Auto Quant. The first login still needs inspection in the private desktop.

1. Clone this repository (or download and extract its ZIP), open its directory,
   and install:

   ```bash
   ./install.sh
   ```

2. If IB Gateway is not already running, prepare its private desktop:

   ```bash
   ./scripts/gateway-desktop.sh
   ```

   Follow the printed SSH/VNC instructions to install **native ARM64 IB Gateway
   10.51**, then close its window. In SSH run `./follow gateway configure` to
   save the local login and select a timezone and Sunday approval time. Run
   `./follow gateway start`, approve the IBKR Mobile prompt, and inspect API
   settings once in VNC: port **4002 paper** or **4001 live**, **Read-Only API off**,
   and localhost only. [IBC setup and scheduling](docs/IBC.md).

3. Choose your account, instrument and size, and paste your personal relay token:

   ```bash
   ./follow configure
   ./follow check
   ./follow start
   ```

`configure` defaults to paper, MNQ and one contract. Live setup requires an
explicit typed confirmation. `check` verifies the relay signature, Gateway
account, positions/orders and available what-if margin. `start` repeats the
check and starts trading only if it passes. Setup alone does not start trading.

For private trade and service DMs from **AQ Bot**, join your provider's **Auto Quant** Discord server
and, after `configure` but before `start`, run `./follow discord link`. Complete
the bot's `/link` command, receive its test DM, then run `./follow discord enable`.
Your provider must enable the notification service first. This opt-in feature
shares your positions, quantities, entry/exit prices, gross P/L, Gateway/service status and liveness
heartbeats with Auto Quant and Discord. Alerts cover API/market-data outages,
verified recovery, safety halts, signal-feed loss and service starts/stops.
[Discord setup and delivery details](docs/DISCORD.md).

Services stay running after SSH disconnects. `gateway start` enables Gateway
autostart, and `start` enables the executor at boot. IBC initiates Gateway login
after reboot and at the scheduled Sunday time; approve any required mobile prompt.
VNC remains available for unexpected dialogs. No inbound ports beyond SSH are
needed. Keep the installation directory at the same path.

## Change sizing later

Wait until the follower is flat, then:

```bash
./follow stop
./follow settings --leverage-fraction 0.5
./follow start
```

`./follow settings` without options asks interactively and previews the NQ/MNQ
split at example weights at your IBKR NetLiquidation. For a fixed size use
`./follow settings --root NQ --quantity 1`, or `--quantity 2` to change only the
quantity of a fixed setup. You can also rerun `./follow configure`. Settings take effect on restart
and future eligible trades; they do not resize an open trade. The command checks
the journal and complete IBKR snapshots, refuses positions or working orders,
and checks every root involved when switching. Keep Gateway logged in for this check.
If the change is refused, the old config is retained; resolve the issue and
restart with the old settings if needed. Never stop during a trade just to
change settings: stopped executors cannot manage exits.

## Everyday commands

| Command | Purpose |
| --- | --- |
| `./follow status` | Local journal, position record and any halt reason |
| `./follow service-status` | Whether the process is running |
| `./follow logs` | Follow service logs; Ctrl-C exits the viewer |
| `./follow stop` | Stop and disable autostart; **does not close positions** |
| `./follow check` | Connection and readiness checks while the service is stopped |
| `./follow watch` | Watch verified signals while stopped; Ctrl-C exits |
| `./follow resume` | Request recovery from a halt; may adopt/close the broker position |

Use a dedicated account for following and do not manually trade the managed
roots (both NQ and MNQ with balance sizing).
`resume` is for deliberate recovery after inspecting the account, not a routine
restart command. Broker stops can remain after stopping the service, but time
exits and stop changes require the executor and Gateway to be running.

A fresh entry is skipped after its deadline. Stops, clock exits, margin checks,
feed reconnects and one-entry-per-trade behavior are retained from the original
executor. These controls do not guarantee a fill, cap losses, or make the
strategy profitable. [Execution behavior and recovery](docs/EXECUTOR.md).

## Local files and privacy

- `~/.config/follow-executor/executor.json`: account and settings, mode `0600`.
- `~/.config/follow-executor/relay.token`: personal token, mode `0600`.
- `~/.config/follow-executor/gateway/ibc.ini`: local IBKR login for IBC, mode `0600`.
- `~/.config/follow-executor/gateway/`: Gateway settings, schedule and runtime data.
- A private Docker volume also holds IBC credentials and Gateway
  settings; `./follow gateway status` shows its name. Preserve it during updates.
- `~/.local/state/follow-executor/executor.sqlite3`: durable journal; keep it.
- `~/.config/systemd/user/follow-executor.service`: local service definition.

In container release 0.3.1, the executor cannot access the managed Gateway
credential directory or maintenance backups through its filesystem mounts.
These paths are obscured by empty read-only mounts in executor commands and
services; the host controller and Gateway retain their existing files. Setup
and trading state keep their original paths. See [the isolation scope](docs/EXECUTOR_DOCKER.md#credential-isolation).

Config, tokens and trade history stay outside the checkout. The provider receives
small status acknowledgements and your connection IP, not your IBKR credentials,
account ID, contract quantity or fill prices. Separately enabled Discord
notifications do share positions, quantity, entry/exit prices, gross P/L, service health and event times as described
above; account IDs and IBKR credentials remain excluded. Local logs/journals may contain
trading details: redact them before sharing. Advanced provider/connection setup
is available through `./follow configure --advanced` on first setup.

Changing IBKR accounts or paper/live mode needs a separate configuration and
journal; see [operations](docs/OPERATIONS.md). Do not delete the journal or copy
the configuration to another machine while this executor is active.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
./scripts/install-ibapi.sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check .
```

Tests use a local signed HTTP/SSE fixture and a simulated broker. The official
IBKR Python API is fetched separately from IBKR, checksum-pinned to 10.50.02;
The executor and its setup tools are GPL-3.0-or-later. The executor image includes
the official IBKR API under its upstream license. Matching source and notices
accompany the release; see [source and licensing](docs/SOURCE.md).
Ubuntu 24.04 ARM64 is the supported
customer platform, and GitHub CI is configured for that platform only.
Actual paper trading and Gateway login must be validated on the target
account before live use. [Build and release instructions](docs/RELEASING.md).

## License and source

Follow Executor's original code, setup tools and original documentation are
licensed under **GPL-3.0-or-later**. See [LICENSE](LICENSE), [NOTICE](NOTICE) and
[third-party notices](THIRD_PARTY_NOTICES.md). Third-party components retain
their own licenses. Product names and third-party UI screenshots are not a
grant of trademark rights or a relicensing of those products.

Each customer release includes matching application source. The dependency
source archive must be offered beside the container download. Customers can
inspect, modify and redistribute the software under its license; source access
is not conditional on renewing a signal subscription.

The separately operated signal service, provider strategy, subscriber records
and credentials are not part of this repository. Access to a paid signal feed
requires separate authorization. See [English source/build guide](docs/SOURCE.md)
or [中文源码与构建指南](docs/SOURCE.zh-CN.md).
