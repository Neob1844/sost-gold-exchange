# Beneficiary Handoff Security Model

## Overview

SOSTEscrowV2 supports transferable beneficiary rights. When a position trades
inside SOST, the on-chain beneficiary must be updated so the new economic owner
receives the principal at maturity.

The original design required the **current beneficiary** (seller) to cooperate
by calling `updateBeneficiary()`. This blocks full automation: after a full
sale, the seller has no economic incentive to cooperate.

The settlement operator pattern solves this.

## Who Can Change Beneficiary

| Caller               | Can updateBeneficiary? | Can withdraw? |
|----------------------|------------------------|---------------|
| currentBeneficiary   | YES                    | YES           |
| settlementOperator   | YES                    | NO            |
| Any other address    | NO                     | NO            |

## Settlement Operator Properties

- **Set at construction** — `address public immutable settlementOperator`
- **Immutable** — cannot be changed after deployment
- **Cannot withdraw** — `withdraw()` still requires `msg.sender == currentBeneficiary`
- **Cannot set beneficiary to zero** — zero address check remains
- **Optional** — passing `address(0)` as operator at construction disables the
  feature entirely (V1-equivalent behavior)

## Trust Model

### What the operator CAN do

- Reassign beneficiary of any deposit to any non-zero address
- This means the operator could point a deposit's beneficiary to a wrong address

### What the operator CANNOT do

- Withdraw any funds from any deposit
- Change the operator address (it is immutable)
- Modify deposit amounts, lock times, or token types
- Create or delete deposits

### Mitigations

1. **On-chain verification**: after `updateBeneficiary()`, the settlement engine
   reads back the on-chain state to verify the beneficiary matches the expected
   buyer address. A mismatch triggers an alert.

2. **Audit trail**: every beneficiary sync is logged in the SOST audit log with
   position ID, deposit ID, old beneficiary, new beneficiary, and tx hash.

3. **Immutability**: the operator address cannot be changed to a compromised key
   after deployment. If the operator key is compromised, a new contract must be
   deployed (positions can be migrated since deposits are independent).

4. **Minimal privilege**: the operator has exactly one capability (reassign
   beneficiary). It cannot extract value.

## Why Not an Admin Key?

An admin key that could pause, upgrade, or emergency-withdraw would violate
SOST's constitutional properties. The settlement operator is strictly scoped:
it can only change who will eventually receive funds, not take funds itself.

This is the minimum trust addition needed for automated settlement.

## Withdrawal Flow (Unchanged)

1. Timelock expires
2. `currentBeneficiary` calls `withdraw(depositId)`
3. Tokens transfer to `currentBeneficiary`
4. No other address can trigger withdrawal

## Contract Upgrade Path

If the operator key is compromised:
1. Deploy a new SOSTEscrowV2 with a new operator address
2. New deposits go to the new contract
3. Existing deposits in the old contract are unaffected — the compromised
   operator can reassign beneficiaries but cannot steal funds
4. Affected beneficiaries can still withdraw normally once timelock expires
