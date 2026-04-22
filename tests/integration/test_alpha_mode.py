"""
Tests for alpha mode configuration, limits, and mode detection.

Validates that the limited alpha config enforces deal limits,
requires operator approval, and correctly detects mode from config files.
"""

import json
import os
import pytest
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALPHA_CONFIG = os.path.join(PROJECT_ROOT, "configs", "limited_public_alpha.json")
MAINNET_CONFIG = os.path.join(PROJECT_ROOT, "configs", "mainnet_model_b.example.json")


@pytest.fixture
def alpha_config():
    with open(ALPHA_CONFIG, "r") as f:
        return json.load(f)


@pytest.fixture
def mainnet_config():
    with open(MAINNET_CONFIG, "r") as f:
        return json.load(f)


def detect_mode(config):
    """Detect operational mode from a config dict."""
    mode = config.get("mode", "unknown")
    if "mainnet" in mode:
        return "mainnet"
    elif "alpha" in mode:
        return "alpha"
    elif "testnet" in mode or "sepolia" in mode:
        return "testnet"
    return "unknown"


def check_deal_within_limits(config, amount_sost, gold_amount_mg):
    """Check whether a proposed deal falls within configured limits."""
    limits = config.get("limits", config.get("pilot", {}))
    max_sost = limits.get("max_position_size_sost", float("inf"))
    max_gold = limits.get("max_gold_amount_mg", float("inf"))
    if amount_sost > max_sost:
        return False, "exceeds max SOST position size"
    if gold_amount_mg > max_gold:
        return False, "exceeds max gold amount"
    return True, "within limits"


def test_load_limited_alpha_config():
    """Verify the limited alpha config file exists and is well-formed."""
    assert os.path.exists(ALPHA_CONFIG), f"Missing config: {ALPHA_CONFIG}"
    with open(ALPHA_CONFIG, "r") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert data.get("mode") == "limited-public-alpha"
    assert "limits" in data
    assert "restrictions" in data
    assert "operator" in data


def test_can_create_deal_within_limits(alpha_config):
    """A deal within configured limits should be accepted."""
    # 10 SOST (well under 500 SOST limit) and 100g gold (well under 311g limit)
    ok, reason = check_deal_within_limits(alpha_config, 1000000000, 100000)
    assert ok is True, f"Expected deal within limits to pass: {reason}"


def test_cannot_create_deal_exceeds_limits(alpha_config):
    """A deal exceeding configured limits should be rejected."""
    # 1000 SOST (over 500 SOST limit)
    ok, reason = check_deal_within_limits(alpha_config, 100000000000, 100000)
    assert ok is False, "Expected deal exceeding SOST limit to fail"
    assert "exceeds" in reason

    # Gold amount over limit (500,000 mg > 311,035 mg)
    ok, reason = check_deal_within_limits(alpha_config, 1000000000, 500000)
    assert ok is False, "Expected deal exceeding gold limit to fail"
    assert "exceeds" in reason


def test_mainnet_disabled_by_default(alpha_config):
    """Limited alpha config must have mainnet disabled."""
    limits = alpha_config.get("limits", {})
    assert limits.get("mainnet_enabled") is False, \
        "Mainnet must be disabled in limited alpha config"


def test_operator_approval_required(alpha_config):
    """Operator approval must be required in alpha mode."""
    limits = alpha_config.get("limits", {})
    assert limits.get("operator_approval_required") is True, \
        "Operator approval must be required in alpha mode"

    operator = alpha_config.get("operator", {})
    assert operator.get("manual_settlement_confirmation") is True, \
        "Manual settlement confirmation must be required"
    assert operator.get("audit_log_required") is True, \
        "Audit log must be required"


def test_mode_detection(alpha_config, mainnet_config):
    """Mode detection should correctly identify alpha vs mainnet configs."""
    assert detect_mode(alpha_config) == "alpha", \
        "Alpha config should be detected as alpha mode"
    assert detect_mode(mainnet_config) == "mainnet", \
        "Mainnet config should be detected as mainnet mode"

    # Unknown config
    assert detect_mode({"mode": "something-else"}) == "unknown"
    assert detect_mode({}) == "unknown"

    # Testnet
    assert detect_mode({"mode": "sepolia-testnet"}) == "testnet"
