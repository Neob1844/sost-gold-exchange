#!/usr/bin/env python3
"""
SOST Gold Exchange — Model B v2 Full Sale Demo

Full lifecycle: create position with principal_owner, reward_owner,
eth_beneficiary -> full sale (all owners change) -> beneficiary sync ->
maturity + auto-withdraw + reward settlement -> complete audit trail.

Usage:
  python3 scripts/demo_model_b_v2_full_sale.py
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
from src.operator.audit_log import AuditLog
from src.services.maturity_watcher import MaturityWatcher
from src.services.auto_withdraw_daemon import AutoWithdrawDaemon
from src.services.reward_settlement_daemon import RewardSettlementDaemon
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

SELLER_SOST = "sost1seller_alice_00000000000000000000"
BUYER_SOST = "sost1buyer_bob_000000000000000000000"
SELLER_ETH = "0x5C02284f3358D5518C9aE7Ba5bDD4Cc8Efd40E9a"
BUYER_ETH = "0xc4A24A4f63F6aCe39415781986653c33F771d6CA"

ETH_CONFIG = {
    "escrow_address": "0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113",
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
}


def banner():
    print(f"""
{Y}{'='*64}{X}
{O}{B}  SOST GOLD EXCHANGE — MODEL B v2 FULL SALE DEMO{X}
{Y}  Full position sale + beneficiary sync + maturity lifecycle{X}
{Y}{'='*64}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*54}{X}")


def info(label, value, color=G):
    print(f"  {D}{label}:{X} {color}{value}{X}")


def lifecycle_arrow(old, new):
    print(f"  {Y}lifecycle:{X} {O}{old}{X} {D}->{X} {M}{new}{X}")


def run():
    audit_dir = os.path.join(PROJECT_ROOT, "data", "audit_v2_full_sale")
    registry = PositionRegistry()
    audit = AuditLog(log_dir=audit_dir)

    maturity_watcher = MaturityWatcher(registry, audit)
    withdraw_daemon = AutoWithdrawDaemon(registry, ETH_CONFIG, audit)
    reward_daemon = RewardSettlementDaemon(registry, audit)
    beneficiary_sync = BeneficiarySync(registry, ETH_CONFIG, audit)

    # ── Step 1: Create position ──
    step(1, "Create Model B v2 position with split ownership")

    now = time.time()
    # Use a very short duration so we can demonstrate maturity
    duration = 5  # 5 seconds for demo purposes

    position = registry.create_model_b(
        owner=SELLER_SOST,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=duration,
        reward_total=10_000_000,
        eth_deposit_id=42,
        eth_tx="0xabc123def456",
    )

    # Set v2 fields
    position.principal_owner = SELLER_SOST
    position.reward_owner = SELLER_SOST
    position.eth_beneficiary = SELLER_ETH
    position.auto_withdraw = True

    info("position_id", position.position_id)
    info("principal_owner", position.principal_owner)
    info("reward_owner", position.reward_owner)
    info("eth_beneficiary", position.eth_beneficiary)
    info("auto_withdraw", str(position.auto_withdraw))
    info("lifecycle_status", position.lifecycle_status)
    info("expiry_time", time.strftime("%H:%M:%S", time.localtime(position.expiry_time)))

    # ── Step 2: Full position sale ──
    step(2, "Execute full position sale (all owners transfer)")

    old_principal = position.principal_owner
    old_reward = position.reward_owner
    old_beneficiary = position.eth_beneficiary

    position.owner = BUYER_SOST
    position.principal_owner = BUYER_SOST
    position.reward_owner = BUYER_SOST
    position.eth_beneficiary = BUYER_ETH
    position.record_event("full_sale", f"seller={SELLER_SOST} buyer={BUYER_SOST}")
    audit.log_event(position.position_id, "full_sale", f"all ownership transferred to {BUYER_SOST}")

    info("new principal_owner", position.principal_owner)
    info("new reward_owner", position.reward_owner)
    info("new eth_beneficiary", position.eth_beneficiary)
    lifecycle_arrow("seller", "buyer")

    # ── Step 3: Beneficiary sync ──
    step(3, "Sync ETH beneficiary on-chain")

    pending = beneficiary_sync.check_pending_syncs()
    info("pending syncs", str(len(pending)))

    if pending:
        tx = beneficiary_sync.sync_beneficiary(pending[0])
        info("sync_tx", tx[:24] + "..." if tx else "None")

    # ── Step 4: Wait for maturity ──
    step(4, "Wait for maturity (short demo duration)")

    # Maturity watcher tick — position may already be past expiry
    print(f"  {D}Waiting for position to mature...{X}")
    time.sleep(max(0, position.expiry_time - time.time() + 0.5))

    transitioned = maturity_watcher.tick()
    info("transitioned", str(len(transitioned)))
    info("lifecycle_status", position.lifecycle_status)
    lifecycle_arrow("ACTIVE", position.lifecycle_status)

    # ── Step 5: Auto-withdraw ──
    step(5, "Auto-withdraw daemon triggers withdrawal")

    withdrawable = withdraw_daemon.check_withdrawable()
    info("withdrawable positions", str(len(withdrawable)))

    results = withdraw_daemon.tick()
    if results:
        pid, tx = results[0]
        info("withdraw_tx", tx[:24] + "...")
        info("lifecycle_status", position.lifecycle_status)
        lifecycle_arrow("MATURED", position.lifecycle_status)
    else:
        info("result", "no withdrawals executed", Y)

    # ── Step 6: Reward settlement ──
    step(6, "Reward settlement daemon credits rewards")

    settleable = reward_daemon.check_settleable()
    info("settleable positions", str(len(settleable)))

    settled = reward_daemon.tick()
    info("settled positions", str(len(settled)))
    info("reward_settled", str(position.reward_settled))
    info("lifecycle_status", position.lifecycle_status)
    lifecycle_arrow("WITHDRAWN", position.lifecycle_status)

    # ── Step 7: Final state ──
    step(7, "Final position state")

    info("position_id", position.position_id, C)
    info("owner", position.owner)
    info("principal_owner", position.principal_owner)
    info("reward_owner", position.reward_owner)
    info("eth_beneficiary", position.eth_beneficiary)
    info("lifecycle_status", position.lifecycle_status, M)
    info("reward_settled", str(position.reward_settled))
    info("withdraw_tx", position.withdraw_tx[:24] + "..." if position.withdraw_tx else "None")
    info("auto_withdraw", str(position.auto_withdraw))

    # ── Step 8: Audit trail ──
    step(8, "Complete audit trail")

    print(f"\n  {W}{B}Position History:{X}")
    for h in position.history:
        ts = time.strftime("%H:%M:%S", time.localtime(h["timestamp"]))
        print(f"  {D}[{ts}]{X} {O}{h['event']:30s}{X} {D}{h.get('detail', '')[:50]}{X}")

    print(f"\n  {W}{B}Audit Log:{X}")
    for entry in audit.get_deal_history(position.position_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:28s}{X} {D}{entry.detail[:55]}{X}")

    # ── Done ──
    print(f"\n{G}{'='*64}{X}")
    print(f"{G}{B}  MODEL B v2 FULL SALE DEMO COMPLETE{X}")
    print(f"{G}{'='*64}{X}")
    print(f"\n{D}Lifecycle: ACTIVE -> MATURED -> WITHDRAWN -> REWARD_SETTLED{X}")
    print(f"{D}All ownership transferred from {SELLER_SOST[:16]}... to {BUYER_SOST[:16]}...{X}\n")


if __name__ == "__main__":
    banner()
    run()
