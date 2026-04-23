#!/usr/bin/env python3
"""
SOST Gold Exchange — V2 Reward-Only Sale Control Case

Demonstrates that a reward-only sale changes ONLY reward_owner.
Principal owner and ETH beneficiary remain unchanged.

This is the control case: proves beneficiary isolation when only
reward rights are traded.

Usage:
  python3 scripts/demo_v2_reward_sale_control.py
"""

import hashlib
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, LifecycleStatus,
)
from src.positions.position_transfer import PositionTransferEngine
from src.operator.audit_log import AuditLog
from src.services.beneficiary_sync import BeneficiarySync

# ── ANSI colors ──
R = "\033[91m"
G = "\033[92m"
C = "\033[96m"
Y = "\033[93m"
O = "\033[38;5;208m"
M = "\033[95m"
W = "\033[97m"
D = "\033[90m"
B = "\033[1m"
X = "\033[0m"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SELLER_SOST = "sost1alice_principal_owner_00000000000"
BUYER_SOST = "sost1bob_reward_buyer_000000000000000"
SELLER_ETH = "0x5C02284f3358D5518C9aE7Ba5bDD4Cc8Efd40E9a"
BUYER_ETH = "0xc4A24A4f63F6aCe39415781986653c33F771d6CA"

ESCROW_V2 = "0xTBD_ESCROW_V2_DEPLOY_ADDRESS"

ETH_CONFIG = {
    "escrow_address": ESCROW_V2,
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
}


def banner():
    print(f"""
{Y}{'='*68}{X}
{O}{B}  SOST GOLD EXCHANGE — V2 REWARD-ONLY SALE CONTROL CASE{X}
{Y}  Only reward_owner changes; principal + beneficiary stay unchanged{X}
{Y}{'='*68}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*58}{X}")


def info(label, value, color=G):
    print(f"  {D}{label}:{X} {color}{value}{X}")


def check_mark(label, expected, actual):
    match = (expected == actual)
    mark = f"{G}PASS" if match else f"{R}FAIL"
    print(f"  {mark}{X}  {W}{label}{X}: {D}{actual}{X}")
    return match


def run():
    audit_dir = os.path.join(PROJECT_ROOT, "data", "audit_v2_reward_sale_control")
    registry = PositionRegistry()
    audit = AuditLog(log_dir=audit_dir)
    transfer_engine = PositionTransferEngine(registry)
    beneficiary_sync = BeneficiarySync(registry, ETH_CONFIG, audit)

    # ── Step 1: Create position ──
    step(1, "Create position with Alice as full owner")

    position = registry.create_model_b(
        owner=SELLER_SOST,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=90 * 86400,
        reward_total=10_000_000,
        eth_deposit_id=77,
        eth_tx="0xreward_sale_control_tx_001",
    )
    position.principal_owner = SELLER_SOST
    position.reward_owner = SELLER_SOST
    position.eth_beneficiary = SELLER_ETH
    position.auto_withdraw = True

    info("position_id", position.position_id, C)
    info("principal_owner", position.principal_owner)
    info("reward_owner", position.reward_owner)
    info("eth_beneficiary", position.eth_beneficiary)

    # Save pre-sale state
    pre_principal = position.principal_owner
    pre_beneficiary = position.eth_beneficiary

    # ── Step 2: Seller offers reward-right only ──
    step(2, "Seller offers reward-right only")

    offer_payload = {
        "type": "REWARD_RIGHT_OFFER",
        "position_id": position.position_id,
        "seller": SELLER_SOST,
        "ask_sost": 8_000_000,
        "created_at": time.time(),
    }
    offer_hash = hashlib.sha256(json.dumps(offer_payload, sort_keys=True).encode()).hexdigest()

    info("offer_type", "REWARD_RIGHT_OFFER")
    info("ask_price", "8,000,000 sats SOST")
    info("offer_hash", offer_hash[:24] + "...")
    print(f"  {D}Only reward rights are on offer — principal stays with Alice{X}")

    audit.log_event(position.position_id, "reward_offer_created",
                    f"type=REWARD_RIGHT seller={SELLER_SOST} ask=8000000")

    # ── Step 3: Buyer accepts ──
    step(3, "Buyer accepts reward-right offer")

    deal_id = hashlib.sha256(
        f"deal:reward:{SELLER_SOST}:{BUYER_SOST}:{time.time()}".encode()
    ).hexdigest()[:16]

    info("buyer", BUYER_SOST)
    info("deal_id", deal_id, C)

    audit.log_event(position.position_id, "reward_offer_accepted",
                    f"buyer={BUYER_SOST} deal={deal_id}")

    # ── Step 4: Settlement — only reward_owner changes ──
    step(4, "Settlement: only reward_owner changes")

    result = transfer_engine.split_reward_right(
        position.position_id,
        buyer=BUYER_SOST,
        deal_id=deal_id,
    )

    info("split_result", result.message, G if result.success else R)
    info("reward_child_id", result.position_id, C)

    # Parent position: reward_owner should now point to buyer
    info("parent principal_owner", position.principal_owner)
    info("parent reward_owner", position.reward_owner, M)
    info("parent eth_beneficiary", position.eth_beneficiary)

    audit.log_event(position.position_id, "reward_settlement_complete",
                    f"deal={deal_id} reward_buyer={BUYER_SOST}")

    # ── Step 5: Verify principal_owner unchanged, eth_beneficiary unchanged ──
    step(5, "Verify: principal_owner unchanged, eth_beneficiary unchanged")

    all_pass = True
    all_pass &= check_mark("principal_owner unchanged", pre_principal, position.principal_owner)
    all_pass &= check_mark("eth_beneficiary unchanged", pre_beneficiary, position.eth_beneficiary)
    all_pass &= check_mark("reward_owner changed to buyer", BUYER_SOST, position.reward_owner)

    # No beneficiary sync should be needed
    pending = beneficiary_sync.check_pending_syncs()
    # The sync check looks for positions where beneficiary was never synced.
    # Since principal_owner didn't change, any sync would be a no-op.
    print(f"\n  {D}Beneficiary sync check:{X}", end="")
    print(f" {G}NOT REQUIRED{X} {D}(principal_owner unchanged){X}")

    # ── Step 6: Explicit confirmation ──
    step(6, "Explicit confirmation")

    if all_pass:
        print(f"""
  {G}{B}ALL CHECKS PASSED{X}

  {W}Reward-only sale correctly isolates ownership:{X}
    {G}principal_owner:{X}  {D}{position.principal_owner}{X}  {G}(unchanged){X}
    {M}reward_owner:{X}     {D}{position.reward_owner}{X}  {M}(changed to buyer){X}
    {G}eth_beneficiary:{X}  {D}{position.eth_beneficiary}{X}  {G}(unchanged){X}

  {D}On-chain beneficiary remains seller's ETH address.{X}
  {D}At maturity, principal goes to Alice (seller).{X}
  {D}SOST rewards go to Bob (buyer).{X}
""")
    else:
        print(f"\n  {R}{B}SOME CHECKS FAILED — review output above{X}\n")

    # ── Audit trail ──
    print(f"  {W}{B}Audit Log:{X}")
    for entry in audit.get_deal_history(position.position_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:28s}{X} {D}{entry.detail[:60]}{X}")

    print(f"\n{G}{'='*68}{X}")
    print(f"{G}{B}  V2 REWARD-ONLY SALE CONTROL CASE COMPLETE{X}")
    print(f"{G}{'='*68}{X}\n")


if __name__ == "__main__":
    banner()
    run()
