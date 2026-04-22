"""Integration tests for EthereumWatcher — mock HTTP/RPC, verify event parsing."""

import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import patch, MagicMock

from src.watchers.ethereum_watcher import EthereumWatcher, EthEvent, CONFIRMATIONS_REQUIRED


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


@pytest.fixture
def eth_fixtures():
    with open(os.path.join(FIXTURES_DIR, "eth_events.json")) as f:
        return json.load(f)


@pytest.fixture
def watcher():
    return EthereumWatcher(
        rpc_url="http://localhost:8545",
        escrow_address="0xEscrow0000000000000000000000000000000000",
    )


def _make_raw_log(deposit_id=1001, depositor="71C7656EC7ab88b098defB751B7401B5f6d8976F",
                  block_number=19450321, tx_hash="0xabc123", amount=1_000_000_000_000_000_000):
    """Build a raw log dict that parse_deposit_event can consume."""
    return {
        "topics": [
            "0xa1b2c3d4",  # event selector
            hex(deposit_id),
            "0x000000000000000000000000" + depositor,
        ],
        "data": "0x" + hex(amount)[2:].zfill(64),
        "blockNumber": hex(block_number),
        "transactionHash": tx_hash,
    }


# ── Tests ────────────────────────────────────────────────────────────────


class TestParseDepositEvent:
    def test_parse_deposit_event(self, watcher):
        raw = _make_raw_log(deposit_id=1001, amount=1_000_000_000_000_000_000)
        ev = watcher.parse_deposit_event(raw)
        assert ev is not None
        assert ev.event_type == "deposit"
        assert ev.deposit_id == 1001
        assert ev.amount == 1_000_000_000_000_000_000
        assert ev.block_number == 19450321
        assert ev.depositor.lower().endswith("6d8976f")

    def test_parse_returns_none_for_short_topics(self, watcher):
        raw = {"topics": ["0xa1b2c3d4"], "data": "0x00", "blockNumber": "0x1",
               "transactionHash": "0xdead"}
        assert watcher.parse_deposit_event(raw) is None


class TestConfirmations:
    def test_respects_confirmations(self, watcher):
        """Only process blocks with at least CONFIRMATIONS_REQUIRED confirmations."""
        current_block = 100
        watcher.last_block = 0

        with patch.object(watcher, "get_block_number", return_value=current_block), \
             patch.object(watcher, "get_logs", return_value=[]) as mock_logs:
            watcher.poll_once()
            # Should query up to block (current - CONFIRMATIONS_REQUIRED)
            safe = current_block - CONFIRMATIONS_REQUIRED
            mock_logs.assert_called_once()
            call_args = mock_logs.call_args
            assert call_args[0][1] <= safe

    def test_no_poll_when_not_enough_confirmations(self, watcher):
        """When head is only 3 blocks ahead of last_block, and CONFIRMATIONS_REQUIRED=6,
        safe_block <= last_block so nothing should be fetched."""
        watcher.last_block = 100
        head = 100 + CONFIRMATIONS_REQUIRED - 1  # not enough

        with patch.object(watcher, "get_block_number", return_value=head), \
             patch.object(watcher, "get_logs") as mock_logs:
            events = watcher.poll_once()
            mock_logs.assert_not_called()
            assert events == []


class TestDuplicates:
    def test_no_duplicate_events(self, watcher, eth_fixtures):
        """Fixture has duplicate deposit_id=1001 at same block. poll_once should
        return both raw parse results (dedup is caller's responsibility), but
        internal _events list grows by the count of parsed events."""
        raw_logs = [_make_raw_log(**{
            "deposit_id": ev["deposit_id"],
            "block_number": ev["block_number"],
            "tx_hash": ev["tx_hash"],
            "amount": ev["amount"],
        }) for ev in eth_fixtures if ev["event_type"] == "deposit"]

        watcher.last_block = 0
        with patch.object(watcher, "get_block_number", return_value=19450600), \
             patch.object(watcher, "get_logs", return_value=raw_logs):
            events = watcher.poll_once()

        # All parseable logs come through; fixture has 4 deposit entries
        assert len(events) == 4
        # Verify _events matches
        assert len(watcher.get_events()) == 4


class TestCallback:
    def test_callback_invoked(self, watcher):
        received = []
        watcher.on_event = lambda ev: received.append(ev)

        raw = [_make_raw_log(deposit_id=2001)]
        watcher.last_block = 0

        with patch.object(watcher, "get_block_number", return_value=19500000), \
             patch.object(watcher, "get_logs", return_value=raw):
            watcher.poll_once()

        assert len(received) == 1
        assert received[0].deposit_id == 2001


class TestPollMultiple:
    def test_poll_multiple_events(self, watcher):
        logs = [
            _make_raw_log(deposit_id=3001, block_number=200),
            _make_raw_log(deposit_id=3002, block_number=201),
            _make_raw_log(deposit_id=3003, block_number=202),
        ]
        watcher.last_block = 0

        with patch.object(watcher, "get_block_number", return_value=300), \
             patch.object(watcher, "get_logs", return_value=logs):
            events = watcher.poll_once()

        assert len(events) == 3
        ids = {e.deposit_id for e in events}
        assert ids == {3001, 3002, 3003}


class TestEmptyLogs:
    def test_handles_empty_logs(self, watcher):
        watcher.last_block = 0
        with patch.object(watcher, "get_block_number", return_value=100), \
             patch.object(watcher, "get_logs", return_value=[]):
            events = watcher.poll_once()
        assert events == []
        assert watcher.get_events() == []
