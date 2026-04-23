#!/usr/bin/env python3
"""
SOST Gold Exchange — Model B v2 Maturity + Withdraw Demo

Demonstrates the full maturity lifecycle:
  ACTIVE -> NEARING_MATURITY -> MATURED -> WITHDRAWN -> REWARD_SETTLED -> CLOSED

Shows:
  - Maturity watcher detecting approaching expiry
  - Auto-withdraw daemon triggering ETH withdrawal
  - Reward settlement crediting SOST rewards
  - Final CLOSED state

Usage:
  python3 scripts/demo_model_b_v2_maturity_withdraw.py
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
from src.services.auto_withdraw_daemon import AutoWithdrawDaemon
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

OWNER_SOST = "sost1owner_maturity_demo_0000000000000"
OWNER_ETH = "0x5C02284f3358D5518C9aE7Ba5bDD4Cc8Efd40E9a"

ETH_CONFIG = {
    "escrow_address": "0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113",
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
}


def banner():
    print(f"""
{Y}{'='*64}{X}
{O}{B}  SOST GOLD EXCHANGE — MATURITY + WITHDRAW LIFECYCLE DEMO{X}
{Y}  ACTIVE -> MATURED -> WITHDRAWN -> REWARD_SETTLED -> CLOSED{X}
{Y}{'='*64}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*54}{X}")


def info(label, value, color=G):
    print(f"  {D}{label}:{X} {color}{value}{X}")


def lifecycle_bar(status):
    stages = ["ACTIVE", "NEARING_MATURITY", "MATURED", "WITHDRAWN", "REWARD_SETTLED", "CLOSED"]
    colors = [G, Y, O, M, C, G]
    bar = ""
    for i, (s, col) in enumerate(zip(stages, colors)):
        if s == status:
            bar += f" {col}{B}[{s}]{X}"
        else:
            bar += f" {D}{s}{X}"
        if i < len(stages) - 1:
            bar += f" {D}->{X}"
    return bar


def run():
    audit_dir = os.path.join(PROJECT_ROOT, "data", "audit_v2_maturity")
    registry = PositionRegistry()
    audit = AuditLog(log_dir=audit_dir)

    maturity_watcher = MaturityWatcher(registry, audit)
    withdraw_daemon = AutoWithdrawDaemon(registry, ETH_CONFIG, audit)
    reward_daemon = RewardSettlementDaemon(registry, audit)

    # ── Step 1: Create position that is "nearing maturity" ──
    step(1, "Create position nearing maturity (3 seconds to expiry)")

    now = time.time()
    position = registry.create_model_b(
        owner=OWNER_SOST,
        token="XAUT",
        amount=500_000_000_000_000_000,
        bond_sost=25_000_000,
        duration_seconds=3,  # very short for demo
        reward_total=5_000_000,
        eth_deposit_id=101,
        eth_tx="0xmaturity_demo_001",
    )

    position.principal_owner = OWNER_SOST
    position.reward_owner = OWNER_SOST
    position.eth_beneficiary = OWNER_ETH
    position.auto_withdraw = True

    info("position_id", position.position_id)
    info("owner", position.owner)
    info("expiry_in", f"{position.expiry_time - time.time():.1f}s")
    info("reward_total", f"{position.reward_total_sost} sats")
    print(f"\n {lifecycle_bar('ACTIVE')}")

    # ── Step 2: Simulate nearing maturity ──
    step(2, "Maturity watcher detects NEARING_MATURITY")

    # Force the lifecycle to nearing (in real use the 7-day threshold applies)
    # For demo, we manually set it to show the transition
    position.lifecycle_status = LifecycleStatus.NEARING_MATURITY.value
    position.record_event("lifecycle_nearing_maturity", "demo: <7d to expiry")
    audit.log_event(position.position_id, "lifecycle_nearing_maturity", "demo transition")

    info("lifecycle_status", position.lifecycle_status, Y)
    print(f"\n {lifecycle_bar('NEARING_MATURITY')}")

    # ── Step 3: Wait for actual maturity ──
    step(3, "Wait for maturity")

    remaining = position.expiry_time - time.time()
    if remaining > 0:
        print(f"  {D}Waiting {remaining:.1f}s for expiry...{X}")
        time.sleep(remaining + 0.5)

    transitioned = maturity_watcher.tick()
    info("transitioned", str(len(transitioned)))
    info("lifecycle_status", position.lifecycle_status, O)
    print(f"\n {lifecycle_bar('MATURED')}")

    # ── Step 4: Auto-withdraw ──
    step(4, "Auto-withdraw daemon executes withdrawal")

    results = withdraw_daemon.tick()
    if results:
        pid, tx = results[0]
        info("withdraw_tx", tx[:24] + "...")
    info("lifecycle_status", position.lifecycle_status, M)
    print(f"\n {lifecycle_bar('WITHDRAWN')}")

    # ── Step 5: Reward settlement ──
    step(5, "Reward settlement daemon credits rewards")

    settled = reward_daemon.tick()
    info("settled", str(len(settled)))
    info("reward_settled", str(position.reward_settled))
    info("lifecycle_status", position.lifecycle_status, C)
    print(f"\n {lifecycle_bar('REWARD_SETTLED')}")

    # ── Step 6: Close position ──
    step(6, "Close position (all obligations fulfilled)")

    position.lifecycle_status = LifecycleStatus.CLOSED.value
    position.record_event("lifecycle_closed", "all obligations fulfilled")
    audit.log_event(position.position_id, "lifecycle_closed", "position fully settled")

    info("lifecycle_status", position.lifecycle_status, G)
    print(f"\n {lifecycle_bar('CLOSED')}")

    # ── Step 7: Complete timeline ──
    step(7, "Complete lifecycle timeline")

    print(f"\n  {W}{B}Position History:{X}")
    for h in position.history:
        ts = time.strftime("%H:%M:%S", time.localtime(h["timestamp"]))
        event = h["event"]
        color = G
        if "nearing" in event:
            color = Y
        elif "matured" in event:
            color = O
        elif "withdraw" in event:
            color = M
        elif "reward" in event:
            color = C
        elif "closed" in event:
            color = G
        print(f"  {D}[{ts}]{X} {color}{event:30s}{X} {D}{h.get('detail', '')[:45]}{X}")

    print(f"\n  {W}{B}Audit Log:{X}")
    for entry in audit.get_deal_history(position.position_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:28s}{X} {D}{entry.detail[:55]}{X}")

    # ── Done ──
    print(f"\n{G}{'='*64}{X}")
    print(f"{G}{B}  MATURITY + WITHDRAW LIFECYCLE DEMO COMPLETE{X}")
    print(f"{G}{'='*64}{X}")
    print(f"""
{D}Lifecycle completed:{X}
  {G}ACTIVE{X} {D}->{X} {Y}NEARING_MATURITY{X} {D}->{X} {O}MATURED{X} {D}->{X} {M}WITHDRAWN{X} {D}->{X} {C}REWARD_SETTLED{X} {D}->{X} {G}CLOSED{X}

{D}Position {position.position_id} is fully settled.{X}
""")


if __name__ == "__main__":
    banner()
    run()
