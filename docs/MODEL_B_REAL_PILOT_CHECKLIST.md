# Model B Real Pilot Checklist — 1 Month

## Decision
- First pilot: 1 month duration
- Operator-assisted
- Single participant (foundation)
- Small amount (0.1-0.5 oz)

## Sepolia Lifecycle Completion
- [ ] Full deposit-lock-mature-withdraw cycle completed on Sepolia
- [ ] Refund path tested on Sepolia (expired deal -> depositor withdraws)
- [ ] Position tracked from ACTIVE through MATURED to REDEEMED in registry
- [ ] Watcher service detected all on-chain events without manual intervention
- [ ] Audit log contains complete record of Sepolia lifecycle

## Relay / API Verification
- [ ] Relay endpoint reachable and routing trade intents
- [ ] Dashboard API returns correct position data
- [ ] Health monitor script runs without errors
- [ ] Signed offer -> accept -> deal flow tested end-to-end via relay

## Position Lifecycle Tracking Verification
- [ ] Position registry correctly records deposit metadata
- [ ] Position status transitions match on-chain state (ACTIVE -> MATURED -> REDEEMED)
- [ ] Position pricing returns correct value based on gold price and time
- [ ] Position transfer works (change owner, verify new owner can withdraw)
- [ ] Reward right split works correctly

## Go/No-Go Review
- [ ] GO_NO_GO_MODEL_B_MAINNET.md reviewed by operator and foundation
- [ ] All GO conditions satisfied (technical, operational, financial, communication)
- [ ] No NO-GO conditions triggered
- [ ] verify_mainnet_prereqs.py returns all-pass
- [ ] Sign-off recorded with date and decision

## Pre-deployment
- [ ] SOSTEscrow audited externally (or risk accepted for pilot)
- [ ] SOSTEscrow deployed on Ethereum mainnet
- [ ] Contract verified on Etherscan
- [ ] Deployer key secured (hardware wallet recommended)

## Token Setup
- [ ] Foundation wallet has sufficient XAUT or PAXG
- [ ] Escrow approved for spending
- [ ] Balance verified on Etherscan

## SOST Side
- [ ] SOST node running and synced
- [ ] PoPC Pool has sufficient balance for reward
- [ ] Reward calculation verified (0.4% of gold value for 1 month)
- [ ] Position registry ready

## Deposit Execution
- [ ] Deposit amount confirmed
- [ ] Lock duration = 28 days minimum
- [ ] TX submitted and confirmed (6+ blocks)
- [ ] depositId recorded
- [ ] GoldDeposited event verified
- [ ] Position registered in SOST position_registry

## Monitoring
- [ ] Watcher service running
- [ ] Dashboard accessible
- [ ] Audit log recording
- [ ] Daily health checks scheduled

## Expiration & Withdrawal
- [ ] Calendar reminder set for unlock date
- [ ] Withdraw procedure documented
- [ ] Withdraw TX tested (Sepolia first)
- [ ] Post-withdraw: position status updated
- [ ] Post-withdraw: audit log entry

## Risk Limits
- [ ] Max amount: 0.5 oz (pilot)
- [ ] Max value: ~$1,500 at current gold price
- [ ] Duration: 28 days exactly
- [ ] Single participant only
- [ ] No public announcement until cycle complete
