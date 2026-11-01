# Guided container setup

English | [简体中文](CONTAINER_SETUP.zh-CN.md)

Use the combined `follow-stack-…-ubuntu24.04-arm64-cp312.tar.gz` customer kit on
Ubuntu 24.04 ARM64. Start with [Codex or Claude Code](../START_HERE.md).
Complete [OCI payment/plan preparation](OCI_ARM.md#oci-payment) before any VCN
and [IBKR account/secondary-login preparation](IBKR_ACCOUNT_SETUP.md) before
the wizard. New VM allocation: **2 OCPUs / 12 GB RAM**.
The wizard manages both Gateway
and executor containers; Ubuntu's built-in Python 3.12 runs the small controller.
No host venv, pip packages, Java installation or full desktop is needed.

**New to terminals? Start with the [beginner guide](SETUP.md).** This page is the
technical setup, maintenance and recovery reference.

Version 0.3.0 is prepared for a limited paper-account rollout. See the
[release notes](RELEASE_NOTES.md) for validation scope. Existing installations
retain their current backend until deliberately migrated.
This wizard supports a new installation, resuming its own saved setup, and an
explicit compatible-release upgrade/rollback while stopped and flat. `setup`
refuses another Gateway installation or a different installed executor image;
use the maintenance commands below for release changes. Migration from a native
installation still needs a separately reviewed procedure.

## Credential isolation in 0.3.0

The executor containers cannot read the managed Gateway credential directory or
maintenance backups. Empty read-only mounts hide both subtrees; credentials,
Gateway volume and journal remain at their existing host paths. The host
controller and Gateway retain access. [Scope and verification](EXECUTOR_DOCKER.md#credential-isolation).

For existing installations, use the compatible stopped-and-flat upgrade procedure
below. It regenerates the executor service with the protected mounts. Updating
only an image or launcher leaves an old service unchanged; `start` refuses a
mismatched definition. A rollback to pre-0.1.11 restores the old access permissions.

## Download sources

The Auto Quant archive and matching checksum come from the approved customer
channel. Discord can provide the archive or a download link. The wizard obtains the components separately:

| Component | Source |
| --- | --- |
| Docker Engine | Docker's official Ubuntu repository, `download.docker.com` |
| Gateway image | The pinned upstream `gnzsnz/ib-gateway` image on `ghcr.io` |
| Executor image | Already included in the Auto Quant archive; loaded locally |

You install Docker Engine on the Ubuntu VM. Docker Desktop on your laptop is not
required. The wizard offers Docker installation when needed; after the instructed
reboot, reconnect and rerun setup. Keep internet access available during setup.

## Start or resume

Obtain the kit and its checksum through your customer release channel. On the VM,
verify the archive before extracting it into a permanent directory:

```bash
sha256sum -c follow-stack-VERSION-ubuntu24.04-arm64-cp312.tar.gz.sha256
tar -xzf follow-stack-VERSION-ubuntu24.04-arm64-cp312.tar.gz
cd follow-stack-VERSION-ubuntu24.04-arm64-cp312
./follow-stack setup
```

Replace `VERSION` with the supplied release version. Run as your ordinary Ubuntu
login, without sudo; the wizard requests sudo only for Docker installation or user
service lingering. Keep the extracted directory at this path: Gateway's supervisor
runs from it. Each invocation verifies the supplied files and image archive.

The five steps are:

1. **Docker and permissions.** If Docker is missing, confirm installation from its
   official Ubuntu repository. After first installation, reboot during a suitable
   maintenance window, reconnect and rerun `./follow-stack setup`. The wizard never
   reboots the machine. It checks Docker access in both your shell and user service
   manager. Enable lingering when prompted so services can run after logout/reboot.
   If a connection loss interrupts installation after Docker is installed, rerun
   setup and accept the prompt to finish Docker permissions, then reboot as directed.
2. **Executor image.** Load the included, checksum-verified ARM64 image if needed and
   install its stopped service. The immutable image ID is pinned. No registry login
   or image build is needed on the customer VM.
3. **Account and relay access.** Enter the account ID and personal relay token in
   your terminal. Defaults are paper, MNQ and one contract. Live mode requires its
   typed confirmation. Saved configuration is reused on subsequent runs.
4. **Gateway login.** Enter the verified, dedicated paper login privately; keep
   phone trading on another username to avoid disconnecting OCI Gateway. Choose the restart schedule,
   and approve IBKR Mobile if requested. New setups enable a recovery screen
   by default, with a separate eight-character password. The wizard prints SSH/VNC
   connection instructions. Complete IBKR notices yourself. Type `later` to pause;
   rerunning setup reuses the saved credentials and leaves a running Gateway alone.
   `./follow-stack setup --no-vnc` disables the screen for a new setup only.
5. **Readiness.** Verify signed relay access, the configured account, position/order
   reconciliation, journal halt, what-if margin and a live bid, ask or last quote.
   API connection, account authentication and market data have separate results.
   A cached account list alone does not count as authenticated readiness; fresh
   snapshots and a connection that remains available are required.
   Error 10197 identifies a competing session. A timeout reports no quote, not a
   confirmed market closure; retry when quotes are available. Failures leave trading stopped.

Do not put IBKR passwords, relay tokens or recovery passwords into chat, command
arguments or support messages. The wizard requires a terminal for private setup.
IBKR authentication and occasional login dialogs still require your participation.

## Explicitly start trading

After reviewing the check results, account mode and contract size:

```bash
./follow-stack start
```

Type the exact displayed confirmation, for example `START PAPER 1 MNQ`. The command
rechecks readiness before enabling and starting the executor. This follows real
signals and can place orders in the selected account. Setup itself never starts
trading. Once explicitly started, systemd can recover the executor after failures
and reboot; existing reconciliation and halt rules remain in force.

Optional notifications: `./follow-stack discord link`, then
`./follow-stack discord enable`. Follow the [Discord guide](DISCORD.md) for personal
consent and linking. Use `./follow-stack` in place of `./follow` in that guide.

## Checkpoints and recovery

| Situation | Next command or action |
| --- | --- |
| Interrupted setup or missed phone approval | Approve the expected login request, then rerun `./follow-stack setup`; saved steps are reused |
| Mobile approval remains pending | Each attempt has five minutes; Gateway makes one fresh login after a 60-second pause. The next approval dialog may take longer to appear. Dismiss old notifications and promptly approve the newest request if received |
| Gateway requests approval but no phone notification arrives | A dialog does not confirm delivery. Follow [IBKR's notification troubleshooting](https://www.ibkrguides.com/kb/en-us/article-3234.htm), including its private manual challenge/response resynchronization if needed. Log out of Client Portal before retrying Gateway; keep codes private |
| Gateway reports login needs attention | Two attempts have ended. When ready, run `./follow-stack gateway start`, approve the new request, then `./follow-stack check`. Restarting the host does not reset the limit |
| Recovery password rejected | Enter the same eight printable ASCII characters twice; eight letters/digits are an easy choice. Input is hidden. Rerun `./follow-stack setup` to retry; saved account and relay settings are reused |
| Docker or startup permissions unclear | `./follow-stack doctor`; reboot once after first Docker group setup |
| Login dialog still open | Use the printed SSH tunnel and VNC screen; Gateway status alone does not prove login |
| Paper login produces no Mobile prompt | Continue to readiness checks to verify account authentication; do not wait indefinitely for a prompt |
| Login refused because the regular username has multiple paper-trading users | While stopped and flat, reconfigure Gateway with the intended paper-trading username and its password, retaining paper mode |
| Check failed after login | Resolve the reported relay/account/margin/halt issue, then `./follow-stack check` |
| Error 10197 | Deliberately log out of the competing live session, including Mobile if applicable, and verify quotes; the wizard does not disconnect it |
| Inspect Gateway | `./follow-stack gateway status` or `./follow-stack gateway logs` |
| API health unavailable after login | The supervisor checks once a minute and restarts after ten consecutive API failures, with a persistent 30-minute cooldown; monitoring pauses for Mobile approval |
| API monitor needs attention | Inspect the pinned probe image/configuration and reserve client ID 9701; probe errors and account mismatches do not restart Gateway |
| Inspect executor | `./follow-stack status`, `./follow-stack service-status`, or `./follow-stack logs` |
| Stop following and disable executor autostart | `./follow-stack stop`; this does not close positions or cancel orders |
| Change size while stopped and flat | `./follow-stack settings` (asks; previews the NQ/MNQ split), `./follow-stack settings --leverage-fraction 0.5`, or a fixed `--root MNQ --quantity 1` |
| Different image from a retained wizard release | Use the explicit upgrade procedure below |
| Gateway belongs to another installation | Arrange a reviewed migration; do not delete settings or journal to bypass the refusal |

`setup` refuses an active executor, including one running outside systemd with the
same configuration/journal locks. It also refuses enabled native or container
executors; stop and disable them deliberately while flat before rerunning setup. Readiness failures never
clear a halt. `resume` is a separate, deliberate recovery operation that may adopt
or close positions; it is never called by setup.

`gateway status` includes cached API health and the last-probe time. A healthy
handshake does not replace full readiness or confirm quote access. For a stuck
login, follow the [manual recovery steps](GATEWAY_DOCKER.md#daily-operation-and-recovery).
Monitoring stops with Gateway and never starts the executor.

Stopping Gateway (`./follow-stack gateway stop`) requires the executor to be stopped.
Neither command closes broker positions. Change credentials or the recovery screen
only while stopped and flat using `./follow-stack gateway configure --vnc` (or
`--no-vnc`), then start Gateway, approve login, check and explicitly start trading.

API/VNC listen on loopback; forward VNC over SSH. Persistent config, credentials,
Gateway volume and journal follow the [Gateway](GATEWAY_DOCKER.md) and
[executor](EXECUTOR_DOCKER.md) guides. Neither container receives Docker's socket.
The host controller talks to Docker; Docker group membership allows host administration.

## Upgrade or roll back while flat

Keep both verified releases in separate permanent directories. Do not extract an
update over the installed release, even if the package version is identical during
the pilot. Stop and disable the executor with its current `./follow-stack stop`
after the **whole account** is flat and has no working orders. Keep Gateway logged
in for the read-only maintenance check. From the new release:

```bash
./follow-stack upgrade --from /absolute/path/to/retained-release
```

The command verifies both kits and checks account-wide positions/orders without
placing, cancelling or submitting what-if orders. It requires the displayed typed
confirmation, makes a private configuration backup and consistent SQLite backup,
then stops Gateway and replaces service definitions and the pinned executor image.
Both services remain stopped. Credentials, Gateway's existing persistent Docker
volume, trading history and existing halts remain in place. This procedure keeps
the same Gateway image and requires identical journal/configuration/Gateway code;
schema changes or Gateway upgrades need a separately reviewed migration.
The reviewed migrations are **0.1.12 or 0.2.0 to 0.3.0**.
For 0.1.12, only the exact published Gateway pair with three added setup
messages is accepted; journal and Docker Gateway code must still match.
For 0.2.0, journal and Gateway code are identical
and 0.3.0 reads 0.2.0 settings unchanged. Follow the [upgrade guide](UPGRADE.md),
which adds choosing the leverage fraction with `./follow-stack settings`. Rolling
back to 0.2.0 requires a fixed size first, because 0.2.0 cannot read balance sizing.

From the selected release, run `./follow-stack gateway start`, approve login,
`./follow-stack check`, then explicitly `./follow-stack start`. Quotes must be
available for this readiness check. Maintenance never clears a halt.

To reverse a completed switch, stop the executor while flat, keep Gateway logged
in, then run `./follow-stack rollback` **from the new release that performed the
upgrade**. It repeats the flat-account check and switches to the retained release.
The current journal, including trades recorded since the upgrade, is retained.
The backup journal is for investigation; it is never restored automatically.
Retained kits built before the quote-readiness feature use their earlier checks;
verify live quote access separately before restarting trading on those releases.

An interrupted switch blocks setup and startup in the new controller. If Gateway
is still running, stop it with `./follow-stack gateway stop` from the release that
owns its service (retained or new, depending on where interruption occurred).
Run `./follow-stack rollback` from the new release and type `ROLLBACK` to restore
the previous stopped services. Changed configuration or trading history blocks
this recovery for manual review. Keep the retained release and private backup;
do not bypass the pending-maintenance marker or launch the older controller to trade.

## Maintainer build and acceptance

From the source checkout, build into a separate output directory:

```bash
python3.12 scripts/build-executor-container.py --tag follow-executor:0.3.0 --output dist/container-wizard/image
python3.12 scripts/test-executor-container.py --image follow-executor:0.3.0
curl --fail --location --output /tmp/follow-dependencies.tar.gz https://github.com/quantmnq/executor-container/releases/download/v0.1.12/follow-executor-0.1.12-dependencies.tar.gz
python3.12 scripts/collect-third-party-source.py --image follow-executor:0.3.0 --reuse-archive /tmp/follow-dependencies.tar.gz --reuse-sha256 c2740a33b3f91508c70116d4c0a4389b47fe2fd1748b16b5cf9f480dac0bb769
python3.12 scripts/build-container-kit.py --build dist/container-wizard/image/BUILD.json --third-party dist/third-party/SOURCES.json --output dist/container-wizard/kit
```

The bundle builder requires the image's recorded build inputs to match the current
checkout, verifies its immutable ID and ARM64 platform, and bundles its export with
the matching bytecode wheel. The archive includes matching application source under `sources/`;
the installed wheel remains CPython 3.12 bytecode. Verify the outer checksum from the
trusted release channel: internal hashes detect corruption, not an attacker who
can replace the entire release and checksum together. Provide the matching dependency source archive and notices beside this image
download; see [source delivery](SOURCE.md). Nothing is published by the builder.

Automated tests cover resuming, cancellations, failed quote readiness, service ownership,
explicit start, bytecode-only loading, damaged releases, upgrade/rollback with newer
history and retained halts, and process termination during a switch.
The earlier combined trading/reboot results apply to the documented pilot image,
not automatically to every rebuilt wizard release. An October 17 Pacific rehearsal
on a fresh emulated Ubuntu 24.04 ARM64 guest passed Docker installation/recovery,
guest reboot, user-manager permissions, private configuration, and interruption/resume
before IBKR login. Actual guest Docker/systemd upgrade and rollback preserved newer
journal history, halts, configuration and Gateway volume data, with only the
flat-account gate simulated. This was functional testing, not a timing benchmark.
The October 18 scheduled Sunday cold restart and authenticated account recovery
passed on the existing pilot by 9:01:55 AM Pacific. The real paper-account
maintenance preflight also passed after the October 17 host reboot, following
earlier snapshot failures. Neither check submits orders or performs a release switch.
On October 18, an isolated Linux test user on the same OCI host passed actual
packaged upgrade and rollback with real account-wide paper-account gates. Both
releases recovered authenticated access, with a flat account, no working orders,
unchanged configuration and journal, and the executor stopped throughout.
The latest image's separate readiness check authenticated and reconciled, but
received no live quote before its timeout; full quote readiness remains unverified
for this check. The fresh Gateway login used a separate paper-trading username
and produced no Mobile challenge; the customer confirmed no request or approval
occurred. A subsequent regular-username login, still fixed to paper mode, was
rejected because that login has multiple associated paper users. Gateway requested
a paper-trading username instead. Neither attempt tests a missed approval.
An October 18 fresh Ubuntu guest also completed the packaged Docker installation,
guest reboot, permissions checks, both image preparations, private account/relay
configuration and the `later` checkpoint. Under software emulation, Gateway hit
the login-window startup timeout. A guest-only increase from 60 to 600 seconds
allowed a paper login attempt, which reported a server disconnection. The saved
credentials matched the working original paper Gateway. Signed access to the real
relay passed, but readiness rejected a 14.7-second clock difference. No Mobile
request appeared. This did not pass authenticated fresh-host onboarding; the
installed customer kit was not changed to accommodate the emulator.
An October 18 follow-up ran the unchanged packaged wizard under a new Linux user
on the existing OCI host, with empty configuration/state and a fresh Gateway volume.
Paper login, real relay signature verification, complete account snapshots,
reconciliation and BUY/SELL what-if margin checks passed. The host reported NTP
synchronization; both readiness runs measured a 0.6-second clock difference, within
the two-second limit. Resuming the actual wizard failed only the live-quote check
(`no_quote`). No executor started, no real orders were submitted, and the original
Gateway was restored with configuration and journal history preserved.
At that point, the remaining paper check for this split validation approach was live quote readiness
through the clean-user wizard. Fresh-OS installation/reboot and authenticated
clean-user readiness were tested separately; this is not a complete authenticated
run on a brand-new VM, and the earlier emulated-guest failure remains recorded.
No tested login with this customer's separate paper username
requested Mobile approval, so a missed-approval test is not a gate for this paper
pilot. An isolated live-mode attempt on October 18 produced genuine Mobile requests,
but approvals after a manual resend failed with a Mobile server-communication error.
The first dialog remained open for over eight minutes; timeout logging after the
manual resend does not prove automatic expiry or recovery. A fresh login at 1:20 PM
Pacific succeeded when the customer promptly approved its first request on the same
phone network. Gateway confirmed read-only API mode, and two separate API connections
verified the expected live account with fresh, complete account data. This passes live
authentication and recovery through a manually initiated fresh login; genuine expiry
and automatic retry were not established by that test. The live test was stopped, the original paper
Gateway remained authenticated and flat, and all executors remained stopped. No live
orders, cancellations or what-if orders were submitted; live-account quotes and trading
were not tested.
Two further isolated live tests used no Resend action or manual restart. Leaving a
request untouched produced no second challenge within 601.3 seconds. In the second
test, the customer attempted the original notification after more than five minutes
and reported an expiry/timeout error; no second challenge appeared during the next
120 seconds. The original authentication dialog stayed open in both cases, with no
IBC timeout/relogin event or supervisor restart. These observed recovery scenarios
did not pass. IBC evaluates the timeout when that dialog closes; its 180-second
setting does not itself close an unanswered dialog. Both tests stopped with the
original paper Gateway authenticated and flat, all executors stopped, and no orders
or cancellations submitted. See the [IBC 3.24.2 login handler](https://github.com/IbcAlpha/IBC/blob/3.24.2/src/ibcalpha/ibc/LoginManager.java#L95).

Later on October 18, the new bounded login watchdog was tested twice using the
installed bytecode matching the local `0.1.7-login-recovery-pilot` image. Both runs
timed out the unanswered request after five minutes, restarted after 60 seconds,
and opened a second authentication dialog. When the second attempt did not
complete, the launcher exited with status 2 and retained `attention` with two
attempts used. In the first run the customer reported expiry/timeout, but was unsure
whether the new notification or an existing app screen was used. In the repeat the
first notification was dismissed without approval; no completed login was observed
before the cutoff. Automatic retry and retry exhaustion are verified. Authenticated
recovery was not verified in those runs; the earlier successful first-prompt live login and API
reconnection remain separate evidence. No live orders, cancellations, what-if orders
or trading executor were involved, and the original paper Gateway was preserved.

A further run at 3:46 PM Pacific timed out and restarted as expected. The second
Gateway spent about three minutes at `Authenticating...` before opening its second
factor dialog at 3:55:13. The customer confirmed that no new phone notification was
received. Login did not complete, and the attempt limit stopped the test at 4:00 PM.
That run left retry-notification delivery and authenticated recovery unresolved.
Opening the Gateway dialog does not verify push delivery; the cause is not established.
The original paper Gateway remained unchanged, authenticated and flat. IBKR's
[notification troubleshooting](https://www.ibkrguides.com/kb/en-us/article-3234.htm)
includes a manual challenge/response login to resynchronize notifications; that
customer-side diagnostic was then requested and completed before the later successful test below.

At 3:18 PM Pacific, the unchanged clean-user packaged wizard passed its remaining
paper quote check: live market data was ready with no quote error codes, all readiness
checks passed, and clock difference was 0.8 seconds. The original paper Gateway was
restored authenticated and flat, with configuration/journals unchanged and all
executors stopped and disabled. This completes the paper checks for the agreed
split validation approach; fresh-OS bootstrap and authenticated clean-user readiness
remain separate tests. At that point the new watchdog build was unpublished and had
not replaced the running pilot or become the customer default.


At 5:10 PM Pacific on October 18, the exact packaged API-monitor candidate passed
live automatic recovery. The customer had completed the private Client Portal
manual login and logged out. The first Mobile request was received and dismissed
without approval; after the five-minute limit and 60-second restart delay, Gateway
opened the next prompt at 5:07:26. The customer confirmed a new notification arrived
and approval succeeded. Gateway completed login, two read-only API connections
received fresh account data, and the packaged health monitor became healthy. There
was one automatic restart, no manual resend/restart, and no live orders, cancels,
what-if requests or trading executor. The isolated live Gateway was stopped and
the original paper setup was preserved. This verifies one coordinated recovery;
it does not establish the cause of earlier missing notifications or prove that the
Portal diagnostic alone fixed them. Live quotes and trading were outside scope.

At 5:11 PM Pacific, the candidate was activated locally through a reviewed paper
supervisor migration. Existing Gateway credentials, schedule and data volume were
retained; the verified clean-user paper config and journal were copied privately
without resetting history. The new monitor and packaged full readiness, including
quotes, passed. The paper account was flat with no working orders, all executors
remained stopped/disabled, and prior native/test configurations and journals were
preserved. Real systemd testing also verified restart after ten simulated API
failures, cooldown persistence, and no competing probes during authentication;
no real broker outage was injected. All agreed ARM64 paper and live-authentication
acceptance checks are complete. The kit remains unpublished and is not the customer
default. The activated archive is immutable; these later acceptance notes are in
the source guides and validation records.

The Sunday observer also
did not verify a fresh Mobile challenge or live quotes.
Do not rerun completed paper trade cycles merely to test the installer.

For 0.3.0, runtime pins match 0.1.12, so the commands retain that release's exact
dependency sources using the trusted SHA-256 above. The collector checks archive
and file hashes; the kit builder checks the complete installed image inventory.
If pins change, collect new sources without `--reuse-archive` and review their
provenance. Never substitute newer source versions for installed dependencies.

### Unrelated stock holdings during maintenance

The maintenance probe still requires complete account-wide position and open-order
snapshots. It permits unrelated long `STK` holdings, including fractional reward
shares. Futures of every root, short stocks, options, unknown contract types and
all working orders still block the switch. Missing stock symbols also block it.
This exception applies only to the upgrade/rollback maintenance probe; trading
readiness, journal reconciliation and start checks are unchanged. It does not
close or cancel anything, and a successful switch leaves both services stopped.
The report uses `maintenance_ready`, not `account_flat`, because permitted stock
holdings mean the account is not entirely flat.
