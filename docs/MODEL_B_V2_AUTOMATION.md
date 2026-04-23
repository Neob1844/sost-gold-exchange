# Model B v2 Automation

## Overview

Model B v2 introduces automated daemons that handle position lifecycle
transitions without manual operator intervention. These daemons run on
periodic ticks and process positions through the full lifecycle:

```
ACTIVE -> NEARING_MATURITY -> MATURED -> WITHDRAWN -> REWARD_SETTLED -> CLOSED
```

## Daemons

### Maturity Watcher (`src/services/maturity_watcher.py`)

Monitors all positions and transitions them based on time:

- **ACTIVE -> NEARING_MATURITY**: When less than 7 days remain before expiry
- **NEARING_MATURITY -> MATURED**: When expiry_time has passed
- **ACTIVE -> MATURED**: If the position jumps past the nearing threshold

Runs every 60 seconds. Logs all transitions to the audit log.

### Auto-Withdraw Daemon (`src/services/auto_withdraw_daemon.py`)

Executes ETH escrow withdrawals for matured positions:

- Checks for positions where `lifecycle_status == MATURED`, `auto_withdraw == True`, and `withdraw_tx is None`
- Generates the `cast send` command to call `withdraw(uint256)` on the escrow
- In alpha mode: logs the command and simulates a tx hash
- In live mode: would execute the withdrawal via RPC

Transitions: **MATURED -> WITHDRAW_PENDING -> WITHDRAWN**

### Reward Settlement Daemon (`src/services/reward_settlement_daemon.py`)

Credits SOST rewards to the reward_owner at maturity:

- Checks for positions where `lifecycle_status in (MATURED, WITHDRAWN)` and `reward_settled == False`
- Credits the full remaining reward to the `reward_owner` (falls back to `principal_owner` then `owner`)
- Sets `reward_settled = True`

Transitions: **MATURED|WITHDRAWN -> REWARD_SETTLED**

### Beneficiary Sync (`src/services/beneficiary_sync.py`)

Syncs on-chain ETH beneficiary after SOST-side position trades:

- When `principal_owner` changes in a trade, the escrow's `currentBeneficiary` must be updated
- Generates `cast send` for `updateBeneficiary(uint256, address)`
- Tracks sync status via position history events

## Integration with Watcher Service

All daemons follow the same pattern as existing services: periodic `tick()`,
audit logging, and registry persistence. They can be integrated into the
`WatcherService` as additional threads.

## Reconciliation Scripts

Three scripts verify consistency between the SOST registry and on-chain state:

| Script | Purpose |
|--------|---------|
| `scripts/reconcile_beneficiaries.py` | Compare registry eth_beneficiary vs on-chain currentBeneficiary |
| `scripts/reconcile_withdraw_status.py` | Compare registry lifecycle_status vs on-chain withdrawn flag |
| `scripts/reconcile_reward_status.py` | Find matured positions with unsettled rewards |

## Demo Scripts

| Script | What it demonstrates |
|--------|---------------------|
| `scripts/demo_model_b_v2_full_sale.py` | Full position sale + beneficiary sync + lifecycle |
| `scripts/demo_model_b_v2_reward_sale.py` | Reward-only sale (principal stays) |
| `scripts/demo_model_b_v2_maturity_withdraw.py` | Complete ACTIVE->CLOSED lifecycle |

## Configuration

Daemons use the same `configs/live_alpha.local.json` as the watcher service.
Key fields:

```json
{
  "ethereum": {
    "escrow_address": "0x...",
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com"
  }
}
```

## Position Schema Fields (v2)

| Field | Type | Description |
|-------|------|-------------|
| `principal_owner` | str | SOST address that owns the principal (gold) |
| `reward_owner` | str | SOST address that receives rewards |
| `eth_beneficiary` | str | ETH address for escrow withdrawal |
| `auto_withdraw` | bool | Whether to auto-withdraw at maturity |
| `withdraw_tx` | str | ETH tx hash of the withdrawal |
| `reward_settled` | bool | Whether rewards have been credited |
| `lifecycle_status` | str | Current lifecycle stage |
