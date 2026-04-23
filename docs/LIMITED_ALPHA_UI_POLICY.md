# Limited Alpha UI Policy

Rules and restrictions for the SOST Gold Exchange alpha user interface.

---

## Access Control

- **Allowlisted participants only**: the alpha UI is restricted to pre-approved addresses. Unapproved addresses cannot view positions, create offers, or interact with the exchange.
- **Operator approval required**: every new participant must be explicitly approved by the operator before gaining access.
- **No public registration**: there is no self-service signup. Participants are onboarded individually.

---

## Trading Limits

- **Max concurrent deals per participant**: 3 active (non-terminal) deals at any time
- **Max position size**: capped per participant based on operator assessment
- **Max total exposure**: aggregate gold reference across all positions is capped during alpha
- **Deal expiry**: all deals expire within 1 hour if not fully locked

---

## What the UI Shows

### Positions Page
- All positions visible to the participant (own positions + available-for-trade positions)
- Position details: ID, owner, token, amount, status, time remaining, rewards
- Escrow verification links (Sepolia Etherscan for Model B)

### Deals Page
- Participant's own deals with full state history
- Deal status progression (CREATED through SETTLED/EXPIRED/REFUNDED)
- Lock confirmation timestamps

### Status Dashboard
- Alpha mode indicator (live-alpha)
- Aggregate position and deal counts
- System health (watcher status, last block seen)

### What the UI Does NOT Show
- Other participants' private details (addresses are pseudonymous)
- Internal operator logs or audit entries
- Fee revenue or operator economics
- Mainnet deployment status or timeline

---

## Disclaimers

The following disclaimers are displayed in the alpha UI:

1. **Alpha software**: this is experimental software running on testnets. Bugs may exist. Data may be reset.
2. **No guarantees**: positions carry no yield guarantee. Reward schedules are contractual but depend on system operation.
3. **Operator-assisted**: all settlements are mediated by a single operator. There is no decentralized settlement yet.
4. **Testnet tokens**: gold tokens on Sepolia are mock tokens with no real value. SOST is the real network asset.
5. **Not financial advice**: participation in the alpha is for testing and evaluation only.
6. **Data retention**: all actions are logged in an append-only audit trail for dispute resolution.

---

## Participant Responsibilities

- Keep private keys secure; the operator cannot recover lost keys
- Report bugs or unexpected behavior to the operator
- Do not attempt to exploit or stress-test without prior coordination
- Understand that alpha parameters (fees, limits, expiries) may change with notice
