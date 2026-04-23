#!/usr/bin/env python3
"""
SOST Gold Exchange — Reconcile Withdraw Status

Compares the registry's lifecycle_status with on-chain withdrawal state
for matured positions. Reports:
  - Matured but not yet withdrawn
  - Withdrawn on-chain but registry still shows matured
  - Registry shows withdrawn but on-chain disagrees

Usage:
  python3 scripts/reconcile_withdraw_status.py
  python3 scripts/reconcile_withdraw_status.py --file data/positions.json
"""

import argparse
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import LifecycleStatus

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


def load_exchange_config():
    for name in ["live_alpha.local.json", "live_alpha.example.json"]:
        path = os.path.join(PROJECT_ROOT, "configs", name)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


def query_on_chain_withdrawn(escrow_address: str, deposit_id: int, rpc_url: str):
    """Query on-chain whether a deposit has been withdrawn."""
    try:
        import urllib.request
        deposit_hex = hex(deposit_id)[2:].zfill(64)
        data = "0x9a7c4b71" + deposit_hex  # getDeposit(uint256)
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "method": "eth_call",
            "params": [{"to": escrow_address, "data": data}, "latest"],
        }).encode()
        req = urllib.request.Request(
            rpc_url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            rpc_result = json.loads(resp.read())
        hex_data = rpc_result.get("result", "0x")
        if hex_data and len(hex_data) >= 322:
            withdrawn = int(hex_data[258:322], 16)
            return bool(withdrawn)
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="SOST — Reconcile Withdraw Status")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip on-chain queries, just show registry state")
    args = parser.parse_args()

    config = load_exchange_config()
    eth_cfg = config.get("ethereum", {})
    escrow_address = eth_cfg.get("escrow_address", "")
    rpc_url = eth_cfg.get("rpc_url", "")

    print(f"\n{O}{B}  WITHDRAW STATUS RECONCILIATION{X}")
    print(f"  {D}{'─' * 50}{X}")
    print(f"  {D}Escrow:{X}  {C}{escrow_address}{X}")
    print(f"  {D}RPC:{X}     {C}{rpc_url}{X}\n")

    if not os.path.exists(args.file):
        print(f"{R}ERROR:{X} Position registry not found at {args.file}")
        sys.exit(1)

    registry = PositionRegistry()
    try:
        registry.load(args.file)
    except Exception as e:
        print(f"{R}ERROR:{X} Failed to load registry: {e}")
        sys.exit(1)

    # Filter to matured+ positions with ETH deposits
    relevant_statuses = {
        LifecycleStatus.MATURED.value,
        LifecycleStatus.WITHDRAW_PENDING.value,
        LifecycleStatus.WITHDRAWN.value,
        LifecycleStatus.REWARD_SETTLED.value,
        LifecycleStatus.CLOSED.value,
    }

    positions = [
        (pid, pos) for pid, pos in registry._positions.items()
        if (pos.lifecycle_status in relevant_statuses
            or (pos.status.value == "MATURED")
            or (time.time() >= pos.expiry_time))
        and pos.eth_escrow_deposit_id is not None
    ]

    if not positions:
        print(f"  {D}No matured positions with ETH deposits found.{X}\n")
        return

    matured_not_withdrawn = 0
    stale_registry = 0
    consistent = 0
    errors = 0

    for pid, pos in positions:
        deposit_id = pos.eth_escrow_deposit_id
        registry_status = pos.lifecycle_status
        registry_withdrawn = registry_status in (
            LifecycleStatus.WITHDRAWN.value,
            LifecycleStatus.REWARD_SETTLED.value,
            LifecycleStatus.CLOSED.value,
        )

        if args.dry_run:
            print(f"  {C}{pid[:12]}{X} deposit=#{deposit_id} lifecycle={D}{registry_status}{X} withdraw_tx={D}{pos.withdraw_tx or 'None'}{X}")
            continue

        on_chain_withdrawn = query_on_chain_withdrawn(escrow_address, deposit_id, rpc_url)

        if on_chain_withdrawn is None:
            print(f"  {Y}[ERR]{X}  {C}{pid[:12]}{X} deposit=#{deposit_id} — on-chain query failed")
            errors += 1
            continue

        if on_chain_withdrawn and registry_withdrawn:
            print(f"  {G}[OK]{X}   {C}{pid[:12]}{X} deposit=#{deposit_id} — both show withdrawn")
            consistent += 1
        elif not on_chain_withdrawn and not registry_withdrawn:
            print(f"  {Y}[PEND]{X} {C}{pid[:12]}{X} deposit=#{deposit_id} — matured, not yet withdrawn")
            matured_not_withdrawn += 1
        elif on_chain_withdrawn and not registry_withdrawn:
            print(f"  {R}[STALE]{X} {C}{pid[:12]}{X} deposit=#{deposit_id} — on-chain withdrawn but registry shows {Y}{registry_status}{X}")
            stale_registry += 1
        else:
            print(f"  {R}[MISMATCH]{X} {C}{pid[:12]}{X} deposit=#{deposit_id} — registry withdrawn but on-chain NOT")
            stale_registry += 1

    if not args.dry_run:
        print(f"\n  {D}{'─' * 50}{X}")
        print(f"  {G}Consistent:{X}          {consistent}")
        print(f"  {Y}Matured/not withdrawn:{X} {matured_not_withdrawn}")
        print(f"  {R}Stale/mismatch:{X}       {stale_registry}")
        print(f"  {Y}Errors:{X}               {errors}")

    print()


if __name__ == "__main__":
    main()
