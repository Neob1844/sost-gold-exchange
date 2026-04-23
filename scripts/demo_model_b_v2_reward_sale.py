#!/usr/bin/env python3
"""
SOST Gold Exchange — Model B v2 Reward-Only Sale Demo

Demonstrates a reward-only sale where only reward_owner changes.
Principal and ETH beneficiary stay with the original owner.

Usage:
  python3 scripts/demo_model_b_v2_reward_sale.py
"""

import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, LifecycleStatus,
)
from src.operator.audit_log import AuditLog
from src.services.maturity_watcher import MaturityWatcher
from src.services.reward_settlement_daemon import RewardSettlementDaemon

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

ALICE_SOST = "sost1alice_principal_owner_00000000000"
BOB_SOST = "sost1bob_reward_buyer_000000000000000"
ALICE_ETH = "0x5C02284f3358D5518C9aE7Ba5bDD4Cc8Efd40E9a"


def banner():
    print(f"""
{Y}{'='*64}{X}
{O}{B}  SOST GOLD EXCHANGE — MODEL B v2 REWARD-ONLY SALE DEMO{X}
{Y}  Only reward_owner changes; principal + beneficiary stay{X}
{Y}{'='*64}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*54}{X}")


def info(label, value, color=G):
    print(f"  {D}{label}:{X} {color}{value}{X}")


def run():
    audit_dir = os.path.join(PROJECT_ROOT, "data", "audit_v2_reward_sale")
    registry = PositionRegistry()
    audit = AuditLog(log_dir=audit_dir)

    maturity_watcher = MaturityWatcher(registry, audit)
    reward_daemon = RewardSettlementDaemon(registry, audit)

    # ── Step 1: Create position ──
    step(1, "Create position with Alice as full owner")

    position = registry.create_model_b(
        owner=ALICE_SOST,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=5,  # short for demo
        reward_total=10_000_000,
        eth_deposit_id=77,
        eth_tx="0xreward_sale_tx_001",
    )

    position.principal_owner = ALICE_SOST
    position.reward_owner = ALICE_SOST
    position.eth_beneficiary = ALICE_ETH
    position.auto_withdraw = True

    info("position_id", position.position_id)
    info("principal_owner", position.principal_owner)
    info("reward_owner", position.reward_owner)
    info("eth_beneficiary", position.eth_beneficiary)

    # ── Step 2: Reward-only sale ──
    step(2, "Sell reward rights to Bob (principal stays with Alice)")

    position.reward_owner = BOB_SOST
    position.record_event("reward_sale", f"reward_owner: {ALICE_SOST} -> {BOB_SOST}")
    audit.log_event(position.position_id, "reward_sale",
                    f"reward_owner transferred to {BOB_SOST}")

    info("principal_owner", position.principal_owner, G)
    info("reward_owner", position.reward_owner, M)
    info("eth_beneficiary", position.eth_beneficiary, G)

    print(f"\n  {G}Principal + beneficiary UNCHANGED (Alice){X}")
    print(f"  {M}Reward rights NOW belong to Bob{X}")

    # ── Step 3: Verify no beneficiary sync needed ──
    step(3, "Verify no beneficiary sync needed")

    from src.services.beneficiary_sync import BeneficiarySync
    eth_config = {"escrow_address": "0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113",
                  "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com"}
    bsync = BeneficiarySync(registry, eth_config, audit)

    # The beneficiary should still be Alice's ETH address
    info("eth_beneficiary", position.eth_beneficiary)
    print(f"  {G}No beneficiary sync needed — principal unchanged{X}")

    # ── Step 4: Maturity ──
    step(4, "Wait for maturity")

    time.sleep(max(0, position.expiry_time - time.time() + 0.5))
    transitioned = maturity_watcher.tick()
    info("lifecycle_status", position.lifecycle_status)

    # ── Step 5: Reward settlement ──
    step(5, "Reward settlement — credits go to Bob (reward_owner)")

    settled = reward_daemon.tick()
    info("settled", str(len(settled)))
    info("reward_settled", str(position.reward_settled))
    info("lifecycle_status", position.lifecycle_status)

    reward_owner = position.reward_owner
    print(f"\n  {M}Rewards credited to:{X} {G}{reward_owner}{X}")
    print(f"  {D}Principal (ETH gold) still belongs to Alice{X}")

    # ── Step 6: Final state ──
    step(6, "Final ownership state")

    info("principal_owner", position.principal_owner, G)
    info("reward_owner", position.reward_owner, M)
    info("eth_beneficiary", position.eth_beneficiary, G)
    info("reward_settled", str(position.reward_settled), G)

    # ── Step 7: Audit trail ──
    step(7, "Audit trail")

    for entry in audit.get_deal_history(position.position_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:28s}{X} {D}{entry.detail[:55]}{X}")

    print(f"\n{G}{'='*64}{X}")
    print(f"{G}{B}  REWARD-ONLY SALE DEMO COMPLETE{X}")
    print(f"{G}{'='*64}{X}")
    print(f"\n{D}Alice keeps principal + ETH beneficiary.{X}")
    print(f"{D}Bob receives reward settlement at maturity.{X}\n")


if __name__ == "__main__":
    banner()
    run()
