#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Value Position

Computes the current value of a position given a gold price in SOST.

Usage:
  python3 scripts/operator_value_position.py --position-id abc123 --gold-price 500000000
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.positions.position_pricing import value_position

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


def fmt_sost(sats):
    return f"{sats / 1e8:.8f}"


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Value Position")
    parser.add_argument("--position-id", required=True, help="Position ID to value")
    parser.add_argument("--gold-price", required=True, type=float,
                        help="Gold price in SOST satoshis per reference unit")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json (default: data/positions.json)")
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

    pos = registry.get(args.position_id)
    if not pos:
        print(f"{R}ERROR:{X} Position {args.position_id} not found")
        sys.exit(1)

    val = value_position(pos, args.gold_price)

    print(f"\n{O}{B}  SOST GOLD EXCHANGE — POSITION VALUATION{X}")
    print(f"  {D}Position: {C}{val.position_id}{X}")
    print(f"  {D}Owner:    {W}{pos.owner}{X}")
    print(f"  {D}Status:   {G}{pos.status.value}{X}")
    print(f"  {D}Model:    {W}{pos.contract_type.value}{X}")
    print(f"  {D}Token:    {W}{pos.token_symbol}{X}")
    print()
    print(f"  {W}{B}{'Gold Value:':<20s}{X} {G}{fmt_sost(val.gold_value_sost):>18s} SOST{X}")
    print(f"  {W}{B}{'Reward Value:':<20s}{X} {C}{fmt_sost(val.reward_value_sost):>18s} SOST{X}")
    print(f"  {W}{B}{'Discount:':<20s}{X} {R}-{fmt_sost(val.discount_sost):>17s} SOST{X}")
    print(f"  {D}{'─' * 44}{X}")
    print(f"  {W}{B}{'Net Value:':<20s}{X} {Y}{B}{fmt_sost(val.net_value_sost):>18s} SOST{X}")
    print()
    print(f"  {D}{val.detail}{X}")
    print()


if __name__ == "__main__":
    main()
