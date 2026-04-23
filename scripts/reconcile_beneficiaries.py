#!/usr/bin/env python3
"""
SOST Gold Exchange — Reconcile Beneficiaries

Compares the SOST position registry's eth_beneficiary with the on-chain
currentBeneficiary in EscrowV2. Reports mismatches.

Usage:
  python3 scripts/reconcile_beneficiaries.py
  python3 scripts/reconcile_beneficiaries.py --file data/positions.json
"""

import argparse
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry

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


def query_on_chain_beneficiary(escrow_address: str, deposit_id: int, rpc_url: str):
    """Query currentBeneficiary for a deposit via eth_call."""
    try:
        import urllib.request
        # currentBeneficiary(uint256) selector
        deposit_hex = hex(deposit_id)[2:].zfill(64)
        data = "0x5c23bdf5" + deposit_hex  # currentBeneficiary(uint256)
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
        if hex_data and len(hex_data) >= 42:
            return "0x" + hex_data[-40:]
    except Exception as e:
        return f"ERROR: {e}"
    return None


def main():
    parser = argparse.ArgumentParser(description="SOST — Reconcile Beneficiaries")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip on-chain queries, just show registry state")
    args = parser.parse_args()

    config = load_exchange_config()
    eth_cfg = config.get("ethereum", {})
    escrow_address = eth_cfg.get("escrow_address", "")
    rpc_url = eth_cfg.get("rpc_url", "")

    print(f"\n{O}{B}  BENEFICIARY RECONCILIATION{X}")
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

    positions_with_deposit = [
        (pid, pos) for pid, pos in registry._positions.items()
        if pos.eth_escrow_deposit_id is not None
    ]

    if not positions_with_deposit:
        print(f"  {D}No positions with ETH deposits found.{X}\n")
        return

    mismatches = 0
    matches = 0
    errors = 0

    for pid, pos in positions_with_deposit:
        registry_beneficiary = pos.eth_beneficiary or pos.owner
        deposit_id = pos.eth_escrow_deposit_id

        if args.dry_run:
            print(f"  {C}{pid[:12]}{X} deposit=#{deposit_id} registry_beneficiary={D}{registry_beneficiary}{X}")
            continue

        on_chain = query_on_chain_beneficiary(escrow_address, deposit_id, rpc_url)

        if on_chain and on_chain.startswith("ERROR"):
            print(f"  {Y}[ERR]{X}  {C}{pid[:12]}{X} deposit=#{deposit_id} — {R}{on_chain}{X}")
            errors += 1
        elif on_chain and on_chain.lower() == registry_beneficiary.lower():
            print(f"  {G}[OK]{X}   {C}{pid[:12]}{X} deposit=#{deposit_id} beneficiary={D}{on_chain}{X}")
            matches += 1
        else:
            print(f"  {R}[MISMATCH]{X} {C}{pid[:12]}{X} deposit=#{deposit_id}")
            print(f"           registry:  {Y}{registry_beneficiary}{X}")
            print(f"           on-chain:  {R}{on_chain}{X}")
            mismatches += 1

    if not args.dry_run:
        print(f"\n  {D}{'─' * 50}{X}")
        print(f"  {G}Matches:{X}    {matches}")
        print(f"  {R}Mismatches:{X} {mismatches}")
        print(f"  {Y}Errors:{X}     {errors}")

    print()


if __name__ == "__main__":
    main()
