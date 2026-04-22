# Phase XI --- Mainnet Preparation and Go/No-Go

Phase XI consolidates all pre-mainnet work into a final decision framework. Everything needed to run the first real Model B escrow pilot on Ethereum mainnet is documented, tested, and verified.

---

## What Was Added

### Documentation
- **GO_NO_GO_MODEL_B_MAINNET.md** -- Decision document with exact GO/NO-GO conditions, pilot parameters, abort procedures, and timeline
- **README_PHASE_XI.md** -- This summary document
- Updated **MODEL_B_REAL_PILOT_CHECKLIST.md** with Sepolia lifecycle, relay/API, position tracking, and Go/No-Go review checkpoints

### Verification
- Updated **verify_mainnet_prereqs.py** with additional checks:
  - Position registry has at least 1 completed Sepolia lifecycle
  - Test suites passing (Python + TypeScript)
  - `configs/mainnet_model_b.example.json` exists
  - Go/No-Go document exists
  - Summary output: READY / NOT READY with reasons

---

## How to Run Alpha With Test Users

### Start the full alpha stack (watcher + settlement daemon + health monitor):
```bash
bash scripts/start_alpha_stack.sh
```

### Register a test position (operator-assisted):
```bash
python3 scripts/operator_register_model_b.py \
  --owner TEST_SOST_ADDRESS \
  --token XAUT \
  --amount AMOUNT_WEI \
  --duration-days 28 \
  --deposit-id DEPOSIT_ID \
  --eth-tx TX_HASH
```

### Check health:
```bash
bash scripts/check_alpha_health.sh
```

### Start the alpha service (API + dashboard):
```bash
python3 scripts/start_alpha_service.py
```

---

## How to Use the Relay for Trades

The relay operates through the sost-comms-private module, which handles signed trade intent messages between participants.

### Trade flow:
1. **Maker** creates and signs an offer intent
2. Offer is relayed to the exchange matching engine
3. **Taker** signs an accept intent referencing the offer
4. Deal ID is derived deterministically: `SHA256(offer_id:accept_id)[:16]`
5. Both parties lock collateral (ETH side: escrow deposit; SOST side: operator registers)
6. Settlement daemon monitors both sides and executes when conditions are met

### Run the signed trade flow demo:
```bash
python3 scripts/demo_position_full_trade.py
python3 scripts/demo_position_reward_trade.py
```

### All trade messages use ED25519 signatures with nonce anti-replay protection.

---

## How to Track Position Lifecycle

### View all positions:
```bash
python3 scripts/operator_show_positions.py
```

### Position states:
```
ACTIVE -> MATURED -> REDEEMED
                  -> EXPIRED (if not withdrawn in time)
```

### Position operations:
```bash
# Value a position (current gold price * amount * time remaining)
python3 scripts/operator_value_position.py

# Transfer a position to a new owner
python3 scripts/operator_transfer_position.py

# Split a reward right
python3 scripts/operator_split_reward_right.py
```

---

## How to Check Maturity

### Check a specific Sepolia deposit:
```bash
python3 scripts/check_sepolia_deposit.py --deposit-id DEPOSIT_ID
```

### Check on-chain via cast:
```bash
cast call $ESCROW_ADDRESS \
  "deposits(uint256)(address,address,uint256,uint256,uint256,bool)" \
  $DEPOSIT_ID --rpc-url $ETH_RPC_URL
```

The fifth return value is the `unlockTime` (unix timestamp). If the current block timestamp exceeds this value, the position has matured.

### Automated monitoring:
The watcher service polls for maturity events. The health monitor script runs daily checks on all active positions.

---

## How to Prepare Withdrawal

1. **Verify maturity**: Confirm `unlockTime` has passed using the check scripts above
2. **Prepare the TX**: Use the depositor key (hardware wallet recommended for mainnet)
3. **Execute**:
   ```bash
   cast send $ESCROW_ADDRESS \
     "withdraw(uint256)" \
     $DEPOSIT_ID \
     --rpc-url $ETH_RPC_URL \
     --private-key $DEPOSITOR_KEY
   ```
4. **Verify**: Check that tokens are returned to the depositor wallet on Etherscan
5. **Update SOST side**: Position status should transition to REDEEMED
6. **Audit**: Confirm the audit log records the withdrawal event

---

## Current Test Counts

| Suite | Location | Description |
|---|---|---|
| Unit tests (6 files) | `tests/unit/` | Deal state machine, position registry, position transfer, position pricing, refund engine, settlement daemon |
| Integration tests (10 files) | `tests/integration/` | Settlement happy path, refund path, watcher service, ETH watcher, SOST watcher, alpha mode, live config, position trade flows, demo state progression |
| Adversarial tests (10 files) | `tests/adversarial/` | Duplicate events, replay attacks, mismatched locks, concurrent settlement, bad signatures, wrong owner, double transfer, expired offers, reward overallocation, expiry races |
| Comms tests | `sost-comms-private/tests/` | TypeScript relay and message signing tests |

Run all Python tests:
```bash
cd /home/sost/SOST/sost-gold-exchange-private
python3 -m pytest tests/ -v
```

Run comms tests:
```bash
cd /home/sost/SOST/sost-comms-private
npm test
```

---

## What Follows After Phase XI

### Immediate Next Step: Execute the Pilot
1. Complete all GO conditions in `GO_NO_GO_MODEL_B_MAINNET.md`
2. Deploy SOSTEscrow to Ethereum mainnet
3. Execute the first real Model B deposit (<=0.5 oz XAUT)
4. Monitor for 28 days
5. Execute withdrawal and write post-mortem

### After Successful Pilot (Stage 2: Limited Alpha)
- Invite 3-5 external participants
- Increase limits to 1.0 oz per position, 5.0 oz total
- Accept PAXG in addition to XAUT
- Extend maximum duration to 90 days
- Require escrow contract peer review or audit

### Longer-Term Roadmap
- On-chain settlement finality on SOST (atomic proof of settlement)
- Decentralized relay network (P2P message passing without operator)
- Automatic ETH refund trigger (keeper bot calls withdraw after expiry)
- Multi-operator consensus for settlement
- Public beta with professional security audit
