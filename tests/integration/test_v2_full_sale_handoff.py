"""
Integration tests for V2 full-sale beneficiary handoff.

Validates the complete flow: position trade -> ownership update ->
beneficiary sync -> lifecycle progression through WITHDRAWN -> REWARD_SETTLED.
"""

import time
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, LifecycleStatus,
)
from src.positions.position_transfer import PositionTransferEngine
from src.operator.audit_log import AuditLog
from src.services.beneficiary_sync import BeneficiarySync
from src.services.auto_withdraw_daemon import AutoWithdrawDaemon
from src.services.reward_settlement_daemon import RewardSettlementDaemon

SELLER_SOST = "sost1seller_test"
BUYER_SOST = "sost1buyer_test"
SELLER_ETH = "0xSellerEthAddress"
BUYER_ETH = "0xBuyerEthAddress"

ETH_CONFIG = {
    "escrow_address": "0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113",
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
}


def _create_seller_position(registry):
    """Create a Model B position owned by seller."""
    pos = registry.create_model_b(
        owner=SELLER_SOST,
        token="XAUT",
        amount=100_000,          # 0.1 oz in 6-decimal
        bond_sost=500_000_000,   # 5 SOST
        duration_seconds=28 * 86400,
        reward_total=100_000_000,
        eth_deposit_id=42,
        eth_tx="0xdeposit_abc",
    )
    pos.eth_beneficiary = SELLER_ETH
    return pos


class TestFullSaleUpdatesAllOwners:
    """After a full sale, all ownership fields point to buyer."""

    def test_full_sale_updates_all_owners(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_seller_position(reg)

        result = engine.transfer(pos.position_id, BUYER_SOST,
                                 deal_id="deal_001", eth_beneficiary=BUYER_ETH)

        assert result.success is True
        assert pos.owner == BUYER_SOST
        assert pos.principal_owner == BUYER_SOST
        assert pos.reward_owner == BUYER_SOST
        assert pos.eth_beneficiary == BUYER_ETH


class TestFullSaleUpdatesEthBeneficiary:
    """The ETH beneficiary address updates to buyer's ETH address."""

    def test_full_sale_updates_eth_beneficiary(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_seller_position(reg)

        engine.transfer(pos.position_id, BUYER_SOST,
                        deal_id="deal_002", eth_beneficiary=BUYER_ETH)

        assert pos.eth_beneficiary == BUYER_ETH
        assert pos.eth_beneficiary != SELLER_ETH


class TestBeneficiarySyncGeneratesCorrectCommand:
    """After transfer, beneficiary_sync generates correct cast command."""

    def test_beneficiary_sync_generates_correct_command(self, tmp_path):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(reg, ETH_CONFIG, audit)
        pos = _create_seller_position(reg)

        engine.transfer(pos.position_id, BUYER_SOST,
                        deal_id="deal_003", eth_beneficiary=BUYER_ETH)

        tx = sync.sync_beneficiary(pos.position_id)
        assert tx is not None
        assert tx.startswith("0x")

        # Verify event recorded
        synced = [h for h in pos.history if h["event"] == "beneficiary_synced"]
        assert len(synced) == 1
        assert BUYER_ETH in synced[0]["detail"]
        assert "42" in synced[0]["detail"]  # deposit_id


class TestFullSaleLifecycleComplete:
    """Full lifecycle: ACTIVE -> MATURED -> WITHDRAWN -> REWARD_SETTLED."""

    def test_full_sale_lifecycle_complete(self, tmp_path):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(reg, ETH_CONFIG, audit)
        withdraw_daemon = AutoWithdrawDaemon(reg, ETH_CONFIG, audit)
        reward_daemon = RewardSettlementDaemon(reg, audit)

        pos = _create_seller_position(reg)

        # 1. Transfer to buyer
        engine.transfer(pos.position_id, BUYER_SOST,
                        deal_id="deal_004", eth_beneficiary=BUYER_ETH)
        assert pos.owner == BUYER_SOST

        # 2. Sync beneficiary
        sync.sync_beneficiary(pos.position_id)

        # 3. Mature the position
        pos.lifecycle_status = LifecycleStatus.MATURED.value
        pos.status = PositionStatus.MATURED

        # 4. Auto-withdraw
        tx = withdraw_daemon.execute_withdraw(pos.position_id)
        assert tx is not None
        assert pos.lifecycle_status == LifecycleStatus.WITHDRAWN.value

        # 5. Settle reward
        result = reward_daemon.settle_reward(pos.position_id)
        assert result is True
        assert pos.lifecycle_status == LifecycleStatus.REWARD_SETTLED.value
        assert pos.reward_settled is True

        # 6. Verify reward went to buyer
        reward_events = [h for h in pos.history
                         if h["event"] == "lifecycle_reward_settled"]
        assert len(reward_events) == 1
        assert BUYER_SOST in reward_events[0]["detail"]


class TestAuditLogRecordsHandoff:
    """Audit log records all handoff events."""

    def test_audit_log_records_handoff(self, tmp_path):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(reg, ETH_CONFIG, audit)
        pos = _create_seller_position(reg)

        engine.transfer(pos.position_id, BUYER_SOST,
                        deal_id="deal_005", eth_beneficiary=BUYER_ETH)
        sync.sync_beneficiary(pos.position_id)

        # Check audit entries (audit uses deal_id field, beneficiary_sync passes position_id)
        entries = audit.get_deal_history(pos.position_id)
        event_types = [e.event for e in entries]
        assert "beneficiary_synced" in event_types


class TestReconciliationAfterHandoff:
    """After handoff, position state is consistent."""

    def test_reconciliation_after_handoff(self, tmp_path):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(reg, ETH_CONFIG, audit)
        pos = _create_seller_position(reg)

        engine.transfer(pos.position_id, BUYER_SOST,
                        deal_id="deal_006", eth_beneficiary=BUYER_ETH)
        sync.sync_beneficiary(pos.position_id)

        # Reconciliation checks
        assert pos.owner == BUYER_SOST
        assert pos.principal_owner == BUYER_SOST
        assert pos.reward_owner == BUYER_SOST
        assert pos.eth_beneficiary == BUYER_ETH
        assert pos.eth_escrow_deposit_id == 42

        # Verify no pending syncs
        pending = sync.check_pending_syncs()
        assert pos.position_id not in pending
