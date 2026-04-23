#!/usr/bin/env python3
"""
SOST Gold Exchange — V2 Full Sale + Beneficiary Handoff Demo

Complete lifecycle: deposit -> register position -> signed offer ->
buyer accepts -> settlement (all owners transfer) -> beneficiary sync
on-chain via settlement operator -> verify on-chain -> audit log.

In mock mode (default): simulates all steps with ANSI colored output.

Usage:
  python3 scripts/demo_v2_full_sale_handoff.py
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

# ── Sepolia V2 addresses ──
MOCK_XAUT = "0x38Ca34c6B7b3772B44212d6c2597Fd91a6f944D0"
MOCK_PAXG = "0x754A7D020D559EDD60848450c563303262cAdec7"
ESCROW_V2 = "0xTBD_ESCROW_V2_DEPLOY_ADDRESS"  # placeholder until deployed

SELLER_SOST = "sost1seller_alice_00000000000000000000"
BUYER_SOST = "sost1buyer_bob_000000000000000000000"
SELLER_ETH = "0x5C02284f3358D5518C9aE7Ba5bDD4Cc8Efd40E9a"
BUYER_ETH = "0xc4A24A4f63F6aCe39415781986653c33F771d6CA"

ETH_CONFIG = {
    "escrow_address": ESCROW_V2,
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
}


def banner():
    print(f"""
{Y}{'='*68}{X}
{O}{B}  SOST GOLD EXCHANGE — V2 FULL SALE + BENEFICIARY HANDOFF DEMO{X}
{Y}  deposit -> position -> offer -> accept -> settle -> sync -> verify{X}
{Y}{'='*68}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*58}{X}")


def info(label, value, color=G):
    print(f"  {D}{label}:{X} {color}{value}{X}")


def lifecycle_arrow(old, new):
    print(f"  {Y}lifecycle:{X} {O}{old}{X} {D}->{X} {M}{new}{X}")


def run():
    audit_dir = os.path.join(PROJECT_ROOT, "data", "audit_v2_full_sale_handoff")
    registry = PositionRegistry()
    audit = AuditLog(log_dir=audit_dir)
    transfer_engine = PositionTransferEngine(registry)
    beneficiary_sync = BeneficiarySync(registry, ETH_CONFIG, audit)

    deposit_id = 42
    deal_id = hashlib.sha256(f"deal:{SELLER_SOST}:{BUYER_SOST}:{time.time()}".encode()).hexdigest()[:16]

    # ── Step 1: Create deposit (seller as beneficiary) ──
    step(1, "Create deposit (seller as on-chain beneficiary)")

    deposit_tx = "0x" + hashlib.sha256(
        f"deposit:{SELLER_ETH}:{deposit_id}:{time.time()}".encode()
    ).hexdigest()

    info("token", f"XAUT ({MOCK_XAUT})")
    info("amount", "1.0 XAUT (1000000000000000000 wei)")
    info("deposit_id", str(deposit_id))
    info("depositor / beneficiary", SELLER_ETH)
    info("deposit_tx", deposit_tx[:24] + "...")
    info("escrow_v2", ESCROW_V2)
    print(f"\n  {D}cast send {MOCK_XAUT} \"approve(address,uint256)\" {ESCROW_V2} 1000000000000000000{X}")
    print(f"  {D}cast send {ESCROW_V2} \"deposit(address,uint256)\" {MOCK_XAUT} 1000000000000000000{X}")

    # ── Step 2: Register position ──
    step(2, "Register position (principal_owner=seller, reward_owner=seller, eth_beneficiary=seller)")

    position = registry.create_model_b(
        owner=SELLER_SOST,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=90 * 86400,  # 90 days
        reward_total=10_000_000,
        eth_deposit_id=deposit_id,
        eth_tx=deposit_tx,
    )
    position.principal_owner = SELLER_SOST
    position.reward_owner = SELLER_SOST
    position.eth_beneficiary = SELLER_ETH
    position.auto_withdraw = True

    info("position_id", position.position_id, C)
    info("principal_owner", position.principal_owner)
    info("reward_owner", position.reward_owner)
    info("eth_beneficiary", position.eth_beneficiary)
    info("lifecycle_status", position.lifecycle_status)

    # ── Step 3: Seller creates signed full-position offer ──
    step(3, "Seller creates signed full-position offer")

    offer_payload = {
        "type": "FULL_POSITION_OFFER",
        "position_id": position.position_id,
        "seller": SELLER_SOST,
        "seller_eth": SELLER_ETH,
        "ask_sost": 55_000_000,
        "created_at": time.time(),
    }
    offer_hash = hashlib.sha256(json.dumps(offer_payload, sort_keys=True).encode()).hexdigest()

    info("offer_type", "FULL_POSITION_OFFER")
    info("ask_price", "55,000,000 sats SOST")
    info("offer_hash", offer_hash[:24] + "...")
    print(f"  {D}Seller signs with SOST private key — offer is binding{X}")

    audit.log_event(position.position_id, "offer_created",
                    f"type=FULL_POSITION seller={SELLER_SOST} ask=55000000")

    # ── Step 4: Buyer accepts ──
    step(4, "Buyer accepts offer")

    accept_payload = {
        "offer_hash": offer_hash,
        "buyer": BUYER_SOST,
        "buyer_eth": BUYER_ETH,
        "accepted_at": time.time(),
    }

    info("buyer", BUYER_SOST)
    info("buyer_eth", BUYER_ETH)
    info("deal_id", deal_id, C)
    print(f"  {D}Buyer sends SOST payment to settlement engine{X}")

    audit.log_event(position.position_id, "offer_accepted",
                    f"buyer={BUYER_SOST} deal={deal_id}")

    # ── Step 5: Settlement engine liquidates trade ──
    step(5, "Settlement engine liquidates trade")

    old_principal = position.principal_owner
    old_reward = position.reward_owner
    old_beneficiary = position.eth_beneficiary

    result = transfer_engine.transfer(
        position.position_id,
        new_owner=BUYER_SOST,
        deal_id=deal_id,
        eth_beneficiary=BUYER_ETH,
    )

    info("transfer_result", result.message, G if result.success else R)
    info("deal_id", deal_id, C)
    print()
    info("principal_owner", f"{old_principal[:20]}... -> {position.principal_owner[:20]}...", M)
    info("reward_owner", f"{old_reward[:20]}... -> {position.reward_owner[:20]}...", M)
    info("eth_beneficiary", f"{old_beneficiary} -> {position.eth_beneficiary}", M)

    audit.log_event(position.position_id, "settlement_complete",
                    f"deal={deal_id} buyer={BUYER_SOST}")

    # ── Step 6: Beneficiary sync -> updateBeneficiary on-chain ──
    step(6, "Beneficiary sync -> updateBeneficiary on-chain (via settlement operator)")

    pending = beneficiary_sync.check_pending_syncs()
    info("pending_syncs", str(len(pending)))

    cast_cmd = (
        f'cast send {ESCROW_V2} '
        f'"updateBeneficiary(uint256,address)" {deposit_id} {BUYER_ETH} '
        f'--rpc-url {ETH_CONFIG["rpc_url"]}'
    )

    if pending:
        sync_tx = beneficiary_sync.sync_beneficiary(pending[0])
        info("sync_tx", sync_tx[:24] + "..." if sync_tx else "None")

    print(f"\n  {W}{B}cast command (settlement operator executes):{X}")
    print(f"  {Y}{cast_cmd}{X}")
    print(f"\n  {D}Settlement operator has updateBeneficiary permission.{X}")
    print(f"  {D}Seller has NO role — handoff is fully automated.{X}")

    # ── Step 7: Verify on-chain ──
    step(7, "Verify on-chain: currentBeneficiary = buyer_eth")

    info("deposit_id", str(deposit_id))
    info("old_beneficiary (seller)", old_beneficiary)
    info("new_beneficiary (buyer)", position.eth_beneficiary, G)

    verify_cmd = (
        f'cast call {ESCROW_V2} '
        f'"currentBeneficiary(uint256)" {deposit_id} '
        f'--rpc-url {ETH_CONFIG["rpc_url"]}'
    )
    print(f"\n  {W}{B}Verification command:{X}")
    print(f"  {Y}{verify_cmd}{X}")
    print(f"\n  {G}EXPECTED RESULT:{X} {W}{BUYER_ETH}{X}")
    print(f"  {G}Buyer receives principal at maturity — no seller cooperation needed{X}")

    # ── Step 8: Audit log complete ──
    step(8, "Audit log complete")

    print(f"\n  {W}{B}Position History:{X}")
    for h in position.history:
        ts = time.strftime("%H:%M:%S", time.localtime(h["timestamp"]))
        print(f"  {D}[{ts}]{X} {O}{h['event']:30s}{X} {D}{h.get('detail', '')[:55]}{X}")

    print(f"\n  {W}{B}Audit Log:{X}")
    for entry in audit.get_deal_history(position.position_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:28s}{X} {D}{entry.detail[:60]}{X}")

    # ── Summary ──
    print(f"\n{G}{'='*68}{X}")
    print(f"{G}{B}  V2 FULL SALE + BENEFICIARY HANDOFF DEMO COMPLETE{X}")
    print(f"{G}{'='*68}{X}")

    print(f"""
  {W}{B}State Transitions:{X}
    {D}deposit_id:{X}       {C}{deposit_id}{X}
    {D}position_id:{X}      {C}{position.position_id}{X}
    {D}deal_id:{X}          {C}{deal_id}{X}
    {D}old beneficiary:{X}  {Y}{old_beneficiary}{X}
    {D}new beneficiary:{X}  {G}{BUYER_ETH}{X}
    {D}principal_owner:{X}  {G}{position.principal_owner[:24]}...{X}
    {D}reward_owner:{X}     {G}{position.reward_owner[:24]}...{X}
    {D}lifecycle:{X}        {G}{position.lifecycle_status}{X}

  {D}Seller cooperation required: NONE{X}
  {D}Settlement operator executed beneficiary update autonomously.{X}
""")


if __name__ == "__main__":
    banner()
    run()
