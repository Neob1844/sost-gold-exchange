# Beneficiary Sync Model

## Problem

When a gold-backed position is traded on the SOST side, the on-chain ETH
escrow still points to the original depositor as the beneficiary. If the
position is sold to a new principal_owner, the escrow must be updated so
the new owner can withdraw the gold at maturity.

## Architecture

```
SOST Registry                    ETH Escrow (EscrowV2)
┌────────────────────┐           ┌────────────────────┐
│ position_id: abc   │           │ deposit_id: 42     │
│ principal_owner:   │           │ beneficiary:       │
│   sost1bob...      │  sync ->  │   0xBob...         │
│ eth_beneficiary:   │           │                    │
│   0xBob...         │           │                    │
└────────────────────┘           └────────────────────┘
```

## Sync Flow

1. A position trade occurs on SOST (full sale or principal-only sale)
2. The registry updates `principal_owner` and `eth_beneficiary`
3. The `BeneficiarySync` service detects the change
4. It generates a `cast send` command:
   ```
   cast send <escrow> "updateBeneficiary(uint256,address)" <deposit_id> <new_beneficiary> --rpc-url <rpc>
   ```
5. In alpha mode: the command is logged for manual execution
6. In live mode: the command would be executed via RPC
7. The sync is recorded in the position's history and audit log

## Detection

The sync service checks for positions where:
- `eth_escrow_deposit_id` is set (Model B positions)
- `eth_beneficiary` is set
- No `beneficiary_synced` event exists in the position history for the current
  `eth_beneficiary` value

## Reconciliation

The `scripts/reconcile_beneficiaries.py` script provides an independent check:
- For each position with an ETH deposit, it queries the on-chain
  `currentBeneficiary` and compares with the registry
- Reports mismatches that need manual attention
- Can be run as a periodic health check

## When Sync is NOT Needed

- **Reward-only sales**: Only `reward_owner` changes; `principal_owner` and
  `eth_beneficiary` remain the same
- **Model A positions**: No ETH escrow involvement (self-custody gold)
- **Initial creation**: The depositor is already the beneficiary

## Alpha Mode Behavior

In the current alpha phase:
- The sync service generates the `cast send` command but does not execute it
- The operator must review and execute the command manually
- This provides a human-in-the-loop safety check before modifying on-chain state
- The simulated tx hash is recorded for tracking purposes

## Security Considerations

- Only the escrow operator can call `updateBeneficiary`
- The SOST registry is the source of truth for ownership
- On-chain beneficiary should always match registry's `eth_beneficiary`
- The reconciliation script should be run before any withdrawal to catch drift
- In live mode, the sync should happen atomically with the trade settlement
