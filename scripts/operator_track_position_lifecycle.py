#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator: Track Position Lifecycle

Displays full lifecycle detail for a single position including status,
timing, reward info, ETH deposit details, and audit history.

Usage:
  python3 scripts/operator_track_position_lifecycle.py --position-id 8afed8fcd27553a7
"""

import argparse
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.operator.audit_log import AuditLog

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

STAGE_COLORS = {
    "ACTIVE": G,
    "NEARING_EXPIRY": Y,
    "MATURE": M,
    "REDEEMED": C,
    "SLASHED": R,
}


def fmt_time(ts):
    if not ts:
        return "---"
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))


def fmt_duration(seconds):
    if seconds <= 0:
        return "expired"
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


def fmt_sost(sats):
    return f"{sats / 1e8:.8f} SOST"


def lifecycle_stage(pos):
    """Determine lifecycle stage from position state."""
    status = pos.status.value
    if status == "REDEEMED":
        return "REDEEMED"
    if status == "SLASHED":
        return "SLASHED"
    if status == "MATURED":
        return "MATURE"
    if pos.is_matured():
        return "MATURE"
    remaining = pos.time_remaining()
    if remaining > 0 and remaining < 7 * 86400:
        return "NEARING_EXPIRY"
    return "ACTIVE"


def info(label, value, color=W):
    print(f"  {D}{label:24s}{X} {color}{value}{X}")


def main():
    parser = argparse.ArgumentParser(description="SOST Operator — Track Position Lifecycle")
    parser.add_argument("--position-id", required=True, help="Position ID to track")
    parser.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "positions.json"),
                        help="Path to positions.json")
    parser.add_argument("--audit-dir", default=os.path.join(PROJECT_ROOT, "data", "audit"),
                        help="Path to audit directory")
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
        # Try prefix match
        matches = [p for pid, p in registry._positions.items()
                    if pid.startswith(args.position_id)]
        if len(matches) == 1:
            pos = matches[0]
        elif len(matches) > 1:
            print(f"{Y}Multiple positions match prefix '{args.position_id}':{X}")
            for p in matches:
                print(f"  {C}{p.position_id}{X} {D}({p.status.value}){X}")
            sys.exit(1)
        else:
            print(f"{R}ERROR:{X} Position '{args.position_id}' not found.")
            sys.exit(1)

    stage = lifecycle_stage(pos)
    sc = STAGE_COLORS.get(stage, D)

    print(f"\n{O}{B}  POSITION LIFECYCLE — {pos.position_id}{X}")
    print(f"  {D}{'─' * 60}{X}")

    # Lifecycle stage banner
    print(f"\n  {B}Lifecycle Stage:{X}  {sc}{B}  {stage}  {X}")
    print()

    # Core info
    print(f"  {W}{B}Position Details{X}")
    info("Position ID", pos.position_id, C)
    info("Owner", pos.owner, W)
    model = pos.contract_type.value.replace("MODEL_", "Model ").replace("_ESCROW", " (escrow)").replace("_CUSTODY", " (custody)")
    info("Model", model, W)
    info("Token", pos.token_symbol, W)
    amount_display = f"{pos.reference_amount:,}"
    if pos.reference_amount >= 1e12:
        amount_display += f" ({pos.reference_amount / 1e18:.8f})"
    info("Reference Amount", amount_display, W)
    info("Status", pos.status.value, sc)

    # Timing
    print(f"\n  {W}{B}Timing{X}")
    info("Start Time", fmt_time(pos.start_time), W)
    info("Expiry Time", fmt_time(pos.expiry_time), W)
    duration_days = (pos.expiry_time - pos.start_time) / 86400
    info("Duration", f"{duration_days:.0f} days", W)
    remaining = pos.time_remaining()
    if remaining > 0:
        info("Time Remaining", fmt_duration(remaining), G if remaining > 7 * 86400 else Y)
    else:
        info("Time Remaining", f"{R}matured{X}", R)
    pct = pos.pct_complete()
    bar_width = 30
    filled = int(pct / 100 * bar_width)
    bar_color = G if pct < 75 else (Y if pct < 100 else M)
    bar = f"{bar_color}{'█' * filled}{D}{'░' * (bar_width - filled)}{X}"
    info("Progress", f"{bar} {pct:.1f}%")

    # Rewards
    print(f"\n  {W}{B}Rewards{X}")
    info("Total Reward", fmt_sost(pos.reward_total_sost), W)
    info("Claimed", fmt_sost(pos.reward_claimed_sost), G if pos.reward_claimed_sost > 0 else D)
    info("Remaining", fmt_sost(pos.reward_remaining()), Y)
    info("Schedule", pos.reward_schedule, D)

    # ETH deposit details
    if pos.eth_escrow_deposit_id is not None or pos.eth_escrow_tx:
        print(f"\n  {W}{B}ETH Escrow{X}")
        if pos.eth_escrow_deposit_id is not None:
            info("Deposit ID", f"#{pos.eth_escrow_deposit_id}", C)
        if pos.eth_escrow_tx:
            info("TX Hash", pos.eth_escrow_tx, C)

    # Backing proof
    if pos.backing_proof_hash:
        print(f"\n  {W}{B}Backing Proof{X}")
        info("Proof Hash", pos.backing_proof_hash, C)

    # Position history
    if pos.history:
        print(f"\n  {W}{B}Position History{X}")
        for h in pos.history:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(h["timestamp"]))
            print(f"  {D}[{ts}]{X} {O}{h['event']:20s}{X} {D}{h.get('detail', '')}{X}")

    # Audit log entries
    audit = AuditLog(log_dir=args.audit_dir)
    audit.load()
    entries = audit.get_deal_history(pos.position_id)
    if entries:
        print(f"\n  {W}{B}Audit Log{X}")
        for entry in entries:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(entry.timestamp))
            print(f"  {D}[{ts}]{X} {C}{entry.event:24s}{X} {D}{entry.detail[:60]}{X}")
    else:
        print(f"\n  {D}  No audit log entries for this position.{X}")

    print()


if __name__ == "__main__":
    main()
