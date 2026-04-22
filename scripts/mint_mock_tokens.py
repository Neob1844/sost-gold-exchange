#!/usr/bin/env python3
"""
Mint mock XAUT/PAXG tokens on Sepolia and approve the escrow contract.

Reads contract addresses from configs/sepolia_contracts.json, then uses
`cast send` (Foundry) to mint tokens and set approvals.

Usage:
    # Mint to a specific address:
    python scripts/mint_mock_tokens.py --to 0xYourAddress

    # Mint to deployer (reads from configs):
    python scripts/mint_mock_tokens.py

    # Custom amounts:
    python scripts/mint_mock_tokens.py --xaut-oz 5 --paxg-oz 5

Environment variables required:
    SEPOLIA_RPC_URL       — Sepolia RPC endpoint
    DEPLOYER_PRIVATE_KEY  — Private key for the minting transaction
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = PROJECT_ROOT / "configs"
SEPOLIA_CONTRACTS_JSON = CONFIGS_DIR / "sepolia_contracts.json"
ENV_FILE = PROJECT_ROOT / "contracts" / "ethereum" / ".env"

# Default mint amounts
DEFAULT_XAUT_OZ = 10   # 10 oz XAUT
DEFAULT_PAXG_OZ = 10   # 10 oz PAXG


def load_contracts() -> dict:
    """Load deployed contract addresses."""
    if not SEPOLIA_CONTRACTS_JSON.exists():
        print(f"ERROR: {SEPOLIA_CONTRACTS_JSON} not found.")
        print("Run sepolia_deploy_capture.py first.")
        sys.exit(1)

    with open(SEPOLIA_CONTRACTS_JSON) as f:
        contracts = json.load(f)

    zero = "0x0000000000000000000000000000000000000000"
    for key in ("mock_xaut", "mock_paxg", "escrow"):
        if contracts.get(key, zero) == zero:
            print(f"ERROR: {key} is still a zero address. Deploy contracts first.")
            sys.exit(1)

    return contracts


def load_env() -> dict:
    """Load environment from .env file if not already set."""
    env = os.environ.copy()

    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key not in env:
                        env[key] = value

    required = ["SEPOLIA_RPC_URL", "DEPLOYER_PRIVATE_KEY"]
    for key in required:
        if key not in env:
            print(f"ERROR: {key} not set. Set it in environment or in {ENV_FILE}")
            sys.exit(1)

    return env


def cast_send(to: str, sig: str, args: list, env: dict, label: str):
    """Execute a cast send transaction."""
    cmd = [
        "cast", "send",
        "--rpc-url", env["SEPOLIA_RPC_URL"],
        "--private-key", env["DEPLOYER_PRIVATE_KEY"],
        to, sig,
    ] + args

    print(f"  {label}...")
    print(f"    cast send {to} '{sig}' {' '.join(args)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}")
        sys.exit(1)

    # Extract tx hash from output
    for line in result.stdout.splitlines():
        if "transactionHash" in line:
            print(f"    tx: {line.strip()}")
            break
    print(f"    OK")


def main():
    parser = argparse.ArgumentParser(description="Mint mock tokens on Sepolia")
    parser.add_argument("--to", type=str, default=None,
                        help="Recipient address (default: deployer from config)")
    parser.add_argument("--xaut-oz", type=float, default=DEFAULT_XAUT_OZ,
                        help=f"Amount of XAUT to mint in troy ounces (default: {DEFAULT_XAUT_OZ})")
    parser.add_argument("--paxg-oz", type=float, default=DEFAULT_PAXG_OZ,
                        help=f"Amount of PAXG to mint in troy ounces (default: {DEFAULT_PAXG_OZ})")
    args = parser.parse_args()

    contracts = load_contracts()
    env = load_env()

    recipient = args.to or contracts.get("deployer", "")
    if not recipient:
        print("ERROR: No recipient address. Use --to or deploy contracts first.")
        sys.exit(1)

    xaut_addr = contracts["mock_xaut"]
    paxg_addr = contracts["mock_paxg"]
    escrow_addr = contracts["escrow"]

    # XAUT: 6 decimals -> 1 oz = 1_000_000
    xaut_amount = int(args.xaut_oz * 10**6)
    # PAXG: 18 decimals -> 1 oz = 10^18
    paxg_amount = int(args.paxg_oz * 10**18)

    # Use uint256 max for approval (unlimited)
    max_uint256 = str(2**256 - 1)

    print()
    print("=" * 60)
    print("  Minting Mock Tokens on Sepolia")
    print("=" * 60)
    print(f"  Recipient:  {recipient}")
    print(f"  XAUT:       {args.xaut_oz} oz ({xaut_amount} raw units)")
    print(f"  PAXG:       {args.paxg_oz} oz ({paxg_amount} raw units)")
    print(f"  Escrow:     {escrow_addr}")
    print("=" * 60)
    print()

    # 1. Mint XAUT
    cast_send(xaut_addr, "mint(address,uint256)", [recipient, str(xaut_amount)],
              env, f"Mint {args.xaut_oz} XAUT to {recipient}")

    # 2. Mint PAXG
    cast_send(paxg_addr, "mint(address,uint256)", [recipient, str(paxg_amount)],
              env, f"Mint {args.paxg_oz} PAXG to {recipient}")

    # 3. Approve escrow for XAUT
    cast_send(xaut_addr, "approve(address,uint256)", [escrow_addr, max_uint256],
              env, f"Approve escrow for XAUT")

    # 4. Approve escrow for PAXG
    cast_send(paxg_addr, "approve(address,uint256)", [escrow_addr, max_uint256],
              env, f"Approve escrow for PAXG")

    print()
    print("Done. Tokens minted and escrow approved.")
    print()


if __name__ == "__main__":
    main()
