"""
SOST Gold Exchange — Test Fixtures
"""

import time
import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, RightType,
)
from src.positions.position_registry import PositionRegistry
from src.settlement.refund_engine import RefundEngine
from src.operator.audit_log import AuditLog


# --------------- Deal fixtures ---------------

@pytest.fixture
def deal_store():
    return DealStore()


@pytest.fixture
def sample_deal():
    now = time.time()
    return Deal(
        deal_id="d00fa83b1e2c7a90",
        pair="SOST/XAUT",
        side="buy",
        amount_sost=500_000_000_00,      # 500 SOST in satoshis
        amount_gold=1_000_000_000_000_000_000,  # 1 XAUT in wei
        maker_sost_addr="sost1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx",
        taker_sost_addr="sost1grfm9nmmxau3la5dkyhe3w5e4pc3n4zmnv55v0g",
        maker_eth_addr="0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
        taker_eth_addr="0xdAC17F958D2ee523a2206206994597C13D831ec7",
        state=DealState.CREATED,
        created_at=now,
        expires_at=now + 3600,
    )


# --------------- Position fixtures ---------------

@pytest.fixture
def position_registry():
    return PositionRegistry()


@pytest.fixture
def sample_position_b():
    now = time.time()
    return Position(
        position_id="pb_8a3f1c0e4d72b6a9",
        owner="sost1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx",
        contract_type=ContractType.MODEL_B_ESCROW,
        backing_type=BackingType.ETH_TOKENIZED_GOLD,
        token_symbol="XAUT",
        reference_amount=1_000_000_000_000_000_000,  # 1 XAUT in wei
        bond_amount_sost=250_000_000_00,              # 250 SOST in satoshis
        start_time=now,
        expiry_time=now + 31_536_000,                 # 1 year
        reward_schedule="linear_365d",
        reward_total_sost=50_000_000_00,              # 50 SOST total rewards
        eth_escrow_deposit_id=1001,
        eth_escrow_tx="0xabc123def456789012345678901234567890abcdef1234567890abcdef123456",
        transferable=True,
    )


@pytest.fixture
def sample_position_a():
    now = time.time()
    return Position(
        position_id="pa_7b2e0d1f5c83a4b8",
        owner="sost1grfm9nmmxau3la5dkyhe3w5e4pc3n4zmnv55v0g",
        contract_type=ContractType.MODEL_A_CUSTODY,
        backing_type=BackingType.AUTOCUSTODY_GOLD,
        token_symbol="PAXG",
        reference_amount=500_000_000_000_000_000,  # 0.5 PAXG in wei
        bond_amount_sost=125_000_000_00,            # 125 SOST in satoshis
        start_time=now,
        expiry_time=now + 15_768_000,               # ~6 months
        reward_schedule="linear_182d",
        reward_total_sost=18_000_000_00,            # 18 SOST total rewards
        backing_proof_hash="e3b0c44298fc1c149afbf4c8996fb924"
                          "27ae41e4649b934ca495991b7852b855",
        transferable=False,
    )


# --------------- Operator / engine fixtures ---------------

@pytest.fixture
def audit_log(tmp_path):
    return AuditLog(log_dir=str(tmp_path / "audit"))


@pytest.fixture
def refund_engine():
    return RefundEngine()
