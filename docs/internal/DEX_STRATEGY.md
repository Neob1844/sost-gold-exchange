# SOST POSITION MARKET — Strategic Internal Document

## Classification: Internal — Foundation Only
## Date: April 22, 2026
## Author: NeoB

---

## 1. Architecture Decision

The SOST market will NOT begin as a traditional AMM (Automated Market Maker) like Uniswap. The primary tradeable asset is not a fungible token, but identified positions and contractual rights with expiry, reward schedules, and precious-metal backing.

Accordingly, the correct initial model is a **private OTC/RFQ market for native positions and rights**, coordinated through signed private messages and settled through the SOST registry and settlement engine with full audit trail.

This decision is driven by three factors:
- **Asset structure:** identified contracts and rights, not fungible pool assets
- **Legal risk reduction:** identified positions are structurally safer than launching a broad public token market from day one
- **Technical fit:** signed offers/accepts + settlement engine fit the product better than liquidity pools

**Important clarification:**
Phase 1 should not be described externally as a "public DEX" or "open exchange."
Phase 1 is better described as a **limited, operator-assisted signed market for identified positions and rights**.

---

## 2. What Can Be Traded

### Phase 1 — Current Alpha

**Model B — Full Position**
A complete Model B position (e.g. 0.5 oz XAUT locked for 28 days plus its associated reward). The seller transfers the entire position to the buyer. Ownership changes in the SOST position registry. The escrow backing remains unchanged on Ethereum/Sepolia.

**Model B — Reward Right Only**
The owner keeps the gold-backed principal but sells only the right to the future SOST reward. The system creates a child reward-only position for the buyer. The parent keeps the principal and loses the reward claim.

### Phase 2 — Near-Term

**Model A — Reward Right Only**
Model A remains in autocustody. The gold stays in the user's own wallet and the custody obligation remains tied to the original holder. Selling only the reward right is the cleanest entry path for Model A: the custodian continues to hold and pass audits, while the economic reward is transferred separately.

**Model A — Claim / Novation (Controlled)**
A transfer of the full Model A position to a new holder is possible only as a controlled novation process. This requires:
- revalidation of the new holder's custody capability
- possible additional bond or guarantee
- explicit acceptance by all required parties
- operator approval during alpha
- legal review before any wider rollout

Model A full-position transfer is NOT a Phase 1 feature.

### Phase 3 — Future

**XAUT/PAXG Entry / Exit Rail**
Ethereum-based tokenized gold should not be the core market mechanism. It should function only as a minimal onboarding and exit rail:
- convert tokenized gold into a native SOST position
- exit a native position back to an external tokenized-gold rail where appropriate

SOST remains the sovereign center for registration, trading, and settlement.

---

## 3. How a Trade Works

1. The seller creates a **signed offer:**
   - ED25519 signature
   - canonical hash
   - unique nonce
   - expiry
   - explicit asset_type and position_id / reward-right reference

2. The buyer responds with a **signed accept**.

3. The system derives a deterministic **deal_id:**
   `SHA256(offer_id:accept_id)[:16]`

4. The settlement engine verifies:
   - the seller is the actual owner of the position or right being sold
   - the position exists and is active
   - the offer has not expired
   - the signature is cryptographically valid
   - the nonce has not already been used
   - no duplicate or double-spend condition exists

5. If all checks pass, the engine executes:
   - full position transfer, OR
   - reward-right split / reassignment

6. A signed **settlement_notice** is emitted.

7. A complete **audit trail** is recorded.

This is not "upload token and someone swaps it."
This is: **"an identified right or position is offered, accepted, validated, and reassigned under explicit rules."**

---

## 4. Economic Logic

### Why sell?

A seller may want:
- immediate liquidity instead of waiting for lock expiry
- early exit to reduce exposure
- capital rotation into another opportunity
- to sell only the future reward while keeping the principal
- to avoid maturity/withdraw operational burden

### Why buy?

A buyer may want:
- to buy a position at a discount
- to capture future reward by waiting
- gold-backed exposure without originating a contract from scratch
- portfolio construction across maturities and risk profiles

### Core principle

**The market exists because the same position does not have the same value for everyone.** Some participants value liquidity today more highly; others value future payoff more highly.

This is economically analogous to:
- selling a bond before maturity
- discounting a future payment
- separating coupon from principal
- factoring a receivable

The principle is the same: **there is future value, and the market determines what it is worth today.**

---

## 5. Regulatory Risk Framework

### 5.1 General Approach

There is no safe strategy based on naming alone.
What matters is the real substance of the system:
- whether it is public or restricted
- whether it functions like a trading platform
- whether the traded objects behave like ordinary crypto-assets, identified contracts, or financial instruments
- whether access is open or controlled
- whether the system is operator-assisted or broadly automated and public

Therefore, the objective is not to "evade" regulation by wording.
**The objective is to design a phased market structure that reduces unnecessary regulatory triggers in early phases while preserving technical and economic functionality.**

### 5.2 MiCA Sensitivity

A fully public trading platform for crypto-assets can trigger substantial operational obligations under MiCA, including transparent operating rules, public market data obligations, resilience obligations, and defined settlement requirements.

For that reason, Phase 1 must remain:
- limited
- operator-assisted
- participant-restricted
- position-based
- non-mass-market

### 5.3 Financial Instrument Risk

If positions, reward rights, or claims are structured in a way that resembles transferable securities, derivatives, or other financial instruments, MiCA may not be the main framework. A stricter legal analysis could then apply.

This is one of the main reasons why:
- positions should remain identified
- reward rights should be carefully described
- broad public fungibilisation should be avoided without legal review

### 5.4 Spanish Context

Given the Spanish transition into the MiCA regime, broad public rollout should remain a later-stage decision.
The safer path is:
- internal alpha
- limited user alpha
- legal review
- only then consider broader public opening

---

## 6. Regulatory Trigger Matrix

| Feature | Risk | Phase 1 | Legal Review |
|---------|------|---------|--------------|
| Limited operator-assisted bilateral position trade | Lower | Allowed internally | Recommended, not blocking for internal alpha |
| Public order book | High | **Not allowed** | Mandatory before any rollout |
| Unrestricted public API for trading | High | **Not allowed** | Mandatory |
| Public market making | High | **Not allowed** | Mandatory |
| Model B full-position transfer | Moderate | Allowed in limited alpha | Recommended before broader use |
| Model B reward-right trading | Moderate | Allowed in limited alpha | Recommended before broader use |
| Model A reward-right trading | Moderate | Phase 2 | Strongly recommended |
| Model A full-position novation | Higher | Phase 2+ | Mandatory before rollout |
| Fungible public tokenisation of claims | High | **Not allowed** | Mandatory |

---

## 7. Model A vs Model B — Market Treatment

### Model B (Escrow)

| Tradeable | Phase | Notes |
|-----------|-------|-------|
| Full position | Phase 1 | Cleanest transfer path; backing sits in escrow |
| Reward right | Phase 1 | Principal retained, reward sold separately |
| Secondary market | Phase 1 | Only in limited, operator-assisted mode |

### Model A (Autocustody)

| Tradeable | Phase | Notes |
|-----------|-------|-------|
| Reward right only | Phase 2 | Cleanest separation without changing custody holder |
| Claim / economic right | Phase 2 | May be represented in registry without changing custodial obligation |
| Full position novation | Phase 2+ | Requires stronger controls, explicit approval, and legal review |

### Why Model A is different

In Model A, the principal is more tightly linked to:
- custodian identity
- custody proof
- audit performance
- holder-specific compliance risk

Therefore, **Model A must not be treated identically to Model B in early market phases.**

---

## 8. Recommended Phased Approach

### Phase 1 — Current Alpha
- Model B full-position trades
- Model B reward-right trades
- signed messages only
- no public order book
- no unrestricted API
- 2–3 test participants maximum
- foundation positions only
- full audit trail
- operator-assisted only

### Phase 2 — Limited Public Alpha
- Model A reward rights enter the market
- Model A claims / controlled novation paths begin under approval
- participant cap increased cautiously
- public position display permitted
- relay access only for approved participants
- operator-assisted settlement remains

### Phase 3 — Broader Market (only after legal review)
- public RFQ board and/or broader access
- entry/exit rails expanded
- wider participant base
- further automation
- **legal go/no-go decision required before this phase**

---

## 9. What Must NOT Be Done Before Legal Review

1. Do NOT open a public order book or matching engine
2. Do NOT market the system as an unrestricted public DEX
3. Do NOT provide unrestricted public trading API access
4. Do NOT describe positions as guaranteed-return products
5. Do NOT promise safe, fixed, or assured yield
6. Do NOT treat identified positions as broadly fungible public tokens
7. Do NOT launch mainnet public trading before legal analysis of MiCA/MiFID II boundaries

---

## 10. Definition of "Position"

For internal and external consistency, a "position" should be defined as:

> **"An identified contractual record within the SOST registry, linked to a specific backing structure, maturity profile, and rights configuration, and not a mass fungible public token admitted to unrestricted broad public trading."**

This definition is strategically important and should remain consistent across technical, operational, and public documentation.

---

## 11. Technical Readiness Summary

| Component | Status | Ready for Phase 1 |
|-----------|--------|-------------------|
| Position registry | Operational | Yes |
| Full position transfer | Operational | Yes |
| Reward-right split | Operational | Yes |
| ED25519 signing | Operational | Yes |
| Relay node with deal channels | Operational | Yes |
| Settlement engine | Operational | Yes |
| SOSTEscrow contract | Deployed on Sepolia | Yes (testnet) |
| Operator dashboard/API | Operational | Yes |
| Lifecycle tracking | Operational | Yes |
| Mainnet deployment | Prepared, not executed | Pending legal + Go/No-Go |
| Public open market | **NOT approved** | Pending legal review |

---

## 12. Summary

The SOST market should begin as a **private, signed market for identified positions and rights** — not as a public mass token exchange.

**Phase 1:** Model B full positions + reward rights
**Phase 2:** Model A reward rights + controlled claims
**Phase 3:** Broader market (legal review required)

**Core principle:**
trade contracts, not pools;
identify positions, not mass tokens;
coordinate privately, settle verifiably.

---

*End of document.*
