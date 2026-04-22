#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Register Model B Position

Creates a SOST-side position backed by an on-chain Sepolia/mainnet deposit.
This is the bridge from an Ethereum escrow deposit to a SOST position.

Usage:
  python3 scripts/operator_register_model_b.py \
    --owner SOST1abc... \
    --token XAUT \
    --amount 100000000000000000 \
    --duration-days 28 \
    --deposit-id 1 \
    --eth-tx 0xabc...

The reward is calculated automatically based on ESCROW_REWARD_RATES.
"""

import argparse
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.operator.audit_log import AuditLog

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

# Reward rates: annualized, keyed by max duration in days.
# For a 28-day lock the rate is 0.4% of gold value (annualized ~5.2%).
ESCROW_REWARD_RATES = {
    30:  0.004,   # 0.4% for up to 1 month
    90:  0.015,   # 1.5% for up to 3 months
    180: 0.035,   # 3.5% for up to 6 months
    365: 0.080,   # 8.0% for up to 12 months
}


def reward_rate_for_days(days: int) -> float:
    """Return the reward rate for a given lock duration."""
    for max_days in sorted(ESCROW_REWARD_RATES.keys()):
        if days <= max_days:
            return ESCROW_REWARD_RATES[max_days]
    # Longer than any defined tier — use highest tier
    return ESCROW_REWARD_RATES[max(ESCROW_REWARD_RATES.keys())]


def fmt_sost(sats):
    return f"{sats / 1e8:.8f}"


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Register Model B Position")
    parser.add_argument("--owner", required=True, help="SOST address of the position owner")
    parser.add_argument("--token", required=True, choices=["XAUT", "PAXG"],
                        help="Gold token symbol")
    parser.add_argument("--amount", required=True, type=int,
                        help="Gold amount in token base units (wei for ERC-20)")
    parser.add_argument("--duration-days", required=True, type=int,
                        help="Lock duration in days")
    parser.add_argument("--deposit-id", required=True, type=int,
                        help="On-chain escrow depositId")
    parser.add_argument("--eth-tx", required=True,
                        help="Ethereum transaction hash of the deposit")
    parser.add_argument("--bond-sost", type=int, default=0,
                        help="SOST bond amount in satoshis (default: 0 for pilot)")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json (default: data/positions.json)")
    parser.add_argument("--audit-dir", default=os.path.join(PROJECT_ROOT, "data", "audit"),
                        help="Path to audit log directory")
    args = parser.parse_args()

    # Calculate reward
    rate = reward_rate_for_days(args.duration_days)
    reward_total = int(args.amount * rate)
    duration_seconds = args.duration_days * 86400

    # Load or create registry
    registry = PositionRegistry()
    if os.path.exists(args.file):
        try:
            registry.load(args.file)
        except Exception as e:
            print(f"{R}ERROR:{X} Failed to load position registry: {e}")
            sys.exit(1)

    # Create position
    pos = registry.create_model_b(
        owner=args.owner,
        token=args.token,
        amount=args.amount,
        bond_sost=args.bond_sost,
        duration_seconds=duration_seconds,
        reward_total=reward_total,
        eth_deposit_id=args.deposit_id,
        eth_tx=args.eth_tx,
    )

    # Ensure data directory exists
    os.makedirs(os.path.dirname(args.file), exist_ok=True)

    # Save registry
    registry.save(args.file)

    # Audit log
    audit = AuditLog(args.audit_dir)
    audit.log_event(
        deal_id=f"op_register:{pos.position_id}",
        event="model_b_registered",
        detail=(f"owner={args.owner} token={args.token} amount={args.amount} "
                f"days={args.duration_days} deposit_id={args.deposit_id} "
                f"eth_tx={args.eth_tx} reward={reward_total}"),
    )

    print(f"\n{O}{B}  SOST GOLD EXCHANGE — MODEL B POSITION REGISTERED{X}")
    print(f"  {D}Position ID:   {C}{B}{pos.position_id}{X}")
    print(f"  {D}Owner:         {W}{pos.owner}{X}")
    print(f"  {D}Token:         {W}{pos.token_symbol}{X}")
    print(f"  {D}Amount:        {W}{pos.reference_amount}{X}")
    print(f"  {D}Duration:      {W}{args.duration_days} days{X}")
    print(f"  {D}Reward Rate:   {Y}{rate * 100:.1f}%{X}")
    print(f"  {D}Reward Total:  {G}{fmt_sost(reward_total)} SOST{X}")
    print(f"  {D}Bond:          {W}{fmt_sost(args.bond_sost)} SOST{X}")
    print(f"  {D}ETH Deposit:   {C}#{args.deposit_id}{X}")
    print(f"  {D}ETH TX:        {C}{args.eth_tx}{X}")
    print(f"  {D}Status:        {G}{B}{pos.status.value}{X}")
    print(f"  {D}Registry saved to {args.file}{X}")
    print()


if __name__ == "__main__":
    main()
