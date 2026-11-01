# Upgrade from 0.1.12 or 0.2.0 to 0.3.0

English | [简体中文](UPGRADE.zh-CN.md)

Version 0.3.0 adds **balance sizing**: you choose a leverage fraction `f` above 0
and at most 1 of the leader's 6x balance sizing, and each new entry trades NQ plus
an MNQ remainder sized from your IBKR NetLiquidation and the `sizing.weight`
each signal carries for its trade (above 0, at most 1). See
[how sizing works](EXECUTOR.md#sizing) and the [release notes](RELEASE_NOTES.md).

This guide is for the combined `follow-stack-…` container kit. Native
`follow-executor-…` installations need a reviewed migration; contact Auto Quant.

**You do not have to update immediately.** 0.2.0 keeps trading its fixed
quantity: the leader still sends `next_rth_open` exit plans (a stop cancel and
an exit shortly before the regular open), so 0.2.0's pre-open protection stays valid, and 0.2.0
ignores the new `sizing` field. It never uses signal weights or your balance.

## Starting from 0.1.12

The reviewed 0.1.12 Gateway change consists only of three setup messages about
separate Gateway and phone usernames. The updater accepts the exact published
old/new Gateway bytecode pair; journal and Docker Gateway code must still match.
Unknown changes remain blocked. Existing account mode, fixed size, credentials
and journal are preserved. Use the same steps below, substituting your retained
`~/follow-stack-0.1.12-ubuntu24.04-arm64-cp312` directory for every 0.2.0 path.
Do not stop until the whole account is flat with no working orders. Gateway must
be authenticated for the read-only maintenance check. An upgrade never starts
trading, changes account mode or selects balance sizing for you.

This path requires a kit built with this compatibility fix; the original
published v0.3.0 kit does not contain it. Do not edit its hashes to bypass checks.

## What is kept

The upgrade keeps your configuration, relay token, Gateway login files and data
volume, trading journal, notification history and any existing halt. It makes a
private backup of the configuration and a consistent journal backup. It replaces
the executor image and regenerates both service definitions. It never closes
positions, cancels orders or starts trading.

## 1. Wait until the whole account is flat

Choose a time with **no position and no working order** in the IBKR account, for
example after the scheduled exit or at the weekend. Check in IBKR, then from the
**0.2.0 directory**:

```bash
cd ~/follow-stack-0.2.0-ubuntu24.04-arm64-cp312
./follow-stack status
```

Require `"expected_positions": {}` and `"halt": null`. Never stop during a trade:
a stopped executor cannot move stops or run timed exits. If the executor is
halted, resolve that first with [operations](OPERATIONS.md); the upgrade keeps
halts.

## 2. Stop the executor while flat

Still in the 0.2.0 directory:

```bash
./follow-stack stop
```

Keep **Gateway logged in**; the upgrade's read-only flat-account check uses it.
Do not delete or move `~/.config/follow-executor` or
`~/.local/state/follow-executor`. Keep the 0.2.0 directory in place: the upgrade
and any rollback read it.

## 3. Copy, verify and extract the new kit

Transfer `follow-stack-0.3.0-ubuntu24.04-arm64-cp312.tar.gz` and its `.sha256`
to Ubuntu as in [setup step 3](SETUP.md#3-copy-and-verify-the-download), then:

```bash
cd ~/Downloads
sha256sum -c follow-stack-0.3.0-ubuntu24.04-arm64-cp312.tar.gz.sha256
tar -xzf follow-stack-0.3.0-ubuntu24.04-arm64-cp312.tar.gz -C ~
cd ~/follow-stack-0.3.0-ubuntu24.04-arm64-cp312
```

Require `OK`. Extract into this **new** directory; never over 0.2.0.

## 4. Install the new kit and regenerate the services

From the 0.3.0 directory:

```bash
./follow-stack upgrade --from ~/follow-stack-0.2.0-ubuntu24.04-arm64-cp312
```

It verifies both kits, checks account-wide positions and orders without placing,
cancelling or simulating any order, and asks you to type the shown confirmation,
for example `UPGRADE PAPER 1 MNQ` (your current 0.2.0 size). It then backs up
privately, stops Gateway, installs the 0.3.0 executor image and rewrites the
executor and Gateway services. 0.2.0 to 0.3.0 is a reviewed migration: the
journal and Gateway code are unchanged and 0.2.0 settings load as they are.
**Both services stay stopped.**

If it reports an interrupted switch, follow
[maintenance recovery](CONTAINER_SETUP.md#upgrade-or-roll-back-while-flat).

## 5. Log Gateway back in

```bash
./follow-stack gateway start
```

Approve the IBKR Mobile prompt. Use the private VNC screen only if a login
dialog needs attention.

## 6. Choose your leverage fraction

Rerun the setup step that asks for the size:

```bash
./follow-stack settings
```

| Prompt | Answer |
| --- | --- |
| Sizing `[MNQ]` (your current root) | Type `balance`. To keep your fixed 0.2.0 size instead, press Enter at this and the next prompt; nothing changes. |
| Leverage fraction of the leader's 6x band | Your chosen number above 0 and at most 1, for example `0.5`. `1` follows the leader's full size. |
| Approximate current NQ price, for the preview `(Enter to skip)` | Optional, for example `21000`. |

It checks NQ and MNQ are flat in IBKR, shows your IBKR NetLiquidation (or asks
for an approximate balance if IBKR does not report it) and the NQ/MNQ split at example weights, then saves `"sizing": {"mode": "balance",
"leverage_fraction": f}` and replaces `instrument`. Without a terminal you can
run `./follow-stack settings --leverage-fraction 0.5`. Your trade history is kept,
so finished trades are never re-entered.

A trade needing more NQ than `risk.max_quantity` (default 10) per order, a
trade whose size rounds to 0 contracts (for example weight 0.4 with a base of
1 MNQ unit), or a balance below one MNQ unit, would be refused without an
order; the preview and the check mark weights that round to 0 as `no entry`. Decide any limit change with Auto Quant; do not raise limits to make a
check pass.

## 7. Run the readiness checks

```bash
./follow-stack check
```

Require exit status 0 and `"problems": []`, quotes included, and compare
`leader_key_id` with the fingerprint from Auto Quant. Review the `sizing`
section: `leverage_fraction`, `net_liquidation`, each example weight's `book` such as
`1 NQ + 7 MNQ`, and `margin` with `"allowed": true`. Quotes may wait for the
market to open; rerun then.

## 8. Start

```bash
./follow-stack start
```

Type the confirmation only if it matches what you chose, for example
`START PAPER BALANCE 0.5`. Starting can submit paper orders immediately. Then:

```bash
./follow-stack service-status
./follow-stack status
```

Keep the 0.2.0 directory until you no longer need a rollback.

## Roll back to 0.2.0

0.2.0 cannot read balance sizing. While stopped and flat, from the 0.3.0
directory, first return to a fixed size, then roll back:

```bash
./follow-stack stop
./follow-stack settings --root MNQ --quantity 1
./follow-stack rollback
```

Rollback repeats the flat-account check, keeps the current journal, and leaves
both services stopped. Continue from the 0.2.0 directory with `gateway start`,
`check` and an explicit `start`.
