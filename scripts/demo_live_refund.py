#!/usr/bin/env python3
"""
SOST Gold Exchange — Live Refund Demo

Demonstrates the refund lifecycle when SOST side fails to lock:
  deal -> ETH lock -> SOST timeout -> expiry -> refund

Usage:
  python3 scripts/demo_live_refund.py --mock           # 2-second expiry (default)
  python3 scripts/demo_live_refund.py --live            # configurable expiry, real RPC
  python3 scripts/demo_live_refund.py --live --expiry 300  # 5 min expiry
"""

import argparse
import hashlib
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.settlement_daemon import SettlementDaemon
from src.settlement.refund_engine import RefundEngine
from src.watchers.ethereum_watcher import EthereumWatcher, EthEvent
from src.watchers.sost_watcher import SostWatcher, SostEvent
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
CONFIG_LOCAL = os.path.join(PROJECT_ROOT, "configs", "live_alpha.local.json")
CONFIG_EXAMPLE = os.path.join(PROJECT_ROOT, "configs", "live_alpha.example.json")


def load_config():
    for path in (CONFIG_LOCAL, CONFIG_EXAMPLE):
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f), path
    print(f"{R}ERROR:{X} No config found. Copy configs/live_alpha.example.json to configs/live_alpha.local.json")
    sys.exit(1)


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*54}{X}")


def info(label, value):
    print(f"  {D}{label}:{X} {G}{value}{X}")


def warn(label, value):
    print(f"  {R}{label}:{X} {Y}{value}{X}")


def status_line(deal):
    eth = f"{G}YES{X}" if deal.eth_tx_hash else f"{R}NO{X}"
    sost = f"{G}YES{X}" if deal.sost_lock_txid else f"{R}NO{X}"
    state = deal.state.value
    if state in ("REFUND_PENDING", "REFUNDED"):
        sc = R
    elif state == "EXPIRED":
        sc = Y
    else:
        sc = O
    print(f"\n  {W}ETH locked:{X} {eth} {D}|{X} {W}SOST locked:{X} {sost} {D}|{X} {sc}{B}{state}{X}")


class MockWatcher:
    def __init__(self):
        self._events = []
        self.on_event = None
    def add_watch_address(self, addr): pass
    def run(self): pass
    def stop(self): pass


def run_mock(cfg):
    print(f"""
{R}{'='*64}{X}
{O}{B}  SOST GOLD EXCHANGE — REFUND DEMO{X}
{Y}  Scenario: ETH locked, SOST never arrives -> expiry -> refund{X}
{R}{'='*64}{X}
{D}mode: MOCK (2-second expiry, simulated events){X}
""")

    demo = cfg.get("demo", {})
    data_cfg = cfg.get("data", {})
    audit_dir = os.path.join(PROJECT_ROOT, data_cfg.get("audit_dir", "data/audit"))

    deal_store = DealStore()
    audit = AuditLog(log_dir=audit_dir)
    refund_engine = RefundEngine()

    daemon = SettlementDaemon(
        deal_store=deal_store,
        eth_watcher=MockWatcher(),
        sost_watcher=MockWatcher(),
        refund_engine=refund_engine,
        audit=audit,
    )

    # Step 1 — deal with short expiry
    step(1, "Create deal with SHORT expiry (2 seconds)")
    offer_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    accept_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    deal_id = hashlib.sha256(f"{offer_id}:{accept_id}".encode()).hexdigest()[:16]

    now = time.time()
    deal = Deal(
        deal_id=deal_id,
        pair=demo["pair"],
        side="sell",
        amount_sost=demo["amount_sost"],
        amount_gold=demo["amount_gold"],
        maker_sost_addr=demo["maker_sost_addr"],
        taker_sost_addr=demo["taker_sost_addr"],
        maker_eth_addr=demo["maker_eth_addr"],
        taker_eth_addr=demo["taker_eth_addr"],
        created_at=now,
        expires_at=now + 2,
    )
    deal_store._deals[deal_id] = deal
    deal.transition(DealState.NEGOTIATED, "offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")

    # Step 2 — register with daemon
    step(2, "Register deal with settlement daemon")
    daemon.register_deal(deal)
    daemon._deal_eth_map[99] = deal.deal_id
    info("deal_id", deal_id)
    info("expiry", "2 seconds from now")
    info("state", deal.state.value)
    time.sleep(0.3)

    # Step 3 — ETH lock only
    step(3, "Simulate ETH lock (one side only)")
    eth_event = EthEvent(
        event_type="deposit",
        tx_hash="0x" + hashlib.sha256(os.urandom(16)).hexdigest(),
        block_number=19500000,
        deposit_id=99,
        depositor=demo["taker_eth_addr"],
        token="0x68749665FF8D2d112Fa859AA293F07A622782F38",
        amount=demo["amount_gold"],
        unlock_time=int(now) + 86400 * 90,
        timestamp=time.time(),
    )
    daemon.on_eth_event(eth_event)
    info("eth_tx", eth_event.tx_hash[:32] + "...")
    info("state", deal.state.value)
    warn("sost_side", "NO deposit — waiting for timeout...")
    time.sleep(0.3)

    # Step 4 — wait for expiry
    step(4, "SOST side times out")
    print(f"  {D}Sleeping 2.5 seconds to exceed expiry...{X}")
    time.sleep(1.5)
    status_line(deal)

    # Step 5 — daemon tick detects expiry
    step(5, "Daemon tick detects expiry")
    daemon.tick()
    info("expired", str(deal.state in (DealState.EXPIRED, DealState.REFUND_PENDING, DealState.REFUNDED)))
    info("state", deal.state.value)
    status_line(deal)
    time.sleep(0.3)

    # Step 6 — refund execution
    step(6, "Refund path executes")
    pending = refund_engine.pending()
    if pending:
        for action in pending:
            info("refund_side", action.side)
            info("reason", action.reason)
            refund_engine.execute(action, deal)
            info("state_after", deal.state.value)
    else:
        info("state", deal.state.value)
        warn("note", "Deal expired before refund engine caught it")

    status_line(deal)
    time.sleep(0.3)

    # Step 7 — audit log
    step(7, "Audit log showing refund")
    for entry in audit.get_deal_history(deal.deal_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:24s}{X} {D}{entry.detail[:50]}{X}")

    # Save
    deals_path = os.path.join(PROJECT_ROOT, data_cfg.get("deals_path", "data/deals.json"))
    os.makedirs(os.path.dirname(deals_path), exist_ok=True)
    deal_store.save(deals_path)

    print(f"\n{R}{'='*64}{X}")
    print(f"{R}{B}  DEMO COMPLETE — REFUND PATH{X}")
    print(f"{R}{'='*64}{X}")
    print(f"\n{D}Deal {deal_id} ended in state: {deal.state.value}{X}")
    print(f"{D}ETH deposit would be returned to depositor after escrow unlock.{X}\n")


def run_live(cfg, expiry_seconds):
    print(f"""
{R}{'='*64}{X}
{O}{B}  SOST GOLD EXCHANGE — LIVE REFUND DEMO{X}
{Y}  Scenario: ETH locked, SOST never arrives -> expiry -> refund{X}
{R}{'='*64}{X}
{D}mode: LIVE (expiry: {expiry_seconds}s, real Sepolia + SOST RPC){X}
""")

    demo = cfg.get("demo", {})
    data_cfg = cfg.get("data", {})
    eth_cfg = cfg["ethereum"]
    sost_cfg = cfg["sost"]
    audit_dir = os.path.join(PROJECT_ROOT, data_cfg.get("audit_dir", "data/audit"))

    deal_store = DealStore()
    audit = AuditLog(log_dir=audit_dir)
    refund_engine = RefundEngine()

    eth_watcher = EthereumWatcher(
        rpc_url=eth_cfg["rpc_url"],
        escrow_address=eth_cfg["escrow_address"],
    )
    sost_watcher = SostWatcher(
        rpc_url=sost_cfg["rpc_url"],
        rpc_user=sost_cfg["rpc_user"],
        rpc_pass=sost_cfg["rpc_pass"],
    )

    step(1, "Verify connectivity")
    try:
        block = eth_watcher.get_block_number()
        info("eth_block", str(block))
    except Exception as e:
        warn("eth_error", str(e))
        sys.exit(1)

    daemon = SettlementDaemon(
        deal_store=deal_store,
        eth_watcher=eth_watcher,
        sost_watcher=sost_watcher,
        refund_engine=refund_engine,
        audit=audit,
    )

    step(2, f"Create deal with {expiry_seconds}s expiry")
    offer_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    accept_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    deal_id = hashlib.sha256(f"{offer_id}:{accept_id}".encode()).hexdigest()[:16]

    now = time.time()
    deal = Deal(
        deal_id=deal_id,
        pair=demo["pair"],
        side="sell",
        amount_sost=demo["amount_sost"],
        amount_gold=demo["amount_gold"],
        maker_sost_addr=demo["maker_sost_addr"],
        taker_sost_addr=demo["taker_sost_addr"],
        maker_eth_addr=demo["maker_eth_addr"],
        taker_eth_addr=demo["taker_eth_addr"],
        created_at=now,
        expires_at=now + expiry_seconds,
    )
    deal_store._deals[deal_id] = deal
    deal.transition(DealState.NEGOTIATED, "offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
    daemon.register_deal(deal)
    info("deal_id", deal_id)
    info("state", deal.state.value)

    step(3, "Waiting for ETH deposit (polling)...")
    print(f"  {Y}Send gold tokens to escrow: {eth_cfg['escrow_address']}{X}")
    print(f"  {D}Polling every {eth_cfg['poll_interval']}s. Ctrl+C to skip to timeout.{X}\n")

    deadline = now + expiry_seconds
    try:
        while time.time() < deadline and deal.state not in (
            DealState.BOTH_LOCKED, DealState.SETTLED,
            DealState.EXPIRED, DealState.REFUND_PENDING, DealState.REFUNDED,
        ):
            try:
                for ev in eth_watcher.poll_once():
                    daemon.on_eth_event(ev)
            except Exception:
                pass
            daemon.tick()

            remaining = int(deadline - time.time())
            print(f"  {D}[{remaining:>4d}s left] state={deal.state.value}{X}", end="\r")
            time.sleep(min(10, max(1, remaining)))
    except KeyboardInterrupt:
        print(f"\n  {Y}Skipping to timeout...{X}")

    step(4, "SOST side times out")
    # Force expiry if not already
    if not deal.is_terminal():
        deal.expires_at = time.time() - 1
        daemon.tick()

    status_line(deal)

    step(5, "Refund execution")
    pending = refund_engine.pending()
    if pending:
        for action in pending:
            info("refund_side", action.side)
            refund_engine.execute(action, deal)
            info("state", deal.state.value)
    else:
        info("state", deal.state.value)

    status_line(deal)

    step(6, "Audit log")
    for entry in audit.get_deal_history(deal.deal_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:24s}{X} {D}{entry.detail[:50]}{X}")

    deals_path = os.path.join(PROJECT_ROOT, data_cfg.get("deals_path", "data/deals.json"))
    os.makedirs(os.path.dirname(deals_path), exist_ok=True)
    deal_store.save(deals_path)

    print(f"\n{R}{'='*64}{X}")
    print(f"{R}{B}  LIVE REFUND DEMO COMPLETE — {deal.state.value}{X}")
    print(f"{R}{'='*64}{X}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SOST Gold Exchange — Live Refund Demo")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock", action="store_true", default=True,
                       help="Simulated mode with 2s expiry (default)")
    group.add_argument("--live", action="store_true",
                       help="Live mode with real RPC")
    parser.add_argument("--expiry", type=int, default=120,
                        help="Expiry seconds for live mode (default: 120)")
    args = parser.parse_args()

    cfg, cfg_path = load_config()
    info("config", cfg_path)

    if args.live:
        run_live(cfg, args.expiry)
    else:
        run_mock(cfg)
