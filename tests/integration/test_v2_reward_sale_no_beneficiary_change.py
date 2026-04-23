"""
Integration tests for V2 reward-only sale — no beneficiary change.

When only reward rights are sold, the principal owner and ETH beneficiary
must NOT change. Only reward_owner changes in the SOST registry.
No on-chain beneficiary sync is needed.
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
    Position, ContractType, BackingType, PositionStatus, RightType,
)
from src.positions.position_transfer import PositionTransferEngine
from src.operator.audit_log import AuditLog
from src.services.beneficiary_sync import BeneficiarySync

SELLER_SOST = "sost1seller_reward"
BUYER_SOST = "sost1buyer_reward"
SELLER_ETH = "0xSellerEthReward"

ETH_CONFIG = {
    "escrow_address": "0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113",
    "rpc_url": "https://ethereum-sepolia-rpc.publicnode.com",
}


def _create_position_with_rewards(registry):
    """Create a Model B position with rewards available."""
    pos = registry.create_model_b(
        owner=SELLER_SOST,
        token="XAUT",
        amount=100_000,
        bond_sost=500_000_000,
        duration_seconds=28 * 86400,
        reward_total=100_000_000,
        eth_deposit_id=99,
        eth_tx="0xreward_deposit",
    )
    pos.eth_beneficiary = SELLER_ETH
    return pos


class TestRewardSaleLeavesPrincipalOwner:
    """Reward sale does not change principal_owner."""

    def test_reward_sale_leaves_principal_owner(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_position_with_rewards(reg)

        result = engine.split_reward_right(pos.position_id, BUYER_SOST,
                                           deal_id="reward_deal_001")

        assert result.success is True
        # Parent position principal_owner unchanged
        assert pos.principal_owner == SELLER_SOST
        assert pos.owner == SELLER_SOST


class TestRewardSaleLeavesEthBeneficiary:
    """Reward sale does not change eth_beneficiary."""

    def test_reward_sale_leaves_eth_beneficiary(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_position_with_rewards(reg)

        engine.split_reward_right(pos.position_id, BUYER_SOST,
                                  deal_id="reward_deal_002")

        assert pos.eth_beneficiary == SELLER_ETH


class TestRewardSaleChangesRewardOwner:
    """Reward sale updates reward_owner to buyer."""

    def test_reward_sale_changes_reward_owner(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_position_with_rewards(reg)

        result = engine.split_reward_right(pos.position_id, BUYER_SOST,
                                           deal_id="reward_deal_003")

        assert result.success is True
        assert pos.reward_owner == BUYER_SOST

        # Child position should be owned by buyer
        child = reg.get(result.position_id)
        assert child is not None
        assert child.owner == BUYER_SOST
        assert child.reward_owner == BUYER_SOST
        assert child.right_type == RightType.REWARD_RIGHT


class TestRewardSaleNoBeneficiarySyncNeeded:
    """After reward sale, no pending beneficiary sync exists."""

    def test_reward_sale_no_beneficiary_sync_needed(self, tmp_path):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        audit = AuditLog(log_dir=str(tmp_path / "audit"))
        sync = BeneficiarySync(reg, ETH_CONFIG, audit)

        pos = _create_position_with_rewards(reg)

        # Mark as already synced (beneficiary was synced at deposit time)
        pos.record_event("beneficiary_synced",
                         f"deposit_id=99 beneficiary={SELLER_ETH}")

        engine.split_reward_right(pos.position_id, BUYER_SOST,
                                  deal_id="reward_deal_004")

        # eth_beneficiary hasn't changed, so no new sync needed
        pending = sync.check_pending_syncs()
        assert pos.position_id not in pending
