#!/usr/bin/env python3
"""
SOST Gold Exchange — Check Sepolia Deposits

Queries the deployed SOSTEscrow contract on Sepolia for locked balances
and deposit details.

Usage:
    python3 scripts/check_sepolia_deposit.py
    python3 scripts/check_sepolia_deposit.py --config configs/live_alpha.local.json
"""

import json
import os
import sys
import argparse
import urllib.request

_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_this_dir)

# Default addresses from deployed contracts
DEFAULT_CONFIG = os.path.join(_project_root, "configs", "live_alpha.local.json")

# ── ABI selectors (keccak256 of function signature, first 4 bytes) ──
# totalLocked(address) -> uint256
SEL_TOTAL_LOCKED = "0xd8fb9337"
# getDeposit(uint256) -> (address depositor, address token, uint256 amount, uint256 unlockTime, bool withdrawn)
SEL_GET_DEPOSIT = "0x9f9fb968"


def eth_call(rpc_url: str, to: str, data: str) -> str:
    """Execute eth_call and return hex result."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
    }).encode()
    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "SOST-Exchange/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    if "error" in result:
        return f"ERROR: {result['error'].get('message', result['error'])}"
    return result.get("result", "0x")


def pad_address(addr: str) -> str:
    """Left-pad an address to 32 bytes for ABI encoding."""
    return addr.lower().replace("0x", "").zfill(64)


def pad_uint(n: int) -> str:
    """Left-pad an integer to 32 bytes for ABI encoding."""
    return hex(n)[2:].zfill(64)


def decode_uint(hex_str: str, offset: int = 0) -> int:
    """Decode a uint256 from hex data at the given 32-byte slot offset."""
    start = 2 + offset * 64  # skip 0x prefix
    end = start + 64
    chunk = hex_str[start:end]
    if not chunk:
        return 0
    return int(chunk, 16)


def decode_address(hex_str: str, offset: int = 0) -> str:
    """Decode an address from hex data at the given 32-byte slot offset."""
    start = 2 + offset * 64
    end = start + 64
    chunk = hex_str[start:end]
    if not chunk:
        return "0x" + "0" * 40
    return "0x" + chunk[-40:]


def decode_bool(hex_str: str, offset: int = 0) -> bool:
    return decode_uint(hex_str, offset) != 0


def main():
    parser = argparse.ArgumentParser(description="Check Sepolia deposit status")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Config JSON path")
    parser.add_argument("--deposit-id", type=int, default=0, help="Deposit ID to query")
    args = parser.parse_args()

    # Load config
    config_path = args.config
    if not os.path.exists(config_path):
        config_path = os.path.join(_project_root, "configs", "live_alpha.example.json")
    with open(config_path) as f:
        config = json.load(f)

    eth = config["ethereum"]
    rpc = eth["rpc_url"]
    escrow = eth["escrow_address"]
    xaut = eth.get("xaut_address", "")
    paxg = eth.get("paxg_address", "")

    print("SOST Gold Exchange — Sepolia Deposit Checker")
    print(f"  RPC:    {rpc}")
    print(f"  Escrow: {escrow}")
    print(f"  XAUT:   {xaut}")
    print(f"  PAXG:   {paxg}")
    print()

    # Query totalLocked for XAUT
    if xaut:
        data = SEL_TOTAL_LOCKED + pad_address(xaut)
        result = eth_call(rpc, escrow, data)
        if result.startswith("ERROR"):
            print(f"  totalLocked(XAUT): {result}")
        else:
            amount = decode_uint(result)
            print(f"  totalLocked(XAUT): {amount} units ({amount / 1e6:.6f} oz)")

    # Query totalLocked for PAXG
    if paxg:
        data = SEL_TOTAL_LOCKED + pad_address(paxg)
        result = eth_call(rpc, escrow, data)
        if result.startswith("ERROR"):
            print(f"  totalLocked(PAXG): {result}")
        else:
            amount = decode_uint(result)
            print(f"  totalLocked(PAXG): {amount} wei ({amount / 1e18:.6f} oz)")

    print()

    # Query getDeposit(deposit_id)
    deposit_id = args.deposit_id
    data = SEL_GET_DEPOSIT + pad_uint(deposit_id)
    result = eth_call(rpc, escrow, data)

    print(f"  getDeposit({deposit_id}):")
    if result.startswith("ERROR"):
        print(f"    {result}")
    elif result == "0x" or len(result) < 66:
        print("    (no data returned — contract may not have this function or no deposits)")
    else:
        depositor = decode_address(result, 0)
        token = decode_address(result, 1)
        amount = decode_uint(result, 2)
        unlock_time = decode_uint(result, 3)
        withdrawn = decode_bool(result, 4)

        # Identify token name
        token_name = "UNKNOWN"
        if token.lower() == xaut.lower():
            token_name = "XAUT"
        elif token.lower() == paxg.lower():
            token_name = "PAXG"

        decimals = 1e6 if token_name == "XAUT" else 1e18
        print(f"    depositor:  {depositor}")
        print(f"    token:      {token} ({token_name})")
        print(f"    amount:     {amount} units ({amount / decimals:.6f} oz)")
        if unlock_time > 0:
            import datetime
            dt = datetime.datetime.utcfromtimestamp(unlock_time)
            print(f"    unlockTime: {unlock_time} ({dt.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        else:
            print(f"    unlockTime: {unlock_time}")
        print(f"    withdrawn:  {withdrawn}")


if __name__ == "__main__":
    main()
