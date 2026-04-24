"""Tests for real SOST on-chain reward payout engine."""

import pytest
import time
from src.services.sost_reward_payout import (
    RewardPayoutEngine, PayoutMode, PayoutStatus,
    PROTOCOL_FEE_ADDRESS, MIN_CONFIRMATIONS,
)
from src.operator.audit_log import AuditLog


@pytest.fixture
def audit(tmp_path):
    return AuditLog(str(tmp_path / "audit"))


@pytest.fixture
def engine_dry(audit):
    return RewardPayoutEngine(audit, mode=PayoutMode.DRY_RUN)


class TestDryRunPayout:
    def test_create_payout(self, engine_dry):
        record = engine_dry.create_payout(
            position_id="pos-001", model="B", reward_owner="sost1user",
            gross_reward=10000, protocol_fee=800, fee_rate=0.08,
        )
        assert record.net_reward == 9200
        assert record.status == PayoutStatus.READY

    def test_execute_dry_run(self, engine_dry):
        engine_dry.create_payout("pos-002", "A", "sost1alice", 5000, 150, 0.03)
        result = engine_dry.execute_payout("pos-002")
        assert result.status == PayoutStatus.CONFIRMED
        assert result.reward_txid.startswith("dry-run")
        assert result.confirmed_at is not None

    def test_idempotent_create(self, engine_dry):
        r1 = engine_dry.create_payout("pos-003", "B", "sost1x", 1000, 80, 0.08)
        r2 = engine_dry.create_payout("pos-003", "B", "sost1x", 1000, 80, 0.08)
        assert r1.payout_id == r2.payout_id

    def test_idempotent_execute(self, engine_dry):
        engine_dry.create_payout("pos-004", "A", "sost1y", 2000, 60, 0.03)
        r1 = engine_dry.execute_payout("pos-004")
        r2 = engine_dry.execute_payout("pos-004")
        assert r1.status == PayoutStatus.CONFIRMED
        assert r2.status == PayoutStatus.CONFIRMED
        assert r1.reward_txid == r2.reward_txid

    def test_finalize(self, engine_dry):
        engine_dry.create_payout("pos-005", "B", "sost1z", 3000, 240, 0.08)
        engine_dry.execute_payout("pos-005")
        ok = engine_dry.finalize("pos-005")
        assert ok is True
        record = engine_dry.get_payout("pos-005")
        assert record.status == PayoutStatus.SETTLED

    def test_no_double_finalize(self, engine_dry):
        engine_dry.create_payout("pos-006", "A", "sost1w", 1000, 30, 0.03)
        engine_dry.execute_payout("pos-006")
        engine_dry.finalize("pos-006")
        ok = engine_dry.finalize("pos-006")
        assert ok is True  # already settled, returns True

    def test_protocol_fee_model_a(self, engine_dry):
        engine_dry.create_payout("pos-a1", "A", "sost1a", 10000, 300, 0.03)
        record = engine_dry.get_payout("pos-a1")
        assert record.protocol_fee == 300
        assert record.net_reward == 9700
        assert record.fee_rate == 0.03

    def test_protocol_fee_model_b(self, engine_dry):
        engine_dry.create_payout("pos-b1", "B", "sost1b", 10000, 800, 0.08)
        record = engine_dry.get_payout("pos-b1")
        assert record.protocol_fee == 800
        assert record.net_reward == 9200
        assert record.fee_rate == 0.08

    def test_stats(self, engine_dry):
        engine_dry.create_payout("pos-s1", "B", "sost1s", 1000, 80, 0.08)
        engine_dry.create_payout("pos-s2", "A", "sost1t", 2000, 60, 0.03)
        engine_dry.execute_payout("pos-s1")
        stats = engine_dry.get_stats()
        assert stats["total"] == 2
        assert stats["confirmed"] == 1
        assert stats["pending"] == 1

    def test_reconcile_empty(self, engine_dry):
        issues = engine_dry.reconcile()
        assert len(issues) == 0

    def test_execute_nonexistent_raises(self, engine_dry):
        with pytest.raises(ValueError):
            engine_dry.execute_payout("nonexistent")

    def test_finalize_before_confirm_fails(self, engine_dry):
        engine_dry.create_payout("pos-pre", "B", "sost1pre", 1000, 80, 0.08)
        ok = engine_dry.finalize("pos-pre")
        assert ok is False

    def test_full_flow_model_a(self, engine_dry):
        engine_dry.create_payout("pos-full-a", "A", "sost1full", 100000, 3000, 0.03)
        engine_dry.execute_payout("pos-full-a")
        engine_dry.finalize("pos-full-a")
        r = engine_dry.get_payout("pos-full-a")
        assert r.status == PayoutStatus.SETTLED
        assert r.net_reward == 97000
        assert r.protocol_fee == 3000

    def test_full_flow_model_b(self, engine_dry):
        engine_dry.create_payout("pos-full-b", "B", "sost1fullb", 100000, 8000, 0.08)
        engine_dry.execute_payout("pos-full-b")
        engine_dry.finalize("pos-full-b")
        r = engine_dry.get_payout("pos-full-b")
        assert r.status == PayoutStatus.SETTLED
        assert r.net_reward == 92000
        assert r.protocol_fee == 8000
