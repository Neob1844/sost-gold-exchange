# Trust Model — Alpha Phase

This document describes what is already cryptographically strong, what depends on the operator, and what should NOT be sold as fully trustless.

## Already Cryptographically Strong

- **ED25519 signatures** on all trade messages (offer, accept, cancel, settlement notice)
- **Canonical hashing** (SHA-256 over deterministic pipe-delimited fields)
- **Nonce anti-replay** (NonceRegistry tracks seen nonces)
- **Deal ID derivation** is deterministic: `SHA256(offer_id:accept_id)[:16]`
- **SOSTEscrow.sol** is immutable — no admin key, no pause, no upgrade proxy
- **Audit entropy** for PoPC uses `SHA256(block_id || commit || checkpoints_root)` — deterministic from block data
- **SOST coinbase split** (50/25/25) is consensus-enforced — invalid blocks are rejected

## Depends on Operator (Alpha)

- **Settlement execution**: the settlement daemon calls `execute_settlement()`, which is operator-triggered. In alpha, a human confirms the settlement after both sides are locked.
- **Refund triggering**: when a deal expires, the refund engine flags it but operator confirms the refund path.
- **Watcher reliability**: if the ETH watcher or SOST watcher goes down, events may be missed. The daemon relies on polling — there is no push notification from either chain.

## Depends on Watchers

- **ETH event detection**: polls Ethereum RPC every 15 seconds, requires 6 block confirmations. If the RPC endpoint is down, events are delayed but not lost (polling resumes).
- **SOST balance detection**: polls SOST node RPC every 10 seconds. If the node is unreachable, detection is delayed.
- **Neither watcher has replay protection at the chain level** — they rely on internal deduplication (seen deposit_id / seen txid).

## NOT Yet Trustless

- **No on-chain settlement finality on SOST**: the settlement daemon writes audit logs and updates state, but there is no SOST on-chain transaction that atomically proves settlement. This is Phase VI work.
- **No decentralized relayer**: trade messages are exchanged between parties but there is no relay network yet. In alpha, the operator facilitates message passing.
- **No automatic refund on Ethereum**: if a deal expires, the ETH escrow tokens remain locked until `unlockTime`. The protocol does not call `withdraw()` — the depositor must do it themselves after expiry.
- **No dispute resolution mechanism**: the DISPUTED state exists but there is no automated arbitration. In alpha, disputes are resolved manually by the operator.

## What Should NOT Be Claimed

- "Fully trustless settlement" — not yet, settlement depends on operator confirmation
- "Decentralized exchange" — the matching is not decentralized, only the escrow is immutable
- "Automatic refund" — ETH refunds require depositor action after timelock expiry
- "Zero counterparty risk" — the watcher/daemon infrastructure introduces operational risk

## Path to Full Trustlessness

1. **On-chain settlement TX on SOST** — an atomic transaction that proves settlement occurred
2. **Decentralized relay network** — P2P message passing without operator intermediation
3. **Automatic ETH refund trigger** — a keeper or bot that calls `withdraw()` on behalf of the depositor after expiry
4. **Multi-operator consensus** — multiple independent settlement daemons that must agree before execution
