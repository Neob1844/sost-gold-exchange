#!/usr/bin/env python3
"""
SOST Gold Exchange — Reward Right Trade Demo

Demonstrates the signed flow for trading reward rights from a position:
  offer -> accept -> deal_id -> deal -> lock -> reward split -> verify -> audit

Usage:
  python3 scripts/demo_position_reward_trade.py
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


def banner():
    print(f"""
{Y}{'='*64}{X}
{O}{B}  SOST GOLD EXCHANGE — REWARD RIGHT TRADE DEMO{X}
{Y}  Signed offer -> settlement -> reward split{X}
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
    audit_dir = os.path.join(PROJECT_ROOT, "data", "audit_reward_trade")
    registry = PositionRegistry()
    audit = AuditLog(log_dir=audit_dir)
    transfer_engine = PositionTransferEngine(registry)
    pos_settlement = PositionSettlement(registry, transfer_engine, audit)
    deal_store = DealStore()

    # ── Step 1: Create position with rewards ──
    step(1, "Load position with rewards")

    position = registry.create_model_b(
        owner=SELLER_SOST,
        token="XAUT",
        amount=1_000_000_000_000_000_000,  # 1 XAUT in wei
        bond_sost=50_000_000,
        duration_seconds=365 * 86400,
        reward_total=10_000_000,
        eth_deposit_id=99,
        eth_tx="0xreward_position_tx",
    )

    info("position_id", position.position_id)
    info("owner", position.owner)
    info("reward_total", str(position.reward_total_sost))
    info("reward_remaining", str(position.reward_remaining()))
    info("right_type", position.right_type.value)

    # ── Step 2: Create signed offer for POSITION_REWARD_RIGHT ──
    step(2, "Create signed offer for POSITION_REWARD_RIGHT")

    reward_price = position.reward_remaining() // 2  # discount to 50%
    now = time.time()
    expiry_seconds = 3600

    offer_payload = (
        f"1|position_offer|POSITION_REWARD_RIGHT|{position.position_id}|"
        f"{SELLER_SOST}|{reward_price}|"
        f"{int(now + expiry_seconds)}"
    )
    offer_hash = hashlib.sha256(offer_payload.encode()).hexdigest()
    offer_id = offer_hash[:16]

    info("offer_id", offer_id)
    info("trade_type", "POSITION_REWARD_RIGHT")
    info("seller", SELLER_SOST)
    info("reward_price_sost", str(reward_price))
    info("canonical_hash", offer_hash[:32] + "...")

    # ── Step 3: Accept ──
    step(3, "Create signed accept from buyer")

    accept_payload = (
        f"1|position_accept|{offer_id}|{BUYER_SOST}|"
        f"{reward_price}|{int(now)}"
    )
    accept_hash = hashlib.sha256(accept_payload.encode()).hexdigest()
    accept_id = accept_hash[:16]

    info("accept_id", accept_id)
    info("buyer", BUYER_SOST)
    info("canonical_hash", accept_hash[:32] + "...")

    # ── Step 4: Deal ──
    step(4, "Derive deal_id and create deal")

    deal_id = derive_deal_id(offer_id, accept_id)
    info("deal_id", deal_id)

    deal = deal_store.create(
        deal_id=deal_id,
        pair="SOST/REWARD",
        side="sell",
        amount_sost=reward_price,
        amount_gold=0,
        maker_sost_addr=SELLER_SOST,
        taker_sost_addr=BUYER_SOST,
        maker_eth_addr=SELLER_ETH,
        taker_eth_addr=BUYER_ETH,
    )

    deal.transition(DealState.NEGOTIATED, "reward offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting payment lock")
    deal.mark_eth_locked("0x" + hashlib.sha256(b"reward_eth").hexdigest(), 99)
    deal.mark_sost_locked(hashlib.sha256(b"reward_sost").hexdigest())

    state_change("CREATED", "BOTH_LOCKED")
    info("deal_state", deal.state.value)

    audit.log_event(deal_id, "deal_created", f"reward_split pos={position.position_id}")
    audit.log_event(deal_id, "both_locked", "payment confirmed")

    # ── Step 5: Execute reward split ──
    step(5, "Execute reward split via PositionSettlement.settle_reward_split()")

    parent_reward_before = position.reward_remaining()
    info("parent_reward_before", str(parent_reward_before))

    settled = pos_settlement.settle_reward_split(deal, position.position_id)
    info("settlement_result", "SUCCESS" if settled else "FAILED")

    # ── Step 6: Verify child position created with reward ──
    step(6, "Verify child position created with reward")

    buyer_positions = registry.by_owner(BUYER_SOST)
    if buyer_positions:
        child = buyer_positions[0]
        info("child_position_id", child.position_id)
        info("child_owner", child.owner)
        info("child_right_type", child.right_type.value)
        info("child_reward_total", str(child.reward_total_sost))
        info("child_parent_id", str(child.parent_position_id))
        info("child_reference_amount", str(child.reference_amount))

        if child.right_type == RightType.REWARD_RIGHT:
            print(f"  {G}{B}VERIFIED: Child has REWARD_RIGHT type{X}")
        else:
            print(f"  {R}{B}FAILED: Child right_type is {child.right_type.value}{X}")

        if child.reward_total_sost == parent_reward_before:
            print(f"  {G}{B}VERIFIED: Child inherited full remaining reward{X}")
        else:
            print(f"  {R}{B}MISMATCH: child={child.reward_total_sost} expected={parent_reward_before}{X}")
    else:
        print(f"  {R}{B}FAILED: No child position found for buyer{X}")

    # ── Step 7: Verify parent reward zeroed ──
    step(7, "Verify parent reward zeroed")

    parent = registry.get(position.position_id)
    info("parent_reward_total", str(parent.reward_total_sost))
    info("parent_reward_claimed", str(parent.reward_claimed_sost))
    info("parent_reward_remaining", str(parent.reward_remaining()))

    if parent.reward_remaining() == 0:
        print(f"  {G}{B}VERIFIED: Parent reward zeroed (total = claimed){X}")
    else:
        print(f"  {R}{B}FAILED: Parent still has {parent.reward_remaining()} reward remaining{X}")

    # ── Step 8: Settlement notice ──
    step(8, "Emit settlement notice")

    child_id = buyer_positions[0].position_id if buyer_positions else "unknown"
    notice = {
        "type": "REWARD_SPLIT_SETTLED",
        "deal_id": deal_id,
        "parent_position_id": position.position_id,
        "child_position_id": child_id,
        "seller": SELLER_SOST,
        "buyer": BUYER_SOST,
        "reward_amount": parent_reward_before,
        "price_sost": reward_price,
        "settlement_tx": deal.settlement_tx_hash,
        "timestamp": time.time(),
    }
    print(f"  {D}{json.dumps(notice, indent=4)}{X}")

    # ── Step 9: Audit log ──
    step(9, "Complete audit log")

    for entry in audit.get_deal_history(deal_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:28s}{X} {D}{entry.detail[:60]}{X}")

    # ── Done ──
    print(f"\n{G}{'='*64}{X}")
    print(f"{G}{B}  REWARD RIGHT TRADE DEMO COMPLETE{X}")
    print(f"{G}{'='*64}{X}")

    transitions = len(deal.history)
    print(f"\n{D}Deal {deal_id} settled in {transitions} transitions.{X}")
    print(f"{D}Reward split: parent={position.position_id} -> child={child_id}{X}\n")


if __name__ == "__main__":
    banner()
    run()
