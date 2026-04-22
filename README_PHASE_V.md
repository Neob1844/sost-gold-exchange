# Phase V — Crypto Hardening, Escrow Tests, Adversarial Coverage & Live Integration Alpha

## What Phase V Adds

Phase IV demonstrated the vertical slice was alive. Phase V converts it into a cryptographically real alpha:

- **ED25519 real signatures** on all trade messages (offer, accept, cancel, settlement notice)
- **Foundry test suite** for the SOSTEscrow.sol Ethereum contract
- **Adversarial tests** covering replay, duplicate events, mismatched locks, expiry races, concurrent settlement, double transfers, and reward over-allocation
- **Live integration config** for Sepolia testnet + SOST RPC
- **Demo scripts** showing the full settlement and refund flows

## How to Run Tests

### Python (settlement stack + adversarial)
```bash
python3 -m pytest tests/ -q
```

### TypeScript (trade protocol + ED25519 crypto)
```bash
cd ~/SOST/sost-comms-private
npm install
npm test
```

### Foundry (SOSTEscrow.sol)
```bash
cd contracts/ethereum
./run_tests.sh
# Or directly: forge test -vvv
```

### Demo scripts
```bash
# Happy path settlement
python3 scripts/demo_end_to_end.py --mode mock

# Refund path
python3 scripts/demo_refund_flow.py
```

## What Is Cryptographically Real

| Component | Status |
|-----------|--------|
| ED25519 key generation | Real (Node.js crypto) |
| Message signing (canonicalHash → signature) | Real ED25519 |
| Signature verification | Real ED25519 |
| Canonical hashing (SHA-256) | Real |
| Nonce replay detection | Real (NonceRegistry) |
| SOSTEscrow.sol | Real Solidity, Foundry-tested |

## What Is Still Mocked

| Component | Status |
|-----------|--------|
| Sepolia deployment | Config ready, contracts not yet deployed |
| ETH watcher in live mode | Polls real RPC, but no live escrow to watch |
| SOST watcher in live mode | Connects to real RPC, needs active deals |
| Settlement execution | Operator-triggered (manual confirmation in alpha) |
| Refund execution | Operator-triggered |

## What Follows

1. Deploy MockERC20 + SOSTEscrow on Sepolia
2. Run first live end-to-end with real Sepolia events
3. Connect to SOST mainnet node for real lock detection
4. Integrate ED25519 signing into the daemon message flow
5. Add WebSocket event streaming for real-time monitoring
