# Auto Quant 0.3.1 — upgrade and setup fixes

English | [简体中文](RELEASE_NOTES.zh-CN.md)

Prepared November 6, 2026 (US Pacific). A maintenance release of 0.3.0 with
contributed fixes. Trading behavior, sizing, protection rules, dependencies and
the Gateway image are unchanged.

## New in 0.3.1

- **Upgrade from 0.1.12.** `follow-stack upgrade` now accepts 0.1.12 kits. Their
  only Gateway code difference is three setup messages; the updater pins the exact
  published old/new Gateway bytecode pair, and journal, configuration and Docker
  Gateway code must still match. Unknown changes remain blocked. The v0.3.0 kit
  refuses 0.1.12, so upgrade directly to 0.3.1.
- **Upgrade from 0.3.0.** Journal, configuration and Gateway code are identical,
  so no migration is needed and balance sizing is kept, including on rollback.
- **Unrelated stock holdings during maintenance.** The upgrade/rollback check
  still needs complete account-wide snapshots, but now permits unrelated long
  `STK` holdings such as fractional reward shares. Futures of every root, short
  stock, options, unknown contract types, missing symbols and all working orders
  still block it. Its report says `maintenance_ready` instead of `account_flat`.
  Trading readiness, reconciliation and start checks are unchanged.
- **Sizing changes use one IBKR connection.** `./follow-stack settings`
  previously reconnected immediately with the same client ID when changing
  roots or switching to balance sizing, which could fail with IBKR error 326.
  It now checks all old and new roots through one connection; every flat,
  order, snapshot, account, journal and halt check is kept.
- **Setup recovery.** A mistyped or mismatched recovery-desktop password is
  asked again instead of ending setup. `start` names any missing setup step,
  `doctor` shows Gateway configuration and service-definition status, and a
  missing Gateway file is no longer reported as a permissions problem.
- **IBKR error 354** is explained as a missing market-data subscription for the
  Gateway username; live quotes are still required before trading.
- **Guides:** loopback-only SSH tunnels with `ExitOnForwardFailure`, macOS VNC,
  local-port conflicts and market-data subscription troubleshooting.

Thanks to the contributor of
[#1](https://github.com/quantmnq/executor-container/pull/1),
[#2](https://github.com/quantmnq/executor-container/pull/2) and
[#3](https://github.com/quantmnq/executor-container/pull/3). The setup
password retry is implemented in the stack controller so that Gateway code stays
byte-identical for reviewed upgrades.

## Update to 0.3.1

From 0.3.0, 0.2.0 or 0.1.12, follow [UPGRADE.md](UPGRADE.md): stop the
executor from the old directory while the account has no blocking positions or
working orders, keep Gateway logged in, extract 0.3.1 into a new directory and
run `./follow-stack upgrade --from <old directory>`. Both services stay stopped.
From 0.3.0, skip choosing the leverage fraction; your sizing is kept.

## Validation and scope (0.3.1)

336 source tests passed, including from the extracted corresponding source; 305
tests passed inside the final ARM64 image (one skipped: example configurations
need the source checkout). Docker lifecycle and credential-isolation checks
passed, including with the final kit's launcher. The kit's journal, configuration
and Gateway bytecode match 0.3.0 exactly; the 0.2.0 and 0.1.12 kits pass the
reviewed compatibility check. Tests use mocked brokers: the one-connection
settings change and the stock-holding exception have not yet run against a real
Gateway. No running installation was updated and no broker orders were placed.

## Retained from 0.3.0 — balance sizing with NQ + MNQ

Prepared October 28, 2026 (US Pacific). Under the leader's current sizing, each
trade is sized from the leader's balance and the weight its signal carries.
Version 0.3.0 lets followers do the same at a fraction of the leader's leverage, trading NQ plus an MNQ remainder
as one book. Dependencies, the Gateway image and the protection rules are retained.


- **Leverage fraction.** Setup asks for `f`, above 0 and at most 1; `1` follows
  the leader's 6x balance sizing with its 5.88x–6.6x band. The configuration is
  `"sizing": {"mode": "balance", "leverage_fraction": f}`. The wizard previews
  the NQ/MNQ split at example weights; `check` shows it from IBKR NetLiquidation
  and the live NQ quote, with the book margin at weight 1, the largest size.
- **Sizing at each new flat entry.** Base `floor(6f·E / (2·P))` MNQ units from
  NetLiquidation `E` and the reference price `P`, then kept, reset or raised
  one unit at a time inside the signal's band scaled by `f`. Each signal carries
  its trade's `sizing.weight` (above 0, at most 1), and the follower uses whatever
  weight it receives: the trade is `round_half_up(base × weight)` units as NQ plus
  an MNQ remainder, for example `1 NQ + 7 MNQ`, with no minimum. A trade that
  rounds to 0 is refused without an order (`size rounds to 0 contracts`); at a
  base of 1, weight 0.4 rounds to 0. A
  missing balance or price reuses the last base; with none, or with a zero base,
  a signal without `sizing` or an order above `risk.max_quantity`, the entry is
  refused with a reason. Held positions never
  resize, including Gap→Drift continuations.
- **One two-contract book.** Margin and stop risk are checked for the whole book
  before either order. Each contract has its own stop at the leader's price and
  follows trailing moves, the planned pre-open cancel and exit, session-close exits,
  emergency exits and restart reconciliation. If one contract's stop fills, the
  other keeps its stop and exits on schedule. Exactly one NQ and one MNQ position
  of the same month are allowed; any other mix halts.
- **Signals.** `target.sizing` (the trade's weight and leverage band) and the Drift exit
  plan's `minutes_before_open` are documented. Both `next_rth_open` and
  `before_next_rth_open` are accepted, including for the verified pre-open
  cancellation exception.
- **Notifications and status.** Discord receives one position message per
  contract with its own root and P/L; `status` shows the book, such as
  `1 NQ + 5 MNQ`. The start confirmation names the size, such as
  `START PAPER BALANCE 0.5`.
- **Upgrade.** New bilingual [upgrade guide](UPGRADE.md). `follow-stack upgrade`
  accepts the reviewed 0.2.0 → 0.3.0 migration (journal and Gateway code
  unchanged; 0.2.0 settings load as they are). Rolling back requires a fixed size.
- A configuration without `sizing`, including every 0.2.0 configuration, keeps
  exact 0.2.0 behavior: one root and the same unweighted quantity.

## Update from 0.2.0

While the whole account is flat: stop the executor from the 0.2.0 directory,
keeping Gateway logged in and the journal and token in place. Extract the 0.3.1
kit into a new directory and run `./follow-stack upgrade --from <0.2.0 directory>`,
which regenerates both services and leaves them stopped. Then `./follow-stack
gateway start`, `./follow-stack settings` to choose the fraction,
`./follow-stack check`, and an explicit `./follow-stack start`. Details:
[UPGRADE.md](UPGRADE.md).

## If you stay on 0.2.0

0.2.0 keeps trading its fixed quantity. It ignores the new `sizing` field, and
the leader sends `next_rth_open` exit plans (a stop cancel and an exit before the open), so its
planned pre-open protection stays valid. It does not use signal weights or the
account balance.

## Validation and scope (0.3.0)

Automated broker fixtures cover the sizing arithmetic and band boundaries, the
book's entries, margin and stop-risk refusals, per-contract stops and trailing
moves, one-sided stop fills, pre-open cancellation under both rule names,
scheduled and emergency exits, halted repairs, restart reconciliation,
notifications, setup prompts and the reviewed migration. The container suite
reruns them against the installed bytecode with networking disabled. Balance
sizing has not yet traded on a real IBKR paper account, and IBKR's
NetLiquidation and what-if "before" margin figures are read from the documented
API fields without a broker rehearsal. No account login or order was part of
this build.

## Retained from 0.2.0

- English/Chinese START_HERE prompts, customer AGENTS.md/CLAUDE.md and generated
  package README guide setup from scratch, with resumable account/cloud checkpoints.
- OCI Home Region recommendation: **US West (San Jose), `us-sanjose-1`**.
- Oracle Mobile MFA instructions select **Offline mode or use another
  authenticator app** before scanning/enrollment.
- Before any VCN creation, customers add/verify a payment method under **Billing &
  Cost Management → Upgrade and Manage Payment**, accept the upgrade themselves,
  and wait for **Plan Type: Pay As You Go**, replacing Free Tier.
- New A1 ARM64 instance allocation: **2 OCPUs / 12 GB RAM**, increased from 8 GB.
- New bilingual [IBKR account guide](IBKR_ACCOUNT_SETUP.md): **Open an Additional
  Account**, then **User & Access Rights → Users → “+” Add** for a secondary
  username. Separate Gateway/phone trading usernames avoid competing sessions.
  Paper credentials, account permissions and market data are verified separately.
- The private Gateway wizard reminds customers to use a dedicated login.
  Account approvals, cost/terms acceptance and secrets stay with the customer.
- IBKR preparation now selects **Futures** with truthful experience answers,
  completes the gear-icon **Market Data API Acknowledgement** and **Market Data
  Subscriber Status** forms, and guides eligible **Non-Professional** customers
  to **CME Real-Time (L1)**, listed at **$1.55/month**. Customers confirm current
  recurring fees and actual Gateway/paper data access.
- Release builds can reuse a trusted dependency source archive when runtime pins
  are unchanged. Archive and per-file checksums are verified, and the kit builder
  still requires exact agreement with the installed image inventory. This avoids
  relying on a current Debian index retaining every pinned source version.

Existing working resources and accounts are reused. No running customer
installation is changed by building or publishing these downloads. The new
browser/account flow and concurrent phone/Gateway login still need observation
on each customer's own accounts; automated checks cannot complete those steps.

## Retained from 0.1.12

- After observing an entry fill, including a partial fill, the executor allows
  **30 seconds** for a broker-confirmed stop covering exactly the held quantity
  in the correct direction and contract. If protection is still missing, it
  starts emergency closing after order/position reconciliation.
- Unexpected cancellation, loss or mismatch of an established stop allows
  **60 seconds** to restore protection before emergency closing.
- A verified strategy-requested stop cancellation in the one-minute window
  before a scheduled market-open exit uses that scheduled exit deadline, plus
  at most **30 seconds** of exit grace. It does not receive another 60 seconds.
  An unexpected cancellation or missing entry stop does not qualify.
- When a fresh, complete broker snapshot confirms a flat position with an
  executor-owned stop still working, the executor cancels the leftover stop
  and blocks new entries until reconciliation finishes. Cleanup also runs while
  halted. If an owned order fills during cleanup, verified resulting exposure
  is closed. Unrelated accounts' or other clients' orders are not adopted.
- Protection deadlines and cleanup state survive executor restarts. Emergency
  closing reconciles existing exits and fills to avoid duplicate closing orders.
- The example JSON uses `max_margin_fraction: 1.0`, as requested. This does not
  change the wizard default or an existing customer's settings.

These safeguards need a running executor and a working broker connection.
Disconnects, delayed confirmations or a closed market can delay actual closing;
30/60 seconds are protection deadlines, not guaranteed fill times.
See [execution and safety behavior](EXECUTOR.md).

## Retained from 0.1.11

- Customer executor, setup/build tools and original documentation are GPL-3.0-or-later.
- Every kit includes matching application source and notices; dependency source is offered beside the container download.
- The public source export excludes Git history, private release evidence and machine state.
- IBKR API archive-level license and third-party notices are preserved in the image.
- Signal-service implementation and provider strategy remain separate and private.

See [source and rebuilding](SOURCE.md).

## Retained from 0.1.10

Executor containers now obscure the managed Gateway credentials and maintenance
backup folders behind empty read-only mounts. Protection applies to commands,
maintenance probes and generated services. Setup and trading files retain their
paths; token/journal/CA settings pointing into protected directories are refused.
Old service definitions must be regenerated while stopped and flat. An image
change alone is insufficient. See [isolation and upgrade scope](EXECUTOR_DOCKER.md#credential-isolation).

Real Docker tests use synthetic credentials and disabled networking, verify
blocked reads/writes and mount-removal attempts, and exercise setup, settings,
Discord configuration and service replacement. Host secret fixtures remain
unchanged; the old launcher fails the same isolation check as expected.
This candidate has not replaced the running pilot or been published.

## Included

- A combined Gateway/executor setup wizard for Ubuntu 24.04 ARM64 and Python 3.12.
  Codex or Claude Code guides setup; no host Java, venv or full desktop is required.
- A bundled, immutable executor image and an upstream Gateway image pinned by
  digest. The Gateway version remains 10.51.1c.
- Private terminal configuration, resumable setup, signed relay/account/quote
  readiness checks and explicit confirmation before trading starts.
- One automatic fresh login after a five-minute unanswered Mobile request and a
  60-second restart delay; a second timeout stops for user attention.
- Authenticated API monitoring, restart after ten consecutive unavailable probes,
  and a persistent 30-minute cooldown. Monitoring pauses during authentication.
- Persistent trading history, reconciliation and halt retention, plus compatible
  release upgrade/rollback while stopped and flat.
- English and Chinese setup, recovery and operation guides.

Version 0.1.9 replaces the main SETUP guides with a first-time terminal workflow:
Windows/Mac terminal basics, local versus remote commands, file transfer/checksum,
Docker reboot/resume, private inputs, optional Discord and explicit paper start.
Native instructions remain separately available. The Chinese guide explains the
program's English prompts; the command-line interface itself remains English.

The protection logic above changes trading behavior relative to the accepted
0.1.7 pilot. Dependencies and the Gateway image remain pinned; older artifacts
remain unchanged. A first-time customer's independent completion of these
rewritten guides has not yet been observed.

## Where downloads come from

| Component | Download source |
| --- | --- |
| Auto Quant kit and matching checksum | Auto Quant's approved customer channel; Discord may carry the files or a download link |
| Docker Engine | Docker's official Ubuntu apt repository, `download.docker.com`; installed by the wizard if needed |
| Gateway container | Pinned `gnzsnz/ib-gateway` image from `ghcr.io`; downloaded directly on the customer's VM |
| Executor container | Included in the Auto Quant kit and loaded locally; customers do not build it or log into a registry |

Docker Engine is installed on the Ubuntu VM. Docker Desktop on the customer's
laptop is not required. Initial setup needs internet access for the external
downloads and broker/relay connections. After the first Docker installation,
reboot when instructed, reconnect and rerun `./follow-stack setup`.

## Validation and scope

The new protection paths are covered by automated broker fixtures, including
partial fills, restart persistence, scheduled cancellation, manual flattening,
halted cleanup, delayed callbacks and cancellation/fill races. The container
regression suite runs these tests against the installed bytecode with networking
disabled. These protection paths have not yet been exercised against a real IBKR paper
account; the earlier pilot results below apply to the earlier implementation.
No account login, executable order or service deployment is part of this rebuild.

The preceding ARM64 pilot passed paper entry/protective-stop/exit, journal and
reconnect recovery, Docker interruption, host reboot, daily and Sunday restarts,
authenticated account checks and quotes. Fresh-OS bootstrap/reboot and
authenticated clean-user setup were tested separately; this was not a single
complete authenticated installation on a fresh VM.

On October 18 Pacific time, an isolated live authentication test received a new
Mobile notification after one automatic retry. The customer approved it; login,
two read-only API reconnects and the packaged health monitor passed. No live
orders, cancels or what-if orders were submitted. Live quotes and live trading
were outside scope. This successful run does not guarantee every future phone
notification will arrive; manual recovery remains documented.

The API-failure restart and cooldown were exercised through actual systemd with
simulated failures and accelerated polling. No real broker outage was injected.
The monitor checks authenticated API access; full readiness additionally checks
quotes, relay access, margin and reconciliation.

## Installation and updates

Start with [Codex or Claude Code](../START_HERE.md) and [the beginner setup guide](SETUP.md); [maintenance and recovery](CONTAINER_SETUP.md)
remain in the technical reference. Setup leaves trading stopped.
Review readiness, account mode and size before explicitly running
`./follow-stack start`. Existing 0.2.0 installations follow [UPGRADE.md](UPGRADE.md).

Keep releases in separate permanent directories and preserve configuration,
Gateway data and the trading journal. Existing native installations need a
reviewed migration. Container upgrades use the compatibility and flat-account
checks in the guide; a version number alone does not establish compatibility.
Initial customer rollout is planned for a small
paper-account cohort on Ubuntu 24.04 ARM64. AMD64 is outside this release's scope.
