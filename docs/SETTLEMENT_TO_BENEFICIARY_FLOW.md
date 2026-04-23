# Settlement to Beneficiary Flow

Step-by-step flow for automated beneficiary handoff after a full-sale trade.

## Preconditions

- SOSTEscrowV2 deployed with a `settlementOperator` address
- Settlement engine holds the operator's private key (for signing txs)
- Position exists in SOST registry with `eth_escrow_deposit_id` set
- Deal has been matched and payment locked (BOTH_LOCKED state)

## Flow

### Step 1: Deal Settles in SOST Registry

The DEX settlement engine confirms the trade:
- Buyer's SOST payment is locked
- Seller's position offer is locked
- Deal transitions to BOTH_LOCKED, then SETTLED

The `PositionSettlement.settle_position_trade()` method:
- Updates `pos.owner` to buyer's SOST address
- Updates `pos.principal_owner` to buyer's SOST address
- Updates `pos.reward_owner` to buyer's SOST address
- Updates `pos.eth_beneficiary` to buyer's ETH address
- Records transfer event in position history

### Step 2: Settlement Engine Calls beneficiary_sync

After the SOST-side settlement completes, the settlement engine triggers
`BeneficiarySync.sync_beneficiary(position_id)`.

The sync module:
- Reads the position's `eth_escrow_deposit_id` and `eth_beneficiary`
- Builds the on-chain transaction

### Step 3: beneficiary_sync Calls updateBeneficiary via settlementOperator

The sync module sends a transaction to SOSTEscrowV2:

```
updateBeneficiary(depositId, newBeneficiary)
```

Signed by the `settlementOperator` key. The contract accepts this because
`msg.sender == settlementOperator`.

In alpha mode, this generates a `cast send` command:
```
cast send <escrow_address> \
  "updateBeneficiary(uint256,address)" <deposit_id> <new_beneficiary> \
  --rpc-url <rpc_url> \
  --private-key <operator_key>
```

### Step 4: On-Chain Beneficiary Updated

The contract:
1. Verifies `msg.sender` is either `currentBeneficiary` or `settlementOperator`
2. Verifies `newBeneficiary != address(0)`
3. Updates `deposits[depositId].currentBeneficiary = newBeneficiary`
4. Emits `BeneficiaryUpdated(depositId, oldBeneficiary, newBeneficiary)`

### Step 5: Reconciliation Verifies

The settlement engine reads back the on-chain state:
```
cast call <escrow_address> "getDeposit(uint256)" <deposit_id>
```

Confirms:
- `currentBeneficiary == buyer's ETH address`
- Matches the SOST registry's `eth_beneficiary` field

If mismatch: alert is raised, position flagged for manual review.

## Lifecycle After Handoff

```
ACTIVE -> (trade settles) -> beneficiary synced on-chain
       -> MATURED (timelock expires)
       -> WITHDRAW_PENDING (auto-withdraw daemon triggers)
       -> WITHDRAWN (funds sent to new beneficiary)
       -> REWARD_SETTLED (SOST rewards credited to buyer's SOST address)
```

## Reward-Only Sale (No Beneficiary Change)

For reward-right trades, the principal owner and ETH beneficiary do NOT change.
Only `reward_owner` is updated in the SOST registry. No on-chain transaction
is needed. The `BeneficiarySync` module is not invoked.
