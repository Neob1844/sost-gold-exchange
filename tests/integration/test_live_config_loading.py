"""
Tests for live alpha configuration loading.

Validates that configs/live_alpha.example.json is well-formed and contains
all required sections and keys for Sepolia + SOST integration.
"""

import json
import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLE_CONFIG = os.path.join(PROJECT_ROOT, "configs", "live_alpha.example.json")


@pytest.fixture
def config():
    with open(EXAMPLE_CONFIG, "r") as f:
        return json.load(f)


def test_load_example_config():
    """Verify the example config file exists and is valid JSON."""
    assert os.path.exists(EXAMPLE_CONFIG), f"Missing config: {EXAMPLE_CONFIG}"
    with open(EXAMPLE_CONFIG, "r") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert len(data) > 0


def test_config_has_required_fields(config):
    """Top-level config must have mode, ethereum, sost, demo, and data sections."""
    required = ["mode", "ethereum", "sost", "demo", "data"]
    for key in required:
        assert key in config, f"Missing required top-level key: {key}"
    assert config["mode"] == "live-alpha"


def test_config_ethereum_section(config):
    """Ethereum section must have RPC URL, chain ID, contract addresses, and poll settings."""
    eth = config["ethereum"]
    required_keys = [
        "rpc_url",
        "chain_id",
        "escrow_address",
        "xaut_address",
        "paxg_address",
        "confirmations",
        "poll_interval",
    ]
    for key in required_keys:
        assert key in eth, f"Missing ethereum.{key}"
    assert eth["chain_id"] == 11155111, "Expected Sepolia chain ID"
    assert isinstance(eth["confirmations"], int)
    assert eth["confirmations"] > 0
    assert isinstance(eth["poll_interval"], (int, float))
    assert eth["poll_interval"] > 0


def test_config_sost_section(config):
    """SOST section must have RPC URL, credentials, and poll interval."""
    sost = config["sost"]
    required_keys = [
        "rpc_url",
        "rpc_user",
        "rpc_pass",
        "poll_interval",
    ]
    for key in required_keys:
        assert key in sost, f"Missing sost.{key}"
    assert "127.0.0.1" in sost["rpc_url"] or "localhost" in sost["rpc_url"]
    assert isinstance(sost["poll_interval"], (int, float))
    assert sost["poll_interval"] > 0


def test_config_demo_section(config):
    """Demo section must have maker/taker addresses, amounts, and lock duration."""
    demo = config["demo"]
    required_keys = [
        "maker_sost_addr",
        "taker_sost_addr",
        "maker_eth_addr",
        "taker_eth_addr",
        "amount_sost",
        "amount_gold",
        "lock_duration_days",
    ]
    for key in required_keys:
        assert key in demo, f"Missing demo.{key}"
    assert isinstance(demo["lock_duration_days"], (int, float))
    assert demo["lock_duration_days"] > 0
