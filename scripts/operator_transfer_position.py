#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Transfer Position

Transfers ownership of a position to a new SOST address.

Usage:
  python3 scripts/operator_transfer_position.py --position-id abc123 --new-owner SOST1xyz
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


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Transfer Position")
    parser.add_argument("--position-id", required=True, help="Position ID to transfer")
    parser.add_argument("--new-owner", required=True, help="New owner SOST address")
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

    pos = registry.get(args.position_id)
    if not pos:
        print(f"{R}ERROR:{X} Position {args.position_id} not found")
        sys.exit(1)

    old_owner = pos.owner
    engine = PositionTransferEngine(registry)
    result = engine.transfer(args.position_id, args.new_owner)

    if not result.success:
        print(f"{R}TRANSFER FAILED:{X} {result.message}")
        sys.exit(1)

    # Save registry
    registry.save(args.file)

    # Audit log
    audit = AuditLog(args.audit_dir)
    audit.log_event(
        deal_id=f"op_transfer:{args.position_id}",
        event="position_transferred",
        detail=f"from={old_owner} to={args.new_owner}",
    )

    print(f"\n{O}{B}  SOST GOLD EXCHANGE — POSITION TRANSFER{X}")
    print(f"  {D}Position:  {C}{args.position_id}{X}")
    print(f"  {D}From:      {W}{old_owner}{X}")
    print(f"  {D}To:        {G}{args.new_owner}{X}")
    print(f"  {D}Result:    {G}{B}SUCCESS{X}")
    print(f"  {D}Registry saved to {args.file}{X}")
    print()


if __name__ == "__main__":
    main()
