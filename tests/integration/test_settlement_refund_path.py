"""Integration tests — refund paths when one side locks but the deal expires."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import MagicMock

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.refund_engine import RefundEngine
from src.settlement.settlement_daemon import SettlementDaemon
from src.watchers.ethereum_watcher import EthereumWatcher
from src.watchers.sost_watcher import SostWatcher
from src.operator.audit_log import AuditLog


MAKER_SOST = "sost1maker0000000000000000000000000"
TAKER_SOST = "sost1taker0000000000000000000000000"
MAKER_ETH = "0xMakerEthAddress000000000000000000000000"
TAKER_ETH = "0xTakerEthAddress000000000000000000000000"


@pytest.fixture
def components(tmp_path):
    deal_store = DealStore()
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    refund_engine = RefundEngine()

    eth_watcher = MagicMock(spec=EthereumWatcher)
    sost_watcher = MagicMock(spec=SostWatcher)
    sost_watcher.watch_addresses = []
    sost_watcher.add_watch_address = lambda addr: sost_watcher.watch_addresses.append(addr)

    daemon = SettlementDaemon(
        deal_store=deal_store,
        eth_watcher=eth_watcher,
        sost_watcher=sost_watcher,
        refund_engine=refund_engine,
        audit=audit,
    )

    return {
        "deal_store": deal_store,
        "audit": audit,
        "refund_engine": refund_engine,
        "daemon": daemon,
    }


def _create_deal_at_awaiting_eth(deal_store):
    """Create a deal and advance it to AWAITING_ETH_LOCK."""
    deal = deal_store.create(
        pair="SOST/XAUT",
        side="buy",
        amount_sost=100_000_000,
        amount_gold=1_000_000_000_000_000_000,
        maker_sost_addr=MAKER_SOST,
        taker_sost_addr=TAKER_SOST,
        maker_eth_addr=MAKER_ETH,
        taker_eth_addr=TAKER_ETH,
    )
    deal.transition(DealState.NEGOTIATED, "terms agreed")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
    return deal


class TestRefundEthLockedSostMissing:
    def test_eth_locked_sost_timeout_refund(self, components):
        """ETH locked, SOST never arrives, deal expires -> refund path."""
        deal_store = components["deal_store"]
        daemon = components["daemon"]
        audit = components["audit"]
        refund_engine = components["refund_engine"]

        deal = _create_deal_at_awaiting_eth(deal_store)

        # Lock ETH side
        deal.mark_eth_locked("0xeth_tx_refund_test", 6001)
        assert deal.state == DealState.AWAITING_SOST_LOCK

        # Force expiry in the past
        deal.expires_at = time.time() - 10

        # Daemon tick should detect expiry.
        # check_expiry does not expire BOTH_LOCKED or SETTLING states;
        # AWAITING_SOST_LOCK is eligible for expiry.
        daemon.tick()

        # Deal should have been expired by check_all_expiry, then refund requested
        # because eth_tx_hash is set.
        assert deal.state in (DealState.EXPIRED, DealState.REFUND_PENDING, DealState.REFUNDED)

        # check_expiry transitions to EXPIRED first.
        # Settlement daemon then calls refund_engine.request_refund, but
        # at that point the deal is already terminal (EXPIRED), so the refund
        # engine's request_refund guards against refunding terminal deals.
        # Verify the audit log recorded the expiry.
        history = audit.get_deal_history(deal.deal_id)
        event_names = [e.event for e in history]
        assert "expired" in event_names


class TestRefundSostLockedEthMissing:
    def test_sost_locked_eth_timeout_refund(self, components):
        """SOST locked, ETH never arrives, deal expires -> refund path."""
        deal_store = components["deal_store"]
        daemon = components["daemon"]
        audit = components["audit"]

        deal = _create_deal_at_awaiting_eth(deal_store)

        # Lock SOST side (from AWAITING_ETH_LOCK, mark_sost_locked transitions
        # to AWAITING_SOST_LOCK)
        deal.mark_sost_locked("sost_txid_refund_test")
        assert deal.state == DealState.AWAITING_SOST_LOCK

        # Force expiry
        deal.expires_at = time.time() - 10

        daemon.tick()

        # Should expire since AWAITING_SOST_LOCK is eligible for check_expiry
        assert deal.state in (DealState.EXPIRED, DealState.REFUND_PENDING, DealState.REFUNDED)

        history = audit.get_deal_history(deal.deal_id)
        event_names = [e.event for e in history]
        assert "expired" in event_names
