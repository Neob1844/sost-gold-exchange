# Phase VI — Sepolia Deployment, Live E2E, Operator Tools & Signed Message Integration

## What Phase VI Adds

Phase V hardened the crypto layer and built the settlement test suite. Phase VI makes it operational:

- **Sepolia testnet deployment** of MockERC20 (XAUT, PAXG) and SOSTEscrow via Foundry
- **Live end-to-end demo** with real Sepolia events and SOST RPC polling
- **Operator CLI tools** for deal inspection, audit review, and manual intervention
- **Dashboard API** (Flask) for real-time deal monitoring on port 8080
- **ED25519 signed message integration** into the daemon message flow (offer, accept, cancel, settlement notice all carry real signatures)
- **Deployment capture script** that reads Forge broadcast output and updates all config files automatically

## How to Deploy to Sepolia

### Prerequisites

- Foundry installed (`foundryup`)
- Sepolia ETH in deployer wallet (faucet: https://sepoliafaucet.com)
- `.env` file in `contracts/ethereum/` with `DEPLOYER_PRIVATE_KEY` and `SEPOLIA_RPC_URL`

### Deploy contracts

```bash
# Option A: automated deploy + address capture
python3 scripts/sepolia_deploy_capture.py --deploy

# Option B: manual Foundry deploy
cd contracts/ethereum
forge create test/MockERC20.sol:MockERC20 \
  --constructor-args "Mock XAUT" "XAUT" 6 \
  --rpc-url $SEPOLIA_RPC_URL --private-key $DEPLOYER_KEY

forge create test/MockERC20.sol:MockERC20 \
  --constructor-args "Mock PAXG" "PAXG" 18 \
  --rpc-url $SEPOLIA_RPC_URL --private-key $DEPLOYER_KEY

forge create SOSTEscrow.sol:SOSTEscrow \
  --constructor-args $MOCK_XAUT_ADDRESS $MOCK_PAXG_ADDRESS \
  --rpc-url $SEPOLIA_RPC_URL --private-key $DEPLOYER_KEY
```

### Save addresses

After deployment, addresses are written to `configs/sepolia_contracts.json` and `src/integration/live_eth_config.py` automatically if you use the capture script. Otherwise, update them manually.

## How to Run the Live Demo

### Mock mode (no network required)

```bash
python3 scripts/demo_end_to_end.py --mode mock
python3 scripts/demo_refund_flow.py
```

Mock mode simulates the full settlement and refund lifecycles with synthetic events. No Sepolia connection or SOST node needed.

### Live mode (requires deployed contracts + SOST node)

```bash
# 1. Ensure contracts are deployed (see above)
# 2. Ensure SOST node is running and accessible
# 3. Copy and configure live config
cp configs/live_alpha.example.json configs/live_alpha.local.json
# Edit live_alpha.local.json with your addresses, RPC credentials, wallet addresses

# 4. Run live demo
python3 scripts/demo_end_to_end.py --mode live
```

Live mode connects to Sepolia RPC for ETH event detection and SOST node RPC for balance confirmation.

## How to Use Operator CLI Tools

```bash
# List all deals in the store
python3 scripts/operator_list_deals.py

# Inspect a specific deal
python3 scripts/operator_show_deal.py --deal-id <deal_id>

# Show full audit trail
python3 scripts/operator_show_audit.py

# Show audit for a specific deal
python3 scripts/operator_show_audit.py --deal-id <deal_id>
```

## How to Start the Dashboard API

```bash
python3 scripts/dashboard_api.py
# Starts Flask server on http://localhost:8080
# Endpoints:
#   GET /deals          — list all deals
#   GET /deals/<id>     — single deal detail
#   GET /audit          — full audit log
#   GET /audit/<id>     — deal-specific audit
#   GET /health         — watcher and daemon status
```

## Test Commands

```bash
# All Python tests
python3 -m pytest tests/ -q

# Integration tests only
python3 -m pytest tests/integration/ -q

# Foundry contract tests
cd contracts/ethereum && forge test -vvv

# TypeScript comms protocol tests
cd ~/SOST/sost-comms-private && npm test
```

## What Is Now Live vs Still Mocked

| Component | Status |
|-----------|--------|
| ED25519 key generation | Live (Node.js crypto) |
| Message signing + verification | Live ED25519 |
| Canonical hashing (SHA-256) | Live |
| Nonce replay detection | Live (NonceRegistry) |
| SOSTEscrow.sol | Live Solidity, Foundry-tested |
| Sepolia deployment pipeline | Live (forge script + capture) |
| Mock token minting | Live on Sepolia |
| ETH watcher (mock mode) | Simulated events |
| ETH watcher (live mode) | Polls real Sepolia RPC |
| SOST watcher (mock mode) | Simulated events |
| SOST watcher (live mode) | Polls real SOST RPC |
| Settlement execution | Operator-triggered (manual confirmation) |
| Refund execution | Operator-triggered |
| Dashboard API | Local Flask server |
| Operator CLI tools | Functional, reads live deal store |

## Current Alpha Limitations

- **Settlement is not atomic**: the daemon writes audit logs and updates state, but there is no on-chain SOST transaction that proves settlement occurred. The operator confirms settlement manually.
- **No automatic ETH refund**: if a deal expires, the depositor must call `withdraw()` on the escrow contract after the timelock expires. There is no keeper or bot to do this automatically.
- **No decentralized relay**: trade messages are exchanged via the operator. There is no P2P relay network yet.
- **No dispute arbitration**: the DISPUTED state exists but resolution is manual.
- **Watcher downtime = delayed detection**: if the ETH or SOST watcher goes offline, events are not lost but detection is delayed until polling resumes.
- **Single operator**: there is no multi-operator consensus. One operator runs the daemon and confirms settlements.
- **Mock tokens only**: XAUT and PAXG on Sepolia are MockERC20 with unrestricted `mint()`. Real gold tokens are not used in alpha.

## What Follows (Phase VII)

1. **On-chain settlement TX on SOST** — an atomic transaction proving settlement occurred, anchored to a SOST block
2. **Automatic ETH refund trigger** — a keeper bot that calls `withdraw()` on behalf of the depositor after timelock expiry
3. **WebSocket event streaming** — real-time push notifications from watchers instead of polling
4. **Multi-operator consensus** — multiple independent settlement daemons that must agree before execution
5. **Decentralized relay network** — P2P message passing without operator intermediation
6. **Production token integration** — replace MockERC20 with real XAUT/PAXG on mainnet
7. **Formal security audit** of SOSTEscrow.sol before mainnet deployment
