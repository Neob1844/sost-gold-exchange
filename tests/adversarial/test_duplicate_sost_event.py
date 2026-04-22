"""
Adversarial: duplicate SOST lock events.

Replaying the same SostEvent must not double-advance deal state
or create duplicate audit entries.
"""

import time
from unittest.mock import MagicMock

import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.settlement_daemon import SettlementDaemon
from src.watchers.sost_watcher import SostEvent
from src.operator.audit_log import AuditLog


SOST_ADDR = "sost1taker_for_sost_lock"
SOST_TXID = "abc123fedcba456789012345678901234567890abcdef1234567890abcdef12"


def _make_deal_and_daemon(tmp_path):
    store = DealStore()
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    eth = MagicMock()
    sost = MagicMock()
    refund = MagicMock()
    daemon = SettlementDaemon(store, eth, sost, refund, audit)

    deal = store.create(
        pair="SOST/XAUT",
        side="buy",
        amount_sost=100_000_000_00,
        amount_gold=1_000_000_000_000_000_000,
        maker_sost_addr="sost1maker",
        taker_sost_addr=SOST_ADDR,
        maker_eth_addr="0xmaker",
        taker_eth_addr="0xtaker",
    )
    # Advance to AWAITING_ETH_LOCK so mark_sost_locked can transition
    deal.transition(DealState.NEGOTIATED, "test setup")
    deal.transition(DealState.AWAITING_ETH_LOCK, "test setup")

    daemon.register_deal(deal)
    return store, daemon, deal, audit


def _sost_event():
    return SostEvent(
        event_type="lock_detected",
        txid=SOST_TXID,
        block_height=5000,
        address=SOST_ADDR,
        amount=100_000_000_00,
        deal_ref="",
        timestamp=time.time(),
    )


class TestDuplicateSostEvent:
    def test_second_identical_sost_event_is_noop(self, tmp_path):
        store, daemon, deal, _ = _make_deal_and_daemon(tmp_path)
        event = _sost_event()

        daemon.on_sost_event(event)
        state_after_first = deal.state

        daemon.on_sost_event(event)
        state_after_second = deal.state

        assert state_after_first == state_after_second

    def test_deal_marked_sost_locked_only_once(self, tmp_path):
        store, daemon, deal, _ = _make_deal_and_daemon(tmp_path)
        event = _sost_event()

        daemon.on_sost_event(event)
        daemon.on_sost_event(event)

        assert deal.sost_lock_txid == SOST_TXID
        assert deal.state == DealState.AWAITING_SOST_LOCK

    def test_no_double_state_advance(self, tmp_path):
        store, daemon, deal, _ = _make_deal_and_daemon(tmp_path)
        event = _sost_event()

        daemon.on_sost_event(event)
        daemon.on_sost_event(event)
        daemon.on_sost_event(event)

        # Count transitions to AWAITING_SOST_LOCK in history
        sost_transitions = [h for h in deal.history
                            if h.get("to") == DealState.AWAITING_SOST_LOCK.value
                            and "sost" in h.get("reason", "").lower()]
        assert len(sost_transitions) == 1

    def test_audit_shows_single_sost_lock(self, tmp_path):
        store, daemon, deal, audit = _make_deal_and_daemon(tmp_path)
        event = _sost_event()

        daemon.on_sost_event(event)
        daemon.on_sost_event(event)

        sost_lock_entries = [e for e in audit.get_deal_history(deal.deal_id)
                            if e.event == "sost_locked"]
        assert len(sost_lock_entries) == 1
