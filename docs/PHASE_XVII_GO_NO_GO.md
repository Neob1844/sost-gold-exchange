# Phase XVII — GO / NO-GO

Binary decision gate for Phase XVII: V2 full sale with autonomous
beneficiary handoff.

Date: 2026-04-22

---

## GO if ALL true:

- [ ] Full sale changes principal_owner, reward_owner, eth_beneficiary correctly
- [ ] Beneficiary sync updates currentBeneficiary on-chain via settlementOperator
- [ ] Reward-only sale leaves beneficiary unchanged
- [ ] Auto-withdraw pays currentBeneficiary (buyer) not original depositor
- [ ] Reward settlement pays reward_owner correctly
- [ ] Reconciliation shows no mismatches
- [ ] No manual intervention by seller required after settlement
- [ ] All tests passing

## NO-GO if ANY true:

- [ ] Beneficiary change depends on seller cooperation
- [ ] Race condition between concurrent sales
- [ ] Persistent registry/on-chain mismatch
- [ ] Auto-withdraw pays wrong address
- [ ] Reward goes to wrong owner

---

## Verification commands

### Run demos

```bash
# Full sale + beneficiary handoff
python3 scripts/demo_v2_full_sale_handoff.py

# Reward-only sale control case
python3 scripts/demo_v2_reward_sale_control.py

# Maturity + auto-withdraw lifecycle
python3 scripts/demo_v2_maturity_autowithdraw.py
```

### Run reconciliation

```bash
# Full V2 reconciliation
python3 scripts/reconcile_v2_live_case.py --file data/positions.json

# Focused beneficiary reconciliation
python3 scripts/reconcile_beneficiary_live.py --file data/positions.json
```

### Run tests

```bash
python3 -m pytest tests/ -v
```

---

## Decision

| Criteria | Result |
|----------|--------|
| Full sale ownership transfer | |
| Beneficiary sync on-chain | |
| Reward-only isolation | |
| Auto-withdraw to correct address | |
| Reward to correct owner | |
| Reconciliation clean | |
| No seller dependency | |
| Tests passing | |

**Decision: ___GO / NO-GO___**

Signed: _______________  Date: _______________
