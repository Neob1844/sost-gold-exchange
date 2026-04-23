#!/usr/bin/env python3
"""
SOST Gold Exchange — Reconcile Reward Status

Checks matured/withdrawn positions for unsettled rewards.
Reports positions that should have rewards settled but don't.

Usage:
  python3 scripts/reconcile_reward_status.py
  python3 scripts/reconcile_reward_status.py --file data/positions.json
"""

import argparse
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


def fmt_sost(sats):
    return f"{sats / 1e8:.8f} SOST"


def main():
    parser = argparse.ArgumentParser(description="SOST — Reconcile Reward Status")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json")
    args = parser.parse_args()

    print(f"\n{O}{B}  REWARD STATUS RECONCILIATION{X}")
    print(f"  {D}{'─' * 50}{X}\n")

    if not os.path.exists(args.file):
        print(f"{R}ERROR:{X} Position registry not found at {args.file}")
        sys.exit(1)

    registry = PositionRegistry()
    try:
        registry.load(args.file)
    except Exception as e:
        print(f"{R}ERROR:{X} Failed to load registry: {e}")
        sys.exit(1)

    now = time.time()
    settled = 0
    unsettled = 0
    active = 0
    total_unsettled_sost = 0

    for pid, pos in registry._positions.items():
        is_past_expiry = now >= pos.expiry_time
        lifecycle = pos.lifecycle_status

        if not is_past_expiry and lifecycle == LifecycleStatus.ACTIVE.value:
            active += 1
            continue

        reward_owner = pos.reward_owner or pos.principal_owner or pos.owner
        remaining = pos.reward_remaining()

        if pos.reward_settled:
            print(f"  {G}[SETTLED]{X}   {C}{pid[:12]}{X} reward_owner={D}{reward_owner[:20]}{X} total={D}{fmt_sost(pos.reward_total_sost)}{X}")
            settled += 1
        else:
            days_past = (now - pos.expiry_time) / 86400 if is_past_expiry else 0
            print(
                f"  {R}[UNSETTLED]{X} {C}{pid[:12]}{X} "
                f"lifecycle={Y}{lifecycle}{X} "
                f"remaining={Y}{fmt_sost(remaining)}{X} "
                f"reward_owner={D}{reward_owner[:20]}{X}"
                + (f" ({days_past:.0f}d past expiry)" if days_past > 0 else "")
            )
            unsettled += 1
            total_unsettled_sost += remaining

    print(f"\n  {D}{'─' * 50}{X}")
    print(f"  {D}Active (not yet matured):{X} {active}")
    print(f"  {G}Settled:{X}                  {settled}")
    print(f"  {R}Unsettled:{X}                {unsettled}")
    if total_unsettled_sost > 0:
        print(f"  {Y}Total unsettled:{X}          {fmt_sost(total_unsettled_sost)}")

    print()


if __name__ == "__main__":
    main()
