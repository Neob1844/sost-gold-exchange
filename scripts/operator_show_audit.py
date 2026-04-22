#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Show Audit Log

Displays chronological audit entries, optionally filtered by deal_id.

Usage:
  python3 scripts/operator_show_audit.py                    # all entries
  python3 scripts/operator_show_audit.py --deal-id abc123   # filtered
"""

import argparse
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

EVENT_COLORS = {
    "registered": C,
    "eth_locked": G,
    "sost_locked": G,
    "both_locked": G,
    "settlement_initiated": O,
    "settled": G,
    "expired": R,
    "refund_requested": Y,
    "refund_executed": R,
    "unmatched_eth_deposit": Y,
}


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Show Audit Log")
    parser.add_argument("--deal-id", default=None, help="Filter by deal ID (or prefix)")
    parser.add_argument("--audit-dir", default=os.path.join(PROJECT_ROOT, "data", "audit"),
                        help="Path to audit directory")
    parser.add_argument("--tail", type=int, default=0,
                        help="Show only the last N entries")
    args = parser.parse_args()

    audit = AuditLog(log_dir=args.audit_dir)
    audit.load()

    entries = audit.get_all()
    if not entries:
        print(f"{Y}No audit entries found in {args.audit_dir}{X}")
        return

    # Filter by deal_id if specified
    if args.deal_id:
        entries = [e for e in entries if e.deal_id == args.deal_id
                   or e.deal_id.startswith(args.deal_id)]
        if not entries:
            print(f"{Y}No audit entries for deal '{args.deal_id}'{X}")
            return

    # Sort chronologically
    entries.sort(key=lambda e: e.timestamp)

    # Tail
    if args.tail > 0:
        entries = entries[-args.tail:]

    title = "AUDIT LOG"
    if args.deal_id:
        title += f" — deal {args.deal_id}"
    print(f"\n{O}{B}  {title}{X}")
    print(f"  {D}{len(entries)} entries{X}\n")

    for entry in entries:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
        ec = EVENT_COLORS.get(entry.event, D)
        detail = entry.detail if entry.detail else ""
        print(f"  {D}[{ts}]{X} {C}[{entry.deal_id:16s}]{X} {ec}{entry.event:24s}{X} {D}— {detail}{X}")

    print()


if __name__ == "__main__":
    main()
