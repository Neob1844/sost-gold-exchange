#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Check Maturity

Checks all positions for maturity transitions and reports on positions
nearing expiry.

Usage:
  python3 scripts/operator_check_maturity.py
  python3 scripts/operator_check_maturity.py --file data/positions.json
"""

import argparse
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
M = "\033[95m"
W = "\033[97m"
D = "\033[90m"
B = "\033[1m"
X = "\033[0m"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEARING_EXPIRY_SECONDS = 7 * 86400  # 7 days


def fmt_duration(seconds):
    if seconds <= 0:
        return "expired"
    days = int(seconds / 86400)
    hours = int((seconds % 86400) / 3600)
    if days > 0:
        return f"{days}d {hours}h"
    mins = int((seconds % 3600) / 60)
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def fmt_time(ts):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts))


def fmt_sost(sats):
    return f"{sats / 1e8:.8f}"


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Check Maturity")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json")
    parser.add_argument("--save", action="store_true",
                        help="Save updated registry after maturity transitions")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"{R}ERROR:{X} Position registry not found at {args.file}")
        sys.exit(1)

    registry = PositionRegistry()
    try:
        registry.load(args.file)
    except Exception as e:
        print(f"{R}ERROR:{X} Failed to load position registry: {e}")
        sys.exit(1)

    all_positions = list(registry._positions.values())
    if not all_positions:
        print(f"{Y}No positions found.{X}")
        return

    print(f"\n{O}{B}  SOST GOLD EXCHANGE — MATURITY CHECK{X}")
    print(f"  {D}Checked at: {fmt_time(time.time())}{X}")
    print(f"  {D}{len(all_positions)} position(s) loaded{X}\n")

    # Run maturity transitions
    newly_matured = registry.check_maturities()

    if newly_matured:
        print(f"  {M}{B}NEWLY MATURED ({len(newly_matured)}){X}")
        print(f"  {D}{'─' * 70}{X}")
        for pid in newly_matured:
            pos = registry.get(pid)
            owner_short = pos.owner[:20] if len(pos.owner) > 20 else pos.owner
            print(f"  {M}  {pid:16s}{X}  {W}{owner_short}{X}  {pos.token_symbol}  reward={fmt_sost(pos.reward_remaining())} remaining")
        print()

        if args.save:
            registry.save(args.file)
            print(f"  {G}Registry saved to {args.file}{X}\n")
    else:
        print(f"  {D}No new maturity transitions.{X}\n")

    # Positions nearing expiry (active, <7 days remaining)
    nearing = []
    for pos in all_positions:
        if pos.is_active() and not pos.is_matured():
            remaining = pos.time_remaining()
            if 0 < remaining < NEARING_EXPIRY_SECONDS:
                nearing.append((pos, remaining))

    if nearing:
        nearing.sort(key=lambda x: x[1])
        print(f"  {Y}{B}NEARING EXPIRY ({len(nearing)}){X}")
        print(f"  {D}{'─' * 70}{X}")
        for pos, remaining in nearing:
            owner_short = pos.owner[:20] if len(pos.owner) > 20 else pos.owner
            print(f"  {Y}  {pos.position_id:16s}{X}  {W}{owner_short}{X}  expires in {Y}{fmt_duration(remaining)}{X}")
        print()

    # Summary table
    active_count = len([p for p in all_positions if p.is_active() and not p.is_matured()])
    matured_count = len([p for p in all_positions if p.status.value == "MATURED"])
    redeemed_count = len([p for p in all_positions if p.status.value == "REDEEMED"])
    slashed_count = len([p for p in all_positions if p.status.value == "SLASHED"])

    print(f"  {W}{B}SUMMARY{X}")
    print(f"  {D}{'─' * 40}{X}")
    print(f"  {'Status':16s}  {'Count':>6s}")
    print(f"  {D}{'─' * 40}{X}")
    print(f"  {G}{'ACTIVE':16s}{X}  {active_count:>6d}")
    print(f"  {Y}{'NEARING EXPIRY':16s}{X}  {len(nearing):>6d}")
    print(f"  {M}{'MATURED':16s}{X}  {matured_count:>6d}")
    print(f"  {C}{'REDEEMED':16s}{X}  {redeemed_count:>6d}")
    print(f"  {R}{'SLASHED':16s}{X}  {slashed_count:>6d}")
    print(f"  {D}{'─' * 40}{X}")
    print(f"  {W}{'TOTAL':16s}{X}  {len(all_positions):>6d}")
    print()


if __name__ == "__main__":
    main()
