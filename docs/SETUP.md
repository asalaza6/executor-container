# Auto Quant setup — no command-line experience needed

English | [简体中文](SETUP.zh-CN.md)

This guide installs **both Gateway and the Auto Quant executor in containers**
using the `follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz` kit. Start with an
IBKR **paper account**, which simulates trading. Use **Codex or Claude Code** to
guide setup from scratch: [open the package and paste this prompt](../START_HERE.md).
You do not need to write code, use GitHub or build an image.

If your archive is named `follow-executor-…` instead, use the
[native guide](SETUP_NATIVE.md). If Auto Quant is already installed on your VM,
read [updates](#update) before changing anything.

You use your laptop to set up a cloud computer running Ubuntu. The cloud computer
can keep running after you close your laptop. Docker runs the two applications;
the wizard installs what it needs. **Setup leaves trading stopped.**

## Before your first command

A **terminal** is a window where you type or paste an instruction, called a
**command**, then press **Enter**. It is not a browser address bar or an AI chat.

- **Windows 10/11:** open Start, type **PowerShell**, and open it. A normal window
  is sufficient; do not choose “Run as administrator.”
- **Mac:** press **Command + Space**, type **Terminal**, then press Enter.
- Paste with **Ctrl + V** or right-click in PowerShell; **Command + V** on Mac.
- Paste one command line at a time, press Enter, and wait for completion. Do not
  copy the Markdown marks or a sample prompt such as `ubuntu@host:~$`.
- An Ubuntu prompt ending in `$` normally means it is ready for a command. If it
  asks a question instead, answer that question before pasting the next command.
- Passwords and tokens may show **no characters or dots** while you type. That
  is normal. Enter the value once and press Enter; never put it in chat.
- At `[paper]`, Enter accepts the displayed default. At `[y/N]`, type `y` then
  Enter only when you want to accept.

**SSH** is the secure connection to your cloud computer. Its **private key** is
a file on your laptop, not an IBKR password. A **VM / instance** means your cloud
computer. **Gateway** logs in to IBKR; the **executor** follows Auto Quant signals.

1. [Gather the download and account details](#prepare)
2. [Create or connect to Ubuntu](#cloud)
3. [Copy and verify the download](#transfer)
4. [Run the wizard; reconnect after the first reboot](#install)
5. [Enter your paper-account settings](#follower)
6. [Complete Gateway login and readiness](#gateway)
7. [Optionally connect Discord](#discord)
8. [Decide whether to start paper trading](#paper)
9. [Daily use, updates and help](#daily)

Start with [Codex or Claude Code](../START_HERE.md); the assistant follows these
steps with you. Your personal login and phone steps still need you. This guide
also contains the complete commands for manual use.

<a id="prepare"></a>

## 1. Gather the download and account details

**Where: your laptop, browser and phone.** Ask Auto Quant for:

| Item | What to do with it |
| --- | --- |
| `follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz` | Save in your laptop's **Downloads** folder; leave it compressed. |
| Matching `.tar.gz.sha256` file | Save beside it. This lets Ubuntu verify the download. |
| Personal relay token | Keep private; enter it into the wizard later. It connects you to the signal service. |
| Expected provider public-key fingerprint | Keep for comparison with readiness results. This identifies the signal provider. |
| Support contact and optional Discord invitation | Use the contact supplied with your customer download. |

Get both download files from Auto Quant's trusted channel. Discord may supply the
files or a download link. These examples use **0.3.1**; if your version differs,
use its included guide and matching filenames. Do not mix releases.

First complete [IBKR account and secondary-login preparation](IBKR_ACCOUNT_SETUP.md):
**Settings → Open an Additional Account**, then **User icon → Settings → User &
Access Rights → Users → “+” Add** for a secondary username belonging to you.
Reserve distinct logins for OCI Gateway and phone trading; a phone trading login
with Gateway's username can disconnect Gateway. Reuse an existing dedicated
account/login when verified. Check the paper login explicitly; creating a live
secondary username does not automatically verify paper access.
During the IBKR application select **Futures** and report your actual experience
(select several years only if accurate). Before setup, complete the **gear-icon
forms** for **Market Data API Acknowledgement** and **Market Data Subscriber
Status**. Eligible customers choose **Non-Professional** and subscribe to
**CME Real-Time (L1)** under **Level 1**, listed at **$1.55/month**; confirm the
current recurring price yourself. The [IBKR guide](IBKR_ACCOUNT_SETUP.md) covers
each form, permissions and paper-data access.

Have your **dedicated paper-trading username, password and paper account ID** ready. An
account ID, such as the fictitious `DU1234567`, is **not your login username**.
Find your actual paper account ID in IBKR's paper-account selector or a paper
account statement. Do not copy the example or substitute your live account ID.
Ask Auto Quant for help identifying it if necessary; keep it out of public chat.

Use an account with the required futures permissions and market-data access.
Keep unrelated MNQ/NQ positions and orders out of this account. If your login
uses IBKR Mobile approval, have your phone ready. Some paper logins complete
without a Mobile request; a missing request alone is not an error.

Docker Engine comes directly from **Docker's official Ubuntu repository**.
Gateway comes from the pinned upstream **GitHub container registry** image. The
executor image is already in your Auto Quant archive. Your laptop does not need
Docker Desktop, and you do not need a GitHub account.

<a id="cloud"></a>

## 2. Create or connect to Ubuntu

**Where: your laptop's browser, then its terminal.** Follow the
[illustrated Oracle Cloud walkthrough](OCI_ARM.md). It covers signup,
cost/capacity choices, network settings, SSH-key download and first connection.
For a new account, choose **US West (San Jose), `us-sanjose-1`** as the suggested
Home Region. At Oracle Mobile 2FA, **first check “Offline mode or use another
authenticator app”**, then enroll. **Before creating a VCN**, go to **Billing &
Cost Management → Upgrade and Manage Payment**, add/verify a payment method,
review and accept the upgrade, and wait for Plan Type to show **Pay As You Go**
instead of **Free Tier**. See the [required payment checkpoint](OCI_ARM.md#oci-payment).
Use **Ubuntu 24.04 LTS, Ampere A1 / ARM64**. A starting allocation is 2 OCPUs and
12 GB memory; review displayed charges before creating the instance.

Already have a VM? Use the walkthrough's [connection](OCI_ARM.md#oci-connect)
and [verification](OCI_ARM.md#oci-check) steps. It must report `aarch64`, Ubuntu
`24.04`, Python `3.12` and a synchronized clock. This kit does not support AMD64.

These examples assume your private key is named **auto-quant.key**, in your
laptop's Downloads folder. Use your actual filename if different. Replace
`YOUR_OCI_PUBLIC_IP` with the instance's public IPv4 address, keeping the rest of
the command. Do not type the placeholder literally.

**On your laptop:**

```bash
cd ~/Downloads
```

**Mac only**, set the key's file permissions. Skip this command on Windows:

```bash
chmod 400 auto-quant.key
```

**Windows or Mac**, connect:

```bash
ssh -i ./auto-quant.key ubuntu@YOUR_OCI_PUBLIC_IP
```

For a first connection, follow the OCI walkthrough's host-verification guidance
before answering `yes`. An unexpected changed-host-key warning on an existing
connection needs investigation. If SSH unexpectedly asks for a password, do not
enter an Oracle or IBKR password; use the walkthrough's troubleshooting section.

**Checkpoint:** you see a prompt similar to `ubuntu@auto-quant:~$`.
Call this **Window A — Ubuntu**. Commands here now run on the cloud computer.

<a id="transfer"></a>

## 3. Copy and verify the download

Keep **Window A** open. Open a second PowerShell or Terminal window on your laptop:
**Window B — Laptop**. Do not run SSH in Window B yet.

| Window | Typical prompt | Used for |
| --- | --- | --- |
| **A — Ubuntu** | `ubuntu@…:~$` | Installing and operating Auto Quant |
| **B — Laptop** | Windows: `PS C:\Users\…>`; Mac: a local name ending in `%` or `$` | Copying files, then optionally opening a recovery connection |

**Window A — Ubuntu:** create the destination folder.

```bash
mkdir -p ~/Downloads
```

**Window B — Laptop:** with the key and both download files in Downloads:

```bash
cd ~/Downloads
```

Replace the IP placeholder, then paste the next command as **one line**. `scp`
means secure file copy; keep the colon and `Downloads/` at the end.

```bash
scp -i ./auto-quant.key follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz.sha256 ubuntu@YOUR_OCI_PUBLIC_IP:Downloads/
```

Wait for both transfers. **Back in Window A — Ubuntu**, run one line at a time:

```bash
cd ~/Downloads
sha256sum -c follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz.sha256
```

**Checkpoint:** the archive's filename ends with **`OK`**. If you see `FAILED`,
stop and obtain matching files again from the trusted channel. Do not extract
or install a failed download.

Extract into a permanent version folder in your Ubuntu home directory:

```bash
tar -xzf follow-stack-0.3.1-ubuntu24.04-arm64-cp312.tar.gz -C ~
cd ~/follow-stack-0.3.1-ubuntu24.04-arm64-cp312
```

No output from `tar` or `cd` is normal. Keep this extracted folder at this path;
Gateway's installed service uses it. Do not rename, move or delete it later.

<a id="install"></a>

## 4. Start the wizard and complete the first reboot

**Window A — Ubuntu, in the extracted folder:**

```bash
./follow-stack setup
```

Do not add `sudo` or run `install.sh` for this combined kit. The wizard asks for
privileges only when needed. The numbered English prompts are explained here
and in the Chinese guide; the program itself still displays English.

At **`1/5 Docker and startup permissions`**:

| Prompt | Answer for a new dedicated VM |
| --- | --- |
| `Install Docker from its official Ubuntu repository using sudo? [y/N]:` | Type `y`, press Enter, and wait for installation to finish. |
| `Finish local Docker startup permissions using sudo? [y/N]:` | Type `y` if shown; this completes an interrupted permissions step. |
| `Enable services after logout and reboot using sudo? [y/N]:` | Type `y` to allow services to remain available after you disconnect. |

After first Docker installation or a permissions change, the wizard may say
**`Docker installed. Reboot ... reconnect and rerun './follow-stack setup'.`**
This is an intentional pause, not an installation failure. Wait for the Ubuntu
command prompt to return.

**On a new dedicated VM**, reboot Ubuntu in Window A:

```bash
sudo reboot
```

This restarts the cloud computer, not your laptop. `Connection ... closed` is
expected. On a shared VM, arrange a maintenance window before this command.
Wait about a minute, then reconnect from your laptop (retry if still booting):

```bash
cd ~/Downloads
ssh -i ./auto-quant.key ubuntu@YOUR_OCI_PUBLIC_IP
```

**Once the Ubuntu prompt returns**, resume from the same folder:

```bash
cd ~/follow-stack-0.3.1-ubuntu24.04-arm64-cp312
./follow-stack setup
```

Saved steps are reused; do not copy or extract the package again.
At **`2/5 Verified executor image and stopped service`**, let the wizard finish.
You do not need to build anything or sign in to a container registry.

<a id="follower"></a>

## 5. Enter your paper-account settings

**Window A — answer the wizard; do not paste shell commands at these prompts.**
At **`3/5 Account and personal relay access`**:

| Prompt | Answer |
| --- | --- |
| Account mode `[paper]` | Press Enter for paper trading. |
| IBKR account ID | Your paper account ID, not the username. |
| Sizing `[balance]` | Press Enter for balance sizing: NQ plus an MNQ remainder, sized from your account balance at each new entry. Type `MNQ` or `NQ` instead for a fixed number of one contract. |
| Leverage fraction of the leader's 6x band | Type your chosen number above 0 and at most 1, for example `0.5`. `1` follows the leader's full size; `0.5` is half. |
| Your current IBKR NetLiquidation in USD, for a size preview `(Enter to skip)` | Optional: your paper account's approximate balance, to preview sizes. Nothing is saved. |
| Approximate current NQ price, for the preview `(Enter to skip)` | Optional: for example `21000`. |
| Number of contracts (1–10) `[1]` | Asked only for a fixed `MNQ`/`NQ` size. |
| Personal relay token `(hidden)` | Paste the private token from Auto Quant and press Enter. Nothing may appear while typing. |

With balance sizing the preview shows the split at example weights, for
example `1 NQ + 7 MNQ` at weight 1, the largest size, and `4 MNQ` at weight 0.25.
Each signal carries its trade's weight. A weight marked `no entry` rounds to
0 contracts at that balance, and trades with it are skipped; the readiness
check later shows it again from your real IBKR balance. MNQ and NQ are
different futures contracts; one NQ equals ten MNQ. If uncertain, pause and
confirm your choice with Auto Quant. This walkthrough uses **paper, balance
sizing at 0.5**. Existing saved settings are reused; review what the wizard
actually reports. It has not started trading.

<a id="gateway"></a>

## 6. Complete Gateway login and readiness

At **`4/5 Gateway login`**, enter these answers privately in Window A:

| Prompt | Answer |
| --- | --- |
| Schedule timezone | Enter for `America/New_York` (US Eastern, including daylight saving). |
| Daily automatic restart | Enter for `23:45` Eastern, normally 8:45 PM US Pacific. |
| Sunday mobile approval time | Enter for `12:00` Eastern, normally 9:00 AM US Pacific. Be available if your login needs approval. |
| Recovery desktop password | Choose **exactly 8 English letters and/or digits**, with no spaces. Use a separate password, not your IBKR password. |
| Confirm recovery desktop password | Enter the same 8-character password again. Both entries are hidden. |
| IBKR login username `(hidden)` | Your paper-trading login username. |
| IBKR password `(hidden)` | The password for that username. |

These defaults must suit your trading hours. If they do not, arrange different
restart times before starting trading. Credentials and the recovery password
remain on your VM; do not send them to support or an AI.

The wizard downloads and starts Gateway. Approve an expected new IBKR Mobile
request promptly. **A paper login may not send one.** If none arrives, allow
login time, then press Enter at:

```text
After login, press Enter to check readiness, or type later to pause:
```

To inspect a login notice, use the recovery desktop below. To leave, type `later`
then Enter. Configuration is saved, Gateway remains available, and trading stays
stopped. Resume with `./follow-stack setup` from the same Ubuntu folder.

At **`5/5 Relay, account, journal and margin checks`**, the wizard also verifies
quotes. **Checkpoint:** it prints **`Setup checks passed, including a live quote
for the selected contract.`** Here “live quote” means current market data;
it does **not** mean the account has switched to live trading.

Compare `leader_key_id` with the expected fingerprint from Auto Quant. Verify
paper mode, your account and size: with balance sizing, the `sizing` section's
NetLiquidation, leverage fraction and the NQ/MNQ split at example weights. If checks fail, use
[help](#help); do not start trading to work around a failed check.

<a id="gateway-api"></a>

### Recovery desktop — only when a login screen needs attention

The wizard configures Gateway's API settings automatically. You normally do not
need a desktop or manual API changes. To inspect an unfinished login:

1. At Window A's login question, type `later` and press Enter to return to the
   Ubuntu prompt. Leave Gateway available.
2. Install a VNC viewer such as [TigerVNC](https://tigervnc.org/) on your **laptop**
   if you do not have one. It shows Gateway's remote screen.
3. In **Window B — Laptop**, from Downloads, replace the IP and run:

   ```bash
   ssh -i ./auto-quant.key -o ExitOnForwardFailure=yes -N -L 127.0.0.1:5901:127.0.0.1:5901 ubuntu@YOUR_OCI_PUBLIC_IP
   ```

4. A blank window without a new prompt is expected; keep it open. In TigerVNC,
   connect to **`localhost::5901`** (two colons). Other viewers: host `localhost`,
   port `5901`. Enter the separate recovery password.
   On macOS you can also open Finder, press **Command+K**, and connect to
   **`vnc://127.0.0.1:5901`**. Run the SSH command on your Mac, not inside Ubuntu
   or OCI Cloud Shell. A Screen Sharing/Remote Management error does not mean
   you should enable Sharing on your Mac: first check that Window B is still
   connected without an SSH error and that `./follow-stack gateway status` in
   Window A reports the Gateway running with the recovery desktop enabled.
5. Inspect the paper login and complete IBKR notices yourself. If support asks
   you to inspect API settings, use **Configure → Settings**, then **API → Settings**
   as illustrated. Do not change mode, ports or settings just to match a screenshot.
6. Back in Window A, run `./follow-stack setup` and complete readiness. Close the
   viewer when finished; Ctrl+C in Window B closes only this recovery connection.

![Gateway Configure menu; Settings opens the configuration window](images/ib-gateway-configure-menu.png)

![Gateway API settings location, for inspection when support requests it](images/ib-gateway-api-settings.png)

The desktop uses your SSH connection. Do not open public ports 5901, 4001 or 4002
in Oracle or Ubuntu firewalls.

<a id="discord"></a>

## 7. Optional: connect private Discord messages

Skip this step if you do not want notifications. Linking lets Auto Quant's
notification service deliver trade details and service status to your Discord
account. It does not start trading. Do this while the executor is stopped.

**Window A — Ubuntu, after the wizard returns to the command prompt:**

```bash
./follow-stack discord link
```

Read and answer the consent prompt. A short-lived code appears in your **own
terminal**. In Discord, join the supplied Auto Quant server, open **#bot-setup**,
select **AQ Bot's `/link` command**, and enter your code in its **code** field.
Submit within ten minutes. Do not post it as an ordinary channel message, and
never post your relay token there.

![Auto Quant #bot-setup: AQ Bot /link command and its code field](images/discord-bot-setup-link.png)

The screenshot's code is an example; use the fresh code from your terminal.
You do not need “Edit Channel” or your own Discord bot. Wait for the private
“Account linked” reply and a test direct message (DM). Then, in Window A:

```bash
./follow-stack discord status
./follow-stack discord enable
```

If no DM arrives, allow direct messages for this server and check message requests.
If `/link` says “The application did not respond,” contact Auto Quant; do not
reinstall. [More notification help](DISCORD.md).

<a id="paper"></a>

## 8. Decide whether to start paper trading

Installation and broker login alone do not start the executor. You may stop here
with the installation ready and trading stopped.

When you choose to start, first run in **Window A — Ubuntu**:

```bash
./follow-stack check
```

Require successful readiness, including quotes, the expected provider fingerprint
and **your intended paper mode and size**. Investigate any listed
problem. Readiness can request margin estimates; it does not place executable orders.

Read [how the executor protects positions](EXECUTOR.md) before starting. This
version starts emergency closing if a matching stop is still missing 30 seconds
after an observed entry fill, or 60 seconds after unexpected loss of an existing
stop. Verified planned exits have their own fixed deadline. It also cleans up
its leftover stops after confirming the position is flat. These checks require
the executor to be running; broker/network delays can delay actual closing.

Starting can **immediately submit paper orders** and enables executor startup
after a VM reboot. If that is what you intend:

```bash
./follow-stack start
```

Read the settings shown. For **paper, balance sizing at 0.5**, the confirmation
is `START PAPER BALANCE 0.5` (a fixed size reads like `START PAPER 1 MNQ`).
Type it only if it matches your intended setup. If the prompt
shows `LIVE` or a different size, do not confirm; ask for help with the settings.
The confirmation uses the actual saved configuration, not this guide's example.

After a successful start:

```bash
./follow-stack service-status
./follow-stack status
```

A running service may be waiting for the next eligible signal. Do not submit
manual test orders just to make it show a trade.

<a id="daily"></a>

## 9. Daily use and coming back later

Each new SSH session starts outside the release folder. Connect as in step 2,
then run:

```bash
cd ~/follow-stack-0.3.1-ubuntu24.04-arm64-cp312
```

| What you want | Command / action |
| --- | --- |
| Resume unfinished setup, with trading stopped | `./follow-stack setup` |
| Inspect Gateway login/API health | `./follow-stack gateway status` |
| Inspect executor service | `./follow-stack service-status` |
| Inspect trading state | `./follow-stack status` |
| Check full readiness while stopped | `./follow-stack check` |
| Watch executor logs | `./follow-stack logs`; Ctrl+C exits the viewer without stopping trading. |
| Stop following and disable executor startup after reboot | `./follow-stack stop` |

**Stop does not close positions or cancel orders.** Inspect IBKR's positions and
orders and follow the agreed exit procedure; “stopped” does not mean “flat.”
Closing SSH or your laptop also does not stop trading. Do not rerun setup against
an actively trading installation.

The daily restart is automatic. At Sunday's scheduled restart, approve the
expected Mobile request if your login requires one. An unanswered request gets
one fresh automatic login after about five minutes plus a 60-second restart
delay; notification delivery can take longer. Approve only the newest request.
After another timeout, user attention is needed. Follow the
[login recovery instructions](CONTAINER_SETUP.md), not repeated reinstalls.

<a id="update"></a>

## 10. Updating or migrating an existing installation

Contact Auto Quant before your first update. Keep the old release directory,
configuration, Gateway data and trading journal. Do not delete state to “start
fresh.” Native installations need a reviewed migration; this fresh-install guide
is not a migration procedure.

**Updating from 0.1.12, 0.2.0 or 0.3.0 to 0.3.1?** Follow the [upgrade guide](UPGRADE.md).
It keeps your journal and token, installs the new kit and regenerates the
services; from 0.1.12 or 0.2.0 you then choose your leverage fraction.

For compatible container releases, use the stopped-and-flat procedure in the
[container maintenance reference](CONTAINER_SETUP.md). An upgrade does not itself
authorize starting trading. Keep private backups out of chat and Discord.

<a id="help"></a>

## 11. Common problems

| What you see | What to do |
| --- | --- |
| Windows does not recognize `ssh` | Use [Microsoft's OpenSSH Client instructions](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse). Install the **client**, not the server, on your laptop; reopen PowerShell. |
| SSH timeout or `Permission denied (publickey)` | Check IP, username `ubuntu`, key filename and Oracle access rules using [OCI help](OCI_ARM.md). Do not share the key's contents. |
| `No such file or directory` | Check which window, folder and exact filename you are using. Downloads sometimes have `(1)` appended; use matching original filenames. |
| `./follow-stack` not found | In Window A, `cd` into the extracted version folder first. |
| Checksum `FAILED` | Stop; obtain matching archive/checksum files again from the trusted channel. |
| No characters when typing a password/token | Normal hidden input. Enter once and press Enter. |
| Recovery password length/character or confirmation error | Choose exactly 8 English letters/digits, no spaces, and enter twice identically. Setup asks again (the Gateway schedule questions repeat; press Enter to keep the defaults); Ctrl+C pauses. Older releases exit with `Use matching recovery passwords of exactly 8 printable ASCII characters`: rerun setup, which reuses saved account settings. |
| `Run './follow-stack setup' first` / `Setup is incomplete` | Account settings may already be saved while Gateway setup is unfinished. Run `./follow-stack doctor`, then rerun `./follow-stack setup` from the same folder and Ubuntu login. Complete step 4/5 and wait for step 5/5 to pass; do not delete saved configuration. |
| VNC connection fails / `Address already in use` | Keep the tunnel running in a separate laptop terminal. An occupied local port may belong to an existing tunnel; do not start another or kill an unknown process. Check the existing tunnel and Gateway status. Do not open VNC to the public internet. |
| Docker permissions / reboot instruction | Reboot as instructed, reconnect and rerun setup from the same folder. Do not add `sudo` to `follow-stack`. |
| No IBKR Mobile request | Paper login may not require one. Try readiness; inspect the recovery desktop if login is incomplete. |
| `10197` / another session using market data | Release that session's market-data use yourself when appropriate, then retry. Review a live session's use before disconnecting it. |
| `354` / market-data status `denied`, even though login and margin pass | IBKR reports that the requested market data is not subscribed. In Client Portal, open **Settings → Trading Platform → Market Data Subscriptions** and verify live data/API coverage for the selected contract and Gateway login username. Review any fees before subscribing. Trading permissions and margin approval are separate. Retry `./follow-stack check`; trading remains blocked until live quotes pass. |
| Quote timeout | No usable quote arrived. Check market hours, data access and login, then retry when available. A timeout does not prove the market is closed. |
| Existing installation, account mismatch, positions/orders or journal halt | Stop setup and contact support. Do not delete configuration/history or run `resume` to bypass the check. |

For support, share the **step, release version and redacted error text**. Remove
usernames, account IDs, tokens, passwords and authentication/linking codes.
Do not upload configuration folders, raw logs, trading journals or VM backups.

## Source code and license

The customer executor is GPL-3.0-or-later. Matching application source is included
in the kit; dependency source is available on the same release page. You do not
need to read or compile it to install. See [source and licensing](SOURCE.md).
