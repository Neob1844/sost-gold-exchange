"""
Adversarial: reward-right over-allocation.

After splitting reward rights from a position, the parent's
remaining rewards must be zero. Attempting a second split or
a reward claim on the zeroed parent must fail.
"""

import time

import pytest

from src.positions.position_registry import PositionRegistry
from src.positions.position_transfer import PositionTransferEngine
from src.positions.position_schema import RightType


OWNER = "sost1position_owner"
BUYER_A = "sost1buyer_a"
BUYER_B = "sost1buyer_b"
REWARD_TOTAL = 100_000_000_00  # 100 SOST


def _create_position(registry):
    return registry.create_model_b(
        owner=OWNER,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=250_000_000_00,
        duration_seconds=365 * 86400,
        reward_total=REWARD_TOTAL,
        eth_deposit_id=2001,
        eth_tx="0xdef456",
    )


class TestRewardRightOverallocation:
    def test_split_zeroes_parent_rewards(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_position(reg)
        assert pos.reward_remaining() == REWARD_TOTAL

        result = engine.split_reward_right(pos.position_id, BUYER_A)
        assert result.success is True

        # Parent rewards should now be zero
        assert pos.reward_remaining() == 0
        assert pos.reward_total_sost == pos.reward_claimed_sost

        # Child should hold the full reward allocation
        child = reg.get(result.position_id)
        assert child is not None
        assert child.reward_total_sost == REWARD_TOTAL
        assert child.right_type == RightType.REWARD_RIGHT

    def test_second_split_from_parent_fails(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_position(reg)

        first = engine.split_reward_right(pos.position_id, BUYER_A)
        assert first.success is True

        second = engine.split_reward_right(pos.position_id, BUYER_B)
        assert second.success is False
        assert "no rewards remaining" in second.message

    def test_claim_reward_on_parent_after_split_fails(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_position(reg)

        engine.split_reward_right(pos.position_id, BUYER_A)

        # Parent has zero rewards — claim must fail
        ok = reg.claim_reward(pos.position_id, 1)
        assert ok is False
