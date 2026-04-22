#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Show Deal Detail

Displays full information for a single deal including history and audit log.

Usage:
  python3 scripts/operator_show_deal.py --deal-id abc123def456
"""

import argparse
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settlement.deal_state_machine import DealStore, DealState
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


def fmt_time(ts):
    if not ts:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def fmt_duration(seconds):
    if seconds <= 0:
        return "expired"
    if seconds < 60:
        return f"{int(seconds)}s"
    mins = int(seconds / 60)
    if mins < 60:
        return f"{mins}m {int(seconds % 60)}s"
    hours = mins // 60
    return f"{hours}h {mins % 60}m"


def info(label, value, color=G):
    print(f"  {D}{label:24s}{X} {color}{value}{X}")


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Show Deal Detail")
    parser.add_argument("--deal-id", required=True, help="Deal ID to display")
    parser.add_argument("--deals-file", default=os.path.join(PROJECT_ROOT, "data", "deals.json"),
                        help="Path to deals.json")
    parser.add_argument("--audit-dir", default=os.path.join(PROJECT_ROOT, "data", "audit"),
                        help="Path to audit directory")
    args = parser.parse_args()

    if not os.path.exists(args.deals_file):
        print(f"{R}ERROR:{X} Deal store not found at {args.deals_file}")
        sys.exit(1)

    store = DealStore()
    store.load(args.deals_file)

    deal = store.get(args.deal_id)
    if not deal:
        # Try prefix match
        matches = [d for did, d in store._deals.items() if did.startswith(args.deal_id)]
        if len(matches) == 1:
            deal = matches[0]
        elif len(matches) > 1:
            print(f"{Y}Multiple deals match prefix '{args.deal_id}':{X}")
            for d in matches:
                print(f"  {C}{d.deal_id}{X} {D}({d.state.value}){X}")
            sys.exit(1)
        else:
            print(f"{R}ERROR:{X} Deal '{args.deal_id}' not found.")
            sys.exit(1)

    # State color
    state = deal.state.value
    if state == "SETTLED":
        sc = G
    elif state in ("EXPIRED", "REFUNDED", "DISPUTED"):
        sc = R
    else:
        sc = Y

    print(f"\n{O}{B}  DEAL {deal.deal_id}{X}")
    print(f"  {D}{'─' * 54}{X}")

    info("state", state, sc)
    info("pair", deal.pair)
    info("side", deal.side)
    info("amount_sost", f"{deal.amount_sost / 1e8:.8f} SOST ({deal.amount_sost} sat)")
    info("amount_gold", f"{deal.amount_gold / 1e18:.8f} ({deal.amount_gold} wei)")

    print(f"\n  {W}{B}Addresses{X}")
    info("maker_sost", deal.maker_sost_addr)
    info("taker_sost", deal.taker_sost_addr)
    info("maker_eth", deal.maker_eth_addr)
    info("taker_eth", deal.taker_eth_addr)

    print(f"\n  {W}{B}Timing{X}")
    info("created", fmt_time(deal.created_at))
    info("last_update", fmt_time(deal.updated_at))
    remaining = deal.expires_at - time.time()
    expires_str = fmt_time(deal.expires_at)
    if remaining > 0:
        expires_str += f" ({fmt_duration(remaining)} remaining)"
    else:
        expires_str += f" ({R}expired {fmt_duration(-remaining)} ago{X})"
    info("expires_at", expires_str)

    print(f"\n  {W}{B}Lock Status{X}")
    if deal.eth_tx_hash:
        info("eth_tx_hash", deal.eth_tx_hash, G)
        info("eth_deposit_id", str(deal.eth_deposit_id), G)
    else:
        info("eth_locked", "NO", R)

    if deal.sost_lock_txid:
        info("sost_lock_txid", deal.sost_lock_txid, G)
    else:
        info("sost_locked", "NO", R)

    if deal.settlement_tx_hash:
        print(f"\n  {W}{B}Settlement{X}")
        info("settlement_tx", deal.settlement_tx_hash, G)

    if deal.refund_reason:
        print(f"\n  {W}{B}Refund{X}")
        info("refund_reason", deal.refund_reason, R)

    # State history
    if deal.history:
        print(f"\n  {W}{B}State History{X}")
        for h in deal.history:
            ts = time.strftime("%H:%M:%S", time.localtime(h["timestamp"]))
            print(f"  {D}[{ts}]{X} {O}{h['from']:20s}{X} {D}->{X} {G}{h['to']:20s}{X} {D}{h.get('reason', '')}{X}")

    # Audit entries
    audit = AuditLog(log_dir=args.audit_dir)
    audit.load()
    entries = audit.get_deal_history(deal.deal_id)
    if entries:
        print(f"\n  {W}{B}Audit Log{X}")
        for entry in entries:
            ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
            print(f"  {D}[{ts}]{X} {C}{entry.event:24s}{X} {D}{entry.detail[:50]}{X}")

    print()


if __name__ == "__main__":
    main()
