# SOST — Production Readiness Checklist

## Model B Lifecycle

- [x] Position creation (create_model_b)
- [x] Full position transfer
- [x] Reward-right split
- [x] Beneficiary handoff model
- [x] Maturity tracking (ACTIVE → NEARING → MATURED)
- [x] Auto-withdraw logic (MATURED → WITHDRAWN)
- [x] Reward settlement (→ REWARD_SETTLED)
- [x] Position finality (→ CLOSED + bond release)
- [x] Reconciliation / audit log
- [ ] Live ETH withdrawal execution (currently generates command)
- [ ] Live beneficiary sync execution (currently generates command)
- [ ] Live proof: full sale → maturity → withdraw → reward → close
- [ ] Live proof: reward-only sale → correct ownership split

## Model A Lifecycle

- [x] Position creation (create_model_a)
- [x] Bond posting (field tracked)
- [x] Custody verification daemon (alpha + live mode)
- [x] Epoch-based audit scheduling (7-day epochs)
- [x] Auto-slash after grace period (7 days)
- [x] Ethereum RPC balance check (ERC-20 balanceOf)
- [x] Reward settlement
- [x] Bond release at finality
- [x] Position finality (REWARD_SETTLED → CLOSED)
- [x] Reward-right split works for Model A
- [x] Full position transfer blocked (by design)
- [ ] Live proof: successful audit path → maturity → bond release → close
- [ ] Live proof: failed audit → grace → slash → close

## DEX Web

- [x] Browser crypto (ED25519, X25519, ChaCha20-Poly1305)
- [x] Keystore (IndexedDB, Argon2id)
- [x] Relay client
- [x] Trade engine (build/sign/encrypt/send)
- [x] Private inbox
- [x] Recipient directory
- [x] Session manager (auto-lock)
- [x] Passkey / WebAuthn
- [x] AI intent parser (EN + ES)
- [x] AI form assistant
- [x] AI deal explainer
- [x] AI risk guardian
- [x] AI compare helper
- [x] AI lifecycle guide
- [x] UI integration (onboarding module)
- [x] Wallet panel in DEX page
- [x] Identity bar
- [x] Status bar
- [x] AI input box
- [x] Inbox section
- [ ] Live proof: create identity → unlock → AI fill → sign → encrypt → send
- [ ] Live proof: receive message → decrypt → view in inbox
- [ ] Live proof: deal channel with real encrypted messages

## E2E / Relay

- [x] 231 TypeScript tests passing
- [x] Browser crypto envelope compatibility with Node.js
- [x] 60+ browser crypto tests (dex-crypto-test.html)
- [x] Relay HTTP API (submit, fetch, ack, prekeys, deals)
- [ ] Live proof: browser → relay → browser (two identities)

## Operations

- [x] Controlled gates documented (CONTROLLED_GATES.md)
- [x] Operator runbook (OPERATOR_RUNBOOK.md)
- [x] Production verdict (PHASE_E_PRODUCTION_VERDICT.md)
- [x] Model A status checker script (check_model_a_status.py)
- [ ] Staging drill with real data
- [ ] Recovery drill (keystore loss + reimport)
- [ ] Multi-daemon concurrent execution test

## Documentation Alignment

- [x] Protocol fees 3%/8% consistent everywhere
- [x] Foundation → Governance rename complete
- [x] PoPC timeline consistent (block 10,000+ / April 2027)
- [x] Model A/B status accurately described
- [x] DEX alpha status with "controlled gates" language
- [x] Help-us-improve section in explorer banner

## Test Summary

| Suite | Count | Status |
|-------|-------|--------|
| C++ (cASERT, consensus) | 193 | PASSING |
| Python (positions, deals, settlement) | 294 | PASSING |
| TypeScript (E2E, relay, crypto) | 231 | PASSING |
| Solidity (SOSTEscrow) | 47 | PASSING |
| Browser (dex-crypto-test.html) | 60+ | PASSING |
| **TOTAL** | **825+** | **ALL PASSING** |
