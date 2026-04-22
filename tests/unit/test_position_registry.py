"""Unit tests for the SOST Gold Exchange Position Registry."""

import time
import pytest

from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, RightType,
)
from src.positions.position_registry import PositionRegistry


OWNER_A = "sost1ownerAAAAAAAAAAAAAAAAAAAAAAAA"
OWNER_B = "sost1ownerBBBBBBBBBBBBBBBBBBBBBBBB"


# ---------------------------------------------------------------------------
# Model B creation
# ---------------------------------------------------------------------------

class TestCreateModelB:
    def test_create_model_b(self, registry):
        pos = registry.create_model_b(
            owner=OWNER_A, token="XAUT", amount=1_000_000,
            bond_sost=50_000, duration_seconds=365 * 86400,
            reward_total=10_000, eth_deposit_id=1, eth_tx="0xaaa",
        )
        assert pos.contract_type == ContractType.MODEL_B_ESCROW
        assert pos.backing_type == BackingType.ETH_TOKENIZED_GOLD
        assert pos.owner == OWNER_A
        assert pos.token_symbol == "XAUT"
        assert pos.bond_amount_sost == 50_000
        assert pos.transferable is True
        assert pos.status == PositionStatus.ACTIVE
        assert pos.eth_escrow_deposit_id == 1

    def test_model_b_properties(self, model_b_position):
        assert model_b_position.transferable is True
        assert model_b_position.backing_type == BackingType.ETH_TOKENIZED_GOLD
        assert model_b_position.right_type == RightType.FULL_POSITION


# ---------------------------------------------------------------------------
# Model A creation
# ---------------------------------------------------------------------------

class TestCreateModelA:
    def test_create_model_a(self, registry):
        pos = registry.create_model_a(
            owner=OWNER_A, token="PAXG", amount=500_000,
            bond_sost=25_000, duration_seconds=180 * 86400,
            reward_total=5_000, proof_hash="abcdef0123456789abcdef0123456789",
        )
        assert pos.contract_type == ContractType.MODEL_A_CUSTODY
        assert pos.backing_type == BackingType.AUTOCUSTODY_GOLD
        assert pos.transferable is False
        assert pos.backing_proof_hash is not None

    def test_model_a_properties(self, model_a_position):
        assert model_a_position.transferable is False
        assert model_a_position.backing_type == BackingType.AUTOCUSTODY_GOLD
        assert model_a_position.right_type == RightType.FULL_POSITION


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

class TestRegistryLookups:
    def test_get_position(self, registry, model_b_position):
        fetched = registry.get(model_b_position.position_id)
        assert fetched is model_b_position

    def test_get_missing(self, registry):
        assert registry.get("nonexistent") is None

    def test_by_owner(self, registry):
        p1 = registry.create_model_b(
            owner=OWNER_A, token="XAUT", amount=100, bond_sost=10,
            duration_seconds=86400, reward_total=10, eth_deposit_id=1, eth_tx="0x1",
        )
        p2 = registry.create_model_b(
            owner=OWNER_B, token="XAUT", amount=200, bond_sost=20,
            duration_seconds=86400, reward_total=20, eth_deposit_id=2, eth_tx="0x2",
        )
        assert p1 in registry.by_owner(OWNER_A)
        assert p2 not in registry.by_owner(OWNER_A)
        assert p2 in registry.by_owner(OWNER_B)

    def test_active_positions(self, registry, model_b_position):
        active = registry.active()
        assert model_b_position in active

    def test_matured_positions(self, registry):
        pos = registry.create_model_b(
            owner=OWNER_A, token="XAUT", amount=100, bond_sost=10,
            duration_seconds=1, reward_total=10, eth_deposit_id=99, eth_tx="0xold",
        )
        # Force expiry to the past
        pos.expiry_time = time.time() - 100
        matured = registry.matured()
        assert pos in matured


# ---------------------------------------------------------------------------
# Maturity checks
# ---------------------------------------------------------------------------

class TestMaturities:
    def test_check_maturities(self, registry):
        pos = registry.create_model_b(
            owner=OWNER_A, token="XAUT", amount=100, bond_sost=10,
            duration_seconds=1, reward_total=10, eth_deposit_id=50, eth_tx="0xmat",
        )
        pos.expiry_time = time.time() - 100
        matured_ids = registry.check_maturities()
        assert pos.position_id in matured_ids
        assert pos.status == PositionStatus.MATURED


# ---------------------------------------------------------------------------
# Reward claims
# ---------------------------------------------------------------------------

class TestRewardClaims:
    def test_claim_reward_valid(self, registry, model_b_position):
        ok = registry.claim_reward(model_b_position.position_id, 1_000_000)
        assert ok is True
        assert model_b_position.reward_claimed_sost == 1_000_000

    def test_claim_reward_exceeds_remaining(self, registry, model_b_position):
        total = model_b_position.reward_total_sost
        ok = registry.claim_reward(model_b_position.position_id, total + 1)
        assert ok is False
        assert model_b_position.reward_claimed_sost == 0


# ---------------------------------------------------------------------------
# Slash
# ---------------------------------------------------------------------------

class TestSlash:
    def test_slash_position(self, registry, model_b_position):
        ok = registry.slash(model_b_position.position_id, "proof-of-custody failure")
        assert ok is True
        assert model_b_position.status == PositionStatus.SLASHED

    def test_slash_is_permanent(self, registry, model_b_position):
        registry.slash(model_b_position.position_id, "bad")
        # Cannot slash again (not active)
        ok = registry.slash(model_b_position.position_id, "double")
        assert ok is False


# ---------------------------------------------------------------------------
# Redeem
# ---------------------------------------------------------------------------

class TestRedeem:
    def test_redeem_active(self, registry, model_b_position):
        ok = registry.redeem(model_b_position.position_id)
        assert ok is True
        assert model_b_position.status == PositionStatus.REDEEMED

    def test_redeem_matured(self, registry, model_b_position):
        model_b_position.status = PositionStatus.MATURED
        ok = registry.redeem(model_b_position.position_id)
        assert ok is True
        assert model_b_position.status == PositionStatus.REDEEMED

    def test_no_double_redeem(self, registry, model_b_position):
        registry.redeem(model_b_position.position_id)
        ok = registry.redeem(model_b_position.position_id)
        assert ok is False


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_save_load(self, registry, model_b_position, tmp_path):
        path = str(tmp_path / "positions.json")
        registry.save(path)

        reg2 = PositionRegistry()
        reg2.load(path)
        loaded = reg2.get(model_b_position.position_id)
        assert loaded is not None
        assert loaded.contract_type == ContractType.MODEL_B_ESCROW
        assert loaded.owner == model_b_position.owner
        assert loaded.reward_total_sost == model_b_position.reward_total_sost
