"""Unit tests for the SOST Gold Exchange Position Transfer Engine."""

import time
import pytest

from src.positions.position_schema import (
    Position, ContractType, PositionStatus, RightType,
)
from src.positions.position_registry import PositionRegistry
from src.positions.position_transfer import PositionTransferEngine, TransferResult


OWNER_A = "sost1ownerAAAAAAAAAAAAAAAAAAAAAAAA"
OWNER_B = "sost1ownerBBBBBBBBBBBBBBBBBBBBBBBB"
BUYER   = "sost1buyerCCCCCCCCCCCCCCCCCCCCCCCC"


class TestCanTransfer:
    def test_can_transfer_model_b(self, transfer_engine, model_b_position):
        ok, reason = transfer_engine.can_transfer(model_b_position, BUYER)
        assert ok is True
        assert reason == "ok"

    def test_cannot_transfer_model_a_full(self, transfer_engine, model_a_position):
        ok, reason = transfer_engine.can_transfer(model_a_position, BUYER)
        assert ok is False
        assert "model_a" in reason.lower()

    def test_cannot_transfer_slashed(self, registry, transfer_engine, model_b_position):
        registry.slash(model_b_position.position_id, "bad")
        ok, reason = transfer_engine.can_transfer(model_b_position, BUYER)
        assert ok is False
        assert "not active" in reason

    def test_cannot_transfer_redeemed(self, registry, transfer_engine, model_b_position):
        registry.redeem(model_b_position.position_id)
        ok, reason = transfer_engine.can_transfer(model_b_position, BUYER)
        assert ok is False
        assert "not active" in reason

    def test_cannot_transfer_to_same_owner(self, transfer_engine, model_b_position):
        ok, reason = transfer_engine.can_transfer(model_b_position, model_b_position.owner)
        assert ok is False
        assert "same owner" in reason


class TestTransfer:
    def test_transfer_changes_owner(self, transfer_engine, model_b_position):
        old_owner = model_b_position.owner
        result = transfer_engine.transfer(model_b_position.position_id, BUYER)
        assert result.success is True
        assert model_b_position.owner == BUYER

    def test_transfer_records_event(self, transfer_engine, model_b_position):
        history_before = len(model_b_position.history)
        transfer_engine.transfer(model_b_position.position_id, BUYER)
        assert len(model_b_position.history) > history_before
        last = model_b_position.history[-1]
        assert last["event"] == "transferred"

    def test_transfer_with_deal_id(self, transfer_engine, model_b_position):
        result = transfer_engine.transfer(model_b_position.position_id, BUYER, deal_id="deal_abc")
        assert result.success is True
        last = model_b_position.history[-1]
        assert "deal_abc" in last["detail"]

    def test_transfer_not_found(self, transfer_engine):
        result = transfer_engine.transfer("nonexistent", BUYER)
        assert result.success is False
        assert "not found" in result.message


class TestSplitRewardRight:
    def test_split_reward_right(self, transfer_engine, model_b_position):
        remaining_before = model_b_position.reward_remaining()
        result = transfer_engine.split_reward_right(model_b_position.position_id, BUYER)
        assert result.success is True
        assert result.message == "reward_right_created"
        # Child exists in registry
        child = transfer_engine.registry.get(result.position_id)
        assert child is not None
        assert child.owner == BUYER
        assert child.right_type == RightType.REWARD_RIGHT
        assert child.reward_total_sost == remaining_before
        assert child.reference_amount == 0

    def test_split_zeros_parent_reward(self, transfer_engine, model_b_position):
        transfer_engine.split_reward_right(model_b_position.position_id, BUYER)
        assert model_b_position.reward_remaining() == 0

    def test_split_not_active(self, registry, transfer_engine, model_b_position):
        registry.slash(model_b_position.position_id, "bad")
        result = transfer_engine.split_reward_right(model_b_position.position_id, BUYER)
        assert result.success is False

    def test_split_no_rewards_remaining(self, registry, transfer_engine, model_b_position):
        # Claim all rewards
        registry.claim_reward(model_b_position.position_id, model_b_position.reward_total_sost)
        result = transfer_engine.split_reward_right(model_b_position.position_id, BUYER)
        assert result.success is False
        assert "no rewards" in result.message
