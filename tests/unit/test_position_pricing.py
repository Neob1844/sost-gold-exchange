"""Unit tests for the SOST Gold Exchange Position Pricing."""

import time
import pytest

from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, RightType,
)
from src.positions.position_pricing import (
    value_position, PositionValuation,
    DISCOUNT_RATE_MODEL_A, DISCOUNT_RATE_MODEL_B, ILLIQUIDITY_DISCOUNT,
)


def _make_position(contract_type=ContractType.MODEL_B_ESCROW,
                   backing_type=BackingType.ETH_TOKENIZED_GOLD,
                   right_type=RightType.FULL_POSITION,
                   amount=1_000_000, reward_total=100_000, reward_claimed=0,
                   duration_seconds=365 * 86400, expired=False):
    now = time.time()
    start = now - (duration_seconds if expired else 0)
    expiry = start + duration_seconds
    return Position(
        position_id="test_pos_id_0001",
        owner="sost1test",
        contract_type=contract_type,
        backing_type=backing_type,
        token_symbol="XAUT",
        reference_amount=amount,
        bond_amount_sost=50_000,
        start_time=start,
        expiry_time=expiry,
        reward_schedule="linear_365d",
        reward_total_sost=reward_total,
        reward_claimed_sost=reward_claimed,
        transferable=True,
        right_type=right_type,
    )


class TestConstants:
    def test_discount_rate_model_b(self):
        assert DISCOUNT_RATE_MODEL_B == 0.05

    def test_discount_rate_model_a(self):
        assert DISCOUNT_RATE_MODEL_A == 0.12

    def test_illiquidity_discount(self):
        assert ILLIQUIDITY_DISCOUNT == 0.03


class TestValueModelB:
    def test_value_model_b_basic(self):
        pos = _make_position(contract_type=ContractType.MODEL_B_ESCROW)
        val = value_position(pos, gold_price_sost_per_unit=2.0)
        assert val.gold_value_sost == int(1_000_000 * 2.0)
        assert val.reward_value_sost > 0
        assert val.discount_sost > 0
        assert val.net_value_sost > 0
        assert val.net_value_sost < val.gold_value_sost + val.reward_value_sost


class TestValueModelA:
    def test_value_model_a_basic(self):
        pos = _make_position(
            contract_type=ContractType.MODEL_A_CUSTODY,
            backing_type=BackingType.AUTOCUSTODY_GOLD,
        )
        val = value_position(pos, gold_price_sost_per_unit=2.0)
        assert val.gold_value_sost == int(1_000_000 * 2.0)
        assert val.net_value_sost > 0


class TestRewardRight:
    def test_reward_right_no_gold_value(self):
        pos = _make_position(right_type=RightType.REWARD_RIGHT, amount=1_000_000)
        val = value_position(pos, gold_price_sost_per_unit=2.0)
        assert val.gold_value_sost == 0
        assert val.reward_value_sost > 0


class TestExpiredPosition:
    def test_expired_position_no_reward_value(self):
        """Expired position: time_remaining()=0 so discount_factor=1, but
        reward_remaining might be 0 if fully claimed. Here we test with
        unclaimed rewards but expired — discount_factor approaches 1."""
        pos = _make_position(expired=True)
        val = value_position(pos, gold_price_sost_per_unit=2.0)
        # Time remaining is ~0, so discount factor ~1/(1+0)=1
        # reward_value should equal remaining reward
        assert val.reward_value_sost == pos.reward_remaining()


class TestZeroPrice:
    def test_zero_price(self):
        pos = _make_position()
        val = value_position(pos, gold_price_sost_per_unit=0.0)
        assert val.gold_value_sost == 0
        # net can still be > 0 from reward value
        assert val.net_value_sost >= 0
