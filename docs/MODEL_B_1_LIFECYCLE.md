# Model B #1 Lifecycle — Position 8afed8fcd27553a7

## Status: ACTIVE
## Registered: April 22, 2026

| Field | Value |
|-------|-------|
| Position ID | 8afed8fcd27553a7 |
| Owner | sost1a8eae8f80fedd8d86187db628a0d81e0367f76de |
| Model | B-escrow |
| Token | XAUT (0.5 oz = 500,000 units) |
| Duration | 28 days |
| Reward Rate | 0.4% |
| ETH Deposit | #1 on Sepolia escrow |
| ETH TX | 0x4d3a6beff787b8fe24f37bb1e8945f823e2b29244a65c7853f89767dc329a8c6 |

## Expected Timeline
- Registered: ~April 22, 2026
- Maturity: ~May 20, 2026
- Withdraw window: after maturity (Sepolia escrow unlock)

## Lifecycle Stages
1. ACTIVE — current
2. NEARING_EXPIRY — 7 days before maturity
3. MATURE — after expiry_time
4. REDEEMED — after withdraw executed

## Operator Commands

Track position lifecycle:
```bash
python3 scripts/operator_track_position_lifecycle.py --position-id 8afed8fcd27553a7
```

Check maturity status:
```bash
python3 scripts/operator_check_maturity.py
```

Prepare withdraw (dry run):
```bash
python3 scripts/operator_prepare_withdraw.py --position-id 8afed8fcd27553a7
```

Execute withdraw on Sepolia:
```bash
python3 scripts/operator_execute_withdraw_demo.py --position-id 8afed8fcd27553a7 --private-key 0x... --execute
```

## Escrow Contract

| Field | Value |
|-------|-------|
| Chain | Sepolia (11155111) |
| Escrow | 0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113 |
| Mock XAUT | 0x38ca34c6b7b3772b44212d6c2597fd91a6f944d0 |
| Deployer | 0x5c02284f3358d5518c9ae7ba5bdd4cc8efd40e9a |

## Notes

- This is the first Model B position registered on the SOST Gold Exchange.
- ETH escrow deposit serves as the on-chain backing proof.
- Position rewards accrue linearly over the 28-day duration.
- Withdraw requires maturity AND escrow release time to have passed.
