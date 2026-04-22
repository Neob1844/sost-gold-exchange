#!/usr/bin/env python3
"""
Sepolia deployment capture script.

Either runs `forge script` to deploy contracts, or reads addresses from
an existing Forge broadcast JSON file. Saves deployed addresses to
configs/sepolia_contracts.json and updates src/integration/live_eth_config.py.

Usage:
    # Deploy and capture (runs forge script):
    python scripts/sepolia_deploy_capture.py --deploy

    # Capture from existing broadcast file:
    python scripts/sepolia_deploy_capture.py --broadcast-file <path>

    # Capture from latest broadcast (auto-detect):
    python scripts/sepolia_deploy_capture.py --latest
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Project root = parent of scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = PROJECT_ROOT / "contracts" / "ethereum"
CONFIGS_DIR = PROJECT_ROOT / "configs"
LIVE_ETH_CONFIG = PROJECT_ROOT / "src" / "integration" / "live_eth_config.py"
SEPOLIA_CONTRACTS_JSON = CONFIGS_DIR / "sepolia_contracts.json"
BROADCAST_DIR = CONTRACTS_DIR / "broadcast" / "DeploySepolia.s.sol" / "11155111"

SEPOLIA_CHAIN_ID = 11155111


def run_forge_deploy() -> Path:
    """Run forge script deployment and return path to broadcast JSON."""
    env_file = CONTRACTS_DIR / ".env"
    if not env_file.exists():
        print(f"ERROR: {env_file} not found. Copy .env.example and fill in your keys.")
        sys.exit(1)

    # Source .env and run forge script
    cmd = (
        f"cd {CONTRACTS_DIR} && "
        f"source .env && "
        f"forge script script/DeploySepolia.s.sol:DeploySepolia "
        f"--rpc-url $SEPOLIA_RPC_URL "
        f"--private-key $DEPLOYER_PRIVATE_KEY "
        f"--broadcast "
        f"-vvvv"
    )
    print("Running forge script deployment...")
    print(f"  {cmd}\n")

    result = subprocess.run(cmd, shell=True, executable="/bin/bash",
                            capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        print("ERROR: forge script failed.")
        sys.exit(1)

    # Find the broadcast JSON
    run_latest = BROADCAST_DIR / "run-latest.json"
    if not run_latest.exists():
        print(f"ERROR: Expected broadcast file not found at {run_latest}")
        sys.exit(1)

    print(f"Broadcast file: {run_latest}")
    return run_latest


def find_latest_broadcast() -> Path:
    """Find the latest broadcast JSON automatically."""
    run_latest = BROADCAST_DIR / "run-latest.json"
    if run_latest.exists():
        return run_latest

    # Fallback: look for any JSON in broadcast dir
    if BROADCAST_DIR.exists():
        jsons = sorted(BROADCAST_DIR.glob("run-*.json"), reverse=True)
        if jsons:
            return jsons[0]

    print(f"ERROR: No broadcast files found in {BROADCAST_DIR}")
    sys.exit(1)


def parse_broadcast(broadcast_path: Path) -> dict:
    """Parse Forge broadcast JSON to extract deployed addresses."""
    with open(broadcast_path) as f:
        data = json.load(f)

    transactions = data.get("transactions", [])
    if not transactions:
        print("ERROR: No transactions found in broadcast file.")
        sys.exit(1)

    # Forge broadcasts contract creations in order.
    # Our deploy script creates: MockERC20 (XAUT), MockERC20 (PAXG), SOSTEscrow
    creates = [tx for tx in transactions if tx.get("transactionType") == "CREATE"]

    if len(creates) < 3:
        print(f"ERROR: Expected 3 CREATE transactions, found {len(creates)}")
        print("Transactions found:")
        for tx in creates:
            print(f"  {tx.get('contractName', '?')} -> {tx.get('contractAddress', '?')}")
        sys.exit(1)

    # Extract addresses by contract name or by order
    addresses = {}
    for tx in creates:
        name = tx.get("contractName", "")
        addr = tx.get("contractAddress", "")
        if name == "MockERC20" and "mock_xaut" not in addresses:
            addresses["mock_xaut"] = addr
        elif name == "MockERC20":
            addresses["mock_paxg"] = addr
        elif name == "SOSTEscrow":
            addresses["escrow"] = addr

    # Fallback: if contract names aren't present, use order
    if len(addresses) < 3:
        addresses = {
            "mock_xaut": creates[0].get("contractAddress", ""),
            "mock_paxg": creates[1].get("contractAddress", ""),
            "escrow": creates[2].get("contractAddress", ""),
        }

    # Get deployer from first transaction
    deployer = creates[0].get("transaction", {}).get("from", "")

    # Get block number from receipts if available
    receipts = data.get("receipts", [])
    block_number = 0
    if receipts:
        bn = receipts[0].get("blockNumber")
        if bn:
            block_number = int(bn, 16) if isinstance(bn, str) and bn.startswith("0x") else int(bn)

    return {
        "chain": "sepolia",
        "chain_id": SEPOLIA_CHAIN_ID,
        "deployed_at_block": block_number,
        "deployed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mock_xaut": addresses["mock_xaut"],
        "mock_paxg": addresses["mock_paxg"],
        "escrow": addresses["escrow"],
        "deployer": deployer,
    }


def save_contracts_json(contracts: dict):
    """Save deployed addresses to configs/sepolia_contracts.json."""
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEPOLIA_CONTRACTS_JSON, "w") as f:
        json.dump(contracts, f, indent=2)
        f.write("\n")
    print(f"Saved: {SEPOLIA_CONTRACTS_JSON}")


def update_live_eth_config(contracts: dict):
    """Update src/integration/live_eth_config.py with actual addresses."""
    if not LIVE_ETH_CONFIG.exists():
        print(f"WARNING: {LIVE_ETH_CONFIG} not found, skipping update.")
        return

    content = LIVE_ETH_CONFIG.read_text()

    # Replace the placeholder addresses
    replacements = [
        (r'(MOCK_XAUT_ADDRESS\s*=\s*")[^"]*(")', f'\\g<1>{contracts["mock_xaut"]}\\2'),
        (r'(MOCK_PAXG_ADDRESS\s*=\s*")[^"]*(")', f'\\g<1>{contracts["mock_paxg"]}\\2'),
        (r'(ESCROW_ADDRESS\s*=\s*")[^"]*(")', f'\\g<1>{contracts["escrow"]}\\2'),
    ]

    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)

    LIVE_ETH_CONFIG.write_text(content)
    print(f"Updated: {LIVE_ETH_CONFIG}")


def print_summary(contracts: dict):
    """Print deployment summary."""
    print()
    print("=" * 60)
    print("  SOST Sepolia Deployment Summary")
    print("=" * 60)
    print(f"  Chain:        sepolia (chain_id={contracts['chain_id']})")
    print(f"  Block:        {contracts['deployed_at_block']}")
    print(f"  Deployed at:  {contracts['deployed_at']}")
    print(f"  Deployer:     {contracts['deployer']}")
    print()
    print(f"  Mock XAUT:    {contracts['mock_xaut']}")
    print(f"  Mock PAXG:    {contracts['mock_paxg']}")
    print(f"  SOSTEscrow:   {contracts['escrow']}")
    print("=" * 60)
    print()


def main():
    parser = argparse.ArgumentParser(description="Capture Sepolia deployment addresses")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--deploy", action="store_true",
                       help="Run forge script deployment")
    group.add_argument("--broadcast-file", type=Path,
                       help="Path to existing Forge broadcast JSON")
    group.add_argument("--latest", action="store_true",
                       help="Read from latest broadcast file")
    args = parser.parse_args()

    if args.deploy:
        broadcast_path = run_forge_deploy()
    elif args.broadcast_file:
        broadcast_path = args.broadcast_file
        if not broadcast_path.exists():
            print(f"ERROR: File not found: {broadcast_path}")
            sys.exit(1)
    else:  # --latest
        broadcast_path = find_latest_broadcast()

    print(f"Reading broadcast: {broadcast_path}")
    contracts = parse_broadcast(broadcast_path)

    save_contracts_json(contracts)
    update_live_eth_config(contracts)
    print_summary(contracts)


if __name__ == "__main__":
    main()
