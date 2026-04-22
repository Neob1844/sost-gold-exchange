#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Show Positions

Reads the position registry and prints a table of all positions.

Usage:
  python3 scripts/operator_show_positions.py
  python3 scripts/operator_show_positions.py --file data/positions.json
"""

import argparse
import json
import time
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

STATUS_COLORS = {
    "ACTIVE": G,
    "MATURED": Y,
    "REDEEMED": C,
    "SLASHED": R,
    "TRANSFERRED": D,
    "EXPIRED": R,
}


def fmt_sost(sats):
    return f"{sats / 1e8:.8f}"


def fmt_remaining(pos):
    remaining = pos.time_remaining()
    if remaining <= 0:
        return f"{R}matured{X}"
    days = int(remaining / 86400)
    if days > 0:
        return f"{days}d"
    hours = int(remaining / 3600)
    if hours > 0:
        return f"{hours}h"
    return f"{int(remaining / 60)}m"


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Show Positions")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json (default: data/positions.json)")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"{R}ERROR:{X} Position registry not found at {args.file}")
        print(f"{D}No positions have been created yet.{X}")
        sys.exit(1)

    registry = PositionRegistry()
    try:
        registry.load(args.file)
    except Exception as e:
        print(f"{R}ERROR:{X} Failed to load position registry: {e}")
        sys.exit(1)

    positions = list(registry._positions.values())
    if not positions:
        print(f"{Y}No positions found.{X}")
        return

    print(f"\n{O}{B}  SOST GOLD EXCHANGE — POSITION REGISTRY{X}")
    print(f"  {D}{len(positions)} position(s) loaded from {args.file}{X}\n")

    # Header
    hdr = f"  {'POSITION ID':16s}  {'OWNER':16s}  {'MODEL':10s}  {'TOKEN':6s}  {'AMOUNT':>20s}  {'STATUS':12s}  {'REWARD LEFT':>14s}  {'EXPIRES':8s}"
    print(f"{W}{B}{hdr}{X}")
    print(f"  {D}{'─' * (len(hdr) - 2)}{X}")

    for pos in sorted(positions, key=lambda p: p.start_time, reverse=True):
        status = pos.status.value
        sc = STATUS_COLORS.get(status, D)
        model = pos.contract_type.value.replace("MODEL_", "").replace("_ESCROW", "-esc").replace("_CUSTODY", "-cus")
        amount_str = f"{pos.reference_amount / 1e18:.8f}" if pos.reference_amount > 1e12 else str(pos.reference_amount)
        reward_rem = fmt_sost(pos.reward_remaining())
        expires = fmt_remaining(pos)
        owner_short = pos.owner[:16] if len(pos.owner) > 16 else pos.owner

        print(f"  {C}{pos.position_id:16s}{X}  {W}{owner_short:16s}{X}  {D}{model:10s}{X}  {pos.token_symbol:6s}  {amount_str:>20s}  {sc}{status:12s}{X}  {reward_rem:>14s}  {expires}")

    # Summary
    active = len([p for p in positions if p.is_active()])
    matured = len([p for p in positions if p.is_matured()])
    print(f"\n  {D}Active: {active}  Matured: {matured}  Total: {len(positions)}{X}\n")


if __name__ == "__main__":
    main()
