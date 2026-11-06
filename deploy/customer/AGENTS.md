# Auto Quant customer installation

These instructions apply to the extracted customer package, not source development.
Read `docs/AGENT_SETUP.md` (or `docs/AGENT_SETUP.zh-CN.md`) and the matching
`docs/SETUP.md` before setup. Use the customer's language and the supplied scripts.
For new customers, guide setup from scratch in Codex or Claude Code, including:

- OCI Home Region recommendation: US West (San Jose), `us-sanjose-1`.
- Oracle Mobile MFA: first check “Offline mode or use another authenticator app”,
  then scan/enroll privately. Preserve working existing MFA.
- Before any VCN creation: Billing & Cost Management → Upgrade and Manage Payment,
  add/verify payment method and upgrade Free Tier to Pay As You Go. Customer
  reviews/accepts the charges and terms; wait for Plan Type to show Pay As You Go.
- New VM: Ubuntu 24.04 ARM64, Ampere A1 Flex, 2 OCPUs / 12 GB RAM.
- Read `docs/IBKR_ACCOUNT_SETUP.md` (or its Chinese counterpart). Help with
  Settings → Open an Additional Account and User icon → Settings → User & Access
  Rights → Users → “+” Add, choosing a secondary username for the same holder.
  Use different usernames for OCI Gateway and phone trading; verify the actual
  paper login, account access and market data. Reuse verified existing accounts.
- IBKR application: select Futures and report actual experience years; select
  several years only when true. Confirm futures permission approval.
- Complete both gear-icon forms: Market Data API Acknowledgement and Market Data
  Subscriber Status. Choose Non-Professional only if eligible. Under Level 1,
  select CME Real-Time (L1), listed at $1.55/month for Non-Professional users;
  customer verifies/accepts the actual recurring fee. Verify the Gateway user's
  subscription and paper-data access before marking quote readiness complete.

For a combined kit (`RELEASE.json` contains `executor_image`), use
`docs/SETUP.md` plus `docs/CONTAINER_SETUP.md` (or their Chinese counterparts)
and `./follow-stack setup`
instead of the native installation steps. No host venv or Java installation is needed.
A native-only kit uses `docs/SETUP_NATIVE.md` or its Chinese counterpart. The
container wizard configures API settings; screenshots are for manual inspection
when needed, not a mandatory reason to change settings.

- Inspect existing installation and service state; resume from verified checkpoints.
- Run installation on Ubuntu 24.04 ARM64 with Python 3.12, not on the laptop.
- Hand private-input prompts to the customer's own terminal. Never ask for secrets
  in chat or read/display credential files. Customer handles phone/Discord consent.
- Keep a private, secret-free progress note as described in the agent guide.
- For native setup or needed manual API inspection, show both Gateway screenshots
  using a customer-visible preview or file link before the corresponding clicks.
  Follow the display guidance in `docs/AGENT_SETUP.md`.
- For Discord linking, show the bundled #bot-setup screenshot before the customer
  submits AQ Bot's `/link`. Explain that the example code is a placeholder; the
  customer enters their own code directly in Discord.
- Sizing (0.3.0): the wizard asks for a leverage fraction above 0 and at most 1
  (1 = the leader's full 6x balance sizing, trading NQ plus an MNQ remainder),
  or a fixed MNQ/NQ quantity. The customer chooses; explain it and show the
  preview and readiness-check split. Do not raise risk limits for them.
- Existing 0.1.12, 0.2.0 or 0.3.0 installations: follow `docs/UPGRADE.md` (or its Chinese
  counterpart) while stopped and flat; never reinstall over them.
- Start with paper trading. Get explicit agreement to the verified mode and size
  (`BALANCE f` with its split at example weights, or the fixed root and quantity) before the
  first trading start. Do not automate LIVE confirmations.
- Do not stop active trading, reset journals, change risk checks
  or operate provider services to complete installation.
- Report actual results and unfinished steps; do not claim unobserved trading tests.
