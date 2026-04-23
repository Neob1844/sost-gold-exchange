"""Unit tests for position ownership fields (principal_owner, reward_owner, eth_beneficiary)."""

import time
import pytest

from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, RightType,
)
from src.positions.position_registry import PositionRegistry
from src.positions.position_transfer import PositionTransferEngine


SELLER = "sost1seller00000000000000000000000"
BUYER = "sost1buyer000000000000000000000000"
BUYER_ETH = "0xBuyerEthAddress0000000000000000000000000"


@pytest.fixture
def registry():
    return PositionRegistry()


@pytest.fixture
def model_b(registry):
    return registry.create_model_b(
        owner=SELLER,
        token="XAUT",
        amount=1_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=365 * 86400,
        reward_total=10_000_000,
        eth_deposit_id=1,
        eth_tx="0xaaa",
    )


@pytest.fixture
def engine(registry):
    return PositionTransferEngine(registry)


class TestFullTradeUpdatesAllOwners:
    def test_full_trade_updates_all_owners(self, engine, model_b):
        assert model_b.principal_owner == SELLER
        assert model_b.reward_owner == SELLER

        result = engine.transfer(model_b.position_id, BUYER, eth_beneficiary=BUYER_ETH)
        assert result.success

        assert model_b.owner == BUYER
        assert model_b.principal_owner == BUYER
        assert model_b.reward_owner == BUYER


class TestRewardTradeOnlyChangesRewardOwner:
    def test_reward_trade_only_changes_reward_owner(self, engine, model_b):
        result = engine.split_reward_right(model_b.position_id, BUYER)
        assert result.success

        # Parent keeps principal_owner, reward_owner changes to buyer
        assert model_b.owner == SELLER
        assert model_b.principal_owner == SELLER
        assert model_b.reward_owner == BUYER


class TestFullTradeUpdatesEthBeneficiary:
    def test_full_trade_updates_eth_beneficiary(self, engine, model_b):
        result = engine.transfer(model_b.position_id, BUYER, eth_beneficiary=BUYER_ETH)
        assert result.success
        assert model_b.eth_beneficiary == BUYER_ETH


class TestRewardTradeLeavesBeneficiaryUnchanged:
    def test_reward_trade_leaves_beneficiary_unchanged(self, engine, model_b):
        model_b.eth_beneficiary = "0xOriginalBeneficiary"
        engine.split_reward_right(model_b.position_id, BUYER)
        assert model_b.eth_beneficiary == "0xOriginalBeneficiary"


class TestPrincipalOwnerDefaultsToOwner:
    def test_principal_owner_defaults_to_owner(self, model_b):
        assert model_b.principal_owner == model_b.owner


class TestRewardOwnerDefaultsToOwner:
    def test_reward_owner_defaults_to_owner(self, model_b):
        assert model_b.reward_owner == model_b.owner


class TestSyncOwnersMigration:
    def test_sync_owners_migration(self):
        """sync_owners() fills empty principal_owner and reward_owner from owner."""
        now = time.time()
        pos = Position(
            position_id="test123",
            owner="sost1owner",
            contract_type=ContractType.MODEL_B_ESCROW,
            backing_type=BackingType.ETH_TOKENIZED_GOLD,
            token_symbol="XAUT",
            reference_amount=1000,
            bond_amount_sost=100,
            start_time=now,
            expiry_time=now + 86400,
            reward_schedule="linear_1d",
            reward_total_sost=10,
        )
        # __post_init__ already sets them, so clear and re-sync
        pos.principal_owner = ""
        pos.reward_owner = ""
        pos.sync_owners()
        assert pos.principal_owner == "sost1owner"
        assert pos.reward_owner == "sost1owner"


class TestLifecycleStatusTransitions:
    def test_lifecycle_status_transitions(self, model_b):
        assert model_b.lifecycle_status == "ACTIVE"

        model_b.lifecycle_status = "NEARING_MATURITY"
        assert model_b.lifecycle_status == "NEARING_MATURITY"

        model_b.lifecycle_status = "MATURED"
        assert model_b.lifecycle_status == "MATURED"

        model_b.lifecycle_status = "WITHDRAW_PENDING"
        assert model_b.lifecycle_status == "WITHDRAW_PENDING"

        model_b.lifecycle_status = "WITHDRAWN"
        assert model_b.lifecycle_status == "WITHDRAWN"

        model_b.lifecycle_status = "CLOSED"
        assert model_b.lifecycle_status == "CLOSED"


class TestWithdrawTxRecorded:
    def test_withdraw_tx_recorded(self, model_b):
        assert model_b.withdraw_tx is None
        model_b.withdraw_tx = "0xwithdrawtx123"
        assert model_b.withdraw_tx == "0xwithdrawtx123"


class TestRewardSettledFlag:
    def test_reward_settled_flag(self, model_b):
        assert model_b.reward_settled is False
        model_b.reward_settled = True
        assert model_b.reward_settled is True
