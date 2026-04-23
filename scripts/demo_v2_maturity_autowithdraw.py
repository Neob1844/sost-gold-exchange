#!/usr/bin/env python3
"""
SOST Gold Exchange — V2 Full Maturity + Auto-Withdraw Lifecycle Demo

Demonstrates the complete post-sale lifecycle:
  1. Position with buyer as principal_owner (from a prior full sale)
  2. MaturityWatcher detects maturity
  3. AutoWithdrawDaemon executes withdraw
  4. Principal sent to buyer ETH beneficiary
  5. RewardSettlementDaemon credits reward to reward_owner
  6. Lifecycle: ACTIVE -> MATURED -> WITHDRAWN -> REWARD_SETTLED -> CLOSED

Usage:
  python3 scripts/demo_v2_maturity_autowithdraw.py
"""

import hashlib
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

# Post-sale state: buyer is now the owner
BUYER_SOST = "sost1buyer_bob_000000000000000000000"
BUYER_ETH = "0xc4A24A4f63F6aCe39415781986653c33F771d6CA"
ORIGINAL_SELLER_ETH = "0x5C02284f3358D5518C9aE7Ba5bDD4Cc8Efd40E9a"

ESCROW_V2 = "0xTBD_ESCROW_V2_DEPLOY_ADDRESS"

ETH_CONFIG = {
    "escrow_address": ESCROW_V2,
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
}


def banner():
    print(f"""
{Y}{'='*68}{X}
{O}{B}  SOST GOLD EXCHANGE — V2 MATURITY + AUTO-WITHDRAW LIFECYCLE{X}
{Y}  ACTIVE -> MATURED -> WITHDRAWN -> REWARD_SETTLED -> CLOSED{X}
{Y}{'='*68}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*58}{X}")


def info(label, value, color=G):
    print(f"  {D}{label}:{X} {color}{value}{X}")


def lifecycle_bar(status):
    stages = ["ACTIVE", "MATURED", "WITHDRAWN", "REWARD_SETTLED", "CLOSED"]
    colors = [G, O, M, C, G]
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
    audit_dir = os.path.join(PROJECT_ROOT, "data", "audit_v2_maturity_autowithdraw")
    registry = PositionRegistry()
    audit = AuditLog(log_dir=audit_dir)

    maturity_watcher = MaturityWatcher(registry, audit)
    withdraw_daemon = AutoWithdrawDaemon(registry, ETH_CONFIG, audit)
    reward_daemon = RewardSettlementDaemon(registry, audit)

    deposit_id = 42

    # ── Step 1: Position with buyer as principal_owner (from prior full sale) ──
    step(1, "Position with buyer as principal_owner (from prior full sale)")

    # Create a position that's about to mature (short duration for demo)
    position = registry.create_model_b(
        owner=BUYER_SOST,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=4,  # 4 seconds for demo
        reward_total=10_000_000,
        eth_deposit_id=deposit_id,
        eth_tx="0xoriginal_deposit_by_seller",
    )
    # Set post-sale ownership state
    position.principal_owner = BUYER_SOST
    position.reward_owner = BUYER_SOST
    position.eth_beneficiary = BUYER_ETH
    position.auto_withdraw = True
    position.record_event("post_sale_state", f"buyer={BUYER_SOST} beneficiary synced to {BUYER_ETH}")

    info("position_id", position.position_id, C)
    info("principal_owner", position.principal_owner)
    info("reward_owner", position.reward_owner)
    info("eth_beneficiary", position.eth_beneficiary, G)
    info("original_seller_eth", ORIGINAL_SELLER_ETH, D)
    info("auto_withdraw", str(position.auto_withdraw))
    info("expiry_in", f"{position.expiry_time - time.time():.1f}s")
    info("lifecycle_status", position.lifecycle_status)
    print(f"\n {lifecycle_bar('ACTIVE')}")

    print(f"\n  {D}Beneficiary was already synced on-chain to buyer after full sale.{X}")
    print(f"  {D}On-chain: currentBeneficiary({deposit_id}) = {BUYER_ETH}{X}")

    # ── Step 2: MaturityWatcher detects maturity ──
    step(2, "MaturityWatcher detects maturity")

    remaining = position.expiry_time - time.time()
    if remaining > 0:
        print(f"  {D}Waiting {remaining:.1f}s for expiry...{X}")
        time.sleep(remaining + 0.5)

    transitioned = maturity_watcher.tick()
    info("transitioned", str(len(transitioned)))
    info("lifecycle_status", position.lifecycle_status, O)
    print(f"\n {lifecycle_bar('MATURED')}")

    # ── Step 3: AutoWithdrawDaemon executes withdraw ──
    step(3, "AutoWithdrawDaemon executes withdraw")

    withdrawable = withdraw_daemon.check_withdrawable()
    info("withdrawable_positions", str(len(withdrawable)))

    results = withdraw_daemon.tick()
    if results:
        pid, tx = results[0]
        info("withdraw_tx", tx[:24] + "...")
        info("lifecycle_status", position.lifecycle_status, M)

        cast_cmd = (
            f'cast send {ESCROW_V2} '
            f'"withdraw(uint256)" {deposit_id} '
            f'--rpc-url {ETH_CONFIG["rpc_url"]}'
        )
        print(f"\n  {W}{B}Withdraw command:{X}")
        print(f"  {Y}{cast_cmd}{X}")
    else:
        info("result", "no withdrawals executed", Y)

    print(f"\n {lifecycle_bar('WITHDRAWN')}")

    # ── Step 4: Principal sent to buyer ETH beneficiary ──
    step(4, "Principal sent to buyer ETH beneficiary")

    info("deposit_id", str(deposit_id))
    info("beneficiary (on-chain)", BUYER_ETH, G)
    info("original seller", ORIGINAL_SELLER_ETH, D)

    print(f"\n  {G}{B}Principal goes to BUYER, not original seller.{X}")
    print(f"  {D}EscrowV2.withdraw({deposit_id}) sends gold tokens to currentBeneficiary.{X}")
    print(f"  {D}currentBeneficiary was updated to buyer during settlement.{X}")

    # ── Step 5: RewardSettlementDaemon credits reward to reward_owner ──
    step(5, "RewardSettlementDaemon credits reward to reward_owner")

    settleable = reward_daemon.check_settleable()
    info("settleable_positions", str(len(settleable)))

    settled = reward_daemon.tick()
    info("settled", str(len(settled)))
    info("reward_settled", str(position.reward_settled))
    info("reward_recipient", position.reward_owner)
    info("reward_amount", f"{position.reward_total_sost} sats SOST")
    info("lifecycle_status", position.lifecycle_status, C)
    print(f"\n {lifecycle_bar('REWARD_SETTLED')}")

    # ── Step 6: Lifecycle complete -> CLOSED ──
    step(6, "Lifecycle: ACTIVE -> MATURED -> WITHDRAWN -> REWARD_SETTLED -> CLOSED")

    position.lifecycle_status = LifecycleStatus.CLOSED.value
    position.record_event("lifecycle_closed", "all obligations fulfilled")
    audit.log_event(position.position_id, "lifecycle_closed", "position fully settled")

    info("lifecycle_status", position.lifecycle_status, G)
    print(f"\n {lifecycle_bar('CLOSED')}")

    # ── Final summary ──
    print(f"\n{W}{B}  Final Position State:{X}")
    info("position_id", position.position_id, C)
    info("owner", position.owner)
    info("principal_owner", position.principal_owner)
    info("reward_owner", position.reward_owner)
    info("eth_beneficiary", position.eth_beneficiary)
    info("lifecycle_status", position.lifecycle_status, G)
    info("reward_settled", str(position.reward_settled), G)
    info("withdraw_tx", position.withdraw_tx[:24] + "..." if position.withdraw_tx else "None")

    # ── Timeline ──
    print(f"\n  {W}{B}Position History:{X}")
    for h in position.history:
        ts = time.strftime("%H:%M:%S", time.localtime(h["timestamp"]))
        event = h["event"]
        color = G
        if "matured" in event:
            color = O
        elif "withdraw" in event:
            color = M
        elif "reward" in event:
            color = C
        elif "closed" in event:
            color = G
        print(f"  {D}[{ts}]{X} {color}{event:30s}{X} {D}{h.get('detail', '')[:50]}{X}")

    print(f"\n  {W}{B}Audit Log:{X}")
    for entry in audit.get_deal_history(position.position_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:28s}{X} {D}{entry.detail[:60]}{X}")

    print(f"\n{G}{'='*68}{X}")
    print(f"{G}{B}  V2 MATURITY + AUTO-WITHDRAW LIFECYCLE COMPLETE{X}")
    print(f"{G}{'='*68}{X}")
    print(f"""
  {D}Lifecycle completed:{X}
    {G}ACTIVE{X} {D}->{X} {O}MATURED{X} {D}->{X} {M}WITHDRAWN{X} {D}->{X} {C}REWARD_SETTLED{X} {D}->{X} {G}CLOSED{X}

  {D}Principal (gold) went to buyer ETH address: {BUYER_ETH}{X}
  {D}Rewards (SOST) went to buyer SOST address: {BUYER_SOST}{X}
  {D}Original seller received nothing at maturity — correct post-sale behavior.{X}
""")


if __name__ == "__main__":
    banner()
    run()
