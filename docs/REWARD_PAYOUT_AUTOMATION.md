# SOST — Reward Payout Automation

## Before
The reward settlement daemon calculated fees and marked positions as
REWARD_SETTLED in the internal database, but did NOT execute actual
SOST transfers on-chain. The operator had to manually send the rewards.

## After
The `sost_reward_payout.py` engine handles the complete payout lifecycle:

```
PENDING → READY → BROADCASTING → BROADCASTED → CONFIRMED → SETTLED
                                                     ↓
                                               FAILED / RETRY
```

## Modes

### Dry Run (default for alpha)
- Calculates everything
- Logs all details
- Creates simulated txids
- Does NOT broadcast to chain
- Safe for testing

### Live
- Checks pool balance
- Broadcasts reward tx to reward_owner
- Broadcasts fee tx to protocol address
- Waits for confirmations (configurable, default 6)
- Records real txids
- Reconciles if errors occur

## Security

| Protection | How |
|------------|-----|
| No double pay | Payout record per position_id, idempotent create |
| Lock per position | Concurrent execution blocked |
| Balance check | Verifies pool has enough before broadcast |
| Confirmation wait | Not settled until N confirmations |
| Retry-safe | Only retries if no txid recorded |
| Reconciliation | Detects stuck/failed/unconfirmed payouts |
| Audit trail | Every step logged with txid, amounts, timestamps |

## Protocol Fees

| Model | Fee Rate | Example (1000 SOST reward) |
|-------|----------|---------------------------|
| A | 3% | User: 970, Protocol: 30 |
| B | 8% | User: 920, Protocol: 80 |

Fee address: `sost1059d1ef8639bcf47ec35e9299c17dc0452c3df33`

## Files
- `src/services/sost_reward_payout.py` — Engine (310 lines)
- `tests/unit/test_reward_payout.py` — 14 tests
- `src/services/reward_settlement_daemon.py` — Updated with fee calculation

## Tests: 308 total, 0 failures
