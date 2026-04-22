# Live Alpha Checklist

Step-by-step checklist for deploying and running the SOST settlement alpha on Sepolia testnet.

## Pre-deployment

- [ ] Sepolia ETH funded in deployer wallet
- [ ] .env configured with private key (`contracts/ethereum/.env`)
- [ ] Foundry installed and forge-std present (`foundryup`)
- [ ] Python 3.10+ with pytest installed
- [ ] Node.js 18+ for comms protocol (optional)

## Deployment

- [ ] MockERC20 XAUT deployed (6 decimals)
- [ ] MockERC20 PAXG deployed (18 decimals)
- [ ] SOSTEscrow deployed (constructor takes XAUT + PAXG addresses)
- [ ] Addresses saved to `configs/sepolia_contracts.json`
- [ ] `live_alpha.local.json` configured with deployed addresses

## Token Setup

- [ ] Mock XAUT minted to taker address (`cast send $XAUT "mint(address,uint256)" $TAKER 1000000`)
- [ ] Mock PAXG minted (optional, same pattern with 18-decimal amounts)
- [ ] Escrow approved for token spending (`cast send $XAUT "approve(address,uint256)" $ESCROW $AMOUNT`)

## SOST Side

- [ ] SOST node running and synced
- [ ] RPC accessible at configured URL (default: `http://127.0.0.1:18232`)
- [ ] RPC credentials set in config (rpc_user, rpc_pass)
- [ ] Maker SOST address funded with sufficient SOST for test deals
- [ ] If remote node: SSH tunnel established (`ssh -L 18232:127.0.0.1:18232 host`)

## Watcher Verification

- [ ] ETH watcher can reach Sepolia RPC (test: `curl -s $SEPOLIA_RPC_URL`)
- [ ] SOST watcher can reach SOST node RPC (test: `curl -s http://127.0.0.1:18232`)
- [ ] Test poll returns data (run watcher in debug mode to confirm first event)

## Demo Execution

- [ ] `python3 scripts/demo_end_to_end.py --mode mock` passes
- [ ] `python3 scripts/demo_end_to_end.py --mode live` connects (requires deployed contracts)
- [ ] `python3 scripts/demo_refund_flow.py` passes
- [ ] `python3 scripts/demo_live_refund.py --mode mock` passes (if present)

## Operator Tools

- [ ] `python3 scripts/operator_list_deals.py` runs and returns deal list
- [ ] `python3 scripts/operator_show_deal.py --deal-id <id>` runs with valid deal ID
- [ ] `python3 scripts/operator_show_audit.py` runs and shows audit entries
- [ ] `python3 scripts/dashboard_api.py` starts on port 8080
- [ ] `curl http://localhost:8080/health` returns OK

## Post-deployment Verification

- [ ] `configs/sepolia_contracts.json` contains non-zero addresses
- [ ] `src/integration/live_eth_config.py` updated with deployed addresses
- [ ] Foundry contract tests still pass (`cd contracts/ethereum && forge test`)
- [ ] Full Python test suite passes (`python3 -m pytest tests/ -q`)

## Security Checklist

- [ ] Deployer private key is a testnet-only key (NEVER use mainnet keys)
- [ ] `.env` file is in `.gitignore` and not committed
- [ ] `live_alpha.local.json` is in `.gitignore` and not committed
- [ ] Mock tokens have unrestricted `mint()` — acknowledged as test-only
- [ ] Settlement daemon is not exposed to untrusted networks
