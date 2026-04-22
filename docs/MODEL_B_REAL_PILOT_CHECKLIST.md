# Model B Real Pilot Checklist — 1 Month

## Decision
- First pilot: 1 month duration
- Operator-assisted
- Single participant (foundation)
- Small amount (0.1-0.5 oz)

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
