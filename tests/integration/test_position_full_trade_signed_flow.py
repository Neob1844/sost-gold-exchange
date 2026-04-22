"""
Integration test — signed full position trade flow.

Verifies the complete lifecycle: signed offer -> deal -> settlement -> ownership transfer.
All tests are deterministic with fresh registries and deal stores.
"""

import hashlib
import time

import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.positions.position_schema import Position, ContractType, BackingType, PositionStatus, RightType
from src.positions.position_registry import PositionRegistry
from src.positions.position_pricing import value_position
from src.positions.position_transfer import PositionTransferEngine
from src.positions.position_settlement import PositionSettlement
from src.operator.audit_log import AuditLog


SELLER = "sost1seller00000000000000000000000000"
BUYER = "sost1buyer000000000000000000000000000"
SELLER_ETH = "0xSellerEthAddress0000000000000000000000"
BUYER_ETH = "0xBuyerEthAddress00000000000000000000000"

GOLD_PRICE = 0.001  # SOST satoshis per wei


def _create_components(tmp_path):
    registry = PositionRegistry()
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    transfer_engine = PositionTransferEngine(registry)
    settlement = PositionSettlement(registry, transfer_engine, audit)
    deal_store = DealStore()
    return registry, audit, transfer_engine, settlement, deal_store


def _create_position(registry, owner=SELLER):
    return registry.create_model_b(
        owner=owner,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=365 * 86400,
        reward_total=10_000_000,
        eth_deposit_id=42,
        eth_tx="0xabc123",
    )


def _create_deal_both_locked(deal_store, amount_sost, amount_gold):
    deal = deal_store.create(
        pair="SOST/XAUT",
        side="sell",
        amount_sost=amount_sost,
        amount_gold=amount_gold,
        maker_sost_addr=SELLER,
        taker_sost_addr=BUYER,
        maker_eth_addr=SELLER_ETH,
        taker_eth_addr=BUYER_ETH,
    )
    deal.transition(DealState.NEGOTIATED, "terms agreed")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH")
    deal.mark_eth_locked("0xeth_lock_hash", 42)
    deal.mark_sost_locked("sost_lock_txid")
    assert deal.state == DealState.BOTH_LOCKED
    return deal


class TestFullPositionTradeSignedFlow:

    def test_full_position_trade_happy_path(self, tmp_path):
        """Create position, simulate signed deal, transfer, verify owner changed."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position(registry)

        valuation = value_position(position, GOLD_PRICE)
        deal = _create_deal_both_locked(deal_store, valuation.net_value_sost, position.reference_amount)

        assert position.owner == SELLER

        settled = settlement.settle_position_trade(deal, position.position_id)

        assert settled is True
        assert position.owner == BUYER
        assert deal.state == DealState.SETTLED

    def test_full_trade_audit_complete(self, tmp_path):
        """Verify audit log has all entries for a successful trade."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position(registry)

        valuation = value_position(position, GOLD_PRICE)
        deal = _create_deal_both_locked(deal_store, valuation.net_value_sost, position.reference_amount)

        settlement.settle_position_trade(deal, position.position_id)

        history = audit.get_deal_history(deal.deal_id)
        event_names = [e.event for e in history]
        assert "position_settled" in event_names

        # Verify the settled entry references the position
        settled_entry = [e for e in history if e.event == "position_settled"][0]
        assert position.position_id in settled_entry.detail
        assert BUYER in settled_entry.detail

    def test_full_trade_position_history(self, tmp_path):
        """Verify position.history records the transfer event."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position(registry)

        valuation = value_position(position, GOLD_PRICE)
        deal = _create_deal_both_locked(deal_store, valuation.net_value_sost, position.reference_amount)

        settlement.settle_position_trade(deal, position.position_id)

        transfer_events = [h for h in position.history if h["event"] == "transferred"]
        assert len(transfer_events) == 1
        assert SELLER in transfer_events[0]["detail"]
        assert BUYER in transfer_events[0]["detail"]
        assert deal.deal_id in transfer_events[0]["detail"]

    def test_full_trade_deal_settled(self, tmp_path):
        """Verify deal reaches SETTLED state with settlement_tx_hash set."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position(registry)

        valuation = value_position(position, GOLD_PRICE)
        deal = _create_deal_both_locked(deal_store, valuation.net_value_sost, position.reference_amount)

        settlement.settle_position_trade(deal, position.position_id)

        assert deal.state == DealState.SETTLED
        assert deal.settlement_tx_hash is not None
        assert "position_transfer" in deal.settlement_tx_hash
        assert position.position_id in deal.settlement_tx_hash
        assert deal.is_terminal() is True

    def test_full_trade_valuation_preserved(self, tmp_path):
        """Value before = value after (same gold backing, same remaining time)."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position(registry)

        val_before = value_position(position, GOLD_PRICE)
        deal = _create_deal_both_locked(deal_store, val_before.net_value_sost, position.reference_amount)

        settlement.settle_position_trade(deal, position.position_id)

        # Position still has same backing — gold value unchanged
        val_after = value_position(position, GOLD_PRICE)
        assert val_after.gold_value_sost == val_before.gold_value_sost
        assert position.reference_amount == 1_000_000_000_000_000_000
        assert position.token_symbol == "XAUT"
        assert position.bond_amount_sost == 50_000_000
