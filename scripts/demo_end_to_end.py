#!/usr/bin/env python3
"""
SOST Settlement Demo — End-to-End Happy Path

Demonstrates the full settlement lifecycle:
  offer → accept → deal → ETH lock → SOST lock → settlement → notice

Usage:
  python3 scripts/demo_end_to_end.py              # mock mode (default)
  python3 scripts/demo_end_to_end.py --mode live   # live RPC mode
"""

import argparse
import hashlib
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

# ANSI colors
R = "\033[91m"  # red
G = "\033[92m"  # green
C = "\033[96m"  # cyan
Y = "\033[93m"  # yellow
O = "\033[38;5;208m"  # orange
W = "\033[97m"  # white
D = "\033[90m"  # dim
B = "\033[1m"   # bold
X = "\033[0m"   # reset


def banner():
    print(f"""
{Y}{'='*60}{X}
{O}{B}  SOST SOVEREIGN SETTLEMENT DEMO{X}
{Y}  End-to-End Happy Path{X}
{Y}{'='*60}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*50}{X}")


def info(label, value):
    print(f"  {D}{label}:{X} {G}{value}{X}")


def state_change(old, new):
    print(f"  {Y}state:{X} {O}{old}{X} {D}→{X} {G}{new}{X}")


def pause():
    time.sleep(0.5)


def derive_deal_id(offer_id, accept_id):
    return hashlib.sha256(f"{offer_id}:{accept_id}".encode()).hexdigest()[:16]


def run_mock_demo():
    banner()
    print(f"{D}mode: MOCK (no network, simulated events){X}\n")

    # Setup
    deal_store = DealStore()
    audit = AuditLog(log_dir="/tmp/sost_demo_audit")
    refund_engine = RefundEngine()

    # Mock watchers (won't poll)
    class MockWatcher:
        def __init__(self):
            self._events = []
            self.on_event = None
        def add_watch_address(self, addr): pass
        def run(self): pass
        def stop(self): pass

    eth_watcher = MockWatcher()
    sost_watcher = MockWatcher()

    daemon = SettlementDaemon(
        deal_store=deal_store,
        eth_watcher=eth_watcher,
        sost_watcher=sost_watcher,
        refund_engine=refund_engine,
        audit=audit,
    )

    # ── Step 1: Create offer ──
    step(1, "Creating trade offer")
    offer_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    offer_hash = hashlib.sha256(
        f"1|trade_offer|{offer_id}|SOST/XAUT|buy|100.00000000|0.05000000|0.0005|"
        f"sost1maker1234|0xMakerEth|{int(time.time())+3600}|escrow_bilateral|"
        f"{os.urandom(16).hex()}|{int(time.time())}".encode()
    ).hexdigest()

    info("offer_id", offer_id)
    info("pair", "SOST/XAUT")
    info("amount", "100 SOST for 0.05 XAUT")
    info("canonical_hash", offer_hash[:32] + "...")
    pause()

    # ── Step 2: Accept offer ──
    step(2, "Accepting offer")
    accept_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    deal_id = derive_deal_id(offer_id, accept_id)

    info("accept_id", accept_id)
    info("deal_id", deal_id)
    info("derivation", f"SHA256({offer_id}:{accept_id})[:16]")
    pause()

    # ── Step 3: Register deal ──
    step(3, "Registering deal with settlement daemon")
    now = time.time()
    deal = deal_store.create(
        deal_id=deal_id,
        pair="SOST/XAUT",
        side="buy",
        amount_sost=10000000000,  # 100 SOST
        amount_gold=50000000000000000,  # 0.05 XAUT in wei
        maker_sost_addr="sost1maker1234567890abcdef1234567890abcdef12",
        taker_sost_addr="sost1taker1234567890abcdef1234567890abcdef12",
        maker_eth_addr="0xMakerEthAddress1234567890abcdef12345678",
        taker_eth_addr="0xTakerEthAddress1234567890abcdef12345678",
        expires_at=now + 3600,
    )
    deal.transition(DealState.NEGOTIATED, "offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
    daemon.register_deal(deal)

    state_change("CREATED", "AWAITING_ETH_LOCK")
    info("expires_in", "3600s")
    pause()

    # ── Step 4: ETH deposit detected ──
    step(4, "ETH deposit detected")
    eth_event = EthEvent(
        event_type="deposit",
        tx_hash="0xabc123def456789012345678901234567890abcdef1234567890abcdef123456",
        block_number=19500000,
        deposit_id=42,
        depositor="0xTakerEthAddress1234567890abcdef12345678",
        token="0x68749665FF8D2d112Fa859AA293F07A622782F38",
        amount=50000000000000000,
        unlock_time=int(now) + 86400 * 90,
        timestamp=time.time(),
    )
    daemon.on_eth_event(eth_event)

    info("deposit_id", "42")
    info("tx_hash", eth_event.tx_hash[:24] + "...")
    info("amount", "0.05 XAUT")
    state_change("AWAITING_ETH_LOCK", deal.state.value)
    pause()

    # ── Step 5: SOST lock detected ──
    step(5, "SOST lock detected")
    sost_event = SostEvent(
        event_type="balance_confirmed",
        txid="f" * 64,
        block_height=5500,
        address="sost1maker1234567890abcdef1234567890abcdef12",
        amount=10000000000,
        deal_ref=deal_id,
        timestamp=time.time(),
    )
    daemon.on_sost_event(sost_event)

    info("txid", sost_event.txid[:24] + "...")
    info("amount", "100 SOST (10,000,000,000 stocks)")
    state_change("AWAITING_SOST_LOCK", deal.state.value)
    pause()

    # ── Step 6: Execute settlement ──
    step(6, "Executing settlement")
    settlement_tx = hashlib.sha256(f"settle:{deal_id}:{time.time()}".encode()).hexdigest()
    result = daemon.execute_settlement(deal.deal_id)

    info("settlement_tx", settlement_tx[:32] + "...")
    info("result", "SUCCESS" if result else "FAILED")
    state_change("BOTH_LOCKED", deal.state.value)
    pause()

    # ── Step 7: Settlement notice ──
    step(7, "Settlement notice emitted")
    notice_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    info("notice_id", notice_id)
    info("outcome", "settled")
    info("deal_id", deal_id)
    info("eth_tx_hash", eth_event.tx_hash[:24] + "...")
    pause()

    # ── Step 8: Audit log ──
    step(8, "Audit log")
    history = audit.get_deal_history(deal.deal_id)
    for entry in history:
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {entry.event} {D}{entry.detail[:60]}{X}")

    # ── Done ──
    print(f"\n{G}{'='*60}{X}")
    print(f"{G}{B}  DEMO COMPLETE — SETTLEMENT SUCCESSFUL{X}")
    print(f"{G}{'='*60}{X}")
    print(f"\n{D}Deal {deal_id} settled in {len(history)} audit steps.{X}")
    print(f"{D}Final state: {deal.state.value}{X}\n")


def run_live_demo():
    print(f"\n{Y}{B}LIVE MODE{X}")
    print(f"{R}Not yet implemented — requires deployed Sepolia contracts.{X}")
    print(f"{D}See docs/SEPOLIA_ALPHA_RUNBOOK.md for deployment instructions.{X}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SOST Settlement Demo")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    args = parser.parse_args()

    if args.mode == "live":
        run_live_demo()
    else:
        run_mock_demo()
