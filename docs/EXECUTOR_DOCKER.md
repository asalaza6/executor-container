# Executor container pilot

English | [简体中文](EXECUTOR_DOCKER.zh-CN.md)

This optional container packages the existing executor and official IBKR API.
Gateway remains a separate service/container. New customers use the
[beginner combined-kit guide](SETUP.md). The [combined wizard](CONTAINER_SETUP.md)
bundles both controllers and the executor image without a host venv.
Building an image or installing its service does not start trading.

Current release preparation and completed authentication results are summarized in
[the release notes](RELEASE_NOTES.md).

## Build and validate (maintainers)

On Linux with CPython 3.12 and Docker, from the source checkout:

```bash
python3.12 scripts/build-executor-container.py
python3.12 scripts/test-executor-container.py
python3.12 scripts/test-executor-isolation.py
```

The default tag is `follow-executor:0.3.1`. The builder records its image ID and
input hashes in `dist/executor-container/BUILD.json`. The base image is pinned by
digest; dependencies are version/hash-pinned. Official IBKR API 10.50.2 is fetched
from the vendor and checksum-verified, never installed from PyPI's `ibapi`.

Docker receives only the bytecode wheel, Dockerfile, dependency locks and API
download helper. No application source, checkout, credentials or journal enters
the build context. Dependencies may contain source; bytecode is not encryption.
The image's default command prints help.

The acceptance test uses disposable simulated broker state, real Docker processes
and `--network none`. It checks shared native/container locks, reconnect, SIGTERM,
SIGKILL/replacement with a held position and protective stop, SQLite integrity,
replay without another entry and retention of a safety halt. No real Gateway,
relay or account is contacted.

For local transfer, export with
`docker save follow-executor:0.3.1 | gzip > executor-image.tar.gz` and load with
`docker load -i executor-image.tar.gz`. Supply the checksum, matching launcher and
guides through the customer release channel. The bytecode kit includes the
launcher/guides, but no image layers. No registry publication is performed.
Distribute the matching source and notices alongside the image; see [source delivery](SOURCE.md).

## Install and configure

The pilot target is Ubuntu 24.04 ARM64 with Docker access and a systemd user
session. Use your ordinary login user, without sudo, for the launcher. After first
granting Docker group access, reboot during a maintenance window so the user service
manager receives the membership; a new SSH shell alone may leave the manager with
its old groups. Do not make the socket
world-writable. This path does not require the native `install.sh` or a host venv.

After loading the image locally:

```bash
./follow-container install
sudo loginctl enable-linger "$USER"
./follow-container configure
./follow-container check
```

`install` creates a stopped, disabled service and pins the local image's immutable
ID. `FOLLOW_EXECUTOR_IMAGE` selects a different local image for installation;
subsequent commands and the service retain that ID even if the tag moves. Images
are not pulled automatically. Lingering permits service operation after logout
and at boot; installation does not enable trading at boot.

Enter the relay token privately in your terminal. IBKR credentials remain with
Gateway. Setup defaults to paper, MNQ and one contract; live setup retains its
typed confirmation. Use `./follow-container` for executor commands in this pilot.
Manage Gateway separately with its existing launcher.

`check` verifies the signed relay state, account, positions/orders, journal halt
and what-if margin. Add `--quotes` to require live market data and distinguish
authentication from quote availability; error 10197 identifies a competing session.
The combined `follow-stack check`, setup and explicit start always include this
quote gate. After reviewing mode, root and quantity, explicitly:

```bash
./follow-container start
```

This repeats readiness checks before enabling and starting trading. Later process
recovery and boot retain the executor's reconnect/reconciliation and halt behavior.
Nothing automatically clears a safety halt. systemd owns restarts, with a 10-second
retry and no restart for configuration error exit 2; Docker restart policy is off.

<a id="credential-isolation"></a>

## Gateway credential isolation (0.3.1)

Every production executor invocation and generated service mounts an empty,
read-only, non-executable tmpfs over these managed subdirectories:

- `$XDG_CONFIG_HOME/follow-executor/gateway`: IBKR login, VNC password, Gateway configuration/runtime files.
- `$XDG_STATE_HOME/follow-executor/maintenance`: backups, including copied Gateway credentials.

The host files are retained unchanged for Gateway and host-side maintenance.
The container sees neither their contents nor writable copies. The executor runs
without mount capabilities, Docker socket or host PID namespace. Gateway's API
health probe already mounts only the executor configuration file read-only.

Tests run the real launcher's Docker arguments and generated service arguments
with synthetic credentials and networking disabled. They verify direct and
symlink reads, writes, directory renames and unmount attempts fail; setup,
settings/Discord atomic updates and journal access still succeed. The unchanged
0.1.9 launcher fails this isolation test, providing a regression control.

Config/state roots must be separate, non-overlapping directories, with no
symlinks at their roots or protected mountpoints. Resolved XDG paths must not
contain newline, comma or colon. Token/journal/CA files cannot live in the
protected subdirectories. Unsupported Docker mount options fail the launch;
there is no unprotected fallback.

Existing installations need the matching new launcher **and a regenerated
executor service** while stopped and flat. A new image alone does not update old
service arguments. `start` refuses a service definition that differs from this
launcher. Combined kits use the [compatible upgrade procedure](CONTAINER_SETUP.md);
standalone container users reinstall the stopped service with `install`, preserving
configuration and history. Rolling back to an older launcher/service restores its
older access permissions. An already running old service is not retroactively changed.

This protects managed credential locations from the supported executor containers.
The VM owner, host setup/controller, Docker administrators and Gateway still have
access. Extra copies placed elsewhere in executor-accessible folders are outside
this boundary; keep backups in the managed location or outside both mounted roots.
It does not change the executor's network access or its ability to trade via Gateway,
and it is not a claim that a malicious host installer or administrator cannot read secrets.

## Runtime and operations

The launcher runs as your UID/GID, drops capabilities, uses a read-only root
filesystem and mounts the configuration/state directories without recursively
including other host mounts. It never mounts Docker's socket. Gateway credentials
and maintenance backups are hidden by separate read-only mounts, as detailed below.
Executor settings/state remain writable for atomic updates and sibling locks. New directories are private; setup writes secrets
with mode 0600. Logs are available in the user journal; Docker logs are rotated.

Linux host networking reaches the existing loopback Gateway (4002 paper / 4001
live), whether native or containerized, without changing the connection identity
bound to the journal. This shares the host network namespace: the container is
not isolated from other local network services. Keep Gateway bound to loopback.
The executor publishes no ports. Docker Desktop is not supported.

| Command | Behavior |
| --- | --- |
| `./follow-container status` | Read journal state and halt reason |
| `./follow-container service-status` | Show process state, not broker readiness |
| `./follow-container logs` | Follow logs; Ctrl-C exits the viewer |
| `./follow-container stop` | Stop and disable autostart; does not close positions or cancel orders |
| `./follow-container settings` (asks), `--leverage-fraction 0.5` or `--root MNQ --quantity 1` | Existing flat-only settings checks |
| `./follow-container discord link` / `discord enable` | Optional notification setup |
| `./follow-container resume` | Deliberate halt recovery; may adopt/close a broker position |

Do not stop a trading executor to test packaging: stopped executors cannot manage
timed exits or update stops. SIGTERM gets 45 seconds for graceful shutdown.

Persistent paths match the native launcher and are mounted at their original paths:

- `~/.config/follow-executor/`: settings, relay token and configuration lock.
- `~/.local/state/follow-executor/`: journal, WAL/SHM, journal lock and image/control files.
- `~/.config/systemd/user/follow-executor-container-<id>.service`: user unit.

Custom XDG paths must be absolute and consistent across commands, and the systemd
user manager must find its unit directory. Other paths referenced by a custom
config (external token, journal, CA file) are not mounted. Do not copy or initialize
a new journal just to make paths fit.

For migration, stop and disable the native executor during an agreed flat-account
window and retain the exact config, token, journal, user and paths. Shared locks
prevent processes using those same files from running together; they cannot protect
an account from another configuration/client ID. System-wide `/etc` and `/var/lib`
installations need a separately reviewed migration; this launcher does not move them.
Never discard trade history or clear a halt to complete migration.

For upgrades, stop while flat, load the reviewed image, run `install` with
`FOLLOW_EXECUTOR_IMAGE`, then `check` and explicitly `start`. Back up SQLite
consistently first. Rollback requires compatibility with the current journal schema;
never overwrite current trade history with a stale backup to force a rollback.
Combined-kit users should use the verified, backed-up `follow-stack upgrade` and
`rollback` [maintenance procedure](CONTAINER_SETUP.md#upgrade-or-roll-back-while-flat).
It keeps the Gateway image unchanged and refuses incompatible journal/Gateway code.

## Validation status

Ubuntu 24.04 ARM64 is the supported customer platform. The ARM64 image builds
locally and passes the offline lifecycle test. CI is configured to build and
exercise ARM64 only; a configured job is not evidence of a completed remote run.
AMD64 support is outside the planned scope and is not a rollout requirement.

On October 16, 2026 at 1:00 AM Pacific, the actual executor image and Gateway
container passed a separately authorized paper cycle using an isolated signed
test feed. One MNQZ6 entry filled and its 20-point protective stop was acknowledged.
After the executor container was killed with SIGKILL, systemd replaced it and the
same journal and broker stop were recovered. Replayed events created no duplicate
entry or stop. A signed flat target closed the position; a subsequent stale entry
did not reopen it. Final counts were one entry, one stop and one exit, with no
positions or working orders. The production feed was not used.

At 1:10 AM Pacific, the full-host reboot check also passed. Gateway and the test
executor started automatically; authenticated account access and live quotes
returned without permission repairs or a Docker socket ACL. The journal remained
intact and no additional orders appeared. Shared host services recovered. The test
executor and flat-only test feed were stopped and disabled afterward; the original
executor stayed stopped with its configuration, journal and halt preserved.

The October 15 daily Gateway restart recovered authentication; live quotes were
initially blocked by a competing live session and recovered after the customer
logged out. The October 18 Sunday cold restart and authenticated flat-account
recovery passed by 9:01:55 AM Pacific; quotes and a fresh Mobile challenge were not
verified by that observation. The new unified wizard's offline
upgrade/rollback and quote-readiness tests pass. A fresh emulated Ubuntu guest also
passed installation, reboot, setup resume and actual service upgrade/rollback with
a simulated account gate; see [wizard acceptance](CONTAINER_SETUP.md#maintainer-build-and-acceptance).
Actual authenticated upgrade and rollback passed on October 18 using an isolated
Linux test user on this OCI host; both releases recovered account access and kept
the journal/configuration unchanged, with trading stopped. A separate latest-image
readiness check received no live quote, and the fresh paper login produced no Mobile
challenge. A later clean Linux user on the same OCI host passed the unchanged
packaged wizard's paper authentication, real relay verification, account reconciliation
and what-if margin checks, with a 0.6-second clock difference. Wizard resume remained
blocked only by missing live quotes. This complements the separate fresh-OS bootstrap
test; it is not a complete authenticated fresh-VM installation. Live quote readiness
through this clean-user setup was pending at that point. Mobile approval timeout/retry is a separate,
unverified live-mode acceptance item; the tested paper username did not request approval.
An isolated live login on October 18 produced Mobile requests, but approval attempts
after manual resend failed with a phone-side server-communication error. A fresh login
with prompt approval then passed live authentication, fresh account-data checks and API
reconnection with API read-only verified. That test did not establish automatic expiry/retry;
the live test stopped without trading, with the original paper Gateway healthy.
Subsequent automatic-recovery tests did not pass: no retry occurred during 601.3
seconds with an untouched request, or during 120 seconds after a customer-reported
expiry/timeout while attempting the original aged request. Neither test used Resend
or manual restart. The authentication dialog stayed open; both tests stopped without
trading and preserved the original paper Gateway.

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
customer-side diagnostic was later completed before the successful test recorded in the release notes.

At 3:18 PM Pacific, the unchanged clean-user packaged wizard passed its remaining
paper quote check: live market data was ready with no quote error codes, all readiness
checks passed, and clock difference was 0.8 seconds. The original paper Gateway was
restored authenticated and flat, with configuration/journals unchanged and all
executors stopped and disabled. This completes the paper checks for the agreed
split validation approach; fresh-OS bootstrap and authenticated clean-user readiness
remain separate tests. At that point the new watchdog build was unpublished and had
not replaced the running pilot or become the customer default.

The host reboot result does not establish a clean customer installation.
