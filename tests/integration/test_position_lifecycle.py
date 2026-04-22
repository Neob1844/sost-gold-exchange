"""
Tests for position lifecycle tracking.

Validates lifecycle stage detection, maturity transitions,
and stage changes over time.
"""

import time
import pytest
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import Position, PositionStatus, ContractType, BackingType


NEARING_EXPIRY_SECONDS = 7 * 86400


def lifecycle_stage(pos):
    """Mirror the lifecycle stage logic from the tracking script."""
    status = pos.status.value
    if status == "REDEEMED":
        return "REDEEMED"
    if status == "SLASHED":
        return "SLASHED"
    if status == "MATURED" or pos.is_matured():
        return "MATURE"
    remaining = pos.time_remaining()
    if remaining > 0 and remaining < NEARING_EXPIRY_SECONDS:
        return "NEARING_EXPIRY"
    return "ACTIVE"


def make_registry_with_position(start_offset=0, duration_days=28,
                                 reward_total=200000000):
    """Create a registry with a single Model B position.

    start_offset: seconds relative to now (negative = started in past)
    duration_days: position duration
    """
    registry = PositionRegistry()
    now = time.time()
    start = now + start_offset
    expiry = start + duration_days * 86400

    pos = Position(
        position_id="test_pos_001",
        owner="sost1testowner1234567890abcdef1234567890abcdef",
        contract_type=ContractType.MODEL_B_ESCROW,
        backing_type=BackingType.ETH_TOKENIZED_GOLD,
        token_symbol="XAUT",
        reference_amount=500000,
        bond_amount_sost=100000000,
        start_time=start,
        expiry_time=expiry,
        reward_schedule="linear_28d",
        reward_total_sost=reward_total,
        eth_escrow_deposit_id=1,
        eth_escrow_tx="0xabcdef1234567890",
    )
    registry._positions[pos.position_id] = pos
    return registry, pos


class TestLifecycleActivePosition:
    """Test that a freshly created position shows ACTIVE lifecycle stage."""

    def test_lifecycle_active_position(self):
        registry, pos = make_registry_with_position(start_offset=0, duration_days=28)

        assert pos.is_active()
        assert not pos.is_matured()
        assert pos.status == PositionStatus.ACTIVE
        assert pos.time_remaining() > 0
        assert pos.pct_complete() < 1.0

        stage = lifecycle_stage(pos)
        assert stage == "ACTIVE"

    def test_active_position_has_full_reward(self):
        registry, pos = make_registry_with_position(reward_total=200000000)
        assert pos.reward_remaining() == 200000000
        assert pos.reward_claimed_sost == 0

    def test_active_position_escrow_details(self):
        registry, pos = make_registry_with_position()
        assert pos.eth_escrow_deposit_id == 1
        assert pos.eth_escrow_tx == "0xabcdef1234567890"
        assert pos.contract_type == ContractType.MODEL_B_ESCROW


class TestLifecycleNearingExpiry:
    """Test NEARING_EXPIRY detection when <7 days remain."""

    def test_lifecycle_nearing_expiry(self):
        # Position started 24 days ago with 28-day duration => 4 days remaining
        registry, pos = make_registry_with_position(
            start_offset=-24 * 86400, duration_days=28
        )

        remaining = pos.time_remaining()
        assert 0 < remaining < NEARING_EXPIRY_SECONDS
        assert pos.is_active()
        assert not pos.is_matured()

        stage = lifecycle_stage(pos)
        assert stage == "NEARING_EXPIRY"

    def test_nearing_expiry_boundary(self):
        # Exactly at the 7-day boundary (just under)
        registry, pos = make_registry_with_position(
            start_offset=-(28 * 86400 - NEARING_EXPIRY_SECONDS + 60),
            duration_days=28
        )
        remaining = pos.time_remaining()
        assert remaining < NEARING_EXPIRY_SECONDS
        assert remaining > 0

        stage = lifecycle_stage(pos)
        assert stage == "NEARING_EXPIRY"


class TestLifecycleMatured:
    """Test MATURE detection when position is past expiry."""

    def test_lifecycle_matured(self):
        # Position started 30 days ago with 28-day duration => expired 2 days ago
        registry, pos = make_registry_with_position(
            start_offset=-30 * 86400, duration_days=28
        )

        assert pos.is_matured()
        assert pos.time_remaining() == 0.0
        assert pos.pct_complete() == 100.0

        stage = lifecycle_stage(pos)
        assert stage == "MATURE"

    def test_matured_status_after_check(self):
        # After check_maturities(), status should be MATURED
        registry, pos = make_registry_with_position(
            start_offset=-30 * 86400, duration_days=28
        )

        matured_ids = registry.check_maturities()
        assert pos.position_id in matured_ids
        assert pos.status == PositionStatus.MATURED

        stage = lifecycle_stage(pos)
        assert stage == "MATURE"


class TestCheckMaturitiesTransitions:
    """Test that check_maturities() correctly transitions positions."""

    def test_check_maturities_transitions(self):
        registry = PositionRegistry()
        now = time.time()

        # Position A: expired (should transition)
        pos_a = Position(
            position_id="pos_expired",
            owner="sost1owner_a",
            contract_type=ContractType.MODEL_B_ESCROW,
            backing_type=BackingType.ETH_TOKENIZED_GOLD,
            token_symbol="XAUT",
            reference_amount=500000,
            bond_amount_sost=100000000,
            start_time=now - 30 * 86400,
            expiry_time=now - 2 * 86400,
            reward_schedule="linear_28d",
            reward_total_sost=200000000,
        )
        registry._positions[pos_a.position_id] = pos_a

        # Position B: still active (should NOT transition)
        pos_b = Position(
            position_id="pos_active",
            owner="sost1owner_b",
            contract_type=ContractType.MODEL_B_ESCROW,
            backing_type=BackingType.ETH_TOKENIZED_GOLD,
            token_symbol="XAUT",
            reference_amount=500000,
            bond_amount_sost=100000000,
            start_time=now,
            expiry_time=now + 28 * 86400,
            reward_schedule="linear_28d",
            reward_total_sost=200000000,
        )
        registry._positions[pos_b.position_id] = pos_b

        # Position C: already matured (should NOT re-transition)
        pos_c = Position(
            position_id="pos_already_matured",
            owner="sost1owner_c",
            contract_type=ContractType.MODEL_B_ESCROW,
            backing_type=BackingType.ETH_TOKENIZED_GOLD,
            token_symbol="XAUT",
            reference_amount=500000,
            bond_amount_sost=100000000,
            start_time=now - 60 * 86400,
            expiry_time=now - 30 * 86400,
            reward_schedule="linear_28d",
            reward_total_sost=200000000,
            status=PositionStatus.MATURED,
        )
        registry._positions[pos_c.position_id] = pos_c

        matured_ids = registry.check_maturities()

        assert "pos_expired" in matured_ids
        assert "pos_active" not in matured_ids
        assert "pos_already_matured" not in matured_ids

        assert pos_a.status == PositionStatus.MATURED
        assert pos_b.status == PositionStatus.ACTIVE
        assert pos_c.status == PositionStatus.MATURED

    def test_check_maturities_records_event(self):
        registry, pos = make_registry_with_position(
            start_offset=-30 * 86400, duration_days=28
        )

        matured_ids = registry.check_maturities()
        assert pos.position_id in matured_ids

        matured_events = [h for h in pos.history if h["event"] == "matured"]
        assert len(matured_events) == 1


class TestLifecycleRedeemed:
    """Test REDEEMED lifecycle stage after redemption."""

    def test_lifecycle_redeemed(self):
        registry, pos = make_registry_with_position(
            start_offset=-30 * 86400, duration_days=28
        )

        # First mature it
        registry.check_maturities()
        assert pos.status == PositionStatus.MATURED

        # Then redeem it
        result = registry.redeem(pos.position_id)
        assert result is True
        assert pos.status == PositionStatus.REDEEMED

        stage = lifecycle_stage(pos)
        assert stage == "REDEEMED"

    def test_redeemed_records_event(self):
        registry, pos = make_registry_with_position(
            start_offset=-30 * 86400, duration_days=28
        )
        registry.check_maturities()
        registry.redeem(pos.position_id)

        redeemed_events = [h for h in pos.history if h["event"] == "redeemed"]
        assert len(redeemed_events) == 1

    def test_cannot_redeem_active(self):
        # redeem() on an active position should still work per registry logic
        # (it accepts ACTIVE or MATURED), but lifecycle shows REDEEMED
        registry, pos = make_registry_with_position(start_offset=0, duration_days=28)
        result = registry.redeem(pos.position_id)
        assert result is True
        assert pos.status == PositionStatus.REDEEMED
        assert lifecycle_stage(pos) == "REDEEMED"
