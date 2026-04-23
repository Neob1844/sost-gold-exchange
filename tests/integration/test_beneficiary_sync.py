"""
Tests for BeneficiarySync — ETH beneficiary synchronization after trades.
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
from src.services.beneficiary_sync import BeneficiarySync

ETH_CONFIG = {
    "escrow_address": "0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113",
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
}


def make_position(registry, position_id, eth_beneficiary="0xBuyer",
                  deposit_id=42, synced=False):
    """Create a test position with ETH beneficiary."""
    now = time.time()
    pos = Position(
        position_id=position_id,
        owner="sost1testowner",
        contract_type=ContractType.MODEL_B_ESCROW,
        backing_type=BackingType.ETH_TOKENIZED_GOLD,
        token_symbol="XAUT",
        reference_amount=500000,
        bond_amount_sost=100000000,
        start_time=now,
        expiry_time=now + 28 * 86400,
        reward_schedule="linear_28d",
        reward_total_sost=200000000,
        eth_escrow_deposit_id=deposit_id,
        eth_escrow_tx="0xtest",
        eth_beneficiary=eth_beneficiary,
        principal_owner="sost1buyer",
    )
    if synced:
        pos.record_event("beneficiary_synced",
                        f"deposit_id={deposit_id} beneficiary={eth_beneficiary}")
    registry._positions[pos.position_id] = pos
    return pos


class TestSyncBeneficiary:
    """Test sync_beneficiary execution."""

    def test_sync_returns_tx(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(registry, ETH_CONFIG, audit)

        make_position(registry, "pos_sync", eth_beneficiary="0xNewBuyer")
        tx = sync.sync_beneficiary("pos_sync")

        assert tx is not None
        assert tx.startswith("0x")

    def test_sync_records_event(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(registry, ETH_CONFIG, audit)

        pos = make_position(registry, "pos_event", eth_beneficiary="0xBob")
        sync.sync_beneficiary("pos_event")

        synced_events = [h for h in pos.history if h["event"] == "beneficiary_synced"]
        assert len(synced_events) == 1
        assert "0xBob" in synced_events[0]["detail"]

    def test_sync_no_deposit_returns_none(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(registry, ETH_CONFIG, audit)

        now = time.time()
        pos = Position(
            position_id="pos_no_deposit",
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
            eth_beneficiary="0xSomeone",
        )
        registry._positions["pos_no_deposit"] = pos

        tx = sync.sync_beneficiary("pos_no_deposit")
        assert tx is None

    def test_sync_no_beneficiary_returns_none(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(registry, ETH_CONFIG, audit)

        make_position(registry, "pos_no_ben", eth_beneficiary="", deposit_id=10)
        tx = sync.sync_beneficiary("pos_no_ben")
        assert tx is None


class TestCheckPendingSyncs:
    """Test check_pending_syncs detection."""

    def test_unsynced_detected(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(registry, ETH_CONFIG, audit)

        make_position(registry, "pos_pending", eth_beneficiary="0xNew", synced=False)
        pending = sync.check_pending_syncs()
        assert "pos_pending" in pending

    def test_synced_not_detected(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(registry, ETH_CONFIG, audit)

        make_position(registry, "pos_done", eth_beneficiary="0xBuyer", synced=True)
        pending = sync.check_pending_syncs()
        assert "pos_done" not in pending

    def test_no_deposit_excluded(self, tmp_path):
        registry = PositionRegistry()
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(registry, ETH_CONFIG, audit)

        now = time.time()
        pos = Position(
            position_id="pos_model_a",
            owner="sost1test",
            contract_type=ContractType.MODEL_A_CUSTODY,
            backing_type=BackingType.AUTOCUSTODY_GOLD,
            token_symbol="PHYSICAL",
            reference_amount=500000,
            bond_amount_sost=100000000,
            start_time=now,
            expiry_time=now + 28 * 86400,
            reward_schedule="linear_28d",
            reward_total_sost=200000000,
            eth_beneficiary="0xSomeone",
        )
        registry._positions["pos_model_a"] = pos

        pending = sync.check_pending_syncs()
        assert "pos_model_a" not in pending
