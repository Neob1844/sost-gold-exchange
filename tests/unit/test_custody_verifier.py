"""Tests for Custody Verifier — Model A balance verification and slashing."""

import pytest
import time
from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import (
    LifecycleStatus, PositionStatus, ContractType,
)
from src.services.custody_verifier import CustodyVerifier, GRACE_PERIOD_SECONDS
from src.operator.audit_log import AuditLog


@pytest.fixture
def registry():
    return PositionRegistry()


@pytest.fixture
def audit(tmp_path):
    return AuditLog(str(tmp_path / "audit"))


@pytest.fixture
def verifier(registry, audit):
    return CustodyVerifier(registry, audit, alpha_mode=True)


@pytest.fixture
def model_a_position(registry):
    return registry.create_model_a(
        owner="sost1modela",
        token="XAUT",
        amount=1_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=180 * 86400,
        reward_total=5_000_000,
        proof_hash="abcdef0123456789",
    )


class TestCustodyVerifierAlpha:
    def test_get_model_a_positions(self, verifier, model_a_position):
        positions = verifier.get_model_a_positions()
        assert model_a_position.position_id in positions

    def test_get_model_a_excludes_model_b(self, verifier, registry):
        pos_b = registry.create_model_b(
            owner="sost1b", token="XAUT", amount=1_000, bond_sost=100,
            duration_seconds=86400, reward_total=1000, eth_deposit_id=99, eth_tx="0x1",
        )
        positions = verifier.get_model_a_positions()
        assert pos_b.position_id not in positions

    def test_alpha_mode_always_passes(self, verifier, model_a_position):
        result = verifier.verify_position(model_a_position.position_id, epoch=1)
        assert result.passed is True
        assert result.reason == "alpha_mode_simulated_pass"
        assert result.epoch == 1

    def test_verify_all(self, verifier, model_a_position):
        results = verifier.verify_all(epoch=2)
        assert len(results) == 1
        assert results[0].passed is True

    def test_verify_records_audit(self, verifier, model_a_position, audit):
        verifier.verify_position(model_a_position.position_id, epoch=3)
        # Audit should have a log entry
        results = verifier.get_results(model_a_position.position_id)
        assert len(results) == 1
        assert results[0].epoch == 3

    def test_stats(self, verifier, model_a_position):
        verifier.verify_all(epoch=1)
        stats = verifier.get_stats()
        assert stats["total_checks"] == 1
        assert stats["passed"] == 1
        assert stats["failed"] == 0

    def test_no_slash_in_alpha(self, verifier, model_a_position):
        verifier.verify_all(epoch=1)
        eligible = verifier.check_slash_eligible()
        assert len(eligible) == 0

    def test_excludes_matured_positions(self, verifier, model_a_position):
        model_a_position.lifecycle_status = LifecycleStatus.MATURED.value
        positions = verifier.get_model_a_positions()
        assert model_a_position.position_id not in positions

    def test_excludes_slashed_positions(self, verifier, registry, model_a_position):
        registry.slash(model_a_position.position_id, "test")
        positions = verifier.get_model_a_positions()
        assert model_a_position.position_id not in positions


class TestCustodyVerifierLive:
    def test_live_mode_fails_without_rpc(self, registry, audit, model_a_position):
        """Live mode without RPC URL should fail verification gracefully."""
        verifier = CustodyVerifier(registry, audit, alpha_mode=False, eth_rpc_url="")
        # Need eth_beneficiary for live check
        model_a_position.eth_beneficiary = "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"
        result = verifier.verify_position(model_a_position.position_id, epoch=1)
        assert result.passed is False
        assert "rpc_query_failed" in result.reason or "No ETH" in result.reason

    def test_slash_after_grace_period(self, registry, audit, model_a_position):
        """Simulate a position failing past grace period."""
        verifier = CustodyVerifier(registry, audit, alpha_mode=False)
        # Manually mark as failed
        verifier._failed_positions[model_a_position.position_id] = (
            time.time() - GRACE_PERIOD_SECONDS - 1
        )
        eligible = verifier.check_slash_eligible()
        assert model_a_position.position_id in eligible

        slashed = verifier.execute_slashes()
        assert model_a_position.position_id in slashed
        st = model_a_position.status.value if hasattr(model_a_position.status, 'value') else model_a_position.status
        assert st == PositionStatus.SLASHED.value

    def test_no_slash_within_grace_period(self, registry, audit, model_a_position):
        """Position failing within grace period should NOT be slashed."""
        verifier = CustodyVerifier(registry, audit, alpha_mode=False)
        verifier._failed_positions[model_a_position.position_id] = time.time()
        eligible = verifier.check_slash_eligible()
        assert model_a_position.position_id not in eligible

    def test_slash_idempotent(self, registry, audit, model_a_position):
        """Slashing same position twice should not double-slash."""
        verifier = CustodyVerifier(registry, audit, alpha_mode=False)
        verifier._failed_positions[model_a_position.position_id] = (
            time.time() - GRACE_PERIOD_SECONDS - 1
        )
        first = verifier.execute_slashes()
        second = verifier.execute_slashes()
        assert len(first) == 1
        assert len(second) == 0  # already slashed, removed from tracking
