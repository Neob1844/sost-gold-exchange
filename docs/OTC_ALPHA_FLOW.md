# OTC Alpha Flow

How operator-assisted OTC (over-the-counter) trades work in the SOST Gold Exchange alpha.

---

## Overview

OTC trades are large or custom trades that do not go through the standard position desk. They are fully operator-assisted: the operator quotes, both parties confirm, and the operator executes.

OTC is designed for qualified participants who want to trade block sizes or non-standard terms.

---

## Flow

### Step 1: Request

The participant contacts the operator with a trade request:
- Direction: buy or sell
- Asset: full position or reward right
- Approximate size
- Any special terms (e.g., custom expiry, partial fill)

Requests can be submitted via the alpha interface or direct message to the operator.

### Step 2: Quote

The operator evaluates the request and provides a quote:
- Exact price in SOST
- Fee amount and fee rate (disclosed explicitly)
- Expiry of the quote (typically 15-60 minutes)
- Any conditions (e.g., escrow must be confirmed first)

No hidden spreads. The fee is shown separately from the execution price.

### Step 3: Confirm

Both parties confirm the quote:
- Buyer confirms willingness to pay the quoted price plus fee
- Seller confirms willingness to deliver at the quoted price minus fee
- The operator creates a Deal in the deal store with both parties' details

### Step 4: Execute

Execution follows the same lock-and-settle pattern as standard trades:
- ETH gold tokens locked in escrow
- SOST payment locked
- Watchers confirm both locks
- Operator settles the deal
- Both parties receive confirmation

The only difference from standard desk trades is that the pricing was negotiated OTC rather than via a posted offer.

---

## Operator Role

The operator in OTC trades:
- Provides honest price discovery (no front-running, no proprietary trading)
- Discloses all fees before execution
- Maintains audit trail of every OTC action
- Can refuse requests that exceed risk limits or violate alpha policy
- Does not take the other side of trades (no principal trading)

---

## Fee Disclosure

All OTC fees are disclosed before the participant confirms:
- Fee rate (percentage of trade value)
- Fee amount (absolute SOST amount)
- Who pays the fee (buyer, seller, or split)
- Net amount each party receives after fees

No trade executes until both parties have seen and accepted the fee.

---

## Current Status

OTC functionality is in early alpha. The data pipeline (`data/otc_requests.json`) is in place but the request submission interface is not yet live. Current OTC trades are handled manually by the operator.
