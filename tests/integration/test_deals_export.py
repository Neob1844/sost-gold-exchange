"""
Tests for the deal export script.

Validates that export_deals_live_json.py produces correct JSON output
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

from src.settlement.deal_state_machine import DealStore, DealState, Deal

sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
from export_deals_live_json import export_deals, load_deals


def _make_sample_deal(store: DealStore, **overrides) -> Deal:
    """Create a sample deal in the store."""
    defaults = {
        "pair": "SOST/XAUT",
        "side": "buy",
        "amount_sost": 5000000000,
        "amount_gold": 50000,
        "maker_sost_addr": "sost1maker_test",
        "taker_sost_addr": "sost1taker_test",
        "maker_eth_addr": "0x1111111111111111111111111111111111111111",
        "taker_eth_addr": "0x2222222222222222222222222222222222222222",
    }
    defaults.update(overrides)
    return store.create(**defaults)


def test_export_produces_valid_json():
    """Export output is valid JSON with the expected top-level structure."""
    store = DealStore()
    _make_sample_deal(store)

    result = export_deals(store)

    # Must be serializable
    output = json.dumps(result)
    parsed = json.loads(output)

    # Required top-level keys
    assert "generated_at" in parsed
    assert "generated_iso" in parsed
    assert "total_deals" in parsed
    assert "active_deals" in parsed
    assert "settled_deals" in parsed
    assert "unique_participants" in parsed
    assert "deals" in parsed
    assert isinstance(parsed["deals"], list)
    assert parsed["total_deals"] == len(parsed["deals"])


def test_export_empty_store():
    """Empty deal store produces valid output with zero counts."""
    store = DealStore()
    result = export_deals(store)

    assert result["total_deals"] == 0
    assert result["active_deals"] == 0
    assert result["settled_deals"] == 0
    assert result["unique_participants"] == 0
    assert result["total_sost_volume"] == 0
    assert result["total_gold_volume"] == 0
    assert result["deals"] == []

    # Must still be valid JSON
    output = json.dumps(result)
    parsed = json.loads(output)
    assert parsed["total_deals"] == 0


def test_export_includes_settled_deal():
    """A settled deal appears in the export with correct status."""
    store = DealStore()
    deal = _make_sample_deal(store)

    # Walk through state machine to SETTLED
    deal.transition(DealState.NEGOTIATED, "test")
    deal.transition(DealState.AWAITING_ETH_LOCK, "test")
    deal.transition(DealState.AWAITING_SOST_LOCK, "test")
    deal.transition(DealState.BOTH_LOCKED, "test")
    deal.transition(DealState.SETTLING, "test")
    deal.transition(DealState.SETTLED, "test")

    result = export_deals(store)

    assert result["settled_deals"] == 1
    assert result["active_deals"] == 0

    exported_deal = result["deals"][0]
    assert exported_deal["deal_id"] == deal.deal_id
    assert exported_deal["status"] == "SETTLED"
    assert exported_deal["is_terminal"] is True
    assert exported_deal["amount_sost"] == 5000000000
    assert exported_deal["amount_gold"] == 50000


def test_export_totals_correct():
    """Totals in the export match the sum of individual deals."""
    store = DealStore()
    _make_sample_deal(store, amount_sost=1000, amount_gold=100,
                      maker_sost_addr="sost1a", taker_sost_addr="sost1b")
    _make_sample_deal(store, amount_sost=2000, amount_gold=200,
                      maker_sost_addr="sost1c", taker_sost_addr="sost1d")
    _make_sample_deal(store, amount_sost=3000, amount_gold=300,
                      maker_sost_addr="sost1a", taker_sost_addr="sost1d")

    result = export_deals(store)

    assert result["total_deals"] == 3
    assert result["total_sost_volume"] == 6000
    assert result["total_gold_volume"] == 600

    # Unique participants: sost1a, sost1b, sost1c, sost1d = 4
    assert result["unique_participants"] == 4

    # All are active (CREATED state, not terminal)
    assert result["active_deals"] == 3
    assert result["settled_deals"] == 0

    # Verify sums match individual deals
    expected_sost = sum(d["amount_sost"] for d in result["deals"])
    assert result["total_sost_volume"] == expected_sost

    expected_gold = sum(d["amount_gold"] for d in result["deals"])
    assert result["total_gold_volume"] == expected_gold
