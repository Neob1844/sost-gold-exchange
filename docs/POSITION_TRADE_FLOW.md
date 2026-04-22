# SOST Gold Exchange — Position Trade Flow

## What is a Position?

A position is a SOST-native representation of a gold-backed contract. Positions live and trade inside SOST; Ethereum is only the onboarding/exit rail.

### Model A (Custody)

The gold holder retains physical or self-custody of tokenized gold and proves continued possession via Proof of Physical Custody (PoPC). The full position is **not transferable** — only reward rights can be split and sold.

- `contract_type`: `MODEL_A_CUSTODY`
- `backing_type`: `AUTOCUSTODY_GOLD`
- `transferable`: `false`

### Model B (Escrow)

Gold tokens (XAUT, PAXG) are locked in the SOSTEscrow smart contract on Ethereum. The full position — including principal and rewards — is freely transferable within SOST.

- `contract_type`: `MODEL_B_ESCROW`
- `backing_type`: `ETH_TOKENIZED_GOLD`
- `transferable`: `true`

## What is a Reward Right?

A reward right is a separated claim on the future SOST rewards from a position, without any claim on the underlying gold principal. When a reward right is split from a parent position:

- A new child position is created with `right_type = REWARD_RIGHT`
- The child inherits the remaining reward amount
- The parent's rewards are zeroed out (`reward_total = reward_claimed`)
- The child has `reference_amount = 0` (no gold principal)
- The child is independently transferable

## Full Position Trade Flow

```
Seller                    Operator                   Buyer
  |                          |                          |
  |--- signed offer -------->|                          |
  |   (position_id, price,   |                          |
  |    expiry, signature)    |                          |
  |                          |                          |
  |                          |<--- signed accept -------|
  |                          |   (offer_id, buyer,      |
  |                          |    signature)             |
  |                          |                          |
  |                          |-- derive deal_id --------|
  |                          |   SHA256(offer:accept)   |
  |                          |                          |
  |                          |-- create Deal            |
  |                          |   state: CREATED         |
  |                          |                          |
  |                          |-- transition chain:      |
  |                          |   CREATED                |
  |                          |   -> NEGOTIATED          |
  |                          |   -> AWAITING_ETH_LOCK   |
  |                          |   -> AWAITING_SOST_LOCK  |
  |                          |   -> BOTH_LOCKED         |
  |                          |                          |
  |                          |-- settle_position_trade()|
  |                          |   transfer ownership     |
  |                          |   -> SETTLING            |
  |                          |   -> SETTLED             |
  |                          |                          |
  |<-- settlement notice ----|--- settlement notice --->|
```

### Steps

1. **Seller creates signed offer**: includes position_id, asking price in SOST, expiry timestamp. The canonical payload is hashed (SHA-256) and signed.
2. **Buyer creates signed accept**: references the offer_id, includes buyer address and signature.
3. **Operator derives deal_id**: `SHA256(offer_id:accept_id)[:16]` — deterministic from both signatures.
4. **Deal created**: operator creates a Deal in the DealStore with both parties' addresses.
5. **Lock phase**: ETH gold tokens locked in escrow, SOST payment locked. Deal transitions through `AWAITING_ETH_LOCK` -> `AWAITING_SOST_LOCK` -> `BOTH_LOCKED`.
6. **Settlement**: `PositionSettlement.settle_position_trade()` transfers position ownership to buyer, deal transitions to `SETTLED`.
7. **Settlement notice**: both parties receive confirmation with deal_id, position_id, and settlement tx hash.

## Reward Right Trade Flow

```
Position Owner             Operator                   Buyer
  |                          |                          |
  |--- signed offer -------->|                          |
  |   (position_id,          |                          |
  |    REWARD_RIGHT, price)  |                          |
  |                          |                          |
  |                          |<--- signed accept -------|
  |                          |                          |
  |                          |-- derive deal_id         |
  |                          |-- create Deal            |
  |                          |-- lock phase             |
  |                          |   -> BOTH_LOCKED         |
  |                          |                          |
  |                          |-- settle_reward_split()  |
  |                          |   split reward right     |
  |                          |   create child position  |
  |                          |   zero parent rewards    |
  |                          |   -> SETTLED             |
  |                          |                          |
  |<-- settlement notice ----|--- settlement notice --->|
  |   (parent zeroed)        |   (child created)        |
```

### Steps

1. **Owner creates signed offer**: specifies `POSITION_REWARD_RIGHT` as the trade type, includes position_id and price for the reward stream.
2. **Buyer accepts**: standard signed accept referencing the offer.
3. **Deal and lock phase**: same as full position trade.
4. **Settlement**: `PositionSettlement.settle_reward_split()` calls `split_reward_right()` which:
   - Creates a new child position owned by buyer with `right_type = REWARD_RIGHT`
   - Sets `reward_total_sost` on child to parent's remaining rewards
   - Zeros parent's remaining rewards (`reward_total = reward_claimed`)
5. **Notices**: parent owner sees rewards zeroed, buyer sees new reward-right position.

## Signature Enforcement

In the current alpha phase, signature enforcement works as follows:

- **Canonical hash**: each offer/accept message is serialized into a deterministic canonical string and SHA-256 hashed.
- **Offer hash**: `SHA256("1|position_offer|{type}|{position_id}|{seller}|{price}|{expiry}")`
- **Accept hash**: `SHA256("1|position_accept|{offer_id}|{buyer}|{price}|{timestamp}")`
- **Deal ID derivation**: `SHA256("{offer_id}:{accept_id}")[:16]` — deterministic from both message IDs.
- **Tamper detection**: any modification to the offer payload changes the hash, which changes the offer_id, which changes the deal_id. The operator verifies hash integrity before creating a deal.
- **Expiry enforcement**: offers include an expiry timestamp. The deal's `expires_at` is set from the offer. Expired deals are automatically transitioned to `EXPIRED` state and cannot settle.

## What is Alpha / Operator-Assisted?

The current system operates in **alpha mode**, meaning:

- The **operator** (exchange service) mediates all trades. There is no direct peer-to-peer settlement yet.
- The operator validates that:
  - The seller actually owns the position (`position.owner == deal.maker_sost_addr`)
  - The offer hash matches the canonical payload (tamper detection)
  - The offer has not expired
  - The position is active and transferable
- Both ETH and SOST locks are verified by watchers (EthereumWatcher, SostWatcher) before settlement proceeds.
- The operator maintains an append-only audit log of every deal action for forensics and dispute resolution.
- In future phases, operator mediation will be replaced by direct on-chain verification.

## Example CLI Commands

### View positions

```bash
python3 scripts/operator_show_positions.py
```

### Value a position

```bash
python3 scripts/operator_value_position.py --position-id <id> --gold-price 0.001
```

### Transfer a position (operator)

```bash
python3 scripts/operator_transfer_position.py --position-id <id> --new-owner <addr>
```

### Split reward rights (operator)

```bash
python3 scripts/operator_split_reward_right.py --position-id <id> --buyer <addr>
```

### Run full position trade demo

```bash
python3 scripts/demo_position_full_trade.py
```

### Run reward right trade demo

```bash
python3 scripts/demo_position_reward_trade.py
```

### View audit log

```bash
python3 scripts/operator_show_audit.py
```
