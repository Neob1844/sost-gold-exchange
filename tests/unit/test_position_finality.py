"""Tests for Position Finality Daemon — REWARD_SETTLED → CLOSED + bond release."""

import pytest
import time
from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import LifecycleStatus, PositionStatus
from src.services.position_finality_daemon import PositionFinalityDaemon
from src.operator.audit_log import AuditLog


@pytest.fixture
def registry():
    return PositionRegistry()


@pytest.fixture
def audit(tmp_path):
    return AuditLog(str(tmp_path / "audit"))


@pytest.fixture
def daemon(registry, audit):
    return PositionFinalityDaemon(registry, audit)


@pytest.fixture
def settled_position(registry):
    """Create a Model B position already in REWARD_SETTLED state."""
    pos = registry.create_model_b(
        owner="sost1owner",
        token="XAUT",
        amount=1_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=90 * 86400,
        reward_total=10_000_000,
        eth_deposit_id=42,
        eth_tx="0xabc123",
    )
    # Manually advance lifecycle to REWARD_SETTLED
    pos.lifecycle_status = LifecycleStatus.REWARD_SETTLED.value
    pos.reward_settled = True
    pos.reward_claimed_sost = pos.reward_total_sost
    pos.withdraw_tx = "0xwithdraw123"
    return pos


class TestPositionFinality:
    def test_check_closeable_finds_settled(self, daemon, settled_position):
        closeable = daemon.check_closeable()
        assert settled_position.position_id in closeable

    def test_check_closeable_ignores_active(self, daemon, registry):
        pos = registry.create_model_b(
            owner="sost1active", token="XAUT", amount=1_000, bond_sost=100,
            duration_seconds=86400, reward_total=1000, eth_deposit_id=99, eth_tx="0x1",
        )
        closeable = daemon.check_closeable()
        assert pos.position_id not in closeable

    def test_close_position_transitions_to_closed(self, daemon, settled_position):
        result = daemon.close_position(settled_position.position_id)
        assert result is True
        assert settled_position.lifecycle_status == LifecycleStatus.CLOSED.value
        assert settled_position.status == PositionStatus.REDEEMED.value

    def test_close_position_records_bond_release(self, daemon, settled_position):
        daemon.close_position(settled_position.position_id)
        events = [e for e in settled_position.history if e["event"] == "bond_released"]
        assert len(events) == 1
        assert "50000000" in events[0]["detail"]

    def test_close_position_idempotent(self, daemon, settled_position):
        first = daemon.close_position(settled_position.position_id)
        second = daemon.close_position(settled_position.position_id)
        assert first is True
        assert second is False  # idempotent guard

    def test_close_position_rejects_active(self, daemon, registry):
        pos = registry.create_model_b(
            owner="sost1x", token="XAUT", amount=1_000, bond_sost=100,
            duration_seconds=86400, reward_total=1000, eth_deposit_id=100, eth_tx="0x2",
        )
        result = daemon.close_position(pos.position_id)
        assert result is False

    def test_tick_closes_settled_positions(self, daemon, settled_position):
        closed = daemon.tick()
        assert settled_position.position_id in closed

    def test_tick_idempotent_second_call(self, daemon, settled_position):
        first = daemon.tick()
        second = daemon.tick()
        assert len(first) == 1
        assert len(second) == 0


class TestModelAFinality:
    def test_model_a_closes_correctly(self, registry, audit):
        daemon = PositionFinalityDaemon(registry, audit)
        pos = registry.create_model_a(
            owner="sost1modela", token="PAXG", amount=500_000,
            bond_sost=25_000, duration_seconds=180 * 86400,
            reward_total=5_000, proof_hash="abc123def456",
        )
        pos.lifecycle_status = LifecycleStatus.REWARD_SETTLED.value
        pos.reward_settled = True

        result = daemon.close_position(pos.position_id)
        assert result is True
        assert pos.lifecycle_status == LifecycleStatus.CLOSED.value

        # Verify bond release event
        events = [e for e in pos.history if e["event"] == "bond_released"]
        assert len(events) == 1
        assert "25000" in events[0]["detail"]
