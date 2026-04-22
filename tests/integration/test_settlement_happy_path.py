"""Integration test — full settlement happy path from deal creation to SETTLED."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import MagicMock

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.refund_engine import RefundEngine
from src.settlement.settlement_daemon import SettlementDaemon
from src.watchers.ethereum_watcher import EthereumWatcher, EthEvent
from src.watchers.sost_watcher import SostWatcher, SostEvent
from src.operator.audit_log import AuditLog


MAKER_SOST = "sost1maker0000000000000000000000000"
TAKER_SOST = "sost1taker0000000000000000000000000"
MAKER_ETH = "0xMakerEthAddress000000000000000000000000"
TAKER_ETH = "0xTakerEthAddress000000000000000000000000"


@pytest.fixture
def components(tmp_path):
    deal_store = DealStore()
    registry_audit = AuditLog(log_dir=str(tmp_path / "audit"))
    refund_engine = RefundEngine()

    # Mock watchers — we drive events manually, no polling
    eth_watcher = MagicMock(spec=EthereumWatcher)
    sost_watcher = MagicMock(spec=SostWatcher)
    sost_watcher.watch_addresses = []
    sost_watcher.add_watch_address = lambda addr: sost_watcher.watch_addresses.append(addr)

    daemon = SettlementDaemon(
        deal_store=deal_store,
        eth_watcher=eth_watcher,
        sost_watcher=sost_watcher,
        refund_engine=refund_engine,
        audit=registry_audit,
    )

    return {
        "deal_store": deal_store,
        "audit": registry_audit,
        "refund_engine": refund_engine,
        "eth_watcher": eth_watcher,
        "sost_watcher": sost_watcher,
        "daemon": daemon,
    }


class TestSettlementHappyPath:
    def test_full_happy_path(self, components):
        deal_store = components["deal_store"]
        daemon = components["daemon"]
        audit = components["audit"]

        # 1. Create deal
        deal = deal_store.create(
            pair="SOST/XAUT",
            side="buy",
            amount_sost=100_000_000,
            amount_gold=1_000_000_000_000_000_000,
            maker_sost_addr=MAKER_SOST,
            taker_sost_addr=TAKER_SOST,
            maker_eth_addr=MAKER_ETH,
            taker_eth_addr=TAKER_ETH,
        )
        assert deal.state == DealState.CREATED

        # 2. Transition to NEGOTIATED
        ok = deal.transition(DealState.NEGOTIATED, "terms agreed")
        assert ok
        assert deal.state == DealState.NEGOTIATED

        # 3. Transition to AWAITING_ETH_LOCK
        ok = deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
        assert ok
        assert deal.state == DealState.AWAITING_ETH_LOCK

        # 4. Register deal with daemon
        deposit_id = 5001
        daemon._deal_eth_map[deposit_id] = deal.deal_id
        daemon.register_deal(deal)
        assert deal.taker_sost_addr in components["sost_watcher"].watch_addresses

        # 5. Simulate ETH lock event
        eth_event = EthEvent(
            event_type="deposit",
            tx_hash="0xeth_lock_tx_hash_001",
            block_number=19500000,
            deposit_id=deposit_id,
            depositor=TAKER_ETH,
            token="0x68749665FF8D2d112Fa859AA293F07A622782F38",
            amount=1_000_000_000_000_000_000,
            unlock_time=int(time.time()) + 3600,
            timestamp=time.time(),
        )
        daemon.on_eth_event(eth_event)

        assert deal.eth_tx_hash == "0xeth_lock_tx_hash_001"
        assert deal.eth_deposit_id == deposit_id
        # After ETH lock from AWAITING_ETH_LOCK: should be AWAITING_SOST_LOCK
        assert deal.state == DealState.AWAITING_SOST_LOCK

        # 6. Simulate SOST lock event
        sost_event = SostEvent(
            event_type="balance_confirmed",
            txid="sost_lock_txid_001",
            block_height=150300,
            address=TAKER_SOST,
            amount=100_000_000,
            deal_ref=deal.deal_id,
            timestamp=time.time(),
        )
        daemon.on_sost_event(sost_event)

        assert deal.sost_lock_txid is not None
        assert deal.state == DealState.BOTH_LOCKED

        # 7. Execute settlement
        settled = daemon.execute_settlement(deal.deal_id)
        assert settled is True
        assert deal.state == DealState.SETTLED
        assert deal.settlement_tx_hash is not None

        # 8. Verify audit log has complete history
        history = audit.get_deal_history(deal.deal_id)
        event_types = [e.event for e in history]
        assert "registered" in event_types
        assert "eth_locked" in event_types
        assert "sost_locked" in event_types
        assert "both_locked" in event_types
        assert "settlement_initiated" in event_types
        assert "settled" in event_types

        # 9. Verify deal.history has all transitions
        states_visited = [h["to"] for h in deal.history]
        assert "NEGOTIATED" in states_visited
        assert "AWAITING_ETH_LOCK" in states_visited
        assert "AWAITING_SOST_LOCK" in states_visited
        assert "BOTH_LOCKED" in states_visited
        assert "SETTLING" in states_visited
        assert "SETTLED" in states_visited
