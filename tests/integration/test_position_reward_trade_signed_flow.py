"""
Integration test — signed reward right trade flow.

Verifies the complete lifecycle of splitting reward rights from a position:
  signed offer -> deal -> settlement -> child position created -> parent zeroed.
All tests are deterministic with fresh registries and deal stores.
"""

import time

import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.positions.position_schema import Position, ContractType, BackingType, PositionStatus, RightType
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


def _create_position_with_rewards(registry, reward_total=10_000_000):
    return registry.create_model_b(
        owner=SELLER,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=365 * 86400,
        reward_total=reward_total,
        eth_deposit_id=99,
        eth_tx="0xreward_pos_tx",
    )


def _create_deal_both_locked(deal_store, amount_sost):
    deal = deal_store.create(
        pair="SOST/REWARD",
        side="sell",
        amount_sost=amount_sost,
        amount_gold=0,
        maker_sost_addr=SELLER,
        taker_sost_addr=BUYER,
        maker_eth_addr=SELLER_ETH,
        taker_eth_addr=BUYER_ETH,
    )
    deal.transition(DealState.NEGOTIATED, "reward offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting lock")
    deal.mark_eth_locked("0xeth_lock_reward", 99)
    deal.mark_sost_locked("sost_lock_reward_txid")
    assert deal.state == DealState.BOTH_LOCKED
    return deal


class TestRewardTradeSignedFlow:

    def test_reward_split_happy_path(self, tmp_path):
        """Create position, split rewards, verify child has reward."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position_with_rewards(registry)

        reward_before = position.reward_remaining()
        deal = _create_deal_both_locked(deal_store, reward_before // 2)

        settled = settlement.settle_reward_split(deal, position.position_id)
        assert settled is True

        buyer_positions = registry.by_owner(BUYER)
        assert len(buyer_positions) == 1

        child = buyer_positions[0]
        assert child.right_type == RightType.REWARD_RIGHT
        assert child.reward_total_sost == reward_before
        assert child.owner == BUYER

    def test_reward_split_parent_zeroed(self, tmp_path):
        """Parent reward_claimed = reward_total after split (remaining = 0)."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position_with_rewards(registry, reward_total=20_000_000)

        deal = _create_deal_both_locked(deal_store, 10_000_000)

        settlement.settle_reward_split(deal, position.position_id)

        parent = registry.get(position.position_id)
        assert parent.reward_remaining() == 0
        assert parent.reward_total_sost == parent.reward_claimed_sost

    def test_reward_split_audit(self, tmp_path):
        """Audit log has reward_split_settled entry."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position_with_rewards(registry)

        deal = _create_deal_both_locked(deal_store, 5_000_000)

        settlement.settle_reward_split(deal, position.position_id)

        history = audit.get_deal_history(deal.deal_id)
        event_names = [e.event for e in history]
        assert "reward_split_settled" in event_names

        split_entry = [e for e in history if e.event == "reward_split_settled"][0]
        assert position.position_id in split_entry.detail
        assert BUYER in split_entry.detail

    def test_reward_split_child_properties(self, tmp_path):
        """Child has right_type=REWARD_RIGHT, parent_position_id set, no principal."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position_with_rewards(registry)

        deal = _create_deal_both_locked(deal_store, 5_000_000)

        settlement.settle_reward_split(deal, position.position_id)

        buyer_positions = registry.by_owner(BUYER)
        child = buyer_positions[0]

        assert child.right_type == RightType.REWARD_RIGHT
        assert child.parent_position_id == position.position_id
        assert child.reference_amount == 0  # no principal in reward-only
        assert child.bond_amount_sost == 0
        assert child.transferable is True
        assert child.token_symbol == position.token_symbol
        assert child.contract_type == position.contract_type

    def test_reward_split_deal_settled(self, tmp_path):
        """Deal reaches SETTLED state after reward split."""
        registry, audit, _, settlement, deal_store = _create_components(tmp_path)
        position = _create_position_with_rewards(registry)

        deal = _create_deal_both_locked(deal_store, 5_000_000)

        settlement.settle_reward_split(deal, position.position_id)

        assert deal.state == DealState.SETTLED
        assert deal.settlement_tx_hash is not None
        assert "reward_split" in deal.settlement_tx_hash
        assert deal.is_terminal() is True
