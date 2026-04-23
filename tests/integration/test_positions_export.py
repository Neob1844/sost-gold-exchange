"""
Tests for the position export script.

Validates that export_positions_json.py produces correct JSON output
matching the web API format.
"""

import json
import os
import sys
import time
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import Position, PositionStatus, ContractType, BackingType

# Import the export function
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from export_positions_json import export_positions, load_positions


POSITIONS_PATH = os.path.join(PROJECT_ROOT, "data", "positions.json")


def _make_registry_from_data() -> PositionRegistry:
    """Load registry from the real data/positions.json."""
    return load_positions(POSITIONS_PATH)


def test_export_produces_valid_json():
    """Export output is valid JSON with the expected top-level structure."""
    registry = _make_registry_from_data()
    result = export_positions(registry)

    # Must be serializable
    output = json.dumps(result)
    parsed = json.loads(output)

    # Required top-level keys
    assert "generated_at" in parsed
    assert "generated_iso" in parsed
    assert "total_positions" in parsed
    assert "active_positions" in parsed
    assert "unique_owners" in parsed
    assert "positions" in parsed
    assert isinstance(parsed["positions"], list)
    assert parsed["total_positions"] == len(parsed["positions"])

    # Even with empty registry, output is still valid
    empty = export_positions(PositionRegistry())
    empty_parsed = json.loads(json.dumps(empty))
    assert empty_parsed["total_positions"] == 0
    assert empty_parsed["positions"] == []


def test_export_includes_position_8afed8fc():
    """The known position 8afed8fcd27553a7 appears in the export."""
    registry = _make_registry_from_data()
    result = export_positions(registry)

    ids = [p["position_id"] for p in result["positions"]]
    assert "8afed8fcd27553a7" in ids

    # Verify key fields on the position
    pos = next(p for p in result["positions"] if p["position_id"] == "8afed8fcd27553a7")
    assert pos["token_symbol"] == "XAUT"
    assert pos["contract_type"] == "MODEL_B_ESCROW"
    assert pos["reference_amount"] == 500000
    assert pos["reward_total_sost"] == 2000
    assert "is_active" in pos
    assert "pct_complete" in pos
    assert "time_remaining" in pos


def test_export_totals_correct():
    """Totals in the export match the sum of individual positions."""
    registry = _make_registry_from_data()
    result = export_positions(registry)

    # total_gold_reference_wei should equal sum of reference_amount
    expected_gold = sum(p["reference_amount"] for p in result["positions"])
    assert result["total_gold_reference_wei"] == expected_gold

    # total_reward_sost should equal sum of reward_total_sost
    expected_reward = sum(p["reward_total_sost"] for p in result["positions"])
    assert result["total_reward_sost"] == expected_reward

    # active_positions count should match
    expected_active = sum(1 for p in result["positions"] if p["is_active"])
    assert result["active_positions"] == expected_active

    # unique_owners
    expected_owners = len(set(p["owner"] for p in result["positions"]))
    assert result["unique_owners"] == expected_owners


def test_export_sepolia_addresses():
    """Sepolia escrow transaction hashes are collected in the export."""
    registry = _make_registry_from_data()
    result = export_positions(registry)

    # Should contain the known tx hash from position 8afed8fc
    known_tx = "0x4d3a6beff787b8fe24f37bb1e8945f823e2b29244a65c7853f89767dc329a8c6"
    assert known_tx in result["sepolia_escrow_txs"]

    # Zero-hash placeholders should be filtered out
    zero_tx = "0x" + "0" * 64
    assert zero_tx not in result["sepolia_escrow_txs"]

    # All entries should be 0x-prefixed hex strings
    for tx in result["sepolia_escrow_txs"]:
        assert tx.startswith("0x")
        assert len(tx) == 66  # 0x + 64 hex chars
