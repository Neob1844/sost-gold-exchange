"""Shared fixtures for SOST Gold Exchange unit tests."""

import sys
import os
import time
import pytest

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.positions.position_schema import (
    Position, ContractType, BackingType, PositionStatus, RightType,
)
from src.positions.position_registry import PositionRegistry
from src.positions.position_transfer import PositionTransferEngine
from src.settlement.refund_engine import RefundEngine


MAKER_SOST = "sost1maker0000000000000000000000000"
TAKER_SOST = "sost1taker0000000000000000000000000"
MAKER_ETH = "0xMakerEthAddress000000000000000000000000"
TAKER_ETH = "0xTakerEthAddress000000000000000000000000"

DEAL_DEFAULTS = dict(
    pair="SOST/XAUT",
    side="buy",
    amount_sost=100_000_000,       # 1 SOST
    amount_gold=1_000_000_000_000, # 1e12 wei-units of gold
    maker_sost_addr=MAKER_SOST,
    taker_sost_addr=TAKER_SOST,
    maker_eth_addr=MAKER_ETH,
    taker_eth_addr=TAKER_ETH,
)


@pytest.fixture
def deal_defaults():
    return dict(DEAL_DEFAULTS)


@pytest.fixture
def fresh_deal():
    """A newly created Deal in CREATED state."""
    now = time.time()
    return Deal(
        deal_id=Deal.generate_id(MAKER_SOST, TAKER_SOST, now),
        created_at=now,
        **DEAL_DEFAULTS,
    )


@pytest.fixture
def deal_store():
    return DealStore()


@pytest.fixture
def registry():
    return PositionRegistry()


@pytest.fixture
def model_b_position(registry):
    return registry.create_model_b(
        owner=MAKER_SOST,
        token="XAUT",
        amount=1_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=365 * 86400,
        reward_total=10_000_000,
        eth_deposit_id=42,
        eth_tx="0xabc123",
    )


@pytest.fixture
def model_a_position(registry):
    return registry.create_model_a(
        owner=MAKER_SOST,
        token="PAXG",
        amount=500_000_000_000,
        bond_sost=25_000_000,
        duration_seconds=180 * 86400,
        reward_total=5_000_000,
        proof_hash="abcdef0123456789abcdef0123456789",
    )


@pytest.fixture
def transfer_engine(registry):
    return PositionTransferEngine(registry)


@pytest.fixture
def refund_engine():
    return RefundEngine()
