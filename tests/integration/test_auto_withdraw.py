"""
Tests for AutoWithdrawDaemon — automatic ETH escrow withdrawal at maturity.
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
from src.services.auto_withdraw_daemon import AutoWithdrawDaemon

ETH_CONFIG = {
    "escrow_address": "0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113",
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
}


def make_matured_position(registry, position_id, deposit_id=42,
                          auto_withdraw=True, withdraw_tx=None):
    """Create a matured position ready for withdrawal."""
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
        reward_total_sost=200000000,
        eth_escrow_deposit_id=deposit_id,
        eth_escrow_tx="0xtest",
        lifecycle_status=LifecycleStatus.MATURED.value,
        auto_withdraw=auto_withdraw,
        withdraw_tx=withdraw_tx,
    )
    registry._positions[pos.position_id] = pos
    return pos


class TestCheckWithdrawable:
    """Test check_withdrawable filtering."""

    def test_matured_auto_withdraw_returns(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = AutoWithdrawDaemon(registry, ETH_CONFIG, audit)

        make_matured_position(registry, "pos_ready")
        result = daemon.check_withdrawable()
        assert "pos_ready" in result

    def test_auto_withdraw_false_excluded(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = AutoWithdrawDaemon(registry, ETH_CONFIG, audit)

        make_matured_position(registry, "pos_manual", auto_withdraw=False)
        result = daemon.check_withdrawable()
        assert "pos_manual" not in result

    def test_already_withdrawn_excluded(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = AutoWithdrawDaemon(registry, ETH_CONFIG, audit)

        make_matured_position(registry, "pos_done", withdraw_tx="0xalready")
        result = daemon.check_withdrawable()
        assert "pos_done" not in result


class TestExecuteWithdraw:
    """Test execute_withdraw logic."""

    def test_successful_withdraw(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = AutoWithdrawDaemon(registry, ETH_CONFIG, audit)

        pos = make_matured_position(registry, "pos_withdraw")
        tx = daemon.execute_withdraw("pos_withdraw")

        assert tx is not None
        assert tx.startswith("0x")
        assert pos.withdraw_tx == tx
        assert pos.lifecycle_status == LifecycleStatus.WITHDRAWN.value

    def test_withdraw_wrong_status_fails(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = AutoWithdrawDaemon(registry, ETH_CONFIG, audit)

        now = time.time()
        pos = Position(
            position_id="pos_active",
            owner="sost1test",
            contract_type=ContractType.MODEL_B_ESCROW,
            backing_type=BackingType.ETH_TOKENIZED_GOLD,
            token_symbol="XAUT",
            reference_amount=500000,
            bond_amount_sost=100000000,
            start_time=now,
            expiry_time=now + 28 * 86400,
            reward_schedule="linear_28d",
            reward_total_sost=200000000,
            lifecycle_status=LifecycleStatus.ACTIVE.value,
        )
        registry._positions["pos_active"] = pos

        tx = daemon.execute_withdraw("pos_active")
        assert tx is None


class TestAutoWithdrawTick:
    """Test tick() method."""

    def test_tick_processes_all_withdrawable(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        daemon = AutoWithdrawDaemon(registry, ETH_CONFIG, audit)

        make_matured_position(registry, "pos_a", deposit_id=1)
        make_matured_position(registry, "pos_b", deposit_id=2)
        make_matured_position(registry, "pos_c", deposit_id=3, auto_withdraw=False)

        results = daemon.tick()
        assert len(results) == 2
        withdrawn_ids = [r[0] for r in results]
        assert "pos_a" in withdrawn_ids
        assert "pos_b" in withdrawn_ids
        assert "pos_c" not in withdrawn_ids
