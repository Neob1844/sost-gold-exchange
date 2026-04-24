# SOST — Controlled Safety Gates

## Definition

A "controlled gate" is an automated operation that generates, validates, and
prepares an action but requires explicit operator approval before irreversible
on-chain execution. This is a deliberate security measure during alpha, not
a technical gap.

## Gate Registry

### Gate 1: ETH Escrow Withdrawal (Model B)

| Field | Value |
|-------|-------|
| Action | Withdraw gold from SOSTEscrow at maturity |
| Why gated | Irreversible on-chain ETH transaction |
| Who approves | Protocol operator |
| What prepares it | `auto_withdraw_daemon.py` — detects MATURED positions, generates `cast send` command |
| Validations required | Position status == MATURED, auto_withdraw == True, no existing withdraw_tx |
| Evidence | Audit log event `lifecycle_withdrawn`, position history event, simulated tx hash in alpha |
| When gate can be removed | After SOSTEscrow V2 live-mode integration with operator key signing automation |

### Gate 2: ETH Beneficiary Update (Model B)

| Field | Value |
|-------|-------|
| Action | Update currentBeneficiary on SOSTEscrow after position transfer |
| Why gated | Only settlementOperator can call updateBeneficiary; cannot withdraw |
| Who approves | Protocol operator (holds settlementOperator key) |
| What prepares it | `beneficiary_sync.py` — detects pending syncs, generates `cast send` command |
| Validations required | Position has eth_beneficiary set, no "beneficiary_synced" event yet, eth_escrow_deposit_id exists |
| Evidence | Audit log event `beneficiary_synced`, position history event |
| When gate can be removed | After automated operator key signing with HSM or multisig approval |

### Gate 3: SOST/ETH Refund Processing

| Field | Value |
|-------|-------|
| Action | Return locked assets when a deal fails or expires |
| Why gated | Requires both SOST chain unlock and ETH escrow withdraw |
| Who approves | Protocol operator |
| What prepares it | `refund_engine.py` — creates RefundAction with validated deal state |
| Validations required | Deal state is EXPIRED or explicitly cancelled, no settlement in progress |
| Evidence | RefundAction logged, deal state transition recorded |
| When gate can be removed | After automated refund execution with chain confirmation + retry logic |

### Gate 4: Settlement Execution (Deal State Machine)

| Field | Value |
|-------|-------|
| Action | Confirm both chains locked, execute final settlement |
| Why gated | Cross-chain coordination (SOST + ETH) requires manual verification in alpha |
| Who approves | Protocol operator (via settlement daemon monitoring) |
| What prepares it | `settlement_daemon.py` — correlates ETH+SOST events, transitions deal state |
| Validations required | Deal in BOTH_LOCKED state, ETH tx confirmed, SOST lock confirmed |
| Evidence | Deal state SETTLED, settlement_tx recorded, audit log |
| When gate can be removed | After automated chain watchers with confirmation depth requirements |

### Gate 5: Custody Verification RPC (Model A)

| Field | Value |
|-------|-------|
| Action | Query XAUT/PAXG balance on Ethereum to verify Model A custody |
| Why gated | Alpha mode uses simulated verification (always passes) |
| Who approves | Automatic (no approval needed — just mode switch) |
| What prepares it | `custody_verifier.py` — has full live-mode implementation with ERC-20 balanceOf |
| Validations required | ETH RPC URL configured, eth_beneficiary address set on position |
| Evidence | Verification result logged to audit with epoch, expected/actual amounts |
| When gate can be removed | When alpha_mode=False and ETH RPC endpoint is configured |

## Gate Removal Roadmap

| Gate | Current | Target | Blocker |
|------|---------|--------|---------|
| ETH Withdrawal | Generates command | Auto-execute with confirmation | Operator key automation |
| Beneficiary Update | Generates command | Auto-execute via settlementOperator | HSM/multisig setup |
| Refund Processing | Creates request | Auto-execute with retry | Chain confirmation logic |
| Settlement Execution | Operator confirms | Auto-confirm after depth N | Cross-chain watcher hardening |
| Custody Verification | Alpha simulated | Live RPC queries | ETH RPC endpoint + mode switch |

## Invariants (Never Gated)

These operations are always automatic and never require operator approval:

- Position creation (Model A and Model B)
- Maturity tracking (ACTIVE → NEARING → MATURED)
- Reward settlement (MATURED/WITHDRAWN → REWARD_SETTLED)
- Position finality (REWARD_SETTLED → CLOSED + bond release)
- Epoch audit scheduling
- Auto-slash after grace period (custody verifier)
- Reward-right splits
- Full position transfers (Model B)
- Transfer blocking (Model A)
- Audit logging
- Risk-differentiated pricing
