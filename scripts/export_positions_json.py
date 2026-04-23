#!/usr/bin/env python3
"""
SOST Gold Exchange — Position Export

Loads position registry from data/positions.json and formats into the
positions_live.json structure matching the web page API format.

Writes to a configurable output path (default: stdout).
Designed to be run periodically (cron or systemd timer) to update the web API.

Usage:
  python3 scripts/export_positions_json.py
  python3 scripts/export_positions_json.py --output /opt/sost/website/api/positions_live.json
  python3 scripts/export_positions_json.py --positions data/positions.json
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

from src.positions.position_registry import PositionRegistry


def load_positions(path: str) -> PositionRegistry:
    """Load position registry from JSON file. Returns empty registry on error."""
    registry = PositionRegistry()
    if os.path.exists(path):
        try:
            registry.load(path)
        except Exception as e:
            print(f"Warning: failed to load positions from {path}: {e}",
                  file=sys.stderr)
    return registry


def export_positions(registry: PositionRegistry) -> dict:
    """Convert registry into the positions_live.json API format."""
    positions = []
    total_gold_wei = 0
    total_reward_sost = 0
    active_count = 0
    sepolia_addresses = set()

    for pos in registry._positions.values():
        d = pos.to_dict()

        # Computed fields matching dashboard_api format
        d["is_active"] = pos.is_active()
        d["is_matured"] = pos.is_matured()
        d["reward_remaining"] = pos.reward_remaining()
        d["time_remaining"] = pos.time_remaining()
        d["pct_complete"] = round(pos.pct_complete(), 2)

        positions.append(d)

        # Aggregate totals
        total_gold_wei += pos.reference_amount
        total_reward_sost += pos.reward_total_sost
        if pos.is_active():
            active_count += 1

        # Collect Sepolia addresses from escrow txs (skip zero-hash placeholders)
        if (pos.eth_escrow_tx
                and pos.eth_escrow_tx.startswith("0x")
                and pos.eth_escrow_tx.replace("0", "").replace("x", "") != ""):
            sepolia_addresses.add(pos.eth_escrow_tx)

    # Collect unique owners
    owners = set(pos.owner for pos in registry._positions.values())

    return {
        "generated_at": time.time(),
        "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_positions": len(positions),
        "active_positions": active_count,
        "unique_owners": len(owners),
        "total_gold_reference_wei": total_gold_wei,
        "total_reward_sost": total_reward_sost,
        "sepolia_escrow_txs": sorted(sepolia_addresses),
        "positions": positions,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export SOST positions to JSON API format"
    )
    parser.add_argument(
        "--positions", default=os.path.join(_project_root, "data", "positions.json"),
        help="Path to positions.json (default: data/positions.json)",
    )
    parser.add_argument(
        "--output", default="",
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    registry = load_positions(args.positions)
    result = export_positions(registry)
    output_json = json.dumps(result, indent=2) + "\n"

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        # Write atomically via temp file
        tmp_path = args.output + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                f.write(output_json)
            os.replace(tmp_path, args.output)
            print(f"Exported {result['total_positions']} positions to {args.output}",
                  file=sys.stderr)
        except Exception as e:
            print(f"Error writing to {args.output}: {e}", file=sys.stderr)
            # Clean up temp file on failure
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            sys.exit(1)
    else:
        sys.stdout.write(output_json)


if __name__ == "__main__":
    main()
