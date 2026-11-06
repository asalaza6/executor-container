# Agent instructions for customer installation

English | [简体中文](AGENT_SETUP.zh-CN.md)

Use this guide in **Codex or Claude Code** to help a customer set up the
**distributed follow-stack package from scratch**, including accounts and OCI.
Read [SETUP.md](SETUP.md) for the commands and [START_HERE.md](../START_HERE.md)
for the customer prompt. Work in the customer's language. No source checkout,
decompilation, development tools or code changes are needed. This guide is not a
request to operate the provider's relay or notification server.

If `RELEASE.json` contains `executor_image`, this is the combined container kit.
Use the beginner [SETUP.md](SETUP.md), the [container reference](CONTAINER_SETUP.md),
and `./follow-stack setup` instead of
the native installation sequence. Hand its private prompts to the customer's own
terminal. Setup can be resumed and never starts trading; `start` requires the
customer's explicit mode/size confirmation. Do not install a host venv or Java.

## Establish the starting point

Ask a small first group of questions: preferred language; laptop OS; whether an
OCI VM and SSH connection already exist; IBKR dedicated-account and secondary-login
preparation complete or pending; new setup, interrupted setup or upgrade.
Locate the archive, checksum and extracted folder. Identify whether each command
runs on **the customer's computer**, **Ubuntu via SSH**, or **the VNC desktop**.
Use the release version in `RELEASE.json` and filenames actually supplied.

If terminal/SSH access is unavailable, say so and give one action at a time for
the customer to perform. Do not claim to have run a command or clicked a screen
that you cannot access. Do not install or sign into an AI tool on the customer's
behalf without their request; use its official instructions when needed.

For a combined kit on an existing VM, use its installed `./follow-stack service-status`
and `./follow-stack gateway status` first; do not infer inactivity from a missing
native unit. For native kits, check the executor and Gateway service states
with `systemctl --user is-active follow-executor.service follow-gateway.service`.
Inactive/not-found states can be expected on first setup; distinguish these from
SSH or user-session failures. Inspect the current unit's `WorkingDirectory` and
`ExecStart` with `systemctl --user show` to identify the installed release. A
different release folder does not mean there is no existing configuration.

If trading is already active, do not stop, reinstall, reconfigure or run a second
executor. Use status information and ask the customer to inspect IBKR. Follow the
[update procedure](SETUP.md#update) only after positions and working orders are
confirmed absent and the customer is ready to stop. A local journal or an empty
early broker cache alone is not proof that the account is flat.

## Questions, private input and decisions

Ask only for information needed at the current stage. Explain why a choice is
needed and offer the guide's default. Collect the sizing choice from the
customer; never infer consent to a trade size. Start new installations in paper
mode. Leave existing account identity, mode, sizing and schedule unchanged
unless the customer explicitly requests the appropriate change procedure.

### Sizing choice (0.3.0)

The wizard's `Sizing` prompt offers `balance` (the default for new setups) or a
fixed `MNQ`/`NQ` quantity. With `balance` it asks for the **leverage fraction**
`f`, a number above 0 and at most 1. Explain it before the customer types it:

- `f = 1` follows the leader's own size: about 6x NetLiquidation in NQ notional,
  held inside a 5.88x–6.6x band. `f = 0.5` is half of that. The executor sizes
  each new entry from IBKR NetLiquidation and the `sizing.weight` each signal
  carries for its trade (above 0, at most 1), trading NQ plus an MNQ remainder
  (for example `1 NQ + 7 MNQ`); held trades never resize.
- The customer chooses `f`. Do not suggest a value as a recommendation, and do
  not raise `risk.max_quantity` or `risk.max_margin_fraction` on their behalf.
- The wizard can preview the NQ/MNQ split at example weights. On a new setup
  it asks for an approximate NetLiquidation and NQ price (Enter skips).
  Rerunning `./follow-stack settings` with Gateway logged in uses IBKR's
  NetLiquidation. `./follow-stack check` reports the real preview, the margin at
  weight 1 (the largest size) and anything that would be refused (base 0, a
  weight rounding to 0 contracts, or above `risk.max_quantity`). There is no
  minimum size: on a small account, low-weight trades are skipped.
- The start confirmation names the size: `START PAPER BALANCE 0.5` (or
  `START PAPER 1 MNQ` for a fixed size).

Existing 0.1.12, 0.2.0 or 0.3.0 customers upgrade with [UPGRADE.md](UPGRADE.md); their
sizing, fixed or balance, keeps working unchanged.

| Information | How to obtain it |
| --- | --- |
| VM IP, SSH username, key file location | Ask if not already available; use the key file without displaying its contents. |
| Provider fingerprint | Ask for the expected non-secret fingerprint and compare it to `leader_key_id` during the check. Do not trust a matching fingerprint you derived only from the supplied package. |
| Leverage fraction `f` (or a fixed instrument and quantity), Discord preference, Sunday schedule | Ask in conversation; confirm choices before configuration. |
| IBKR account ID | Have the customer enter it into the configuration wizard and compare it with Gateway; avoid copying it into chat or progress notes. |
| IBKR username/password, relay token, VNC or sudo password | Customer enters these directly in their own terminal or official login UI. Never request them in chat, command arguments or environment variables. |
| Discord one-time code | Have the customer run linking in their terminal and submit the displayed code to AQ Bot's `/link`; do not retain the code. |

For `./follow-stack setup`, `./follow-stack gateway configure`,
`./scripts/gateway-desktop.sh`, `./follow gateway configure`, and
`./follow configure`, hand the command to the customer's **own interactive SSH
terminal in the release directory** when it needs private input. Do not launch a
hidden-password prompt in an agent-only terminal where the customer cannot type.
Explain the non-secret answers first, wait for the customer to finish, then
verify with status/check commands. Do not route secrets through the model to
drive an interactive prompt. If hidden input is unavailable or produces a warning
that input may be echoed, cancel and use a real interactive terminal.

Do not read, print, upload or include in tool output `relay.token`, `ibc.ini`, SSH
private keys, VNC password files or their backups. Do not dump the whole config,
home directory, environment or logs. Program execution necessarily reads its own
credentials; this instruction concerns exposing them to the agent/transcript.
VM access can technically allow reading these files; the guide is an instruction,
not an isolation mechanism. Use the public status commands and bounded diagnostic
output, redact account/trade details before sharing, and keep backups private.

Routine installation may proceed within the customer's setup request. The
customer completes account verification, terms acceptance, phone approval and
Discord consent/linking. Confirm concrete cloud costs before creating paid
resources. Before the **first trading start**, summarize the verified account
mode, instrument and quantity and obtain explicit agreement to start that setup.
Do not synthesize `LIVE` confirmations. Live migration and `./follow resume` need
their own deliberate decision; `resume` can adopt or close broker positions.

For combined-kit service checks use `./follow-stack service-status` and
`./follow-stack gateway status` from the installed release. The legacy
`follow-executor.service` name alone does not detect the container executor.
Follow SETUP's full five-step wizard, quote readiness and explicit start flow;
do not apply the native checkpoint table below. Use `follow-stack` for subsequent
container status/check/Discord commands; do not run native `follow configure`.

## Account and cloud checkpoints — both package types

Do these before the installation wizard. Help from the first unfinished step,
even when the customer has no Oracle or IBKR account yet. Read the linked guide
before each stage; give one browser/phone action at a time and verify completion.

| Stage | Action and completion evidence |
| --- | --- |
| Oracle account and region | Follow [OCI signup](OCI_ARM.md#oci-account). Recommend **US West (San Jose), `us-sanjose-1`** for a new Home Region. Explain it cannot be changed; preserve an existing region. Customer completes identity verification and terms. |
| Oracle Mobile 2FA | At [enrollment](OCI_ARM.md#oci-mfa), **first select “Offline mode or use another authenticator app”**, then scan/enroll and verify. Customer handles QR code, secret key, recovery codes and OTP privately. Preserve working existing MFA. |
| Payment before VCN | **Before opening the VCN wizard**, guide **Billing & Cost Management → Upgrade and Manage Payment → add/verify payment method → upgrade Free Tier to Pay As You Go**. Customer reviews costs and accepts terms. Require confirmation that **Plan Type is Pay As You Go**; pending is not complete. If declined or unavailable, pause this stage. |
| Network and VM | After the payment checkpoint, follow [VCN](OCI_ARM.md#oci-network), restricted SSH and [instance creation](OCI_ARM.md#oci-instance): **Ubuntu 24.04 ARM64, A1 Flex, 2 OCPUs / 12 GB RAM**. Customer reviews the estimate. Verify SSH, `aarch64`, Python 3.12 and clock sync. Reuse a compatible existing VM; do not resize/rebuild it during active trading. |
| IBKR additional account | Follow [IBKR preparation](IBKR_ACCOUNT_SETUP.md). Help with initial signup if needed, then **User icon → Settings → Trading → Open an Additional Account**. Customer completes the application and approvals, or confirms an existing dedicated account. Do not choose financial/experience answers or initiate funding/transfers. |
| IBKR secondary username | Guide **User icon → Settings → User & Access Rights → Users → “+” Add**, choosing **Yes** for a secondary username for the same holder. Reserve different usernames for OCI Gateway and phone trading. Verify security enrollment, account access, futures and market data; explain any extra data fees. Verify the actual **paper** login separately. Never request the usernames/passwords in chat or log into mobile trading with Gateway's username. |
| Futures permission | During the application select **Futures** and the needed US market. Customer enters **actual** experience years, trades and knowledge; several years only if true. For an existing account use **Settings → Trading → Trading Permissions**. Wait for approval; do not invent years or change profile answers to bypass eligibility. |
| Market-data forms and CME | In **Settings → Trading Platform → Market Data Subscriptions**, click each **gear** for **Market Data API Acknowledgement** and **Market Data Subscriber Status** and finish both forms. Select **Non-Professional** only when the customer's truthful answers qualify. In **Current Subscriptions → gear → US/North America → Level 1**, select **CME Real-Time (L1)**, listed at **$1.55/month** for Non-Professional. Customer confirms the actual recurring fee and agreements. Verify saved forms, active subscription for the Gateway username and intended paper-data sharing/access. Follow the [full IBKR steps](IBKR_ACCOUNT_SETUP.md). |

Record each checkpoint as complete/pending in the progress note, without account,
card or credential details. Do not create duplicate accounts/users on resume.
An unavailable option or pending Oracle/IBKR approval is a specific unfinished
checkpoint, not permission to bypass it.

## Combined-kit installation checkpoints

After account/cloud preparation, follow [SETUP.md](SETUP.md) in order:

1. Verify the archive against its trusted checksum and transfer it to Ubuntu.
   Extract to a permanent folder; install through **`./follow-stack setup`**.
2. Hand the interactive wizard to the customer's own SSH terminal. Explain
   paper account ID, the sizing choice and leverage fraction, dedicated Gateway
   paper login, relay token and schedule first. Never answer hidden prompts
   through the agent transcript.
3. Follow the Docker reboot instruction once needed, save progress, reconnect,
   and rerun the same command. Saved steps and credentials are reused.
4. Customer approves Gateway authentication. The wizard configures API settings;
   show the bundled screenshots only if manual inspection is needed. Use a
   private SSH tunnel for recovery; keep ports 4001/4002/5901 private.
5. With trading still stopped, require **`./follow-stack check`** to pass account,
   relay, margin and quote checks. Have the customer sign into phone trading
   using the other username, then recheck that Gateway remains connected.
   If quote verification waits on the market, record it as pending.
6. If Discord is wanted, follow the bundled screenshot and linking steps with
   `./follow-stack discord link`, test DM, then `./follow-stack discord enable`.
7. Present the verified paper mode and size (`BALANCE f` with the check's
   split at example weights, or the fixed root and quantity). Obtain explicit agreement
   before `./follow-stack start`; otherwise finish configured with trading stopped.

Use bounded logs such as `journalctl --user -u 'follow-executor-container-*.service' -n 60 --no-pager`, plus public status
commands. Distinguish a running Gateway process from authenticated account/quote
readiness and from observed paper trades. Do not place test orders to finish setup.

## Native-kit checkpoints only

If the customer selected the container pilot, or saved `gateway status` reports
`backend: docker`, read [GATEWAY_DOCKER.md](GATEWAY_DOCKER.md) and use it for
checkpoints 3–5. Do not run the native desktop helper or ask for an installation
directory. Hand off `./follow gateway configure --backend docker --vnc` for private
input. A first Docker installation needs one VM reboot to refresh service-group
permissions; record progress first. Preserve the backend on resume, never migrate
an active installation, and retain the same readiness and trading-start checkpoints.
The Docker volume also contains credentials: do not inspect it or paste Docker
inspect output into chat. Use the secret-free `gateway status` report.

Read the linked setup section before each stage. Run dependent commands
sequentially; check exit status and evidence before advancing. Use the included
scripts, not improvised replacements. Do not run `sudo ./install.sh` or
`sudo ./follow`; scripts request the privileges they need.

| Stage | Action and evidence required |
| --- | --- |
| 1. Accounts and VM | Follow [preparation](SETUP_NATIVE.md#prepare) and [OCI walkthrough](OCI_ARM.md). Customer completes signup and reviews region/capacity/cost. Confirm SSH works and Ubuntu is 24.04, architecture is `aarch64`, Python is 3.12. Do not run the Linux installer on the laptop. |
| 2. Verify and install | Follow [transfer](SETUP_NATIVE.md#transfer) and [installation](SETUP_NATIVE.md#install). Verify the original archive against the trusted matching checksum, extract to a fresh permanent folder on Ubuntu, then run `./install.sh --verify-only` and `./install.sh`. Require successful verification and installation messages. Installation leaves trading stopped. |
| 3. Desktop and Gateway | Follow [Gateway setup](SETUP_NATIVE.md#gateway). Hand off the VNC password prompt. Customer uses an SSH tunnel to the loopback desktop, installs the pinned Gateway, reviews its terms, and closes any manually launched Gateway. Do not expose ports 5901, 4001 or 4002 publicly. |
| 4. Gateway configuration | Hand off `./follow gateway configure`. New defaults: paper, `America/New_York`, daily `23:45`, Sunday `12:00`. This is US Eastern with EST/EDT changes, not fixed UTC−5. Preserve existing schedules. Read [IBC.md](IBC.md) for allowed changes. |
| 5. Gateway login | Run `./follow gateway start`; customer approves IBKR Mobile and inspects the first login in VNC. Check `./follow gateway status`. A running process alone does not prove login succeeded. Show both screenshots from the [API settings walkthrough](SETUP_NATIVE.md#gateway-api) before the corresponding clicks. Customer checks paper account/API port 4002, Read-Only API off, localhost only, and resolves dialogs. |
| 6. Follower settings | Hand off `./follow configure` following [configuration](SETUP_NATIVE.md#follower). Customer enters account ID and relay token privately. Confirm chosen paper mode, root and quantity. Re-running this wizard on an existing setup only changes root/quantity and is not a resume/check command. |
| 7. Optional AQ Bot | Follow [Discord setup](SETUP_NATIVE.md#discord). Explain sharing of trade details, service/Gateway status and heartbeats. Show the bundled #bot-setup screenshot before the customer submits `/link`. Customer runs `./follow discord link`, consents, and uses their own Discord account in Auto Quant → #bot-setup → AQ Bot → `/link`. Confirm the test DM arrived, then run `./follow discord status` and `./follow discord enable` while the executor is stopped. No customer bot/token creation. |
| 8. Readiness | While the executor is stopped, run `./follow check`. Require exit 0, `problems: []`, intended `account_type`, `root`, `quantity`, and independently confirmed `leader_key_id`. Customer verifies their account ID in Gateway. This check may request what-if margin estimates; it submits no executable orders. `--skip-broker` is not sufficient for this checkpoint. |
| 9. Trading start | Present results, unresolved items and the exact paper mode/root/quantity. Explain that `./follow start` may immediately submit eligible orders and enables boot startup. After explicit customer agreement, run it once; inspect service state and bounded logs. If the customer declines, finish as **configured; trading stopped**. |

For bounded process diagnostics use `systemctl --user --no-pager status follow-executor.service`
or `journalctl --user -u follow-executor.service -n 60 --no-pager`
(one line each). Gateway logs use `follow-gateway.service`. Avoid
unbounded `./follow logs`, `./follow gateway logs` and `./follow watch` in agent
tools; they keep running. For the customer's log viewer, Ctrl+C only exits the
viewer. Do not use a stop command to exit a viewer.

`./follow check` does not prove every live market-data subscription is ready.
After an authorized start, AQ Bot's full Gateway-ready/recovered message requires
API reconciliation and confirmed live quotes. API-only readiness or quote-waiting
is a separate state; closed markets may leave quotes unconfirmed. Distinguish
**installed**, **configured**, **check passed**, **running**, and **paper trades
observed**. Do not place test orders solely to make a check pass or claim fills,
stop handling, weekly reauthentication or recovery were tested without evidence.

## Show the Gateway settings during setup

At stage 5, proactively open the [Gateway API settings section](SETUP_NATIVE.md#gateway-api)
for the customer. Show both bundled screenshots, one at a time, before giving
the corresponding click instructions:

1. `docs/images/ib-gateway-configure-menu.png`: **Configure → Settings**.
2. `docs/images/ib-gateway-api-settings.png`: **API → Settings**.

Give one action at a time and explain that Read-Only API must
be unchecked and the paper Socket port must be 4002. Gateway enables API
connections automatically; a missing ActiveX checkbox is expected.

Use a user-visible image/file preview when the tool provides one. For local image
embeds in chat, resolve the image path against the extracted package and use its
absolute path. Merely inspecting an image with a model-only tool does not show it
to the customer. If the interface cannot display images, provide a clickable file
link or direct the customer to open the guide in their local extracted package.
Do not promise a popup in every AI tool, or launch a viewer on a headless VM and
assume it appeared on the customer's laptop. If an image is missing, say so and
use the written steps; do not invent a screenshot or claim to have displayed it.

Reference screenshots do not verify the customer's own settings. Have the
customer confirm the settings in their VNC desktop and save with Apply/OK before
marking this checkpoint complete. The normal readiness check still follows.

## Show the Discord linking screen

At stage 7, if the customer wants notifications, show
`docs/images/discord-bot-setup-link.png` before they submit AQ Bot's `/link`.
Use the same user-visible preview or file-link fallback described above.
Point out **#bot-setup**, the **/link** command and its **code** field. Explain that
`xxxxxxx` is a placeholder for the fresh code from the customer's own Ubuntu
terminal, and the administrator's **Edit Channel** button is not needed.
The customer enters the code directly in Discord; never ask them to paste it
into the agent chat or retain it in progress notes. Require the private linking
confirmation and the test DM before marking delivery verified.

## Resume without resetting

Maintain a small progress note on Ubuntu at
`~/.local/state/auto-quant-onboarding/progress.md`, outside the checksummed release
and application state. Create its parent directory with mode `0700`, the note
with mode `0600`; do not change permissions of unrelated directories. Update it
after each completed stage and when handing off to the customer. If Ubuntu is
not reachable yet, provide a secret-free progress summary in chat and save the
note when connected. Do not overwrite an existing note before reading it.

Record only: release version/path, last verified stage and timestamp, paper/live
mode, selected root/quantity, schedule, Discord enabled/skipped/pending, whether
trading start was authorized/executed, next action and a sanitized error summary.
Exclude passwords, usernames, account IDs, tokens, linking codes, key contents,
raw config/logs and trade/signal payloads. Record customer decisions accurately;
an old note is not authorization for a different account, size or mode.
Include completion/pending flags for Oracle MFA, Pay As You Go, VM, IBKR additional
account, secondary login, paper access and the phone/Gateway coexistence check.
Include futures approval, API acknowledgement, subscriber status and CME L1
completion/pending flags; exclude personal questionnaire answers.

On resuming, read the note and recheck service states and completed checkpoints.
For combined kits use `./follow-stack service-status`, `./follow-stack gateway status`
and, only while stopped, `./follow-stack check`; the commands below are for native kits.
A stale note does not justify reinstalling, stopping a running service, or
repeating a start/consent. Use `./follow gateway status` when Gateway configuration
exists, `./follow status` for journal information, and `./follow check` only while
stopped. Presence of a file is not proof of success. Never delete journals,
notification queues or credentials to make installation appear fresh; never
copy active state to a second executor. For combined-kit upgrades from 0.2.0 use
[UPGRADE.md](UPGRADE.md); for native kits use [SETUP_NATIVE.md](SETUP_NATIVE.md#update).
Preserve both private configuration and state.

## If a checkpoint fails

| Problem | Next action |
| --- | --- |
| Checksum, unsupported OS/Python/CPU, upstream pinned-download mismatch | Stop this stage. Recheck the original trusted files/platform. Ask Auto Quant for a compatible release if needed; do not disable verification, change pinned hashes, or install a random vendor version. |
| SSH fails or OCI has no A1 capacity | Follow [OCI troubleshooting](OCI_ARM.md#oci-help); verify IP/key path/network. Customer decides region or paid-resource changes. Do not open all ports or weaken SSH verification. |
| VNC/Gateway login/API unavailable | Check the private SSH tunnel, service status and bounded logs. Customer inspects Gateway and approves their phone. Do not force another IBKR session offline or repeatedly restart an active trading setup. |
| Wrong account, halt, positions/orders or margin failure | Preserve state, show the specific failure, and follow [OPERATIONS.md](OPERATIONS.md). Customer inspects IBKR. Do not increase limits, disable checks, cancel orders, flatten positions or invoke recovery as an installation workaround. |
| Relay unauthorized or fingerprint mismatch | Ask Auto Quant to verify the subscription or expected fingerprint; do not print the token or replace the verification key just to match. |
| Discord code expired, command missing or DM blocked | Use [DISCORD.md](DISCORD.md). Customer can request a new code, check channel access and allow DMs. Record pending/skipped if they choose to proceed without notifications; never mark delivery verified without a received DM. |
| Agent cannot complete a GUI or private-input step | Give the customer its exact location, one action and the expected result. Wait for completion before dependent work. |

Finish with a short plain-language handover: what is installed and running, the
confirmed mode/root/quantity and weekly schedule, Discord state, remaining
checks, progress-note location, and the next customer action. State that
`./follow stop` stops management and boot startup but does not close positions
or cancel orders. Actual paper-account login, fills/stops and reconnect behavior
still need observation before any later live deployment.

Instruction-file references: [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
and [Claude Code project instructions](https://code.claude.com/docs/en/memory).
