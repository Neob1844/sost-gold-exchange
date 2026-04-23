#!/usr/bin/env python3
"""
SOST Gold Exchange — V2 Live Case Reconciliation

Reads the position registry and reconciles each position with ETH deposits:
  - Ownership: principal_owner, reward_owner, eth_beneficiary
  - Lifecycle: lifecycle_status, reward_settled, withdraw_tx
  - Beneficiary sync: registry vs expected on-chain state
  - Withdraw status
  - Reward status

Color-coded: green=synced, yellow=pending, red=mismatch.

Usage:
  python3 scripts/reconcile_v2_live_case.py
  python3 scripts/reconcile_v2_live_case.py --file data/positions.json
  python3 scripts/reconcile_v2_live_case.py --dry-run
"""

import argparse
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import LifecycleStatus

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


def load_exchange_config():
    for name in ["live_alpha.local.json", "live_alpha.example.json"]:
        path = os.path.join(PROJECT_ROOT, "configs", name)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


def beneficiary_sync_status(pos):
    """Determine beneficiary sync status from position history.

    Returns (status_str, color):
      OK       / green   — synced event found for current eth_beneficiary
      PENDING  / yellow  — beneficiary set but no sync event
      MISMATCH / red     — sync event exists but for a different address
      N/A      / dim     — no eth_beneficiary set
    """
    if not pos.eth_beneficiary:
        return "N/A", D

    for h in reversed(pos.history):
        if h.get("event") == "beneficiary_synced":
            detail = h.get("detail", "")
            if pos.eth_beneficiary.lower() in detail.lower():
                return "OK", G
            else:
                return "MISMATCH", R

    # No sync event at all — check if principal_owner == owner (original, no trade happened)
    if pos.principal_owner == pos.owner and pos.eth_beneficiary:
        # Original owner still has it — sync may not have been needed yet
        # Check if there's a transfer event
        has_transfer = any(
            h.get("event") in ("transferred", "full_sale")
            for h in pos.history
        )
        if has_transfer:
            return "PENDING", Y
        else:
            return "OK", G  # original owner, no trade, no sync needed

    return "PENDING", Y


def withdraw_status(pos):
    """Determine withdraw status."""
    if pos.withdraw_tx:
        return f"DONE ({pos.withdraw_tx[:16]}...)", G
    if pos.lifecycle_status == LifecycleStatus.WITHDRAW_PENDING.value:
        return "PENDING", Y
    if pos.lifecycle_status == LifecycleStatus.MATURED.value and pos.auto_withdraw:
        return "AWAITING_DAEMON", Y
    if pos.lifecycle_status in (LifecycleStatus.ACTIVE.value,
                                 LifecycleStatus.NEARING_MATURITY.value):
        return "NOT_YET", D
    return "N/A", D


def reward_status(pos):
    """Determine reward status."""
    if pos.reward_settled:
        return f"SETTLED ({pos.reward_total_sost} sats)", G
    if pos.lifecycle_status in (LifecycleStatus.MATURED.value,
                                 LifecycleStatus.WITHDRAWN.value):
        return "PENDING_SETTLEMENT", Y
    if pos.lifecycle_status in (LifecycleStatus.ACTIVE.value,
                                 LifecycleStatus.NEARING_MATURITY.value):
        claimed = pos.reward_claimed_sost
        total = pos.reward_total_sost
        pct = (claimed / total * 100) if total > 0 else 0
        return f"ACCRUING ({claimed}/{total} = {pct:.0f}%)", D
    return "N/A", D


def main():
    parser = argparse.ArgumentParser(description="SOST — V2 Live Case Reconciliation")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip on-chain queries, just show registry state")
    args = parser.parse_args()

    config = load_exchange_config()
    eth_cfg = config.get("ethereum", {})
    escrow_address = eth_cfg.get("escrow_address", "")
    rpc_url = eth_cfg.get("rpc_url", "")

    print(f"\n{O}{B}  V2 LIVE CASE RECONCILIATION{X}")
    print(f"  {D}{'─' * 55}{X}")
    print(f"  {D}Escrow:{X}  {C}{escrow_address}{X}")
    print(f"  {D}RPC:{X}     {C}{rpc_url}{X}")
    print(f"  {D}File:{X}    {C}{args.file}{X}\n")

    if not os.path.exists(args.file):
        print(f"  {Y}Position registry not found at {args.file}{X}")
        print(f"  {D}Run a demo first to generate positions, or provide --file path.{X}\n")
        return

    registry = PositionRegistry()
    try:
        registry.load(args.file)
    except Exception as e:
        print(f"  {R}ERROR:{X} Failed to load registry: {e}\n")
        sys.exit(1)

    positions_with_deposit = [
        (pid, pos) for pid, pos in registry._positions.items()
        if pos.eth_escrow_deposit_id is not None
    ]

    if not positions_with_deposit:
        print(f"  {D}No positions with ETH deposits found.{X}\n")
        return

    summary = {"ok": 0, "pending": 0, "mismatch": 0}

    for pid, pos in positions_with_deposit:
        deposit_id = pos.eth_escrow_deposit_id

        print(f"  {C}{B}{pid}{X}")
        print(f"    {D}deposit_id:{X}       {W}{deposit_id}{X}")
        print(f"    {D}principal_owner:{X}  {W}{pos.principal_owner[:32]}...{X}")
        print(f"    {D}reward_owner:{X}     {W}{pos.reward_owner[:32]}...{X}")
        print(f"    {D}eth_beneficiary:{X}  {W}{pos.eth_beneficiary}{X}")
        print(f"    {D}lifecycle_status:{X} {W}{pos.lifecycle_status}{X}")

        # Beneficiary sync
        bsync_status, bsync_color = beneficiary_sync_status(pos)
        print(f"    {D}beneficiary_sync:{X} {bsync_color}{bsync_status}{X}")

        if bsync_status == "OK":
            summary["ok"] += 1
        elif bsync_status == "PENDING":
            summary["pending"] += 1
        elif bsync_status == "MISMATCH":
            summary["mismatch"] += 1

        # Withdraw status
        wstatus, wcolor = withdraw_status(pos)
        print(f"    {D}withdraw_status:{X}  {wcolor}{wstatus}{X}")

        # Reward status
        rstatus, rcolor = reward_status(pos)
        print(f"    {D}reward_status:{X}    {rcolor}{rstatus}{X}")

        print()

    # Summary
    print(f"  {D}{'─' * 55}{X}")
    print(f"  {W}{B}Summary:{X}")
    print(f"    {G}Synced:{X}     {summary['ok']}")
    print(f"    {Y}Pending:{X}    {summary['pending']}")
    print(f"    {R}Mismatch:{X}   {summary['mismatch']}")
    total = sum(summary.values())
    if summary["mismatch"] == 0 and total > 0:
        print(f"\n  {G}{B}NO MISMATCHES DETECTED{X}")
    elif summary["mismatch"] > 0:
        print(f"\n  {R}{B}MISMATCHES DETECTED — INVESTIGATE IMMEDIATELY{X}")
    print()


if __name__ == "__main__":
    main()
