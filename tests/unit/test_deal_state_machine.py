"""Unit tests for the SOST Gold Exchange Deal State Machine."""

import json
import time
import pytest

from src.settlement.deal_state_machine import Deal, DealStore, DealState, VALID_TRANSITIONS


# ---------------------------------------------------------------------------
# Deal creation
# ---------------------------------------------------------------------------

class TestDealCreation:
    def test_create_deal(self, fresh_deal):
        assert fresh_deal.state == DealState.CREATED
        assert fresh_deal.pair == "SOST/XAUT"
        assert fresh_deal.side == "buy"
        assert fresh_deal.amount_sost == 100_000_000
        assert fresh_deal.eth_tx_hash is None
        assert fresh_deal.sost_lock_txid is None
        assert fresh_deal.settlement_tx_hash is None

    def test_deal_id_stable(self):
        ts = 1700000000.0
        id1 = Deal.generate_id("addrA", "addrB", ts)
        id2 = Deal.generate_id("addrA", "addrB", ts)
        assert id1 == id2

    def test_deal_id_unique(self):
        ts = 1700000000.0
        id1 = Deal.generate_id("addrA", "addrB", ts)
        id2 = Deal.generate_id("addrA", "addrC", ts)
        id3 = Deal.generate_id("addrA", "addrB", ts + 1)
        assert id1 != id2
        assert id1 != id3

    def test_deal_id_length(self):
        did = Deal.generate_id("a", "b", 1.0)
        assert len(did) == 16

    def test_default_expiry(self, fresh_deal):
        assert fresh_deal.expires_at == pytest.approx(fresh_deal.created_at + 3600, abs=1)


# ---------------------------------------------------------------------------
# State transitions — valid paths
# ---------------------------------------------------------------------------

class TestValidTransitions:
    @pytest.mark.parametrize("from_state,to_state", [
        (DealState.CREATED, DealState.NEGOTIATED),
        (DealState.CREATED, DealState.EXPIRED),
        (DealState.NEGOTIATED, DealState.AWAITING_ETH_LOCK),
        (DealState.NEGOTIATED, DealState.EXPIRED),
        (DealState.AWAITING_ETH_LOCK, DealState.AWAITING_SOST_LOCK),
        (DealState.AWAITING_ETH_LOCK, DealState.BOTH_LOCKED),
        (DealState.AWAITING_ETH_LOCK, DealState.REFUND_PENDING),
        (DealState.AWAITING_ETH_LOCK, DealState.EXPIRED),
        (DealState.AWAITING_SOST_LOCK, DealState.BOTH_LOCKED),
        (DealState.AWAITING_SOST_LOCK, DealState.REFUND_PENDING),
        (DealState.AWAITING_SOST_LOCK, DealState.EXPIRED),
        (DealState.BOTH_LOCKED, DealState.SETTLING),
        (DealState.BOTH_LOCKED, DealState.REFUND_PENDING),
        (DealState.BOTH_LOCKED, DealState.DISPUTED),
        (DealState.SETTLING, DealState.SETTLED),
        (DealState.SETTLING, DealState.REFUND_PENDING),
        (DealState.SETTLING, DealState.DISPUTED),
        (DealState.REFUND_PENDING, DealState.REFUNDED),
        (DealState.DISPUTED, DealState.SETTLED),
        (DealState.DISPUTED, DealState.REFUND_PENDING),
    ])
    def test_valid_transition(self, fresh_deal, from_state, to_state):
        fresh_deal.state = from_state
        assert fresh_deal.transition(to_state, "test") is True
        assert fresh_deal.state == to_state


# ---------------------------------------------------------------------------
# State transitions — invalid paths
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    @pytest.mark.parametrize("from_state,to_state", [
        (DealState.CREATED, DealState.SETTLED),
        (DealState.CREATED, DealState.BOTH_LOCKED),
        (DealState.SETTLED, DealState.CREATED),
        (DealState.SETTLED, DealState.REFUND_PENDING),
        (DealState.REFUNDED, DealState.CREATED),
        (DealState.EXPIRED, DealState.CREATED),
        (DealState.NEGOTIATED, DealState.SETTLED),
        (DealState.BOTH_LOCKED, DealState.CREATED),
    ])
    def test_invalid_transition(self, fresh_deal, from_state, to_state):
        fresh_deal.state = from_state
        assert fresh_deal.transition(to_state, "bad") is False
        assert fresh_deal.state == from_state


# ---------------------------------------------------------------------------
# Terminal states
# ---------------------------------------------------------------------------

class TestTerminalStates:
    @pytest.mark.parametrize("state", [DealState.SETTLED, DealState.REFUNDED, DealState.EXPIRED])
    def test_terminal_states_no_reopen(self, fresh_deal, state):
        fresh_deal.state = state
        assert fresh_deal.is_terminal() is True
        for target in DealState:
            if target != state:
                assert fresh_deal.transition(target) is False
        assert fresh_deal.state == state

    def test_non_terminal(self, fresh_deal):
        assert fresh_deal.is_terminal() is False


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

class TestExpiry:
    def test_expiry_detection(self, fresh_deal):
        fresh_deal.expires_at = time.time() - 10
        assert fresh_deal.is_expired() is True

    def test_not_expired_when_future(self, fresh_deal):
        fresh_deal.expires_at = time.time() + 3600
        assert fresh_deal.is_expired() is False

    def test_not_expired_when_terminal(self, fresh_deal):
        fresh_deal.expires_at = time.time() - 10
        fresh_deal.state = DealState.SETTLED
        assert fresh_deal.is_expired() is False

    def test_check_expiry_auto_transitions(self, fresh_deal):
        fresh_deal.expires_at = time.time() - 10
        result = fresh_deal.check_expiry()
        assert result is True
        assert fresh_deal.state == DealState.EXPIRED

    def test_check_expiry_not_both_locked(self, fresh_deal):
        """BOTH_LOCKED should NOT auto-expire — funds are committed."""
        fresh_deal.state = DealState.BOTH_LOCKED
        fresh_deal.expires_at = time.time() - 10
        result = fresh_deal.check_expiry()
        assert result is False
        assert fresh_deal.state == DealState.BOTH_LOCKED

    def test_check_expiry_not_settling(self, fresh_deal):
        """SETTLING should NOT auto-expire."""
        fresh_deal.state = DealState.SETTLING
        fresh_deal.expires_at = time.time() - 10
        result = fresh_deal.check_expiry()
        assert result is False
        assert fresh_deal.state == DealState.SETTLING


# ---------------------------------------------------------------------------
# Lock marking
# ---------------------------------------------------------------------------

class TestLockMarking:
    def test_mark_eth_locked(self, fresh_deal):
        fresh_deal.state = DealState.AWAITING_ETH_LOCK
        assert fresh_deal.mark_eth_locked("0xtx1", 1) is True
        assert fresh_deal.eth_tx_hash == "0xtx1"
        assert fresh_deal.eth_deposit_id == 1
        assert fresh_deal.state == DealState.AWAITING_SOST_LOCK

    def test_mark_sost_locked(self, fresh_deal):
        fresh_deal.state = DealState.AWAITING_ETH_LOCK
        assert fresh_deal.mark_sost_locked("txid_sost_1") is True
        assert fresh_deal.sost_lock_txid == "txid_sost_1"
        assert fresh_deal.state == DealState.AWAITING_SOST_LOCK

    def test_both_locked_after_both_marks(self, fresh_deal):
        fresh_deal.state = DealState.AWAITING_ETH_LOCK
        fresh_deal.mark_eth_locked("0xtx1", 1)
        assert fresh_deal.state == DealState.AWAITING_SOST_LOCK
        fresh_deal.mark_sost_locked("txid_sost_1")
        assert fresh_deal.state == DealState.BOTH_LOCKED

    def test_both_locked_sost_then_eth(self, fresh_deal):
        fresh_deal.state = DealState.AWAITING_ETH_LOCK
        fresh_deal.mark_sost_locked("txid_sost_1")
        assert fresh_deal.state == DealState.AWAITING_SOST_LOCK
        fresh_deal.mark_eth_locked("0xtx1", 1)
        assert fresh_deal.state == DealState.BOTH_LOCKED


# ---------------------------------------------------------------------------
# Settlement + refund
# ---------------------------------------------------------------------------

class TestSettleAndRefund:
    def test_settle_happy_path(self, fresh_deal):
        fresh_deal.state = DealState.BOTH_LOCKED
        result = fresh_deal.settle("0xsettle_tx")
        assert result is True
        assert fresh_deal.state == DealState.SETTLED
        assert fresh_deal.settlement_tx_hash == "0xsettle_tx"

    def test_request_refund(self, fresh_deal):
        fresh_deal.state = DealState.AWAITING_ETH_LOCK
        result = fresh_deal.request_refund("timeout")
        assert result is True
        assert fresh_deal.state == DealState.REFUND_PENDING
        assert fresh_deal.refund_reason == "timeout"

    def test_confirm_refund(self, fresh_deal):
        fresh_deal.state = DealState.REFUND_PENDING
        result = fresh_deal.confirm_refund()
        assert result is True
        assert fresh_deal.state == DealState.REFUNDED


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class TestHistory:
    def test_history_records_transitions(self, fresh_deal):
        fresh_deal.transition(DealState.NEGOTIATED, "step1")
        fresh_deal.transition(DealState.AWAITING_ETH_LOCK, "step2")
        assert len(fresh_deal.history) == 2
        assert fresh_deal.history[0]["from"] == "CREATED"
        assert fresh_deal.history[0]["to"] == "NEGOTIATED"
        assert fresh_deal.history[0]["reason"] == "step1"
        assert fresh_deal.history[1]["from"] == "NEGOTIATED"
        assert fresh_deal.history[1]["to"] == "AWAITING_ETH_LOCK"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_serialization(self, fresh_deal):
        d = fresh_deal.to_dict()
        assert d["state"] == "CREATED"
        assert d["pair"] == "SOST/XAUT"
        assert isinstance(d["history"], list)

    def test_to_json_roundtrip(self, fresh_deal):
        j = fresh_deal.to_json()
        parsed = json.loads(j)
        assert parsed["deal_id"] == fresh_deal.deal_id
        assert parsed["state"] == "CREATED"
        assert parsed["amount_sost"] == 100_000_000


# ---------------------------------------------------------------------------
# DealStore
# ---------------------------------------------------------------------------

class TestDealStore:
    def test_deal_store_create_and_get(self, deal_store, deal_defaults):
        deal = deal_store.create(**deal_defaults)
        assert deal_store.get(deal.deal_id) is deal

    def test_deal_store_get_missing(self, deal_store):
        assert deal_store.get("nonexistent") is None

    def test_deal_store_active_deals(self, deal_store, deal_defaults):
        d1 = deal_store.create(**deal_defaults)
        d2 = deal_store.create(**deal_defaults)
        d2.state = DealState.SETTLED
        active = deal_store.active_deals()
        assert d1 in active
        assert d2 not in active

    def test_deal_store_check_all_expiry(self, deal_store, deal_defaults):
        d1 = deal_store.create(**deal_defaults)
        d1.expires_at = time.time() - 10
        d2 = deal_store.create(**deal_defaults)
        d2.expires_at = time.time() + 3600
        expired = deal_store.check_all_expiry()
        assert d1.deal_id in expired
        assert d2.deal_id not in expired

    def test_deal_store_save_load(self, deal_store, deal_defaults, tmp_path):
        d = deal_store.create(**deal_defaults)
        d.transition(DealState.NEGOTIATED, "test")
        path = str(tmp_path / "deals.json")
        deal_store.save(path)

        store2 = DealStore()
        store2.load(path)
        loaded = store2.get(d.deal_id)
        assert loaded is not None
        assert loaded.state == DealState.NEGOTIATED
        assert loaded.pair == "SOST/XAUT"
