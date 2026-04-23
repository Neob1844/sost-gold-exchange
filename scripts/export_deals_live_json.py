#!/usr/bin/env python3
"""
SOST Gold Exchange — Deal Export

Loads DealStore from data/deals.json and formats into the
deals_live.json structure matching the web page API format.

Writes to a configurable output path (default: stdout).
Designed to be run periodically (cron or systemd timer) to update the web API.

Usage:
  python3 scripts/export_deals_live_json.py
  python3 scripts/export_deals_live_json.py --output /opt/sost/website/api/deals_live.json
  python3 scripts/export_deals_live_json.py --deals data/deals.json
"""

import json
import os
import sys
import argparse
import time

_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_this_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.settlement.deal_state_machine import DealStore, DealState


def load_deals(path: str) -> DealStore:
    """Load deal store from JSON file. Returns empty store on error."""
    store = DealStore()
    if os.path.exists(path):
        try:
            store.load(path)
        except Exception as e:
            print(f"Warning: failed to load deals from {path}: {e}",
                  file=sys.stderr)
    return store


def format_deal(deal) -> dict:
    """Format a single deal into the web API structure."""
    return {
        "deal_id": deal.deal_id,
        "type": deal.pair,
        "status": deal.state.value,
        "side": deal.side,
        "maker_sost_addr": deal.maker_sost_addr,
        "taker_sost_addr": deal.taker_sost_addr,
        "maker_eth_addr": deal.maker_eth_addr,
        "taker_eth_addr": deal.taker_eth_addr,
        "amount_sost": deal.amount_sost,
        "amount_gold": deal.amount_gold,
        "created_at": deal.created_at,
        "updated_at": deal.updated_at,
        "expires_at": deal.expires_at,
        "is_terminal": deal.is_terminal(),
        "eth_tx_hash": deal.eth_tx_hash,
        "sost_lock_txid": deal.sost_lock_txid,
        "settlement_tx_hash": deal.settlement_tx_hash,
    }


def export_deals(store: DealStore) -> dict:
    """Convert deal store into the deals_live.json API format."""
    deals = []
    total_sost = 0
    total_gold = 0
    settled_count = 0
    active_count = 0

    for deal in store._deals.values():
        deals.append(format_deal(deal))

        total_sost += deal.amount_sost
        total_gold += deal.amount_gold

        if deal.state == DealState.SETTLED:
            settled_count += 1
        if not deal.is_terminal():
            active_count += 1

    # Collect unique participants
    participants = set()
    for deal in store._deals.values():
        participants.add(deal.maker_sost_addr)
        participants.add(deal.taker_sost_addr)

    return {
        "generated_at": time.time(),
        "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_deals": len(deals),
        "active_deals": active_count,
        "settled_deals": settled_count,
        "unique_participants": len(participants),
        "total_sost_volume": total_sost,
        "total_gold_volume": total_gold,
        "deals": deals,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export SOST deals to JSON API format"
    )
    parser.add_argument(
        "--deals", default=os.path.join(_project_root, "data", "deals.json"),
        help="Path to deals.json (default: data/deals.json)",
    )
    parser.add_argument(
        "--output", default="",
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    store = load_deals(args.deals)
    result = export_deals(store)
    output_json = json.dumps(result, indent=2) + "\n"

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        tmp_path = args.output + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                f.write(output_json)
            os.replace(tmp_path, args.output)
            print(f"Exported {result['total_deals']} deals to {args.output}",
                  file=sys.stderr)
        except Exception as e:
            print(f"Error writing to {args.output}: {e}", file=sys.stderr)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            sys.exit(1)
    else:
        sys.stdout.write(output_json)


if __name__ == "__main__":
    main()
