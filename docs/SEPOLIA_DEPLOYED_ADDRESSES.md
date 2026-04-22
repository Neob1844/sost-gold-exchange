# Sepolia Deployed Addresses

## Status: PENDING DEPLOYMENT

| Contract | Address | Verified |
|----------|---------|----------|
| MockERC20 XAUT | TBD | No |
| MockERC20 PAXG | TBD | No |
| SOSTEscrow | TBD | No |

Chain: Sepolia (chain_id: 11155111)
Deployed at block: TBD
Deployer: TBD

## Contract Details

| Contract | Constructor Args | Source |
|----------|-----------------|--------|
| MockERC20 XAUT | ("Mock XAUT", "XAUT", 6) | test/MockERC20.sol |
| MockERC20 PAXG | ("Mock PAXG", "PAXG", 18) | test/MockERC20.sol |
| SOSTEscrow | (XAUT_address, PAXG_address) | SOSTEscrow.sol |

## How to Verify on Etherscan

After deployment, verify each contract on Sepolia Etherscan:

### Option A: Forge verify (recommended)

```bash
cd contracts/ethereum

# Verify MockERC20 XAUT
forge verify-contract $MOCK_XAUT_ADDRESS test/MockERC20.sol:MockERC20 \
  --chain sepolia \
  --constructor-args $(cast abi-encode "constructor(string,string,uint8)" "Mock XAUT" "XAUT" 6) \
  --etherscan-api-key $ETHERSCAN_API_KEY

# Verify MockERC20 PAXG
forge verify-contract $MOCK_PAXG_ADDRESS test/MockERC20.sol:MockERC20 \
  --chain sepolia \
  --constructor-args $(cast abi-encode "constructor(string,string,uint8)" "Mock PAXG" "PAXG" 18) \
  --etherscan-api-key $ETHERSCAN_API_KEY

# Verify SOSTEscrow
forge verify-contract $ESCROW_ADDRESS SOSTEscrow.sol:SOSTEscrow \
  --chain sepolia \
  --constructor-args $(cast abi-encode "constructor(address,address)" $MOCK_XAUT_ADDRESS $MOCK_PAXG_ADDRESS) \
  --etherscan-api-key $ETHERSCAN_API_KEY
```

### Option B: Manual verification

1. Go to `https://sepolia.etherscan.io/address/<contract_address>#code`
2. Click "Verify & Publish"
3. Select compiler version matching `foundry.toml`
4. Paste flattened source (`forge flatten <source_file>`)
5. Provide constructor arguments in ABI-encoded hex

### Checking verification status

```bash
forge verify-check $GUID --chain sepolia --etherscan-api-key $ETHERSCAN_API_KEY
```

## Machine-readable addresses

Deployed addresses are also stored in `configs/sepolia_contracts.json`:

```json
{
  "chain": "sepolia",
  "chain_id": 11155111,
  "deployed_at_block": 0,
  "deployed_at": "",
  "mock_xaut": "0x0000000000000000000000000000000000000000",
  "mock_paxg": "0x0000000000000000000000000000000000000000",
  "escrow": "0x0000000000000000000000000000000000000000",
  "deployer": ""
}
```

This file is updated automatically by `scripts/sepolia_deploy_capture.py`.
