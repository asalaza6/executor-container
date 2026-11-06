# Start here — set up Auto Quant

English | [简体中文](START_HERE.zh-CN.md)

**Start with Codex or Claude Code.** Open the extracted package as its workspace
and paste the prompt in step 2. The assistant guides the setup from scratch.
The [beginner setup guide](docs/SETUP.md)
shows how to open a terminal on Windows/Mac, connect to Ubuntu, transfer the
kit and answer the wizard. Both Gateway and executor use containers.
The Chinese guide is [here](docs/SETUP.zh-CN.md).

**Already running 0.1.12, 0.2.0 or 0.3.0?** Do not reinstall. Follow the
[upgrade guide](docs/UPGRADE.md) while flat: it keeps your journal, token and
sizing, installs this kit and regenerates the services.
[升级指南（中文）](docs/UPGRADE.zh-CN.md).

If your archive is named `follow-executor-…` rather than `follow-stack-…`, use
[the native guide](docs/SETUP_NATIVE.md). The AI workflow below applies
to either kit; the assistant must identify the package before choosing commands.

Use Codex or Claude Code with file and terminal access to
read the installation guide and help you through setup. You do not need to read
the whole guide first. The assistant runs the technical steps it can and explains
the browser, terminal and phone actions that need you.

## 1. Get ready

Get the **installation archive and matching checksum**, your personal relay token,
the expected signal-provider public-key fingerprint, and the optional Auto Quant
Discord invitation from Auto Quant. Keep the original download files. Have your
IBKR Mobile ready. If you do not have an IBKR account or paper login yet, the
assistant starts with [account preparation](docs/IBKR_ACCOUNT_SETUP.md).

You need your own access to the AI tool; Auto Quant does not install it or include
its subscription. Sign in using that tool's normal setup. The tool must be able
to read the package and run commands on your computer or the Ubuntu VM. A chat
that only reads attachments can explain steps but cannot install on your VM.

## 2. Open the package in your AI tool

On your own computer, extract a copy of the archive to a folder for the assistant
to read. Open that folder as its project/workspace. This local copy is for reading;
installation runs on **Ubuntu 24.04 ARM64 with Python 3.12**. Keep the original
archive and checksum for verification and transfer to Ubuntu.

If the package is already extracted on your Ubuntu VM, open the AI tool there
instead. If the agent is on your own computer, it can use SSH once you have a VM
and a working SSH connection. Give it the key's **file location**, never the key's
contents. The assistant should help establish that connection before installing.

The package includes `AGENTS.md` and `CLAUDE.md` entry instructions for customer
setup. To make sure the guide is read, paste this prompt even if your tool loads
those files automatically:

> Help me set up Auto Quant from this installation package. Read
> `docs/AGENT_SETUP.md` and `docs/SETUP.md` first. Use English and assume I have no
> experience with a shell or command line. Identify the package using `RELEASE.json`: use
> `follow-stack setup` for the combined kit; `docs/SETUP_NATIVE.md` for a native kit.
> Ask what computer I use and whether I already have an
> Ubuntu VM, then check what is already complete. Carry out the technical steps
> from account preparation onward. For a new OCI account, recommend Home Region
> US West (San Jose), us-sanjose-1. At Oracle Mobile 2FA, have me first check
> “Offline mode or use another authenticator app” before scanning. Before any VCN
> creation, guide me to Billing & Cost Management → Upgrade and Manage Payment,
> add/verify a payment method, and wait for Plan Type to change from Free Tier to
> Pay As You Go. Have me review and accept the costs and terms. Create the new
> Ubuntu ARM64 instance with 2 OCPUs and 12 GB RAM. Follow
> `docs/IBKR_ACCOUNT_SETUP.md`: Open an Additional Account in Settings, then
> User icon → Settings → User & Access Rights → Users → “+” Add to create a
> secondary username for me. Reserve separate usernames for Gateway and phone
> trading. Select Futures and have me report my actual experience; several years
> must be selected only when true. Complete the gear-icon forms for Market Data
> API Acknowledgement and Market Data Subscriber Status; choose Non-Professional
> only if I qualify. Select CME Real-Time (L1), listed at $1.55/month for
> Non-Professional users, and have me confirm the current recurring fee.
> Verify the paper login, account and data access before the wizard. Reuse
> verified existing resources and accounts. Continue the technical steps
> you can and ask for missing information as it becomes necessary. Give me one
> action at a time when you need my browser, terminal or phone. Have me enter
> passwords and tokens directly into my own terminal, never this chat, and do not
> read credential files. Start with paper trading. Before starting any trading,
> show the check results and ask me to confirm the account mode and my sizing:
> the leverage fraction I chose and its NQ/MNQ split at example weights, or a fixed size. The container wizard configures Gateway API settings automatically. If manual
> inspection is needed, show the included Gateway screenshots before asking me to click. If I choose Discord notifications, show
> me the #bot-setup screenshot when linking AQ Bot. Keep a private, secret-free
> progress note so we can resume later.

If the tool cannot find the files, show it the extracted folder's location. If it
cannot access SSH or a terminal, it should say so and guide you through the
necessary commands in your own terminal. Do not give it an Auto Quant bot token;
customers do not need one.

## 3. Answer the assistant and complete the personal steps

The assistant will ask about your computer, existing VM, dedicated IBKR account
and secondary login, paper account, your **leverage fraction** (above 0, at most
1; 1 follows the leader's full 6x size) or a fixed size, and whether you want
Discord notifications. It will check
the download, install the software, and work through the existing setup prompts.

You still complete Oracle signup/verification and spending decisions, IBKR terms
and login approval, and Discord joining/linking. When a terminal step needs a
password or token, the assistant should give you the command to run yourself.
Hidden input may show no letters or dots. Reply **Done** when it finishes; do not
paste the secret or an unredacted screenshot into chat.

The normal Sunday approval time is **12:00 noon US Eastern** (`America/New_York`,
EST in winter and EDT in summer). Tell the assistant if you want a different
time. It should preserve an existing setup's saved schedule.

Before trading begins, the assistant should explain what passed and anything
still waiting for you. **Installing software and logging into Gateway do not
start trading.** Starting Auto Quant can submit paper orders immediately and
enables startup after a VM reboot; you make that decision separately.

## If you pause or encounter a problem

The assistant should keep a private progress note on the Ubuntu VM at
`~/.local/state/auto-quant-onboarding/progress.md`, without passwords, tokens,
account IDs or linking codes. It should tell you if it cannot save that note.
For a new session, open the same package folder and paste:

> Resume my Auto Quant setup using `docs/AGENT_SETUP.md` and the private progress
> note. Recheck the current service state before changing anything. Tell me the
> next unfinished step; do not reinstall completed parts or start trading without
> my confirmation.

An assistant can still encounter an unsupported login screen or a cloud capacity
problem. It should explain the exact unfinished step. Keep a problem's step
number and redacted error text for Auto Quant support.

If you prefer to set up manually, use the [full setup guide](docs/SETUP.md).
The [agent guide](docs/AGENT_SETUP.md) contains the detailed checkpoints. No access
to Auto Quant's source repository is needed.
