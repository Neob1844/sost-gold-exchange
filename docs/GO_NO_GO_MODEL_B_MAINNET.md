# GO / NO-GO --- First Model B Mainnet Pilot

## Decision Framework

This document defines the exact conditions that must be met before executing the first PoPC Model B contract on Ethereum mainnet with real XAUT/PAXG. Every GO condition must be satisfied. Any single NO-GO condition blocks launch.

---

## GO CONDITIONS (ALL must be true)

### Technical

- [ ] SOSTEscrow deployed on mainnet and verified on Etherscan
- [ ] `verify_mainnet_prereqs.py` returns all-pass
- [ ] Settlement flow demonstrated end-to-end on Sepolia (happy path + refund path)
- [ ] Position lifecycle tracked to maturity on Sepolia (deposit -> lock -> mature -> withdraw)
- [ ] All Python tests passing (`pytest`)
- [ ] All TypeScript tests passing (`npm test` in sost-comms-private)
- [ ] All Solidity tests passing (`forge test` in contracts/)
- [ ] Watcher service stable for 48+ hours on Sepolia without restart
- [ ] Dashboard API accessible and reporting correct position data
- [ ] Relay endpoint reachable and able to route trade intents

### Operational

- [ ] Operator assigned and available for full 28-day monitoring period
- [ ] Secondary operator identified for backup coverage
- [ ] Runbook (MODEL_B_MAINNET_RUNBOOK.md) reviewed and dry-run tested on Sepolia
- [ ] Audit log export verified (can produce CSV/JSON for any date range)
- [ ] Emergency contact chain established (primary -> secondary -> foundation)
- [ ] Calendar reminders set for: deposit day, midpoint check, maturity day, withdraw day

### Financial

- [ ] Pilot amount confirmed: <=0.5 oz XAUT (approx $1,500)
- [ ] Foundation wallet funded with sufficient XAUT
- [ ] Gas budget available: deposit TX + withdraw TX + buffer (approx 0.01 ETH)
- [ ] No external capital at risk (foundation funds only)
- [ ] PoPC reward pool funded with sufficient SOST for 0.4% reward

### Communication

- [ ] Internal announcement only (no public marketing before cycle completes)
- [ ] BTCTalk update prepared: "first mainnet pilot in progress" (post after deposit, not before)
- [ ] Explorer status page updated to reflect mainnet pilot in progress
- [ ] Clear disclaimer published: operator-assisted settlement, not fully trustless

---

## NO-GO CONDITIONS (ANY one triggers NO-GO)

- Any test suite failing (Python, TypeScript, or Solidity)
- Watcher service unstable (>2 unplanned restarts in 48 hours)
- Sepolia full lifecycle not completed to maturity and withdrawal
- SOSTEscrow audit finding of critical or high severity unresolved
- Operator unavailable for the 28-day monitoring commitment
- Gold price volatility >15% in the preceding 7 days (re-evaluate timing)
- Ethereum network instability (>5 reorgs or consensus issues in 7 days)
- Position registry unable to track Sepolia lifecycle from deposit to redemption
- Relay/API endpoint unreachable or returning incorrect data
- `verify_mainnet_prereqs.py` reporting any FAIL result

---

## PILOT PARAMETERS

| Parameter | Value |
|---|---|
| Duration | 28 days (1 month minimum) |
| Amount | <=0.5 oz XAUT |
| Participants | 1 (foundation only) |
| Reward rate | 0.4% of gold value |
| Settlement | Operator-assisted |
| Monitoring | Daily health checks |
| Network | Ethereum mainnet (chain ID 1) |
| Confirmations | 12 blocks |
| Token | XAUT (0x68749665FF8D2d112Fa859AA293F07A622782F38) |

---

## ABORT / ROLLBACK

### Escrow Failure
Gold remains locked in the contract until `unlockTime` passes. After `unlockTime`, the depositor calls `withdraw()` to recover tokens. No operator action can prevent recovery after timelock expiry.

### Watcher Failure
Restart the watcher service. Missed events are replayed from the last known checkpoint. No on-chain state is lost.

### SOST Node Failure
Restart the node and wait for sync. Position registry is persisted to `data/positions.json`. Audit log is append-only and survives restarts.

### Operator Unavailable
Secondary contact takes over monitoring duties only (no settlement actions). If both operators are unavailable, the position simply runs to maturity and the depositor withdraws after timelock.

### Key Compromise
- Escrow owner key: pause contract immediately (if pause is supported)
- Depositor key: withdraw immediately if lock expired; otherwise monitor
- Rotate all related keys and file incident report

### Fundamental Guarantee
Gold is ALWAYS recoverable by the depositor after `unlockTime`, regardless of system state. The SOSTEscrow contract is immutable with no admin override.

---

## TIMELINE

| Day | Action |
|---|---|
| T-7 | Final review of all GO conditions against this checklist |
| T-5 | Run `verify_mainnet_prereqs.py` -- all checks must pass |
| T-3 | Deploy SOSTEscrow to mainnet, verify on Etherscan |
| T-2 | Update `configs/mainnet_model_b.example.json` with deployed address |
| T-1 | Dry run of deposit flow against mainnet contract (0-value or minimal) |
| T-0 | **Execute deposit** -- record TX hash, depositId, block number |
| T+1 | Verify deposit on Etherscan, register position in SOST registry |
| T+1 | Confirm watcher detected GoldDeposited event |
| T+7 | Week 1 check -- all systems healthy, audit log current |
| T+14 | Midpoint check -- all systems healthy, position tracking correct |
| T+21 | Week 3 check -- prepare withdrawal procedure |
| T+28 | **Maturity** -- execute withdraw, verify tokens returned |
| T+29 | Update position status to REDEEMED |
| T+30 | Write post-mortem document with findings and next steps |

---

## SIGN-OFF

| Role | Name | Date | Decision |
|---|---|---|---|
| Operator (primary) | | | GO / NO-GO |
| Foundation lead | | | GO / NO-GO |

**Final decision**: ______________ (GO / NO-GO)

**Decision date**: ______________

**Target deposit date**: ______________
