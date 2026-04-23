"""
Tests for RewardSettlementDaemon — automatic reward crediting at maturity.
"""

import time
import pytest
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, LifecycleStatus,
)
from src.operator.audit_log import AuditLog
from src.services.reward_settlement_daemon import RewardSettlementDaemon


def make_position(registry, position_id, lifecycle_status, reward_total=200000000,
                  reward_settled=False, reward_owner="", principal_owner=""):
    """Create a test position."""
    now = time.time()
    pos = Position(
        position_id=position_id,
        owner="sost1testowner",
        contract_type=ContractType.MODEL_B_ESCROW,
        backing_type=BackingType.ETH_TOKENIZED_GOLD,
        token_symbol="XAUT",
        reference_amount=500000,
        bond_amount_sost=100000000,
        start_time=now - 30 * 86400,
        expiry_time=now - 2 * 86400,
        reward_schedule="linear_28d",
        reward_total_sost=reward_total,
        lifecycle_status=lifecycle_status,
        reward_settled=reward_settled,
        reward_owner=reward_owner,
        principal_owner=principal_owner,
    )
    registry._positions[pos.position_id] = pos
    return pos


class TestCheckSettleable:
    """Test check_settleable filtering."""

    def test_matured_unsettled_returns(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = RewardSettlementDaemon(registry, audit)

        make_position(registry, "pos_matured", LifecycleStatus.MATURED.value)
        result = daemon.check_settleable()
        assert "pos_matured" in result

    def test_withdrawn_unsettled_returns(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = RewardSettlementDaemon(registry, audit)

        make_position(registry, "pos_withdrawn", LifecycleStatus.WITHDRAWN.value)
        result = daemon.check_settleable()
        assert "pos_withdrawn" in result

    def test_already_settled_excluded(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = RewardSettlementDaemon(registry, audit)

        make_position(registry, "pos_settled", LifecycleStatus.MATURED.value,
                     reward_settled=True)
        result = daemon.check_settleable()
        assert "pos_settled" not in result

    def test_active_excluded(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = RewardSettlementDaemon(registry, audit)

        make_position(registry, "pos_active", LifecycleStatus.ACTIVE.value)
        result = daemon.check_settleable()
        assert "pos_active" not in result


class TestSettleReward:
    """Test settle_reward logic."""

    def test_settle_credits_reward(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = RewardSettlementDaemon(registry, audit)

        pos = make_position(registry, "pos_settle", LifecycleStatus.WITHDRAWN.value,
                           reward_total=500000000)

        result = daemon.settle_reward("pos_settle")
        assert result is True
        assert pos.reward_settled is True
        assert pos.reward_claimed_sost == 500000000
        assert pos.lifecycle_status == LifecycleStatus.REWARD_SETTLED.value

    def test_settle_uses_reward_owner(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = RewardSettlementDaemon(registry, audit)

        pos = make_position(registry, "pos_split", LifecycleStatus.WITHDRAWN.value,
                           reward_owner="sost1reward_buyer")
        daemon.settle_reward("pos_split")

        # Check audit log mentions the reward_owner
        entries = audit.get_deal_history("pos_split")
        assert any("sost1reward_buyer" in e.detail for e in entries)

    def test_settle_already_settled_fails(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = RewardSettlementDaemon(registry, audit)

        make_position(registry, "pos_done", LifecycleStatus.REWARD_SETTLED.value,
                     reward_settled=True)
        result = daemon.settle_reward("pos_done")
        assert result is False


class TestRewardSettlementTick:
    """Test tick() method."""

    def test_tick_settles_all(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = RewardSettlementDaemon(registry, audit)

        make_position(registry, "pos_a", LifecycleStatus.WITHDRAWN.value)
        make_position(registry, "pos_b", LifecycleStatus.MATURED.value)
        make_position(registry, "pos_c", LifecycleStatus.ACTIVE.value)

        settled = daemon.tick()
        assert "pos_a" in settled
        assert "pos_b" in settled
        assert "pos_c" not in settled
