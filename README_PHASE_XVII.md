# Phase XVII — V2 Full Sale with Autonomous Beneficiary Handoff

## What was proved

Phase XVII demonstrates that the SOST Gold Exchange can execute a
full position sale where the buyer receives both the SOST-side ownership
and the on-chain ETH beneficiary rights — without any cooperation from
the seller after settlement.

Key proofs:

1. **Full sale transfers all ownership.** When a full position sale settles,
   `principal_owner`, `reward_owner`, and `eth_beneficiary` all transfer to the
   buyer in a single atomic operation.

2. **Beneficiary sync is autonomous.** The settlement operator calls
   `updateBeneficiary(depositId, buyerEthAddress)` on EscrowV2 immediately
   after settlement. The seller has no role in this update.

3. **Reward-only sales are isolated.** When only reward rights are sold,
   `principal_owner` and `eth_beneficiary` remain unchanged. The control
   case proves that beneficiary changes only occur on full position sales.

4. **Auto-withdraw pays the correct beneficiary.** After a full sale and
   beneficiary sync, the `AutoWithdrawDaemon` triggers
   `EscrowV2.withdraw(depositId)` at maturity. The contract sends the gold
   tokens to `currentBeneficiary` — the buyer, not the original depositor.

5. **Reward settlement pays the correct owner.** The `RewardSettlementDaemon`
   credits SOST rewards to `reward_owner` at maturity, which after a full
   sale is the buyer.

6. **Full lifecycle completes cleanly.**
   `ACTIVE -> MATURED -> WITHDRAWN -> REWARD_SETTLED -> CLOSED` with every
   transition logged in the audit trail.

## Sepolia V2 contract addresses

| Contract | Address |
|----------|---------|
| Mock XAUT | `0x38Ca34c6B7b3772B44212d6c2597Fd91a6f944D0` |
| Mock PAXG | `0x754A7D020D559EDD60848450c563303262cAdec7` |
| EscrowV2 | TBD (deploy pending) |

## How to run demos

```bash
cd ~/SOST/sost-gold-exchange-private

# Full sale + beneficiary handoff (8-step demo)
python3 scripts/demo_v2_full_sale_handoff.py

# Reward-only sale control case (6-step demo)
python3 scripts/demo_v2_reward_sale_control.py

# Maturity + auto-withdraw lifecycle (6-step demo)
python3 scripts/demo_v2_maturity_autowithdraw.py
```

Each demo runs in mock mode by default with ANSI colored output.
No network access or running node required.

## How to reconcile

```bash
# Full V2 reconciliation — shows ownership, lifecycle, sync, withdraw, reward
python3 scripts/reconcile_v2_live_case.py --file data/positions.json

# Focused beneficiary reconciliation — SYNCED / PENDING_SYNC / MISMATCH
python3 scripts/reconcile_beneficiary_live.py --file data/positions.json

# Existing reconciliation tools (still valid)
python3 scripts/reconcile_beneficiaries.py --dry-run
python3 scripts/reconcile_withdraw_status.py
python3 scripts/reconcile_reward_status.py
```

## Go/No-Go status

See `docs/PHASE_XVII_GO_NO_GO.md` for the binary decision checklist.

All GO criteria must be checked before proceeding to mainnet deployment.

## What follows for mainnet

1. **Deploy EscrowV2 to mainnet** with `updateBeneficiary` restricted to
   the settlement operator address.

2. **Migrate from mock tokens to real XAUT/PAXG** — update contract
   addresses in `configs/live_alpha.local.json`.

3. **Enable live beneficiary sync** — switch `BeneficiarySync` from
   cast-command logging to actual RPC execution with the operator key.

4. **Enable live auto-withdraw** — switch `AutoWithdrawDaemon` from
   simulated tx hashes to actual on-chain withdrawals.

5. **Rate-limit and queue concurrent sales** — add a position-level lock
   to prevent race conditions between simultaneous offers on the same
   position.

6. **Monitoring and alerting** — wire reconciliation scripts into the
   operator dashboard with alerts on PENDING_SYNC and MISMATCH states.

7. **Audit log persistence** — move from local JSONL to append-only
   storage with replication.
