"""Integration tests for SostWatcher — mock RPC calls, verify event detection."""

import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import patch, MagicMock

from src.watchers.sost_watcher import SostWatcher, SostEvent


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")

ADDR_A = "sost1maker0000000000000000000000000"
ADDR_B = "sost1taker0000000000000000000000000"


@pytest.fixture
def sost_fixtures():
    with open(os.path.join(FIXTURES_DIR, "sost_rpc_samples.json")) as f:
        return json.load(f)


@pytest.fixture
def watcher():
    return SostWatcher(
        rpc_url="http://localhost:18332",
        rpc_user="test",
        rpc_pass="test",
        watch_addresses=[ADDR_A],
    )


# ── Tests ────────────────────────────────────────────────────────────────


class TestDetectBalance:
    def test_detect_balance(self, watcher, sost_fixtures):
        """When an address has UTXOs, poll_once should emit a balance_confirmed event."""
        # Fixture is a list; find entries by method name
        info_entry = next(e for e in sost_fixtures if e["method"] == "getinfo")
        block_height = info_entry["result"]["blocks"]

        with patch.object(watcher, "get_block_height", return_value=block_height), \
             patch.object(watcher, "check_address_balance", return_value=150_000_000):
            events = watcher.poll_once()

        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "balance_confirmed"
        assert ev.address == ADDR_A
        assert ev.amount == 150_000_000

    def test_no_event_for_zero_balance(self, watcher, sost_fixtures):
        """Addresses with zero balance should not generate events."""
        with patch.object(watcher, "get_block_height", return_value=150200), \
             patch.object(watcher, "check_address_balance", return_value=0):
            events = watcher.poll_once()
        assert events == []


class TestNoDuplicateReads:
    def test_no_duplicate_reads(self, watcher):
        """Polling at same height should not re-emit events."""
        watcher.last_height = 0

        with patch.object(watcher, "get_block_height", return_value=100), \
             patch.object(watcher, "check_address_balance", return_value=50_000_000):
            first = watcher.poll_once()

        assert len(first) == 1

        # Same height again — should return nothing
        with patch.object(watcher, "get_block_height", return_value=100), \
             patch.object(watcher, "check_address_balance", return_value=50_000_000):
            second = watcher.poll_once()

        assert second == []


class TestWatchAddressManagement:
    def test_watch_address_management(self, watcher):
        assert ADDR_A in watcher.watch_addresses
        assert ADDR_B not in watcher.watch_addresses

        watcher.add_watch_address(ADDR_B)
        assert ADDR_B in watcher.watch_addresses

        # Adding same address again should not duplicate
        watcher.add_watch_address(ADDR_B)
        assert watcher.watch_addresses.count(ADDR_B) == 1

        watcher.remove_watch_address(ADDR_B)
        assert ADDR_B not in watcher.watch_addresses


class TestCallback:
    def test_callback_invoked(self, watcher):
        received = []
        watcher.on_event = lambda ev: received.append(ev)

        with patch.object(watcher, "get_block_height", return_value=200), \
             patch.object(watcher, "check_address_balance", return_value=100_000_000):
            watcher.poll_once()

        assert len(received) == 1
        assert received[0].address == ADDR_A


class TestEmptyUtxos:
    def test_handles_empty_utxos(self, watcher, sost_fixtures):
        """get_address_utxos returning [] should yield balance 0 and no event."""
        with patch.object(watcher, "get_block_height", return_value=150200), \
             patch.object(watcher, "get_address_utxos", return_value=[]):
            balance = watcher.check_address_balance(ADDR_A)
        assert balance == 0


class TestRepeatedPollingStable:
    def test_repeated_polling_stable(self, watcher):
        """Multiple polls at increasing heights with same balance should
        produce one event per new height."""
        collected = []
        watcher.on_event = lambda ev: collected.append(ev)

        for height in [100, 101, 102]:
            with patch.object(watcher, "get_block_height", return_value=height), \
                 patch.object(watcher, "check_address_balance", return_value=75_000_000):
                watcher.poll_once()

        assert len(collected) == 3
        # Internal events list should match
        assert len(watcher.get_events()) == 3
        heights = [ev.block_height for ev in watcher.get_events()]
        assert heights == [100, 101, 102]
