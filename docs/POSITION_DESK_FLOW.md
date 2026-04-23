# Position Desk Flow

How the position trading desk works in the SOST Gold Exchange alpha.

---

## Overview

The position desk allows alpha participants to trade gold-backed SOST positions and reward rights. All trades are operator-assisted during the alpha phase.

---

## Full Position Trade

### Step 1: View Available Positions

The positions page shows all active gold-backed positions with:
- Position ID and owner
- Token type (XAUT or PAXG) and reference amount
- Contract type (Model A Custody or Model B Escrow)
- Time remaining and percent complete
- Reward total and reward claimed

Only Model B (Escrow) positions are fully transferable. Model A positions can only trade reward rights.

### Step 2: Select a Position

Click on a position to view full details:
- Escrow deposit ID and Ethereum transaction hash
- Reward schedule (linear over duration)
- Event history (created, reward claims, etc.)
- Current valuation based on gold reference and accrued rewards

### Step 3: Create an Offer

The seller creates a signed offer specifying:
- Position ID
- Asking price in SOST
- Expiry timestamp

The offer payload is canonically hashed (SHA-256) and signed. The offer is submitted to the operator.

### Step 4: Buyer Accepts

The buyer reviews the offer details and creates a signed accept message referencing the offer ID. The operator verifies both signatures and derives the deal ID.

### Step 5: Lock Phase

Both sides lock their assets:
- **ETH side**: gold tokens locked in SOSTEscrow contract on Ethereum
- **SOST side**: payment locked via SOST transaction

The deal transitions through `AWAITING_ETH_LOCK` -> `AWAITING_SOST_LOCK` -> `BOTH_LOCKED` as watchers confirm each lock.

### Step 6: Settlement

Once both sides are locked:
- Operator calls `settle_position_trade()`
- Position ownership transfers to buyer
- Deal transitions to `SETTLED`
- Both parties receive settlement confirmation with deal ID and tx hashes

---

## Reward Right Trade

### Step 1: View Position with Remaining Rewards

The position owner sees their position with unclaimed reward balance. Reward rights can be split and sold independently of the gold principal.

### Step 2: Create Reward Right Offer

The owner creates a signed offer specifying:
- Position ID
- Trade type: `POSITION_REWARD_RIGHT`
- Asking price for the reward stream

### Step 3: Buyer Accepts

Same signed accept flow as full position trades.

### Step 4: Lock and Settle

Lock phase proceeds identically. On settlement:
- `settle_reward_split()` creates a new child position for the buyer
- Child position has `right_type = REWARD_RIGHT` with the remaining reward balance
- Parent position's remaining rewards are zeroed out
- Buyer now holds an independent, transferable reward-right position

---

## What Happens on Failure

- **Offer expires**: deal transitions to `EXPIRED` automatically. No assets are locked.
- **Lock timeout**: if one side locks but the other does not before expiry, the deal expires. The locked party can withdraw from escrow after the timelock.
- **Dispute**: either party can flag `DISPUTED`. Resolution is manual in alpha.
- **Refund**: operator can initiate `REFUND_PENDING` -> `REFUNDED` for failed deals.

---

## CLI Commands

```bash
# View all positions
python3 scripts/operator_show_positions.py

# Value a position
python3 scripts/operator_value_position.py --position-id <id> --gold-price 0.001

# Transfer (operator)
python3 scripts/operator_transfer_position.py --position-id <id> --new-owner <addr>

# Split reward rights (operator)
python3 scripts/operator_split_reward_right.py --position-id <id> --buyer <addr>

# Run full trade demo
python3 scripts/demo_position_full_trade.py

# Run reward right trade demo
python3 scripts/demo_position_reward_trade.py
```
