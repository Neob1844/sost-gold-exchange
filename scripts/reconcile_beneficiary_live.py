#!/usr/bin/env python3
"""
SOST Gold Exchange — Focused Beneficiary Reconciliation

For each position with an ETH deposit:
  - Check if principal_owner changed since registration
  - Check if eth_beneficiary matches principal_owner's ETH address
  - Report: SYNCED / PENDING_SYNC / MISMATCH

Usage:
  python3 scripts/reconcile_beneficiary_live.py
  python3 scripts/reconcile_beneficiary_live.py --file data/positions.json
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry

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


def determine_status(pos):
    """Determine beneficiary sync status for a position.

    Returns (status, color, detail):
      SYNCED       / green  — beneficiary_synced event matches current eth_beneficiary
      PENDING_SYNC / yellow — principal_owner changed but no matching sync event
      MISMATCH     / red    — sync event exists for a different address
      ORIGINAL     / green  — no transfer has occurred, original owner
    """
    # Check if a transfer/sale has occurred
    transfer_events = [
        h for h in pos.history
        if h.get("event") in ("transferred", "full_sale", "reward_right_split")
    ]
    has_transfer = len(transfer_events) > 0

    if not has_transfer:
        return "ORIGINAL", G, "no transfer — original owner"

    # A transfer happened. Check if beneficiary was synced.
    sync_events = [
        h for h in pos.history
        if h.get("event") == "beneficiary_synced"
    ]

    if not sync_events:
        return "PENDING_SYNC", Y, "principal_owner changed, no sync event found"

    # Check if latest sync matches current eth_beneficiary
    latest_sync = sync_events[-1]
    detail = latest_sync.get("detail", "")

    if pos.eth_beneficiary and pos.eth_beneficiary.lower() in detail.lower():
        return "SYNCED", G, f"synced to {pos.eth_beneficiary}"
    else:
        return "MISMATCH", R, f"sync event does not match current eth_beneficiary ({pos.eth_beneficiary})"


def main():
    parser = argparse.ArgumentParser(description="SOST — Focused Beneficiary Reconciliation")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json")
    args = parser.parse_args()

    print(f"\n{O}{B}  BENEFICIARY RECONCILIATION (FOCUSED){X}")
    print(f"  {D}{'─' * 55}{X}\n")

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

    counts = {"SYNCED": 0, "ORIGINAL": 0, "PENDING_SYNC": 0, "MISMATCH": 0}

    for pid, pos in positions_with_deposit:
        deposit_id = pos.eth_escrow_deposit_id
        status, color, detail = determine_status(pos)

        # Status badge
        badge_width = 13
        badge = f"{color}{status:>{badge_width}}{X}"

        print(f"  {badge}  {C}{pid[:16]}{X}  "
              f"{D}deposit=#{deposit_id}{X}  "
              f"{D}principal={pos.principal_owner[:20]}...{X}")

        if status == "PENDING_SYNC":
            print(f"  {' ' * badge_width}  {Y}eth_beneficiary={pos.eth_beneficiary}{X}")
            print(f"  {' ' * badge_width}  {Y}{detail}{X}")
        elif status == "MISMATCH":
            print(f"  {' ' * badge_width}  {R}eth_beneficiary={pos.eth_beneficiary}{X}")
            print(f"  {' ' * badge_width}  {R}{detail}{X}")

        counts[status] = counts.get(status, 0) + 1

    # Summary
    total = sum(counts.values())
    print(f"\n  {D}{'─' * 55}{X}")
    print(f"  {W}{B}Summary ({total} positions with ETH deposits):{X}")
    print(f"    {G}SYNCED:{X}       {counts.get('SYNCED', 0)}")
    print(f"    {G}ORIGINAL:{X}     {counts.get('ORIGINAL', 0)}")
    print(f"    {Y}PENDING_SYNC:{X} {counts.get('PENDING_SYNC', 0)}")
    print(f"    {R}MISMATCH:{X}     {counts.get('MISMATCH', 0)}")

    if counts.get("MISMATCH", 0) == 0:
        print(f"\n  {G}{B}NO MISMATCHES{X}")
    else:
        print(f"\n  {R}{B}MISMATCHES DETECTED — REQUIRES INVESTIGATION{X}")

    if counts.get("PENDING_SYNC", 0) > 0:
        print(f"  {Y}Pending syncs should be resolved by beneficiary_sync daemon.{X}")

    print()


if __name__ == "__main__":
    main()
