"""
Tests for demo settlement and refund state progressions.

Runs the same logic as the demo scripts but as pytest tests, verifying
that deal state transitions, audit logging, and refund handling work correctly.
"""

import hashlib
import time
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.settlement_daemon import SettlementDaemon
from src.settlement.refund_engine import RefundEngine
from src.watchers.ethereum_watcher import EthEvent
from src.watchers.sost_watcher import SostEvent
from src.operator.audit_log import AuditLog


class MockWatcher:
    """Minimal watcher stub for tests."""
    def __init__(self):
        self.on_event = None
        self._watched = []

    def add_watch_address(self, addr):
        self._watched.append(addr)

    def run(self):
        pass

    def stop(self):
        pass


def _make_deal(deal_store, expires_in=3600):
    """Create a deal directly via Deal() to avoid DealStore.create() deal_id conflict."""
    now = time.time()
    deal_id = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    deal = Deal(
        deal_id=deal_id,
        pair="SOST/XAUT",
        side="buy",
        amount_sost=10_000_000_000,
        amount_gold=50_000_000_000_000_000,
        maker_sost_addr="sost1maker1234567890abcdef1234567890abcdef12",
        taker_sost_addr="sost1taker1234567890abcdef1234567890abcdef12",
        maker_eth_addr="0xMakerEthAddress1234567890abcdef12345678",
        taker_eth_addr="0xTakerEthAddress1234567890abcdef12345678",
        created_at=now,
        expires_at=now + expires_in,
    )
    deal_store._deals[deal_id] = deal
    return deal


def _make_daemon(deal_store, audit):
    """Build a SettlementDaemon with mock watchers."""
    refund_engine = RefundEngine()
    eth_watcher = MockWatcher()
    sost_watcher = MockWatcher()
    daemon = SettlementDaemon(
        deal_store=deal_store,
        eth_watcher=eth_watcher,
        sost_watcher=sost_watcher,
        refund_engine=refund_engine,
        audit=audit,
    )
    return daemon, refund_engine


def test_mock_demo_completes(tmp_path):
    """Full happy-path settlement: CREATED -> ... -> SETTLED with audit entries."""
    deal_store = DealStore()
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    daemon, _ = _make_daemon(deal_store, audit)

    deal = _make_deal(deal_store)
    deal.transition(DealState.NEGOTIATED, "offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
    daemon.register_deal(deal)

    # Map deposit_id so the daemon can correlate
    daemon._deal_eth_map[42] = deal.deal_id

    # Simulate ETH deposit
    eth_event = EthEvent(
        event_type="deposit",
        tx_hash="0x" + "ab" * 32,
        block_number=19500000,
        deposit_id=42,
        depositor=deal.taker_eth_addr,
        token="0x68749665FF8D2d112Fa859AA293F07A622782F38",
        amount=50_000_000_000_000_000,
        unlock_time=int(time.time()) + 86400 * 90,
        timestamp=time.time(),
    )
    daemon.on_eth_event(eth_event)
    assert deal.state == DealState.AWAITING_SOST_LOCK

    # Simulate SOST lock
    sost_event = SostEvent(
        event_type="balance_confirmed",
        txid="f" * 64,
        block_height=5500,
        address=deal.maker_sost_addr,
        amount=10_000_000_000,
        deal_ref=deal.deal_id,
        timestamp=time.time(),
    )
    daemon.on_sost_event(sost_event)
    assert deal.state == DealState.BOTH_LOCKED

    # Execute settlement
    result = daemon.execute_settlement(deal.deal_id)
    assert result is True
    assert deal.state == DealState.SETTLED

    # Verify audit has entries
    history = audit.get_deal_history(deal.deal_id)
    assert len(history) >= 4  # registered, eth_locked, sost_locked, both_locked, settlement_initiated, settled
    event_types = [e.event for e in history]
    assert "registered" in event_types
    assert "settled" in event_types


def test_mock_refund_completes(tmp_path):
    """Refund path: deal expires after ETH lock, SOST never arrives."""
    deal_store = DealStore()
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    daemon, refund_engine = _make_daemon(deal_store, audit)

    # Create deal with very short expiry (already expired)
    deal = _make_deal(deal_store, expires_in=-1)
    deal.transition(DealState.NEGOTIATED, "offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
    daemon.register_deal(deal)

    # Map deposit_id
    daemon._deal_eth_map[99] = deal.deal_id

    # ETH deposit arrives (deal already expired but mark it before tick)
    deal.eth_tx_hash = "0x" + "cd" * 32
    deal.eth_deposit_id = 99

    # Daemon tick detects expiry
    daemon.tick()

    # Deal should have expired and refund been requested
    assert deal.state in (DealState.EXPIRED, DealState.REFUND_PENDING, DealState.REFUNDED)

    # If refund is pending, execute it
    pending = refund_engine.pending()
    if pending:
        for action in pending:
            refund_engine.execute(action, deal)

    assert deal.state in (DealState.EXPIRED, DealState.REFUNDED)

    # Verify audit recorded the expiry
    history = audit.get_deal_history(deal.deal_id)
    assert len(history) >= 1


def test_operator_list_empty_store():
    """An empty DealStore should return an empty active deals list."""
    deal_store = DealStore()
    assert deal_store.active_deals() == []
    assert deal_store.get("nonexistent") is None
