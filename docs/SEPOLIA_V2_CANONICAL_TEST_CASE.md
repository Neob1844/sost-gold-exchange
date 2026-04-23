# Sepolia V2 Canonical Test Case

Reference test case for validating the full-sale beneficiary handoff flow
on Sepolia testnet.

## Actors

| Role   | SOST Address          | ETH Address  |
|--------|-----------------------|--------------|
| Seller | `sost1seller_test`    | `0xSeller`   |
| Buyer  | `sost1buyer_test`     | `0xBuyer`    |

(Replace with real testnet addresses before execution.)

## Deposit Parameters

| Field         | Value                          |
|---------------|--------------------------------|
| Token         | Mock XAUT (6 decimals)         |
| Amount        | 100,000 units (0.1 oz)         |
| Lock duration | 28 days                        |
| Beneficiary   | `0xSeller` (depositor default) |

## Trade Parameters

| Field      | Value                   |
|------------|-------------------------|
| Sale type  | Full position sale      |
| Price      | 5 SOST (500,000,000 sat)|
| Buyer ETH  | `0xBuyer`               |

## Expected Outcomes

### After Settlement

1. SOST registry:
   - `pos.owner` == `sost1buyer_test`
   - `pos.principal_owner` == `sost1buyer_test`
   - `pos.reward_owner` == `sost1buyer_test`
   - `pos.eth_beneficiary` == `0xBuyer`

2. On-chain (SOSTEscrowV2):
   - `deposits[depositId].currentBeneficiary` == `0xBuyer`
   - `BeneficiaryUpdated` event emitted with old=`0xSeller`, new=`0xBuyer`

### After Maturity (28 days)

3. Auto-withdraw daemon:
   - Calls `withdraw(depositId)` from `0xBuyer`
   - 0.1 oz XAUT transferred to `0xBuyer`
   - `GoldWithdrawn` event emitted with beneficiary=`0xBuyer`

4. Seller receives nothing from the escrow (already received 5 SOST as payment)

### After Reward Settlement

5. Reward settlement daemon:
   - Credits SOST rewards to `sost1buyer_test` (buyer's SOST address)
   - `pos.lifecycle_status` == `REWARD_SETTLED`

## Verification Steps

1. **Pre-trade**: confirm deposit exists, beneficiary is seller
   ```
   cast call <escrow> "getDeposit(uint256)" <id>
   ```

2. **Post-settlement**: confirm beneficiary changed to buyer
   ```
   cast call <escrow> "getDeposit(uint256)" <id>
   ```

3. **Post-maturity**: confirm withdrawal pays buyer
   ```
   cast call <xaut> "balanceOf(address)" <0xBuyer>
   ```

4. **Audit log**: confirm beneficiary_synced event recorded

## Negative Cases to Verify

- Old beneficiary (`0xSeller`) cannot withdraw after handoff
- Random address cannot call `updateBeneficiary`
- `updateBeneficiary` to `address(0)` reverts
- Double withdrawal reverts with `AlreadyWithdrawn`
