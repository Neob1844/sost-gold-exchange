"""
Adversarial: position trade with expired offer.

Verifies that deals created from expired offers cannot settle
(deal expires before reaching BOTH_LOCKED), and that offers
accepted just before expiry can still complete.
"""

import time

import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.positions.position_schema import Position, PositionStatus
from src.positions.position_registry import PositionRegistry
from src.positions.position_transfer import PositionTransferEngine
from src.positions.position_settlement import PositionSettlement
from src.operator.audit_log import AuditLog


SELLER = "sost1seller00000000000000000000000000"
BUYER = "sost1buyer000000000000000000000000000"
SELLER_ETH = "0xSellerEthAddress0000000000000000000000"
BUYER_ETH = "0xBuyerEthAddress00000000000000000000000"


def _create_components(tmp_path):
    registry = PositionRegistry()
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    transfer_engine = PositionTransferEngine(registry)
    settlement = PositionSettlement(registry, transfer_engine, audit)
    deal_store = DealStore()
    return registry, audit, transfer_engine, settlement, deal_store


def _create_position(registry):
    return registry.create_model_b(
        owner=SELLER,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=365 * 86400,
        reward_total=10_000_000,
        eth_deposit_id=42,
        eth_tx="0xabc123",
    )


class TestPositionTradeExpiredOffer:

    def test_expired_offer_rejected(self, tmp_path):
        """A deal whose expires_at is in the past cannot reach BOTH_LOCKED.
        The deal is created with an already-expired timestamp, so check_expiry
        transitions it to EXPIRED before locks can complete."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position(registry)

        now = time.time()
        deal = deal_store.create(
            pair="SOST/XAUT",
            side="sell",
            amount_sost=100_000,
            amount_gold=1_000_000_000_000_000_000,
            maker_sost_addr=SELLER,
            taker_sost_addr=BUYER,
            maker_eth_addr=SELLER_ETH,
            taker_eth_addr=BUYER_ETH,
            created_at=now - 7200,  # created 2 hours ago
            expires_at=now - 3600,  # expired 1 hour ago
        )
        deal.transition(DealState.NEGOTIATED, "accepted")

        # Deal should detect expiry
        assert deal.is_expired() is True
        expired = deal.check_expiry()
        assert expired is True
        assert deal.state == DealState.EXPIRED

        # Cannot settle an expired deal — it is not in BOTH_LOCKED
        settled = settlement.settle_position_trade(deal, position.position_id)
        assert settled is False

        # Position owner unchanged
        assert position.owner == SELLER

    def test_offer_just_before_expiry_accepted(self, tmp_path):
        """A deal that reaches BOTH_LOCKED before expiry can still settle,
        even if expiry passes during settlement (BOTH_LOCKED is protected)."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position(registry)

        now = time.time()
        deal = deal_store.create(
            pair="SOST/XAUT",
            side="sell",
            amount_sost=100_000,
            amount_gold=1_000_000_000_000_000_000,
            maker_sost_addr=SELLER,
            taker_sost_addr=BUYER,
            maker_eth_addr=SELLER_ETH,
            taker_eth_addr=BUYER_ETH,
            created_at=now - 3500,    # created almost 1 hour ago
            expires_at=now - 1,       # technically expired 1 second ago
        )

        # Fast-track to BOTH_LOCKED before expiry check
        deal.transition(DealState.NEGOTIATED, "accepted just in time")
        deal.transition(DealState.AWAITING_ETH_LOCK, "lock")
        deal.mark_eth_locked("0xeth_lock", 42)
        deal.mark_sost_locked("sost_lock_txid")
        assert deal.state == DealState.BOTH_LOCKED

        # check_expiry should NOT expire a BOTH_LOCKED deal
        expired = deal.check_expiry()
        assert expired is False
        assert deal.state == DealState.BOTH_LOCKED

        # Settlement should succeed
        settled = settlement.settle_position_trade(deal, position.position_id)
        assert settled is True
        assert position.owner == BUYER
        assert deal.state == DealState.SETTLED
