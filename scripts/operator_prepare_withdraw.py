#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Prepare Withdraw

Checks whether a position is ready for ETH escrow withdrawal and
prints the cast command to execute. Does NOT execute the withdrawal.

Usage:
  python3 scripts/operator_prepare_withdraw.py --position-id 8afed8fcd27553a7
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
M = "\033[95m"
W = "\033[97m"
D = "\033[90m"
B = "\033[1m"
X = "\033[0m"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fmt_time(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))


def fmt_duration(seconds):
    if seconds <= 0:
        return "now"
    days = int(seconds / 86400)
    hours = int((seconds % 86400) / 3600)
    mins = int((seconds % 3600) / 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0:
        parts.append(f"{mins}m")
    return " ".join(parts) if parts else "<1m"


def load_contracts_config():
    """Load Sepolia contract addresses."""
    path = os.path.join(PROJECT_ROOT, "configs", "sepolia_contracts.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def load_exchange_config():
    """Load exchange config for RPC URL."""
    for name in ["live_alpha.local.json", "live_alpha.example.json"]:
        path = os.path.join(PROJECT_ROOT, "configs", name)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Prepare Withdraw")
    parser.add_argument("--position-id", required=True, help="Position ID to check")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json")
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
        matches = [p for pid, p in registry._positions.items()
                    if pid.startswith(args.position_id)]
        if len(matches) == 1:
            pos = matches[0]
        else:
            print(f"{R}ERROR:{X} Position '{args.position_id}' not found.")
            sys.exit(1)

    contracts = load_contracts_config()
    config = load_exchange_config()

    escrow_address = contracts.get("escrow", config.get("ethereum", {}).get("escrow_address", ""))
    rpc_url = config.get("ethereum", {}).get("rpc_url", "https://rpc.sepolia.org")

    print(f"\n{O}{B}  WITHDRAW PREPARATION — {pos.position_id}{X}")
    print(f"  {D}{'─' * 55}{X}\n")

    # Check position status
    is_matured = pos.is_matured() or pos.status.value in ("MATURED",)
    remaining = pos.time_remaining()

    print(f"  {W}{B}Position Status{X}")
    print(f"  {D}{'Status:':20s}{X} {pos.status.value}")
    print(f"  {D}{'Expiry:':20s}{X} {fmt_time(pos.expiry_time)}")

    if pos.status.value == "REDEEMED":
        print(f"\n  {Y}Position already redeemed.{X}\n")
        return

    if pos.status.value == "SLASHED":
        print(f"\n  {R}Position has been slashed. Withdraw not available.{X}\n")
        return

    if not is_matured and remaining > 0:
        print(f"  {D}{'Time Remaining:':20s}{X} {Y}{fmt_duration(remaining)}{X}")
        print(f"\n  {Y}Position has not matured yet.{X}")
        print(f"  {D}Maturity expected: {fmt_time(pos.expiry_time)}{X}")
        print(f"  {D}Time until maturity: {fmt_duration(remaining)}{X}\n")
        return

    print(f"  {D}{'Matured:':20s}{X} {G}YES{X}")

    if pos.eth_escrow_deposit_id is None:
        print(f"\n  {R}No ETH escrow deposit ID on this position.{X}")
        print(f"  {D}This may be a Model A (custody) position.{X}\n")
        return

    deposit_id = pos.eth_escrow_deposit_id

    print(f"\n  {W}{B}Escrow Details{X}")
    print(f"  {D}{'Escrow Contract:':20s}{X} {C}{escrow_address}{X}")
    print(f"  {D}{'Deposit ID:':20s}{X} {C}#{deposit_id}{X}")
    if pos.eth_escrow_tx:
        print(f"  {D}{'Deposit TX:':20s}{X} {C}{pos.eth_escrow_tx}{X}")

    # Check canWithdraw on-chain (read-only call)
    can_withdraw_known = False
    can_withdraw = None
    try:
        import urllib.request
        # canWithdraw(uint256) selector = 0x4a1b0d8e (approximate — depends on ABI)
        # Use getDeposit to check timing instead
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
        if hex_data and len(hex_data) > 66:
            can_withdraw_known = True
            # Parse release timestamp from deposit struct
            # Typical layout: depositor(address), token(address), amount(uint256), releaseTime(uint256), withdrawn(bool)
            # releaseTime is at offset 192 (3rd uint256 after two addresses)
            if len(hex_data) >= 258:
                release_time = int(hex_data[194:258], 16)
                withdrawn = int(hex_data[258:322], 16) if len(hex_data) >= 322 else 0
                now = time.time()
                can_withdraw = (now >= release_time) and not withdrawn
                print(f"  {D}{'Release Time:':20s}{X} {fmt_time(release_time)}")
                print(f"  {D}{'Already Withdrawn:':20s}{X} {'YES' if withdrawn else 'NO'}")
                print(f"  {D}{'Can Withdraw:':20s}{X} {G + 'YES' + X if can_withdraw else R + 'NO' + X}")
    except Exception as e:
        print(f"  {D}On-chain check failed: {e}{X}")

    # Print cast command
    print(f"\n  {W}{B}Withdraw Command{X}")
    print(f"  {D}The following cast command will withdraw deposit #{deposit_id}:{X}\n")

    cast_cmd = (
        f"cast send {escrow_address} "
        f'"withdraw(uint256)" {deposit_id} '
        f"--rpc-url {rpc_url} "
        f"--private-key $PRIVATE_KEY"
    )

    print(f"  {G}{cast_cmd}{X}\n")

    if can_withdraw is False and can_withdraw_known:
        print(f"  {R}WARNING: On-chain check indicates withdraw is NOT yet available.{X}")
        print(f"  {D}The escrow release time has not been reached, or deposit was already withdrawn.{X}\n")
    elif can_withdraw is True:
        print(f"  {G}On-chain check confirms: withdraw is available.{X}\n")
    else:
        print(f"  {Y}Could not verify on-chain status. Check manually before executing.{X}\n")

    print(f"  {D}Replace $PRIVATE_KEY with the depositor's private key.{X}")
    print(f"  {D}Use operator_execute_withdraw_demo.py to execute with safety checks.{X}\n")


if __name__ == "__main__":
    main()
