# SOST Gold Exchange — Phase XVI: Automation Daemons

Phase XVI adds automated lifecycle management for Model B v2 positions,
including maturity detection, auto-withdrawal, reward settlement, and
beneficiary synchronization.

## What's New

### Automation Daemons

| Service | File | Purpose |
|---------|------|---------|
| Maturity Watcher | `src/services/maturity_watcher.py` | Detects ACTIVE -> NEARING_MATURITY -> MATURED transitions |
| Auto-Withdraw | `src/services/auto_withdraw_daemon.py` | Executes ETH escrow withdrawals at maturity |
| Reward Settlement | `src/services/reward_settlement_daemon.py` | Credits SOST rewards to reward_owner |
| Beneficiary Sync | `src/services/beneficiary_sync.py` | Syncs ETH beneficiary after position trades |

### Reconciliation Scripts

| Script | Purpose |
|--------|---------|
| `scripts/reconcile_beneficiaries.py` | SOST registry vs on-chain beneficiary |
| `scripts/reconcile_withdraw_status.py` | Registry lifecycle vs on-chain withdraw state |
| `scripts/reconcile_reward_status.py` | Find unsettled rewards for matured positions |

### Demo Scripts

| Script | Scenario |
|--------|----------|
| `scripts/demo_model_b_v2_full_sale.py` | Full sale + beneficiary sync + lifecycle |
| `scripts/demo_model_b_v2_reward_sale.py` | Reward-only sale (principal stays) |
| `scripts/demo_model_b_v2_maturity_withdraw.py` | Complete ACTIVE -> CLOSED lifecycle |

### Documentation

| Document | Topic |
|----------|-------|
| `docs/MODEL_B_V2_AUTOMATION.md` | Daemon architecture and configuration |
| `docs/PRINCIPAL_VS_REWARD_OWNERSHIP.md` | Split ownership model |
| `docs/BENEFICIARY_SYNC_MODEL.md` | ETH beneficiary sync design |

### Tests

| Test | Coverage |
|------|----------|
| `tests/integration/test_maturity_watcher.py` | Maturity transitions |
| `tests/integration/test_auto_withdraw.py` | Auto-withdrawal daemon |
| `tests/integration/test_reward_settlement.py` | Reward settlement |
| `tests/integration/test_beneficiary_sync.py` | Beneficiary sync |

## Position Lifecycle

```
ACTIVE
  |
  v  (< 7 days to expiry)
NEARING_MATURITY
  |
  v  (past expiry_time)
MATURED
  |
  v  (auto_withdraw daemon)
WITHDRAW_PENDING -> WITHDRAWN
  |
  v  (reward settlement daemon)
REWARD_SETTLED
  |
  v  (all obligations done)
CLOSED
```

## Split Ownership

Positions now support independent ownership of principal (gold) and
reward (SOST mining rewards):

- **Full sale**: All owners change, beneficiary sync required
- **Reward-only sale**: Only reward_owner changes, no sync needed
- **Principal-only sale**: Principal + beneficiary change, sync required

## Running

```bash
# Run demos
python3 scripts/demo_model_b_v2_full_sale.py
python3 scripts/demo_model_b_v2_reward_sale.py
python3 scripts/demo_model_b_v2_maturity_withdraw.py

# Run reconciliation
python3 scripts/reconcile_beneficiaries.py
python3 scripts/reconcile_withdraw_status.py
python3 scripts/reconcile_reward_status.py

# Run tests
python3 -m pytest tests/integration/test_maturity_watcher.py -v
python3 -m pytest tests/integration/test_auto_withdraw.py -v
python3 -m pytest tests/integration/test_reward_settlement.py -v
python3 -m pytest tests/integration/test_beneficiary_sync.py -v
```

## Alpha Mode

All daemons operate in alpha mode by default:
- ETH transactions are simulated (cast commands logged, not executed)
- Tx hashes are deterministic simulations
- Reconciliation scripts support `--dry-run` to skip on-chain queries
- Human-in-the-loop for all ETH state changes
