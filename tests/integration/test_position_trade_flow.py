"""Integration test — position trade flow through deal settlement."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.positions.position_schema import Position, ContractType, BackingType, PositionStatus, RightType
from src.positions.position_registry import PositionRegistry
from src.positions.position_pricing import value_position
from src.positions.position_transfer import PositionTransferEngine
from src.positions.position_settlement import PositionSettlement
from src.operator.audit_log import AuditLog


MAKER_SOST = "sost1maker0000000000000000000000000"
TAKER_SOST = "sost1taker0000000000000000000000000"
MAKER_ETH = "0xMakerEthAddress000000000000000000000000"
TAKER_ETH = "0xTakerEthAddress000000000000000000000000"


@pytest.fixture
def components(tmp_path):
    registry = PositionRegistry()
    audit = AuditLog(log_dir=str(tmp_path / "audit"))
    transfer_engine = PositionTransferEngine(registry)
    pos_settlement = PositionSettlement(registry, transfer_engine, audit)

    return {
        "registry": registry,
        "audit": audit,
        "transfer_engine": transfer_engine,
        "pos_settlement": pos_settlement,
    }


class TestPositionTradeFlow:
    def test_model_b_position_trade_and_settle(self, components):
        registry = components["registry"]
        audit = components["audit"]
        pos_settlement = components["pos_settlement"]

        # 1. Create a Model B position owned by maker
        position = registry.create_model_b(
            owner=MAKER_SOST,
            token="XAUT",
            amount=1_000_000_000_000_000_000,
            bond_sost=50_000_000,
            duration_seconds=365 * 86400,
            reward_total=10_000_000,
            eth_deposit_id=42,
            eth_tx="0xabc123",
        )
        assert position.owner == MAKER_SOST
        assert position.status == PositionStatus.ACTIVE
        assert position.contract_type == ContractType.MODEL_B_ESCROW
        assert position.transferable is True

        # 2. Value the position
        valuation = value_position(position, gold_price_sost_per_unit=0.001)
        assert valuation.net_value_sost > 0
        assert valuation.gold_value_sost > 0
        assert valuation.reward_value_sost > 0

        # 3. Create a deal for position trade
        deal_store = DealStore()
        deal = deal_store.create(
            pair="SOST/XAUT",
            side="sell",
            amount_sost=valuation.net_value_sost,
            amount_gold=position.reference_amount,
            maker_sost_addr=MAKER_SOST,
            taker_sost_addr=TAKER_SOST,
            maker_eth_addr=MAKER_ETH,
            taker_eth_addr=TAKER_ETH,
        )
        assert deal.state == DealState.CREATED

        # 4. Transition deal through states to BOTH_LOCKED
        deal.transition(DealState.NEGOTIATED, "terms agreed")
        deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")

        # Simulate ETH lock
        deal.mark_eth_locked("0xeth_lock_pos_trade", 7001)
        assert deal.state == DealState.AWAITING_SOST_LOCK

        # Simulate SOST lock
        deal.mark_sost_locked("sost_lock_pos_trade_txid")
        assert deal.state == DealState.BOTH_LOCKED

        # 5. Settle the position trade
        settled = pos_settlement.settle_position_trade(deal, position.position_id)
        assert settled is True

        # 6. Verify position owner changed to taker
        updated_pos = registry.get(position.position_id)
        assert updated_pos.owner == TAKER_SOST

        # 7. Verify position history records the transfer
        transfer_events = [h for h in updated_pos.history if h["event"] == "transferred"]
        assert len(transfer_events) == 1
        assert MAKER_SOST in transfer_events[0]["detail"]
        assert TAKER_SOST in transfer_events[0]["detail"]

        # 8. Verify deal reached SETTLED state
        assert deal.state == DealState.SETTLED
        assert deal.settlement_tx_hash is not None
        assert position.position_id in deal.settlement_tx_hash

        # 9. Verify audit log recorded the settlement
        history = audit.get_deal_history(deal.deal_id)
        event_names = [e.event for e in history]
        assert "position_settled" in event_names
