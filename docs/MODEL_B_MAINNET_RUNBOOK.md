# Model B Mainnet Runbook

Step-by-step operations guide for running Model B escrow on Ethereum mainnet.

---

## 1. Deploy SOSTEscrow on Mainnet

### Prerequisites
- Deployer wallet funded with ETH for gas (~0.05 ETH minimum)
- Hardware wallet recommended for deployer key
- Foundry installed (`forge --version`)

### Steps
```bash
# Set environment
export ETH_RPC_URL="https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
export DEPLOYER_PRIVATE_KEY="..."  # USE HARDWARE WALLET IN PRODUCTION

# Deploy
cd contracts/
forge script script/DeployEscrow.s.sol:DeployEscrow \
  --rpc-url $ETH_RPC_URL \
  --broadcast \
  --verify \
  --etherscan-api-key YOUR_ETHERSCAN_KEY
```

### Record
- Contract address: `0x___`
- Deploy TX: `0x___`
- Block number: `___`
- Update `configs/mainnet_model_b.example.json` with the deployed address

---

## 2. Verify on Etherscan

If `--verify` failed during deploy:
```bash
forge verify-contract \
  --chain-id 1 \
  --compiler-version v0.8.24 \
  --etherscan-api-key YOUR_KEY \
  CONTRACT_ADDRESS \
  src/SOSTEscrow.sol:SOSTEscrow
```

Confirm:
- [ ] Source code visible on Etherscan
- [ ] Read/Write contract tabs work
- [ ] Owner matches deployer

---

## 3. Execute a Deposit

### Pre-checks
```bash
# Verify token balance
python3 scripts/verify_mainnet_prereqs.py

# Confirm escrow is ready
cast call $ESCROW_ADDRESS "depositCount()(uint256)" --rpc-url $ETH_RPC_URL
```

### Approve and Deposit
```bash
# Approve escrow to spend XAUT (amount in wei, e.g. 0.1 oz = 100000000000000000)
cast send $XAUT_ADDRESS \
  "approve(address,uint256)" \
  $ESCROW_ADDRESS $AMOUNT \
  --rpc-url $ETH_RPC_URL \
  --private-key $DEPOSITOR_KEY

# Deposit with lock duration (28 days = 2419200 seconds)
cast send $ESCROW_ADDRESS \
  "deposit(address,uint256,uint256)" \
  $XAUT_ADDRESS $AMOUNT 2419200 \
  --rpc-url $ETH_RPC_URL \
  --private-key $DEPOSITOR_KEY
```

### Record
- Deposit TX: `0x___`
- depositId: `___`
- Amount: `___`
- Lock until: `___` (unix timestamp)

### Register on SOST Side
```bash
python3 scripts/operator_register_model_b.py \
  --owner SOST_ADDRESS \
  --token XAUT \
  --amount AMOUNT_WEI \
  --duration-days 28 \
  --deposit-id DEPOSIT_ID \
  --eth-tx TX_HASH
```

---

## 4. Monitor During Lock Period

### Daily Checks
```bash
# Health check script
bash scripts/check_alpha_health.sh

# Verify deposit still locked
python3 scripts/check_sepolia_deposit.py --deposit-id DEPOSIT_ID

# Check position status
python3 scripts/operator_show_positions.py

# Review audit log
python3 scripts/operator_show_audit.py
```

### Automated Watcher
The watcher service monitors on-chain events. Ensure it is running:
```bash
bash scripts/start_alpha_stack.sh
```

### Alerts
Monitor for:
- Escrow contract balance changes
- Unexpected withdrawal attempts
- SOST node sync issues
- Watcher service crashes

---

## 5. Withdraw After Expiry

### Pre-checks
```bash
# Verify lock has expired
cast call $ESCROW_ADDRESS \
  "deposits(uint256)(address,address,uint256,uint256,uint256,bool)" \
  $DEPOSIT_ID --rpc-url $ETH_RPC_URL
```

Confirm the unlock timestamp is in the past.

### Execute Withdrawal
```bash
cast send $ESCROW_ADDRESS \
  "withdraw(uint256)" \
  $DEPOSIT_ID \
  --rpc-url $ETH_RPC_URL \
  --private-key $DEPOSITOR_KEY
```

### Post-Withdrawal
1. Verify tokens returned to depositor wallet
2. Update position status on SOST side:
   ```bash
   # Position should be marked REDEEMED via the operator or automatically
   python3 scripts/operator_show_positions.py
   ```
3. Record in audit log

---

## 6. Handling Failures

### Deposit TX Fails
- Check gas price and retry
- Verify token approval is sufficient
- Confirm escrow contract is not paused

### Watcher Misses an Event
- Manually query the escrow contract for the deposit
- Register position manually via `operator_register_model_b.py`
- Cross-reference with Etherscan event logs

### SOST Node Goes Down
- Restart node, wait for sync
- Positions are persisted in `data/positions.json`
- Audit log is append-only and survives restarts

### Withdrawal Fails
- Verify lock period has truly expired (check block timestamp, not wall clock)
- Check that deposit has not already been withdrawn
- If contract is paused, contact deployer/owner to unpause

---

## 7. Emergency Procedures

### Suspected Exploit
1. **Do NOT withdraw** — assess first
2. Check escrow contract balance on Etherscan
3. Check for unauthorized transactions
4. If contract has `pause()`, consider pausing
5. Document everything in audit log

### Private Key Compromise
1. If escrow owner key: pause contract immediately
2. If depositor key: withdraw immediately if lock expired; otherwise monitor
3. Rotate all related keys
4. File incident report

### Gold Token Depeg
1. Monitor XAUT/PAXG price vs spot gold
2. If >2% deviation, halt new deposits
3. Existing positions: let them run to maturity unless systemic risk
4. Document decision in audit log

---

## 8. Contact and Escalation

| Role | Contact | When |
|---|---|---|
| Operator (primary) | Internal | Daily operations, routine issues |
| Deployer/Owner | Internal | Contract pause, upgrades, emergencies |
| Ethereum support | Alchemy/Infura dashboard | RPC issues, rate limits |
| Etherscan | etherscan.io/contactus | Verification issues |

### Escalation Path
1. **L1 — Operator**: Routine monitoring, position management
2. **L2 — Foundation**: Deposit/withdrawal decisions, limit changes
3. **L3 — Emergency**: Key compromise, exploit, contract pause
