"""
Adversarial: duplicate ETH deposit events.

Replaying the same on-chain EthEvent must not double-advance deal state
or create duplicate audit entries.
"""

import time
from unittest.mock import MagicMock

import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.settlement_daemon import SettlementDaemon
from src.watchers.ethereum_watcher import EthEvent
from src.operator.audit_log import AuditLog


DEPOSIT_ID = 42
TX_HASH = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


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
        taker_sost_addr="sost1taker",
        maker_eth_addr="0xmaker",
        taker_eth_addr="0xtaker",
    )
    # Advance to NEGOTIATED so mark_eth_locked can fire
    deal.transition(DealState.NEGOTIATED, "test setup")
    deal.transition(DealState.AWAITING_ETH_LOCK, "test setup")

    daemon.register_deal(deal)
    daemon._deal_eth_map[DEPOSIT_ID] = deal.deal_id
    return store, daemon, deal, audit


def _eth_event():
    return EthEvent(
        event_type="deposit",
        tx_hash=TX_HASH,
        block_number=100,
        deposit_id=DEPOSIT_ID,
        depositor="0xtaker",
        token="0xtoken",
        amount=1_000_000_000_000_000_000,
        unlock_time=9999999999,
        timestamp=time.time(),
    )


class TestDuplicateEthEvent:
    def test_second_identical_eth_event_is_noop(self, tmp_path):
        store, daemon, deal, _ = _make_deal_and_daemon(tmp_path)
        event = _eth_event()

        daemon.on_eth_event(event)
        state_after_first = deal.state

        daemon.on_eth_event(event)
        state_after_second = deal.state

        # State should not change on replay
        assert state_after_first == state_after_second

    def test_deal_marked_eth_locked_only_once(self, tmp_path):
        store, daemon, deal, _ = _make_deal_and_daemon(tmp_path)
        event = _eth_event()

        daemon.on_eth_event(event)
        daemon.on_eth_event(event)

        assert deal.eth_tx_hash == TX_HASH
        assert deal.eth_deposit_id == DEPOSIT_ID
        # Should have advanced to AWAITING_SOST_LOCK (not beyond)
        assert deal.state == DealState.AWAITING_SOST_LOCK

    def test_no_double_state_advance(self, tmp_path):
        store, daemon, deal, _ = _make_deal_and_daemon(tmp_path)
        event = _eth_event()

        daemon.on_eth_event(event)
        daemon.on_eth_event(event)
        daemon.on_eth_event(event)

        # Count state transitions that mention eth
        eth_transitions = [h for h in deal.history if "eth" in h.get("reason", "").lower()
                           or "locked" in h.get("reason", "").lower()]
        # Only one eth lock transition should have occurred
        assert len(eth_transitions) <= 2  # setup + one lock

    def test_audit_shows_single_eth_lock(self, tmp_path):
        store, daemon, deal, audit = _make_deal_and_daemon(tmp_path)
        event = _eth_event()

        daemon.on_eth_event(event)
        daemon.on_eth_event(event)

        eth_lock_entries = [e for e in audit.get_deal_history(deal.deal_id)
                           if e.event == "eth_locked"]
        assert len(eth_lock_entries) == 1
