#!/usr/bin/env python3
"""
SOST Settlement Demo — Refund Path

Demonstrates the refund lifecycle when one side fails to lock:
  offer → accept → deal → ETH lock → timeout → refund

Usage:
  python3 scripts/demo_refund_flow.py
"""

import hashlib
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.settlement_daemon import SettlementDaemon
from src.settlement.refund_engine import RefundEngine
from src.watchers.ethereum_watcher import EthEvent
from src.watchers.sost_watcher import SostEvent
from src.operator.audit_log import AuditLog

# ANSI colors
R = "\033[91m"; G = "\033[92m"; C = "\033[96m"; Y = "\033[93m"
O = "\033[38;5;208m"; W = "\033[97m"; D = "\033[90m"; B = "\033[1m"; X = "\033[0m"


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*50}{X}")


def info(label, value):
    print(f"  {D}{label}:{X} {G}{value}{X}")


def warn(label, value):
    print(f"  {R}{label}:{X} {Y}{value}{X}")


def main():
    print(f"\n{R}{'='*60}{X}")
    print(f"{O}{B}  SOST SETTLEMENT DEMO — REFUND PATH{X}")
    print(f"{R}{'='*60}{X}")
    print(f"\n{D}Scenario: ETH locked, SOST lock never arrives → expiry → refund{X}\n")

    deal_store = DealStore()
    audit = AuditLog(log_dir="/tmp/sost_demo_refund")
    refund_engine = RefundEngine()

    class MockWatcher:
        def __init__(self):
            self.on_event = None
        def add_watch_address(self, addr): pass
        def run(self): pass
        def stop(self): pass

    daemon = SettlementDaemon(
        deal_store=deal_store,
        eth_watcher=MockWatcher(),
        sost_watcher=MockWatcher(),
        refund_engine=refund_engine,
        audit=audit,
    )

    # ── Step 1: Create and register deal with SHORT expiry ──
    step(1, "Creating deal with 2-second expiry")
    offer_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    accept_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    deal_id = hashlib.sha256(f"{offer_id}:{accept_id}".encode()).hexdigest()[:16]

    now = time.time()
    deal = deal_store.create(
        deal_id=deal_id,
        pair="SOST/XAUT",
        side="sell",
        amount_sost=5000000000,
        amount_gold=25000000000000000,
        maker_sost_addr="sost1maker1234567890abcdef1234567890abcdef12",
        taker_sost_addr="sost1taker1234567890abcdef1234567890abcdef12",
        maker_eth_addr="0xMakerEthAddress1234567890abcdef12345678",
        taker_eth_addr="0xTakerEthAddress1234567890abcdef12345678",
        expires_at=now + 2,  # expires in 2 seconds
    )
    deal.transition(DealState.NEGOTIATED, "offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
    daemon.register_deal(deal)

    info("deal_id", deal_id)
    info("expires_in", "2 seconds")
    info("state", deal.state.value)
    time.sleep(0.3)

    # ── Step 2: ETH deposit arrives ──
    step(2, "ETH deposit detected (one side locked)")
    eth_event = EthEvent(
        event_type="deposit",
        tx_hash="0x" + "ab" * 32,
        block_number=19500000,
        deposit_id=99,
        depositor="0xTakerEthAddress1234567890abcdef12345678",
        token="0x68749665FF8D2d112Fa859AA293F07A622782F38",
        amount=25000000000000000,
        unlock_time=int(now) + 86400 * 90,
        timestamp=time.time(),
    )
    daemon.on_eth_event(eth_event)
    info("deposit_id", "99")
    info("state", deal.state.value)
    info("eth_locked", "YES")
    warn("sost_locked", "NO — waiting...")
    time.sleep(0.3)

    # ── Step 3: Wait for expiry ──
    step(3, "Waiting for deal expiry...")
    print(f"  {D}Sleeping 2.5 seconds to exceed expiry window...{X}")
    time.sleep(2.5)

    # ── Step 4: Daemon tick detects expiry ──
    step(4, "Daemon tick — expiry detection")
    daemon.tick()

    info("expired", str(deal.is_expired() or deal.state in (DealState.EXPIRED, DealState.REFUND_PENDING, DealState.REFUNDED)))
    info("state", deal.state.value)
    time.sleep(0.3)

    # ── Step 5: Refund execution ──
    step(5, "Refund path")
    pending = refund_engine.pending()
    if pending:
        for action in pending:
            info("refund_side", action.side)
            info("reason", action.reason)
            refund_engine.execute(action, deal)
            info("state_after_refund", deal.state.value)
    else:
        # Deal may have gone directly to EXPIRED
        info("state", deal.state.value)
        warn("note", "Deal expired before refund engine intervention")
    time.sleep(0.3)

    # ── Step 6: Audit log ──
    step(6, "Audit log")
    history = audit.get_deal_history(deal.deal_id)
    for entry in history:
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {entry.event} {D}{entry.detail[:60]}{X}")

    # ── Done ──
    print(f"\n{R}{'='*60}{X}")
    print(f"{R}{B}  DEMO COMPLETE — REFUND PATH{X}")
    print(f"{R}{'='*60}{X}")
    print(f"\n{D}Deal {deal_id} ended in state: {deal.state.value}{X}")
    print(f"{D}ETH deposit would be returned to depositor after escrow unlock.{X}\n")


if __name__ == "__main__":
    main()
