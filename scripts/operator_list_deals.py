#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: List All Deals

Reads the deal store and prints a color-coded table of all deals.

Usage:
  python3 scripts/operator_list_deals.py
  python3 scripts/operator_list_deals.py --file data/deals.json
"""

import argparse
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settlement.deal_state_machine import DealStore, DealState

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

STATE_COLORS = {
    "SETTLED": G,
    "REFUNDED": R,
    "EXPIRED": R,
    "DISPUTED": R,
    "BOTH_LOCKED": G,
    "CREATED": Y,
    "NEGOTIATED": Y,
    "AWAITING_ETH_LOCK": Y,
    "AWAITING_SOST_LOCK": Y,
    "SETTLING": O,
    "REFUND_PENDING": O,
}


def fmt_time(ts):
    if not ts:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def fmt_expires(ts):
    if not ts:
        return "—"
    remaining = ts - time.time()
    if remaining <= 0:
        return f"{R}expired{X}"
    mins = int(remaining / 60)
    if mins < 60:
        return f"{mins}m"
    return f"{mins // 60}h{mins % 60:02d}m"


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — List Deals")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "deals.json"),
                        help="Path to deals.json (default: data/deals.json)")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"{R}ERROR:{X} Deal store not found at {args.file}")
        print(f"{D}Run a demo first to create deals, or specify --file.{X}")
        sys.exit(1)

    store = DealStore()
    try:
        store.load(args.file)
    except Exception as e:
        print(f"{R}ERROR:{X} Failed to load deal store: {e}")
        sys.exit(1)

    deals = list(store._deals.values())
    if not deals:
        print(f"{Y}No deals found.{X}")
        return

    print(f"\n{O}{B}  SOST GOLD EXCHANGE — DEAL LIST{X}")
    print(f"{D}  {len(deals)} deal(s) loaded from {args.file}{X}\n")

    # Header
    hdr = f"  {'DEAL ID':16s}  {'STATE':20s}  {'PAIR':10s}  {'SOST':>16s}  {'GOLD':>20s}  {'CREATED':16s}  {'EXPIRES':10s}"
    print(f"{W}{B}{hdr}{X}")
    print(f"  {D}{'─' * (len(hdr) - 2)}{X}")

    for deal in sorted(deals, key=lambda d: d.created_at, reverse=True):
        state = deal.state.value
        sc = STATE_COLORS.get(state, D)
        sost_str = f"{deal.amount_sost / 1e8:.8f}"
        gold_str = f"{deal.amount_gold / 1e18:.8f}"
        created = fmt_time(deal.created_at)
        expires = fmt_expires(deal.expires_at)

        print(f"  {C}{deal.deal_id:16s}{X}  {sc}{state:20s}{X}  {deal.pair:10s}  {sost_str:>16s}  {gold_str:>20s}  {D}{created}{X}  {expires}")

    print()


if __name__ == "__main__":
    main()
