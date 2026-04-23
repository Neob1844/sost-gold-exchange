"""
Tests for MaturityWatcher — lifecycle transitions based on time.
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
from src.services.maturity_watcher import MaturityWatcher, NEARING_MATURITY_THRESHOLD


def make_position(registry, position_id, start_offset, duration_days,
                  lifecycle_status="ACTIVE"):
    """Create a test position with given timing."""
    now = time.time()
    pos = Position(
        position_id=position_id,
        owner="sost1testowner",
        contract_type=ContractType.MODEL_B_ESCROW,
        backing_type=BackingType.ETH_TOKENIZED_GOLD,
        token_symbol="XAUT",
        reference_amount=500000,
        bond_amount_sost=100000000,
        start_time=now + start_offset,
        expiry_time=now + start_offset + duration_days * 86400,
        reward_schedule="linear_28d",
        reward_total_sost=200000000,
        eth_escrow_deposit_id=1,
        eth_escrow_tx="0xtest",
        lifecycle_status=lifecycle_status,
    )
    registry._positions[pos.position_id] = pos
    return pos


class TestMaturityWatcherActiveToNearing:
    """Test ACTIVE -> NEARING_MATURITY transition."""

    def test_nearing_maturity_transition(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        watcher = MaturityWatcher(registry, audit)

        # Position with 3 days remaining (< 7 day threshold)
        pos = make_position(registry, "pos_nearing", -25 * 86400, 28)

        transitioned = watcher.check_all()
        assert "pos_nearing" in transitioned
        assert pos.lifecycle_status == LifecycleStatus.NEARING_MATURITY.value

    def test_active_position_not_transitioned(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        watcher = MaturityWatcher(registry, audit)

        # Position with 14 days remaining (> 7 day threshold)
        pos = make_position(registry, "pos_active", -14 * 86400, 28)

        transitioned = watcher.check_all()
        assert "pos_active" not in transitioned
        assert pos.lifecycle_status == LifecycleStatus.ACTIVE.value


class TestMaturityWatcherNearingToMatured:
    """Test NEARING_MATURITY -> MATURED transition."""

    def test_matured_transition(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        watcher = MaturityWatcher(registry, audit)

        # Position already past expiry, in NEARING_MATURITY state
        pos = make_position(registry, "pos_matured", -30 * 86400, 28,
                           lifecycle_status=LifecycleStatus.NEARING_MATURITY.value)

        transitioned = watcher.check_all()
        assert "pos_matured" in transitioned
        assert pos.lifecycle_status == LifecycleStatus.MATURED.value

    def test_active_jumps_to_matured(self, tmp_path):
        """Position that was ACTIVE but jumped past expiry goes straight to MATURED."""
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        watcher = MaturityWatcher(registry, audit)

        pos = make_position(registry, "pos_jumped", -30 * 86400, 28)

        transitioned = watcher.check_all()
        assert "pos_jumped" in transitioned
        assert pos.lifecycle_status == LifecycleStatus.MATURED.value


class TestMaturityWatcherTick:
    """Test the tick() method."""

    def test_tick_returns_transitioned(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        watcher = MaturityWatcher(registry, audit)

        make_position(registry, "pos_a", -30 * 86400, 28)
        make_position(registry, "pos_b", 0, 28)

        result = watcher.tick()
        assert "pos_a" in result
        assert "pos_b" not in result
        assert watcher._last_tick is not None

    def test_tick_audit_logged(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        watcher = MaturityWatcher(registry, audit)

        make_position(registry, "pos_audit", -30 * 86400, 28)
        watcher.tick()

        entries = audit.get_deal_history("pos_audit")
        assert len(entries) > 0
        assert any("matured" in e.event for e in entries)
