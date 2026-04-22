# Model B Risk Limits

Risk framework for the SOST Gold Exchange Model B escrow system.

---

## Stage 1: Pilot

**Goal**: Prove the full cycle works end-to-end with real assets.

| Parameter | Limit |
|---|---|
| Max amount per position | 0.5 oz (~$1,500) |
| Max total exposure | 0.5 oz |
| Max duration | 28 days |
| Max participants | 1 (foundation only) |
| Operator approval | Required for every action |
| Network | Ethereum mainnet |
| Tokens accepted | XAUT only |

### Entry Criteria
- SOSTEscrow deployed and verified on mainnet
- Pre-flight checks pass (`verify_mainnet_prereqs.py`)
- SOST node synced and stable for 7+ days
- Reward pool funded

### Exit Criteria (to proceed to Stage 2)
- [ ] At least 1 full deposit-lock-withdraw cycle completed
- [ ] Position correctly tracked from creation to redemption
- [ ] Audit log complete and verified
- [ ] No bugs or unexpected behavior
- [ ] Post-mortem written

---

## Stage 2: Limited Alpha

**Goal**: Validate with a small number of external participants.

| Parameter | Limit |
|---|---|
| Max amount per position | 1.0 oz (~$3,000) |
| Max total exposure | 5.0 oz (~$15,000) |
| Max duration | 90 days |
| Max participants | 3-5 (invited only) |
| Operator approval | Required for deposits |
| Tokens accepted | XAUT, PAXG |

### Entry Criteria
- Stage 1 exit criteria met
- Escrow contract audited (at minimum, peer-reviewed)
- Watcher service running reliably for 30+ days
- Automated health checks passing daily

### Exit Criteria (to proceed to Stage 3)
- [ ] At least 5 full cycles completed across multiple participants
- [ ] Reward distribution verified correct
- [ ] Transfer and reward-split operations tested
- [ ] No operator intervention required for routine operations
- [ ] Documentation reviewed by external participant

---

## Stage 3: Public Beta

**Goal**: Open to any participant with reasonable limits.

| Parameter | Limit |
|---|---|
| Max amount per position | 5.0 oz (~$15,000) |
| Max total exposure | 50 oz (~$150,000) |
| Max duration | 365 days |
| Max participants | Unlimited (with KYC if required) |
| Operator approval | Deposits > 1 oz only |
| Tokens accepted | XAUT, PAXG |

### Entry Criteria
- Stage 2 exit criteria met
- Professional security audit completed
- Automated settlement (no manual operator step)
- Insurance or reserve fund for potential losses
- Legal review completed

### Exit Criteria (to proceed to Production)
- [ ] 6 months of operation with no critical issues
- [ ] >$50k total value processed
- [ ] Dispute resolution tested
- [ ] Performance under load validated

---

## Stage 4: Production

| Parameter | Limit |
|---|---|
| Max amount per position | Governed by protocol |
| Max total exposure | Governed by protocol |
| Max duration | Governed by protocol |
| Participants | Open |
| Operator approval | Automated with override |

### Entry Criteria
- Stage 3 exit criteria met
- Governance mechanism in place for limit changes
- Multi-sig for escrow owner key
- Formal insurance/hedging in place

---

## Risk Considerations

### Smart Contract Risk
- **Pilot mitigation**: Small amounts, single participant, manual oversight
- **Alpha mitigation**: Audit, increased monitoring
- **Long-term**: Formal verification, bug bounty program

### Gold Token Risk (XAUT/PAXG)
- These are centralized tokens backed by custodied gold
- Issuer default risk exists but is outside SOST control
- Mitigation: diversify across tokens, monitor issuer health
- Depeg threshold: halt new deposits if spot deviation > 2%

### Ethereum Network Risk
- Chain reorg: require 12+ confirmations on mainnet
- Gas spikes: may delay withdrawals but do not affect locked deposits
- RPC provider: use multiple providers, fallback configured

### SOST Side Risk
- Node downtime: positions persisted, no loss
- Reward pool exhaustion: monitor balance, alert at 20% remaining
- Position registry corruption: daily backups, append-only audit log

### Hedging
- Pilot: no hedging needed (foundation bears all risk)
- Alpha: consider SOST reserve fund equal to max exposure
- Production: formal hedging strategy required before launch

### Maximum Loss Scenarios

| Stage | Worst Case | Max Loss |
|---|---|---|
| Pilot | Escrow drained | ~$1,500 |
| Limited Alpha | Escrow drained | ~$15,000 |
| Public Beta | Escrow drained | ~$150,000 |

All max-loss figures assume total loss of escrowed assets, which requires a critical smart contract vulnerability.
