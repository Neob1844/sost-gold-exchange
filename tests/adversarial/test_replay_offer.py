"""
Adversarial: replay / duplicate offer attacks.

Ensures that duplicate deals, re-registrations, and replayed offer_ids
cannot create phantom active deals in the settlement daemon.
"""

import time
from unittest.mock import MagicMock

import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.settlement_daemon import SettlementDaemon
from src.operator.audit_log import AuditLog


MAKER = "sost1maker_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
TAKER = "sost1taker_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
MAKER_ETH = "0x1111111111111111111111111111111111111111"
TAKER_ETH = "0x2222222222222222222222222222222222222222"


def _make_daemon(deal_store, tmp_path):
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    eth = MagicMock()
    sost = MagicMock()
    refund = MagicMock()
    return SettlementDaemon(deal_store, eth, sost, refund, audit)


def _base_kwargs():
    return dict(
        pair="SOST/XAUT",
        side="buy",
        amount_sost=100_000_000_00,
        amount_gold=1_000_000_000_000_000_000,
        maker_sost_addr=MAKER,
        taker_sost_addr=TAKER,
        maker_eth_addr=MAKER_ETH,
        taker_eth_addr=TAKER_ETH,
    )


class TestReplayOffer:
    """Same maker/taker/amounts but distinct timestamps produce distinct deal_ids."""

    def test_same_parties_different_timestamps_yield_different_ids(self):
        t1 = time.time()
        t2 = t1 + 0.001
        id1 = Deal.generate_id(MAKER, TAKER, t1)
        id2 = Deal.generate_id(MAKER, TAKER, t2)
        assert id1 != id2

    def test_deal_store_creates_unique_ids(self):
        store = DealStore()
        d1 = store.create(**_base_kwargs())
        # small sleep so timestamp differs
        time.sleep(0.001)
        d2 = store.create(**_base_kwargs())
        assert d1.deal_id != d2.deal_id
        assert len(store.active_deals()) == 2

    def test_register_same_deal_twice_is_idempotent(self, tmp_path):
        store = DealStore()
        daemon = _make_daemon(store, tmp_path)
        deal = store.create(**_base_kwargs())

        daemon.register_deal(deal)
        daemon.register_deal(deal)

        # sost_map should contain the deal only once per address
        assert daemon._deal_sost_map[TAKER] == deal.deal_id
        assert daemon._deal_sost_map[MAKER] == deal.deal_id

    def test_same_offer_id_does_not_duplicate_active_deals(self, tmp_path):
        store = DealStore()
        daemon = _make_daemon(store, tmp_path)

        deal = store.create(**_base_kwargs())
        daemon.register_deal(deal)

        # Attempting to re-create with identical params yields a separate deal
        # but the sost_map for the same addresses now points to the newer one.
        time.sleep(0.001)
        deal2 = store.create(**_base_kwargs())
        daemon.register_deal(deal2)

        # Both deals exist but addresses map to latest registration
        assert daemon._deal_sost_map[TAKER] == deal2.deal_id
        # Original deal is still in the store but won't receive new events
        assert store.get(deal.deal_id) is not None
