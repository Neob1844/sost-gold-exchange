# Principal vs Reward Ownership

## Overview

Model B v2 introduces split ownership: a single gold-backed position can have
different owners for the **principal** (the underlying gold) and the **reward**
(the SOST mining rewards earned over the lock period).

This enables a secondary market where reward rights can be traded independently
of the principal claim.

## Ownership Fields

### principal_owner

The SOST address that owns the principal claim — the right to receive the
underlying gold (via ETH escrow withdrawal) at maturity.

- Set at position creation, defaults to `owner`
- Changes when the full position is sold
- Does NOT change when only reward rights are sold
- Controls who the `eth_beneficiary` should point to

### reward_owner

The SOST address that receives SOST mining rewards when the position matures.

- Set at position creation, defaults to `owner`
- Changes when reward rights are sold (reward-only sale)
- Also changes when the full position is sold
- The reward settlement daemon credits rewards to this address

### eth_beneficiary

The Ethereum address that can withdraw gold from the escrow at maturity.

- Set at position creation, typically the principal_owner's ETH address
- Must be synced on-chain via `updateBeneficiary()` when principal_owner changes
- Does NOT need to change for reward-only sales
- The beneficiary sync service handles this automatically

### owner (legacy)

The original single-owner field. In v2, this is kept in sync with
`principal_owner` for backward compatibility.

## Trade Scenarios

### Full Position Sale

All three ownership fields change:

```
principal_owner:  Alice -> Bob
reward_owner:     Alice -> Bob
eth_beneficiary:  0xAlice -> 0xBob  (requires on-chain sync)
```

The beneficiary sync daemon detects the change and generates the
`updateBeneficiary` transaction.

### Reward-Only Sale

Only `reward_owner` changes:

```
principal_owner:  Alice (unchanged)
reward_owner:     Alice -> Charlie
eth_beneficiary:  0xAlice (unchanged, no sync needed)
```

At maturity:
- Alice receives the gold (via ETH withdrawal to 0xAlice)
- Charlie receives the SOST rewards

### Principal-Only Sale (rare)

Only `principal_owner` and `eth_beneficiary` change:

```
principal_owner:  Alice -> Dave
reward_owner:     Alice (unchanged)
eth_beneficiary:  0xAlice -> 0xDave  (requires on-chain sync)
```

At maturity:
- Dave receives the gold
- Alice receives the SOST rewards

## Lifecycle Impact

The split ownership affects the maturity lifecycle:

1. **MATURED**: Position has passed expiry_time
2. **WITHDRAWN**: Gold withdrawn to `eth_beneficiary` (controlled by `principal_owner`)
3. **REWARD_SETTLED**: SOST rewards credited to `reward_owner`
4. **CLOSED**: All obligations fulfilled

Steps 2 and 3 go to different parties in a split-ownership scenario.

## Invariants

- `principal_owner` and `eth_beneficiary` must always correspond to the same
  economic interest (the gold holder)
- `reward_owner` is independent and can point to any valid SOST address
- When `principal_owner` changes, `eth_beneficiary` MUST be updated on-chain
  before the position matures
- `reward_settled` is only set once, at which point `reward_owner` is locked
