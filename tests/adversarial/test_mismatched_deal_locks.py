"""
Adversarial: cross-deal lock confusion.

ETH lock for deal_A and SOST lock for deal_B must not cause either
deal to reach BOTH_LOCKED. Each deal should remain in a partial state.
"""

import time
from unittest.mock import MagicMock

import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.settlement_daemon import SettlementDaemon
from src.watchers.ethereum_watcher import EthEvent
from src.watchers.sost_watcher import SostEvent
from src.operator.audit_log import AuditLog


DEPOSIT_A = 100
DEPOSIT_B = 200
SOST_ADDR_A = "sost1deal_a_taker"
SOST_ADDR_B = "sost1deal_b_taker"


def _build(tmp_path):
    store = DealStore()
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    eth = MagicMock()
    sost = MagicMock()
    refund = MagicMock()
    daemon = SettlementDaemon(store, eth, sost, refund, audit)

    deal_a = store.create(
        pair="SOST/XAUT", side="buy",
        amount_sost=50_000_000_00, amount_gold=500_000_000_000_000_000,
        maker_sost_addr="sost1maker_a", taker_sost_addr=SOST_ADDR_A,
        maker_eth_addr="0xmakerA", taker_eth_addr="0xtakerA",
    )
    deal_b = store.create(
        pair="SOST/PAXG", side="sell",
        amount_sost=80_000_000_00, amount_gold=800_000_000_000_000_000,
        maker_sost_addr="sost1maker_b", taker_sost_addr=SOST_ADDR_B,
        maker_eth_addr="0xmakerB", taker_eth_addr="0xtakerB",
    )

    for d in (deal_a, deal_b):
        d.transition(DealState.NEGOTIATED, "setup")
        d.transition(DealState.AWAITING_ETH_LOCK, "setup")
        daemon.register_deal(d)

    daemon._deal_eth_map[DEPOSIT_A] = deal_a.deal_id
    daemon._deal_eth_map[DEPOSIT_B] = deal_b.deal_id

    return daemon, deal_a, deal_b


class TestMismatchedDealLocks:
    def test_cross_lock_does_not_reach_both_locked(self, tmp_path):
        daemon, deal_a, deal_b = _build(tmp_path)

        # ETH lock for deal_A
        daemon.on_eth_event(EthEvent(
            event_type="deposit", tx_hash="0xeth_a", block_number=10,
            deposit_id=DEPOSIT_A, depositor="0xtakerA", token="0xtok",
            amount=500_000_000_000_000_000, unlock_time=9999999999,
            timestamp=time.time(),
        ))
        # SOST lock for deal_B
        daemon.on_sost_event(SostEvent(
            event_type="lock_detected", txid="sost_tx_b", block_height=600,
            address=SOST_ADDR_B, amount=80_000_000_00, deal_ref="",
            timestamp=time.time(),
        ))

        assert deal_a.state != DealState.BOTH_LOCKED
        assert deal_b.state != DealState.BOTH_LOCKED

    def test_each_deal_in_partial_lock_state(self, tmp_path):
        daemon, deal_a, deal_b = _build(tmp_path)

        daemon.on_eth_event(EthEvent(
            event_type="deposit", tx_hash="0xeth_a", block_number=10,
            deposit_id=DEPOSIT_A, depositor="0xtakerA", token="0xtok",
            amount=500_000_000_000_000_000, unlock_time=9999999999,
            timestamp=time.time(),
        ))
        daemon.on_sost_event(SostEvent(
            event_type="lock_detected", txid="sost_tx_b", block_height=600,
            address=SOST_ADDR_B, amount=80_000_000_00, deal_ref="",
            timestamp=time.time(),
        ))

        # deal_a has ETH lock only → AWAITING_SOST_LOCK
        assert deal_a.state == DealState.AWAITING_SOST_LOCK
        assert deal_a.eth_tx_hash == "0xeth_a"
        assert deal_a.sost_lock_txid is None

        # deal_b has SOST lock only → AWAITING_SOST_LOCK
        assert deal_b.state == DealState.AWAITING_SOST_LOCK
        assert deal_b.sost_lock_txid is not None
        assert deal_b.eth_tx_hash is None

    def test_completing_correct_pairs_reaches_both_locked(self, tmp_path):
        daemon, deal_a, deal_b = _build(tmp_path)

        # Cross-lock (partial)
        daemon.on_eth_event(EthEvent(
            event_type="deposit", tx_hash="0xeth_a", block_number=10,
            deposit_id=DEPOSIT_A, depositor="0xtakerA", token="0xtok",
            amount=500_000_000_000_000_000, unlock_time=9999999999,
            timestamp=time.time(),
        ))
        daemon.on_sost_event(SostEvent(
            event_type="lock_detected", txid="sost_tx_b", block_height=600,
            address=SOST_ADDR_B, amount=80_000_000_00, deal_ref="",
            timestamp=time.time(),
        ))

        # Now complete the correct counterparts
        daemon.on_sost_event(SostEvent(
            event_type="lock_detected", txid="sost_tx_a", block_height=601,
            address=SOST_ADDR_A, amount=50_000_000_00, deal_ref="",
            timestamp=time.time(),
        ))
        daemon.on_eth_event(EthEvent(
            event_type="deposit", tx_hash="0xeth_b", block_number=11,
            deposit_id=DEPOSIT_B, depositor="0xtakerB", token="0xtok",
            amount=800_000_000_000_000_000, unlock_time=9999999999,
            timestamp=time.time(),
        ))

        assert deal_a.state == DealState.BOTH_LOCKED
        assert deal_b.state == DealState.BOTH_LOCKED
