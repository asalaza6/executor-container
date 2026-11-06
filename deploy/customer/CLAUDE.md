# Auto Quant customer installation

Read `AGENTS.md`, then `docs/AGENT_SETUP.md` (or `docs/AGENT_SETUP.zh-CN.md`) and
the matching setup guide before doing installation work. Follow the shared customer
workflow, including private terminal input, verified checkpoints, progress notes
and explicit agreement before the first trading start. Use the customer's language.
Start with the shared account/cloud checkpoints: San Jose Home Region; Oracle
offline-authenticator checkbox before enrollment; payment method and verified
Pay As You Go before VCN; 2 OCPUs / 12 GB RAM; and the IBKR additional account
plus secondary username. Read `docs/IBKR_ACCOUNT_SETUP.md` (or its Chinese version)
before the wizard. Keep Gateway and phone trading on different usernames and
verify the actual paper login. Reuse completed resources and record pending steps.
Select Futures with truthful experience years (several years only if accurate).
Complete the gear-icon Market Data API Acknowledgement and Market Data Subscriber
Status forms; Non-Professional only if eligible. Select CME Real-Time (L1) in
Level 1, listed at $1.55/month, with the customer accepting the actual recurring
fee. Verify the Gateway user's data entitlement and paper-data access.
For native setup or needed manual API inspection, show both Gateway screenshots to
the customer before the corresponding clicks, as described in the agent guide;
use a file link if previews are unavailable.
For Discord linking, show the bundled #bot-setup screenshot before the customer
submits AQ Bot's `/link`, following the same preview/file-link guidance.
The customer chooses the sizing: a leverage fraction above 0 and at most 1 of the
leader's 6x balance sizing (NQ plus an MNQ remainder), or a fixed size. Existing
0.1.12, 0.2.0 or 0.3.0 installations upgrade with `docs/UPGRADE.md` while stopped and flat.
