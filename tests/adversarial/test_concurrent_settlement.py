"""
Adversarial: double-settlement attempts.

Calling execute_settlement twice on the same deal must not
produce a double payout — the second call must fail.
"""

import time
from unittest.mock import MagicMock

import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.settlement_daemon import SettlementDaemon
from src.operator.audit_log import AuditLog


def _build_both_locked(tmp_path):
    store = DealStore()
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    eth = MagicMock()
    sost = MagicMock()
    refund = MagicMock()
    daemon = SettlementDaemon(store, eth, sost, refund, audit)

    deal = store.create(
        pair="SOST/XAUT", side="buy",
        amount_sost=200_000_000_00, amount_gold=2_000_000_000_000_000_000,
        maker_sost_addr="sost1maker", taker_sost_addr="sost1taker",
        maker_eth_addr="0xmaker", taker_eth_addr="0xtaker",
    )
    deal.transition(DealState.NEGOTIATED, "setup")
    deal.transition(DealState.AWAITING_ETH_LOCK, "setup")
    deal.eth_tx_hash = "0xeth"
    deal.eth_deposit_id = 1
    deal.sost_lock_txid = "sost_tx"
    deal.transition(DealState.BOTH_LOCKED, "both locked")

    daemon.register_deal(deal)
    return daemon, deal, audit


class TestConcurrentSettlement:
    def test_first_settlement_succeeds(self, tmp_path):
        daemon, deal, _ = _build_both_locked(tmp_path)

        result = daemon.execute_settlement(deal.deal_id)
        assert result is True
        assert deal.state == DealState.SETTLED

    def test_second_settlement_fails(self, tmp_path):
        daemon, deal, _ = _build_both_locked(tmp_path)

        first = daemon.execute_settlement(deal.deal_id)
        second = daemon.execute_settlement(deal.deal_id)

        assert first is True
        assert second is False
        assert deal.state == DealState.SETTLED

    def test_no_double_settlement_in_audit(self, tmp_path):
        daemon, deal, audit = _build_both_locked(tmp_path)

        daemon.execute_settlement(deal.deal_id)
        daemon.execute_settlement(deal.deal_id)

        settled_entries = [e for e in audit.get_deal_history(deal.deal_id)
                          if e.event == "settled"]
        assert len(settled_entries) == 1
