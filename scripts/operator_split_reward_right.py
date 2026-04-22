#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Split Reward Right

Splits the reward right from a position into a new child position
owned by the buyer. The parent retains the principal claim.

Usage:
  python3 scripts/operator_split_reward_right.py --position-id abc123 --buyer SOST1xyz
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.positions.position_transfer import PositionTransferEngine
from src.operator.audit_log import AuditLog

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
    parser = argparse.ArgumentParser(description="SOST Operator — Split Reward Right")
    parser.add_argument("--position-id", required=True, help="Parent position ID")
    parser.add_argument("--buyer", required=True, help="Buyer SOST address for reward right")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json (default: data/positions.json)")
    parser.add_argument("--audit-dir", default=os.path.join(PROJECT_ROOT, "data", "audit"),
                        help="Path to audit log directory")
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

    parent = registry.get(args.position_id)
    if not parent:
        print(f"{R}ERROR:{X} Position {args.position_id} not found")
        sys.exit(1)

    reward_before = parent.reward_remaining()
    engine = PositionTransferEngine(registry)
    result = engine.split_reward_right(args.position_id, args.buyer)

    if not result.success:
        print(f"{R}SPLIT FAILED:{X} {result.message}")
        sys.exit(1)

    # Save registry
    registry.save(args.file)

    # Audit log
    audit = AuditLog(args.audit_dir)
    audit.log_event(
        deal_id=f"op_split:{args.position_id}",
        event="reward_right_split",
        detail=f"parent={args.position_id} child={result.position_id} buyer={args.buyer} reward={reward_before}",
    )

    print(f"\n{O}{B}  SOST GOLD EXCHANGE — REWARD RIGHT SPLIT{X}")
    print(f"  {D}Parent Position:  {C}{args.position_id}{X}")
    print(f"  {D}Child Position:   {G}{B}{result.position_id}{X}")
    print(f"  {D}Buyer:            {W}{args.buyer}{X}")
    print(f"  {D}Reward Moved:     {Y}{fmt_sost(reward_before)} SOST{X}")
    print(f"  {D}Result:           {G}{B}SUCCESS{X}")
    print(f"  {D}Registry saved to {args.file}{X}")
    print()


if __name__ == "__main__":
    main()
