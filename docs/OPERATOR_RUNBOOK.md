# SOST — Operator Runbook

## Overview

This runbook covers every operator action in the SOST position/PoPC system.
Each section describes: what triggers the action, what to verify before
executing, how to execute, and what evidence to check after.

---

## 1. Model B: Execute ETH Withdrawal at Maturity

### Trigger
`auto_withdraw_daemon.py` logs: "Position X: MATURED, withdraw command ready"

### Pre-checks
- [ ] Position lifecycle_status == MATURED or WITHDRAW_PENDING
- [ ] Position auto_withdraw == True
- [ ] Position eth_escrow_deposit_id is set
- [ ] No existing withdraw_tx (not already withdrawn)
- [ ] SOSTEscrow contract on correct network (Sepolia in alpha)

### Execute
```bash
# The daemon generates this command:
cast send <ESCROW_ADDRESS> "withdraw(uint256)" <DEPOSIT_ID> --private-key <OPERATOR_KEY> --rpc-url <ETH_RPC>
```

### Post-checks
- [ ] Transaction confirmed on Ethereum
- [ ] Position withdraw_tx updated with real tx hash
- [ ] Position lifecycle_status == WITHDRAWN
- [ ] Audit log has "lifecycle_withdrawn" event
- [ ] Gold tokens returned to currentBeneficiary address

---

## 2. Model B: Sync Beneficiary After Transfer

### Trigger
`beneficiary_sync.py` logs: "Pending sync for position X"

### Pre-checks
- [ ] Position has been transferred (new principal_owner)
- [ ] eth_beneficiary is set to new owner's ETH address
- [ ] No "beneficiary_synced" event in position history
- [ ] Position eth_escrow_deposit_id exists

### Execute
```bash
# The sync daemon generates this command:
cast send <ESCROW_ADDRESS> "updateBeneficiary(uint256,address)" <DEPOSIT_ID> <NEW_BENEFICIARY> --private-key <SETTLEMENT_OPERATOR_KEY> --rpc-url <ETH_RPC>
```

### Post-checks
- [ ] Transaction confirmed on Ethereum
- [ ] SOSTEscrow.currentBeneficiary(depositId) == new address
- [ ] Position history has "beneficiary_synced" event
- [ ] Audit log records the sync

---

## 3. Process Refund (Failed/Expired Deal)

### Trigger
`refund_engine.py` creates a RefundAction for expired/cancelled deal

### Pre-checks
- [ ] Deal state is EXPIRED or explicitly cancelled
- [ ] No settlement in progress (not BOTH_LOCKED → SETTLING)
- [ ] Identify which assets need returning:
  - ETH side: gold tokens in escrow → withdraw back to original depositor
  - SOST side: locked SOST → unlock back to maker/taker

### Execute ETH refund
```bash
# If gold was deposited in escrow:
cast send <ESCROW_ADDRESS> "withdraw(uint256)" <DEPOSIT_ID> --private-key <OPERATOR_KEY> --rpc-url <ETH_RPC>
```

### Execute SOST refund
```bash
# SOST-side unlock (if applicable):
sost-cli unlock-bond <BOND_TX_ID>
```

### Post-checks
- [ ] Deal state == REFUNDED
- [ ] Assets returned to correct parties
- [ ] Audit log records refund event
- [ ] No double-refund possible (deal in terminal state)

---

## 4. Settlement Confirmation

### Trigger
`settlement_daemon.py` detects BOTH_LOCKED state

### Pre-checks
- [ ] ETH lock confirmed (tx hash verified, sufficient confirmations)
- [ ] SOST lock confirmed (txid in mempool/confirmed)
- [ ] Deal parties match position participants
- [ ] Amounts match agreed terms

### Execute
```bash
# Trigger settlement in the daemon:
python3 -c "from src.settlement.settlement_daemon import SettlementDaemon; ..."
# Or via operator dashboard API
```

### Post-checks
- [ ] Deal state == SETTLED
- [ ] Position ownership updated
- [ ] Beneficiary sync queued (if full sale)
- [ ] Audit trail complete

---

## 5. Model A: Switch Custody Verifier to Live Mode

### Trigger
Operator decision to enable real ETH RPC verification

### Pre-checks
- [ ] ETH RPC endpoint available and tested
- [ ] All Model A positions have eth_beneficiary set (user's custody address)
- [ ] Grace period understood (7 days before auto-slash)

### Execute
```python
# In custody_verifier initialization:
verifier = CustodyVerifier(registry, audit, alpha_mode=False, eth_rpc_url="https://...")
```

### Post-checks
- [ ] Verification results show real balance queries
- [ ] No false positives (legitimate positions passing)
- [ ] Grace period tracking working for failures
- [ ] Audit log records all verification attempts

---

## 6. Daily Operations Checklist

### Every tick cycle (~60s)
Automated — no operator action needed:
- [ ] maturity_watcher checks maturities
- [ ] reward_settlement_daemon settles rewards
- [ ] position_finality_daemon closes completed positions

### Every epoch (~7 days)
Automated in alpha mode — verify results:
- [ ] epoch_audit_daemon runs custody verification
- [ ] Check epoch summary in audit log
- [ ] Review any failed verifications

### As needed
Operator-initiated:
- [ ] Execute pending ETH withdrawals
- [ ] Process pending beneficiary syncs
- [ ] Review and execute refunds
- [ ] Confirm pending settlements

---

## 7. Recovery Procedures

### Daemon crash
1. Check last_tick timestamps in daemon logs
2. Restart daemon — all operations are idempotent
3. Verify no positions stuck in intermediate state

### RPC failure
1. Check ETH RPC endpoint health
2. Retry failed operations after RPC recovery
3. No data loss — commands are regenerated from position state

### Double-execution risk
All daemons have idempotency guards:
- position_finality_daemon: `_processed` set prevents re-close
- custody_verifier: `_failed_positions` tracking prevents re-slash
- reward_settlement: `reward_settled` flag prevents re-settle
- auto_withdraw: `withdraw_tx` check prevents re-withdraw

### Identity/keystore loss (DEX browser)
1. User must have exported backup JSON
2. Import via DEX "Import Backup" flow
3. Re-unlock with original passphrase
4. If no backup exists: identity is lost (by design — no server storage)
