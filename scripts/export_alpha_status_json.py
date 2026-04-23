#!/usr/bin/env python3
"""
SOST Gold Exchange — Alpha Status Export

Reads position registry, deal store, and configs to produce a comprehensive
alpha_status.json for the web dashboard.

Usage:
  python3 scripts/export_alpha_status_json.py
  python3 scripts/export_alpha_status_json.py --output /opt/sost/website/api/alpha_live_status.json
"""

import json
import os
import sys
import argparse
import time
import glob as globmod

_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_this_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.positions.position_registry import PositionRegistry
from src.settlement.deal_state_machine import DealStore, DealState


def load_config(path: str) -> dict:
    """Load config JSON. Returns empty dict on error."""
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: failed to load config from {path}: {e}",
                  file=sys.stderr)
    return {}


def load_positions(path: str) -> PositionRegistry:
    """Load position registry from JSON file."""
    registry = PositionRegistry()
    if os.path.exists(path):
        try:
            registry.load(path)
        except Exception as e:
            print(f"Warning: failed to load positions from {path}: {e}",
                  file=sys.stderr)
    return registry


def load_deals(path: str) -> DealStore:
    """Load deal store from JSON file."""
    store = DealStore()
    if os.path.exists(path):
        try:
            store.load(path)
        except Exception as e:
            print(f"Warning: failed to load deals from {path}: {e}",
                  file=sys.stderr)
    return store


def count_tests() -> dict:
    """Count test files in the test directories."""
    test_dir = os.path.join(_project_root, "tests")
    counts = {
        "unit": 0,
        "integration": 0,
        "settlement": 0,
        "adversarial": 0,
    }
    for category in counts:
        pattern = os.path.join(test_dir, category, "test_*.py")
        counts[category] = len(globmod.glob(pattern))
    return counts


def check_e2e_status() -> dict:
    """Check basic e2e readiness indicators."""
    indicators = {}
    # Check if live config exists
    indicators["live_config_exists"] = os.path.exists(
        os.path.join(_project_root, "configs", "live_alpha.local.json")
    )
    # Check if deals data exists
    indicators["deals_data_exists"] = os.path.exists(
        os.path.join(_project_root, "data", "deals.json")
    )
    # Check if positions data exists
    indicators["positions_data_exists"] = os.path.exists(
        os.path.join(_project_root, "data", "positions.json")
    )
    # Check if audit directory exists
    indicators["audit_dir_exists"] = os.path.isdir(
        os.path.join(_project_root, "data", "audit")
    )
    return indicators


def export_alpha_status(
    registry: PositionRegistry,
    store: DealStore,
    config: dict,
) -> dict:
    """Produce the comprehensive alpha status payload."""
    # Position stats
    all_positions = list(registry._positions.values())
    active_positions = [p for p in all_positions if p.is_active()]
    total_gold_wei = sum(p.reference_amount for p in all_positions)
    total_reward_sost = sum(p.reward_total_sost for p in all_positions)

    # Deal stats
    all_deals = list(store._deals.values())
    settled_deals = [d for d in all_deals if d.state == DealState.SETTLED]
    active_deals = [d for d in all_deals if not d.is_terminal()]

    # Participants
    participants = set()
    for d in all_deals:
        participants.add(d.maker_sost_addr)
        participants.add(d.taker_sost_addr)
    for p in all_positions:
        participants.add(p.owner)

    return {
        "generated_at": time.time(),
        "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": config.get("mode", "unknown"),
        "positions": {
            "total": len(all_positions),
            "active": len(active_positions),
            "total_gold_reference_wei": total_gold_wei,
            "total_reward_sost": total_reward_sost,
        },
        "deals": {
            "total": len(all_deals),
            "active": len(active_deals),
            "settled": len(settled_deals),
        },
        "participants": {
            "unique_count": len(participants),
        },
        "test_counts": count_tests(),
        "e2e_status": check_e2e_status(),
        "ethereum": {
            "chain_id": config.get("ethereum", {}).get("chain_id"),
            "escrow_address": config.get("ethereum", {}).get("escrow_address"),
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export SOST alpha status to JSON"
    )
    parser.add_argument(
        "--config",
        default=os.path.join(_project_root, "configs", "live_alpha.local.json"),
        help="Path to live config (default: configs/live_alpha.local.json)",
    )
    parser.add_argument(
        "--positions",
        default=os.path.join(_project_root, "data", "positions.json"),
        help="Path to positions.json",
    )
    parser.add_argument(
        "--deals",
        default=os.path.join(_project_root, "data", "deals.json"),
        help="Path to deals.json",
    )
    parser.add_argument(
        "--output", default="",
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    registry = load_positions(args.positions)
    store = load_deals(args.deals)

    result = export_alpha_status(registry, store, config)
    output_json = json.dumps(result, indent=2) + "\n"

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        tmp_path = args.output + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                f.write(output_json)
            os.replace(tmp_path, args.output)
            print(f"Exported alpha status to {args.output}", file=sys.stderr)
        except Exception as e:
            print(f"Error writing to {args.output}: {e}", file=sys.stderr)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            sys.exit(1)
    else:
        sys.stdout.write(output_json)


if __name__ == "__main__":
    main()
