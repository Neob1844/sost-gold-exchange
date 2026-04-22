"""
Adversarial: double-transfer of a Model B position.

After transferring a position to owner_1, a second transfer
to owner_2 should succeed (position is still ACTIVE and transferable).
However, the final owner must be owner_2, not a duplication.

If the position is closed/slashed between transfers, the second must fail.
"""

import time

import pytest

from src.positions.position_registry import PositionRegistry
from src.positions.position_transfer import PositionTransferEngine
from src.positions.position_schema import Position, PositionStatus


ORIGINAL = "sost1original_owner"
BUYER_1 = "sost1buyer_one"
BUYER_2 = "sost1buyer_two"


def _create_position(registry):
    return registry.create_model_b(
        owner=ORIGINAL,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=250_000_000_00,
        duration_seconds=365 * 86400,
        reward_total=50_000_000_00,
        eth_deposit_id=1001,
        eth_tx="0xabc123",
    )


class TestPositionDoubleTransfer:
    def test_first_transfer_succeeds(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_position(reg)

        result = engine.transfer(pos.position_id, BUYER_1)
        assert result.success is True
        assert pos.owner == BUYER_1

    def test_second_transfer_after_slash_fails(self):
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_position(reg)

        engine.transfer(pos.position_id, BUYER_1)
        assert pos.owner == BUYER_1

        # Slash the position (e.g., backing proof failed)
        reg.slash(pos.position_id, "backing proof expired")
        assert pos.status == PositionStatus.SLASHED

        # Second transfer must fail — position is slashed
        result2 = engine.transfer(pos.position_id, BUYER_2)
        assert result2.success is False
        assert pos.owner == BUYER_1  # unchanged

    def test_sequential_transfers_to_different_owners(self):
        """Two valid sequential transfers — owner should be the last transferee."""
        reg = PositionRegistry()
        engine = PositionTransferEngine(reg)
        pos = _create_position(reg)

        r1 = engine.transfer(pos.position_id, BUYER_1)
        assert r1.success is True
        assert pos.owner == BUYER_1

        # BUYER_1 transfers to BUYER_2
        r2 = engine.transfer(pos.position_id, BUYER_2)
        assert r2.success is True
        assert pos.owner == BUYER_2

        # Cannot transfer back to current owner
        r3 = engine.transfer(pos.position_id, BUYER_2)
        assert r3.success is False
        assert "same owner" in r3.message
