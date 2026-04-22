# Sepolia Alpha Runbook

Step-by-step guide to deploying and running the SOST settlement alpha on Sepolia testnet.

## Prerequisites

- **Foundry** installed: `curl -L https://foundry.paradigm.xyz | bash && foundryup`
- **Sepolia ETH** in a test wallet (get from a faucet: https://sepoliafaucet.com)
- **SOST node** running locally with RPC enabled (port 18232)
- **Python 3.10+** with `pytest` installed
- **Node.js 18+** for comms protocol tests

## Step 1: Deploy Mock Tokens on Sepolia

```bash
cd contracts/ethereum

# Deploy MockERC20 as XAUT (6 decimals)
forge create test/MockERC20.sol:MockERC20 \
  --constructor-args "Mock XAUT" "XAUT" 6 \
  --rpc-url https://rpc.sepolia.org \
  --private-key $DEPLOYER_KEY

# Deploy MockERC20 as PAXG (18 decimals)
forge create test/MockERC20.sol:MockERC20 \
  --constructor-args "Mock PAXG" "PAXG" 18 \
  --rpc-url https://rpc.sepolia.org \
  --private-key $DEPLOYER_KEY

# Note the deployed addresses
```

## Step 2: Deploy SOSTEscrow

```bash
# Replace with actual addresses from Step 1
forge create SOSTEscrow.sol:SOSTEscrow \
  --constructor-args $MOCK_XAUT_ADDRESS $MOCK_PAXG_ADDRESS \
  --rpc-url https://rpc.sepolia.org \
  --private-key $DEPLOYER_KEY

# Note the escrow address
```

## Step 3: Configure Integration

Edit `src/integration/live_eth_config.py`:
```python
SEPOLIA_RPC = "https://rpc.sepolia.org"
MOCK_XAUT_ADDRESS = "0x..."  # from Step 1
MOCK_PAXG_ADDRESS = "0x..."  # from Step 1
ESCROW_ADDRESS = "0x..."     # from Step 2
```

Edit `src/integration/live_sost_config.py`:
```python
SOST_RPC_URL = "http://127.0.0.1:18232"
SOST_RPC_USER = "sost"
SOST_RPC_PASS = "your_password"
```

## Step 4: Mint Test Tokens

```bash
# Mint 1 XAUT (1e6 units) to the taker address
cast send $MOCK_XAUT_ADDRESS "mint(address,uint256)" \
  $TAKER_ADDRESS 1000000 \
  --rpc-url https://rpc.sepolia.org \
  --private-key $DEPLOYER_KEY

# Approve escrow to spend taker's XAUT
cast send $MOCK_XAUT_ADDRESS "approve(address,uint256)" \
  $ESCROW_ADDRESS 1000000 \
  --rpc-url https://rpc.sepolia.org \
  --private-key $TAKER_KEY
```

## Step 5: Run Demo in Mock Mode (Verify Setup)

```bash
python3 scripts/demo_end_to_end.py --mode mock
```

## Step 6: Run Demo in Live Mode

```bash
python3 scripts/demo_end_to_end.py --mode live
```

**Note:** Live mode requires deployed contracts (Steps 1-3) and funded wallets (Step 4). Until deployment is complete, use mock mode.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `forge: command not found` | Install Foundry: `foundryup` |
| Sepolia RPC timeout | Try alternative: `https://1rpc.io/sepolia` |
| SOST RPC connection refused | Verify node is running: `curl -s http://127.0.0.1:18232` |
| Insufficient Sepolia ETH | Get from faucet: https://sepoliafaucet.com |
| Mock token deploy fails | Check gas, verify Foundry is latest version |

## Security Notes

- **NEVER use mainnet private keys** for Sepolia testing
- **NEVER deploy to mainnet** without full audit
- Mock tokens have unrestricted `mint()` — this is intentional for testing only
- The settlement daemon runs with operator privileges — do not expose to untrusted networks
