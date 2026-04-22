#!/usr/bin/env python3
"""
SOST Gold Exchange — Full Position Trade Demo

Demonstrates the complete signed flow for trading a full SOST position:
  offer -> accept -> deal_id -> deal -> lock -> settlement -> verify -> audit

Usage:
  python3 scripts/demo_position_full_trade.py
"""

import hashlib
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import Position, ContractType, BackingType, PositionStatus, RightType
from src.positions.position_transfer import PositionTransferEngine
from src.positions.position_settlement import PositionSettlement
from src.positions.position_pricing import value_position
from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.operator.audit_log import AuditLog

# ── ANSI colors ──
R = "\033[91m"
G = "\033[92m"
C = "\033[96m"
Y = "\033[93m"
O = "\033[38;5;208m"
W = "\033[97m"
D = "\033[90m"
B = "\033[1m"
X = "\033[0m"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SELLER_SOST = "sost1seller00000000000000000000000000"
BUYER_SOST = "sost1buyer000000000000000000000000000"
SELLER_ETH = "0xSellerEthAddress0000000000000000000000"
BUYER_ETH = "0xBuyerEthAddress00000000000000000000000"

GOLD_PRICE_SOST_PER_UNIT = 0.001  # SOST satoshis per wei of gold


def banner():
    print(f"""
{Y}{'='*64}{X}
{O}{B}  SOST GOLD EXCHANGE — FULL POSITION TRADE DEMO{X}
{Y}  Signed offer -> settlement -> ownership transfer{X}
{Y}{'='*64}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*54}{X}")


def info(label, value):
    print(f"  {D}{label}:{X} {G}{value}{X}")


def state_change(old, new):
    print(f"  {Y}state:{X} {O}{old}{X} {D}->{X} {G}{new}{X}")


def derive_deal_id(offer_id, accept_id):
    return hashlib.sha256(f"{offer_id}:{accept_id}".encode()).hexdigest()[:16]


def run():
    audit_dir = os.path.join(PROJECT_ROOT, "data", "audit_position_trade")
    registry = PositionRegistry()
    audit = AuditLog(log_dir=audit_dir)
    transfer_engine = PositionTransferEngine(registry)
    pos_settlement = PositionSettlement(registry, transfer_engine, audit)
    deal_store = DealStore()

    # ── Step 1: Create test position ──
    step(1, "Load position registry, show position to sell")

    position = registry.create_model_b(
        owner=SELLER_SOST,
        token="XAUT",
        amount=1_000_000_000_000_000_000,  # 1 XAUT in wei
        bond_sost=50_000_000,
        duration_seconds=365 * 86400,
        reward_total=10_000_000,
        eth_deposit_id=42,
        eth_tx="0xabc123def456",
    )

    info("position_id", position.position_id)
    info("owner", position.owner)
    info("token", f"{position.token_symbol} ({position.reference_amount} wei)")
    info("contract_type", position.contract_type.value)
    info("right_type", position.right_type.value)
    info("status", position.status.value)
    info("transferable", str(position.transferable))

    # ── Step 2: Create signed offer ──
    step(2, "Create signed offer for POSITION_FULL")

    valuation = value_position(position, GOLD_PRICE_SOST_PER_UNIT)
    info("valuation", valuation.detail)
    info("net_value_sost", str(valuation.net_value_sost))

    now = time.time()
    expiry_seconds = 3600
    offer_payload = (
        f"1|position_offer|POSITION_FULL|{position.position_id}|"
        f"{SELLER_SOST}|{valuation.net_value_sost}|"
        f"{int(now + expiry_seconds)}"
    )
    offer_hash = hashlib.sha256(offer_payload.encode()).hexdigest()
    offer_id = offer_hash[:16]

    info("offer_id", offer_id)
    info("seller", SELLER_SOST)
    info("position_id", position.position_id)
    info("price_sost", str(valuation.net_value_sost))
    info("canonical_hash", offer_hash[:32] + "...")
    info("expires_in", f"{expiry_seconds}s")

    # ── Step 3: Create signed accept ──
    step(3, "Create signed accept from buyer")

    accept_payload = (
        f"1|position_accept|{offer_id}|{BUYER_SOST}|"
        f"{valuation.net_value_sost}|{int(now)}"
    )
    accept_hash = hashlib.sha256(accept_payload.encode()).hexdigest()
    accept_id = accept_hash[:16]

    info("accept_id", accept_id)
    info("buyer", BUYER_SOST)
    info("accepted_price", str(valuation.net_value_sost))
    info("canonical_hash", accept_hash[:32] + "...")

    # ── Step 4: Derive deal_id ──
    step(4, "Derive deal_id = SHA256(offer_id:accept_id)[:16]")

    deal_id = derive_deal_id(offer_id, accept_id)
    info("deal_id", deal_id)
    info("derivation", f"SHA256({offer_id}:{accept_id})[:16]")

    # ── Step 5: Create deal, transition to BOTH_LOCKED ──
    step(5, "Create deal, transition to BOTH_LOCKED (simulated)")

    deal = deal_store.create(
        deal_id=deal_id,
        pair="SOST/XAUT",
        side="sell",
        amount_sost=valuation.net_value_sost,
        amount_gold=position.reference_amount,
        maker_sost_addr=SELLER_SOST,
        taker_sost_addr=BUYER_SOST,
        maker_eth_addr=SELLER_ETH,
        taker_eth_addr=BUYER_ETH,
    )

    deal.transition(DealState.NEGOTIATED, "offer accepted")
    state_change("CREATED", "NEGOTIATED")

    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
    state_change("NEGOTIATED", "AWAITING_ETH_LOCK")

    deal.mark_eth_locked("0x" + hashlib.sha256(b"eth_lock").hexdigest(), 42)
    state_change("AWAITING_ETH_LOCK", deal.state.value)

    deal.mark_sost_locked(hashlib.sha256(b"sost_lock").hexdigest())
    state_change("AWAITING_SOST_LOCK", deal.state.value)

    audit.log_event(deal_id, "deal_created", f"pos={position.position_id} seller={SELLER_SOST}")
    audit.log_event(deal_id, "both_locked", "ETH and SOST confirmed")

    # ── Step 6: Execute position transfer ──
    step(6, "Execute position transfer via PositionSettlement.settle_position_trade()")

    old_owner = position.owner
    settled = pos_settlement.settle_position_trade(deal, position.position_id)
    info("settlement_result", "SUCCESS" if settled else "FAILED")

    # ── Step 7: Verify owner changed ──
    step(7, "Verify owner changed")

    updated = registry.get(position.position_id)
    info("old_owner", old_owner)
    info("new_owner", updated.owner)
    info("status", updated.status.value)
    info("deal_state", deal.state.value)

    if updated.owner == BUYER_SOST:
        print(f"  {G}{B}VERIFIED: Ownership transferred to buyer{X}")
    else:
        print(f"  {R}{B}FAILED: Owner did not change{X}")

    # ── Step 8: Settlement notice ──
    step(8, "Emit settlement notice")

    notice = {
        "type": "POSITION_TRADE_SETTLED",
        "deal_id": deal_id,
        "position_id": position.position_id,
        "seller": old_owner,
        "buyer": BUYER_SOST,
        "price_sost": valuation.net_value_sost,
        "settlement_tx": deal.settlement_tx_hash,
        "timestamp": time.time(),
    }
    print(f"  {D}{json.dumps(notice, indent=4)}{X}")

    # ── Step 9: Print audit log ──
    step(9, "Complete audit log")

    for entry in audit.get_deal_history(deal_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:28s}{X} {D}{entry.detail[:60]}{X}")

    # ── Done ──
    print(f"\n{G}{'='*64}{X}")
    print(f"{G}{B}  FULL POSITION TRADE DEMO COMPLETE{X}")
    print(f"{G}{'='*64}{X}")

    transitions = len(deal.history)
    print(f"\n{D}Deal {deal_id} settled in {transitions} transitions.{X}")
    print(f"{D}Position {position.position_id} transferred: {old_owner} -> {BUYER_SOST}{X}\n")


if __name__ == "__main__":
    banner()
    run()
