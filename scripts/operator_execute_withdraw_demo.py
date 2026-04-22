#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Execute Withdraw Demo

Builds and optionally executes the ETH escrow withdraw on Sepolia.
Without --execute, this is a dry run only.

Usage:
  python3 scripts/operator_execute_withdraw_demo.py --position-id 8afed8fcd27553a7 --private-key 0x...
  python3 scripts/operator_execute_withdraw_demo.py --position-id 8afed8fcd27553a7 --private-key 0x... --execute
"""

import argparse
import json
import subprocess
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


def load_contracts_config():
    path = os.path.join(PROJECT_ROOT, "configs", "sepolia_contracts.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def load_exchange_config():
    for name in ["live_alpha.local.json", "live_alpha.example.json"]:
        path = os.path.join(PROJECT_ROOT, "configs", name)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


def check_can_withdraw(escrow_address, deposit_id, rpc_url):
    """Query on-chain to check if deposit is withdrawable."""
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
            release_time = int(hex_data[194:258], 16)
            withdrawn = int(hex_data[258:322], 16)
            now = time.time()
            return (now >= release_time) and not withdrawn, release_time, bool(withdrawn)
    except Exception:
        pass
    return None, None, None


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Execute Withdraw Demo")
    parser.add_argument("--position-id", required=True, help="Position ID")
    parser.add_argument("--private-key", required=True, help="Depositor private key (0x...)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually execute the withdraw (default: dry run only)")
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

    print(f"\n{O}{B}  WITHDRAW {'EXECUTION' if args.execute else 'DRY RUN'} — {pos.position_id}{X}")
    print(f"  {D}{'─' * 55}{X}\n")

    # Pre-flight checks
    checks_passed = True

    # Check 1: Position matured
    is_matured = pos.is_matured() or pos.status.value == "MATURED"
    if is_matured:
        print(f"  {G}[PASS]{X} Position is matured")
    else:
        print(f"  {R}[FAIL]{X} Position is NOT matured (status={pos.status.value}, remaining={pos.time_remaining():.0f}s)")
        checks_passed = False

    # Check 2: Not already redeemed
    if pos.status.value == "REDEEMED":
        print(f"  {R}[FAIL]{X} Position is already redeemed")
        checks_passed = False
    else:
        print(f"  {G}[PASS]{X} Position not yet redeemed")

    # Check 3: Not slashed
    if pos.status.value == "SLASHED":
        print(f"  {R}[FAIL]{X} Position has been slashed")
        checks_passed = False
    else:
        print(f"  {G}[PASS]{X} Position not slashed")

    # Check 4: Has escrow deposit
    if pos.eth_escrow_deposit_id is not None:
        print(f"  {G}[PASS]{X} ETH escrow deposit ID: #{pos.eth_escrow_deposit_id}")
    else:
        print(f"  {R}[FAIL]{X} No ETH escrow deposit ID")
        checks_passed = False

    # Check 5: On-chain canWithdraw
    if pos.eth_escrow_deposit_id is not None and escrow_address:
        can_withdraw, release_time, already_withdrawn = check_can_withdraw(
            escrow_address, pos.eth_escrow_deposit_id, rpc_url
        )
        if can_withdraw is True:
            print(f"  {G}[PASS]{X} On-chain: escrow is withdrawable")
        elif can_withdraw is False:
            reason = "already withdrawn" if already_withdrawn else "release time not reached"
            print(f"  {R}[FAIL]{X} On-chain: escrow NOT withdrawable ({reason})")
            checks_passed = False
        else:
            print(f"  {Y}[SKIP]{X} On-chain check failed (network issue?)")

    # Build cast command
    deposit_id = pos.eth_escrow_deposit_id if pos.eth_escrow_deposit_id is not None else 0
    cast_cmd = [
        "cast", "send", escrow_address,
        "withdraw(uint256)", str(deposit_id),
        "--rpc-url", rpc_url,
        "--private-key", args.private_key,
    ]

    cast_display = (
        f"cast send {escrow_address} "
        f'"withdraw(uint256)" {deposit_id} '
        f"--rpc-url {rpc_url} "
        f"--private-key {args.private_key[:6]}...{args.private_key[-4:]}"
    )

    print(f"\n  {W}{B}Cast Command{X}")
    print(f"  {C}{cast_display}{X}\n")

    if not checks_passed:
        print(f"  {R}{B}PRE-FLIGHT CHECKS FAILED — aborting.{X}\n")
        sys.exit(1)

    if not args.execute:
        print(f"  {Y}{B}DRY RUN — not executing.{X}")
        print(f"  {D}Add --execute to actually send the transaction.{X}\n")
        return

    # Execute
    print(f"  {O}{B}EXECUTING withdraw on Sepolia...{X}\n")

    try:
        result = subprocess.run(
            cast_cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print(f"  {G}{B}SUCCESS{X}")
            print(f"  {D}{result.stdout.strip()}{X}\n")

            # Update position status
            registry.redeem(pos.position_id)
            registry.save(args.file)
            print(f"  {G}Position status updated to REDEEMED{X}")
            print(f"  {D}Registry saved to {args.file}{X}\n")
        else:
            print(f"  {R}{B}FAILED{X}")
            print(f"  {R}{result.stderr.strip()}{X}\n")
            sys.exit(1)
    except FileNotFoundError:
        print(f"  {R}ERROR: 'cast' command not found. Install foundry: https://getfoundry.sh{X}\n")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"  {R}ERROR: Transaction timed out after 120 seconds.{X}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
