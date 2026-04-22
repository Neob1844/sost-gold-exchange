"""Unit tests for the SOST Gold Exchange Refund Engine."""

import time
import pytest

from src.settlement.deal_state_machine import Deal, DealState
from src.settlement.refund_engine import RefundEngine, RefundAction


MAKER_SOST = "sost1maker0000000000000000000000000"
TAKER_SOST = "sost1taker0000000000000000000000000"
MAKER_ETH = "0xMakerEthAddress000000000000000000000000"
TAKER_ETH = "0xTakerEthAddress000000000000000000000000"


def _make_deal(state=DealState.AWAITING_ETH_LOCK, eth_locked=False, sost_locked=False):
    now = time.time()
    d = Deal(
        deal_id=Deal.generate_id(MAKER_SOST, TAKER_SOST, now),
        pair="SOST/XAUT",
        side="buy",
        amount_sost=100_000_000,
        amount_gold=1_000_000_000_000,
        maker_sost_addr=MAKER_SOST,
        taker_sost_addr=TAKER_SOST,
        maker_eth_addr=MAKER_ETH,
        taker_eth_addr=TAKER_ETH,
        state=state,
        created_at=now,
    )
    if eth_locked:
        d.eth_tx_hash = "0xeth_locked"
        d.eth_deposit_id = 99
    if sost_locked:
        d.sost_lock_txid = "txid_sost_locked"
    return d


class TestRequestRefund:
    def test_request_refund_eth_only(self, refund_engine):
        deal = _make_deal(eth_locked=True, sost_locked=False)
        action = refund_engine.request_refund(deal)
        assert action is not None
        assert action.side == "eth"
        assert deal.state == DealState.REFUND_PENDING

    def test_request_refund_sost_only(self, refund_engine):
        deal = _make_deal(eth_locked=False, sost_locked=True)
        action = refund_engine.request_refund(deal)
        assert action is not None
        assert action.side == "sost"

    def test_request_refund_both(self, refund_engine):
        deal = _make_deal(
            state=DealState.BOTH_LOCKED, eth_locked=True, sost_locked=True,
        )
        action = refund_engine.request_refund(deal)
        assert action is not None
        assert action.side == "both"

    def test_request_refund_neither(self, refund_engine):
        deal = _make_deal(eth_locked=False, sost_locked=False)
        action = refund_engine.request_refund(deal)
        assert action is not None
        # No locks — still "both" by default logic (neither branch triggers)
        assert action.side == "both"

    def test_request_refund_terminal_rejected(self, refund_engine):
        deal = _make_deal(state=DealState.SETTLED)
        action = refund_engine.request_refund(deal)
        assert action is None


class TestRefundActionFields:
    def test_refund_action_fields(self, refund_engine):
        deal = _make_deal(eth_locked=True)
        deal.refund_reason = "counterparty timeout"
        action = refund_engine.request_refund(deal)
        assert action.deal_id == deal.deal_id
        assert action.reason == "counterparty timeout"
        assert action.executed is False
        assert action.executed_at is None


class TestExecuteRefund:
    def test_execute_refund(self, refund_engine):
        deal = _make_deal(eth_locked=True)
        action = refund_engine.request_refund(deal)
        assert deal.state == DealState.REFUND_PENDING
        ok = refund_engine.execute(action, deal)
        assert ok is True
        assert action.executed is True
        assert action.executed_at is not None
        assert deal.state == DealState.REFUNDED

    def test_refund_transitions_deal(self, refund_engine):
        deal = _make_deal(
            state=DealState.BOTH_LOCKED, eth_locked=True, sost_locked=True,
        )
        action = refund_engine.request_refund(deal)
        assert deal.state == DealState.REFUND_PENDING
        refund_engine.execute(action, deal)
        assert deal.state == DealState.REFUNDED


class TestTracking:
    def test_pending_tracking(self, refund_engine):
        deal = _make_deal(eth_locked=True)
        action = refund_engine.request_refund(deal)
        assert len(refund_engine.pending()) == 1
        assert refund_engine.pending()[0].deal_id == deal.deal_id

    def test_completed_tracking(self, refund_engine):
        deal = _make_deal(eth_locked=True)
        action = refund_engine.request_refund(deal)
        refund_engine.execute(action, deal)
        assert len(refund_engine.pending()) == 0
        assert len(refund_engine.completed()) == 1
        assert refund_engine.completed()[0].deal_id == deal.deal_id
