#!/usr/bin/env python3
"""
SOST Gold Exchange — Reward Right Trade via Relay

Demonstrates the relay-based flow for trading reward rights from a position:
  1. Start relay HTTP API as subprocess (localhost:3000)
  2. Seller creates signed offer for POSITION_REWARD_RIGHT, POSTs to relay /submit
  3. Buyer creates signed accept, POSTs to relay /submit
  4. Exchange reads deal from relay GET /deals/:id
  5. Executes reward split
  6. Posts settlement_notice to relay
  7. Prints full audit trail

Falls back to direct mode if relay is not available.

Usage:
  python3 scripts/demo_relay_position_reward_trade.py
"""

import hashlib
import json
import time
import sys
import os
import subprocess
import signal
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import Position, ContractType, BackingType, PositionStatus, RightType
from src.positions.position_transfer import PositionTransferEngine
from src.positions.position_settlement import PositionSettlement
from src.positions.position_pricing import value_position
from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.operator.audit_log import AuditLog

# ── ANSI colors ──
R = "\033[91m"
G = "\033[92m"
C = "\033[96m"
Y = "\033[93m"
O = "\033[38;5;208m"
W = "\033[97m"
D = "\033[90m"
B = "\033[1m"
X = "\033[0m"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMS_ROOT = os.path.join(os.path.dirname(PROJECT_ROOT), "sost-comms-private")

RELAY_URL = "http://localhost:3000"

SELLER_SOST = "sost1seller_alpha_test_001"
BUYER_SOST = "sost1buyer_alpha_test_001"
SELLER_ETH = "0xSellerEthAddress0000000000000000000000"
BUYER_ETH = "0xBuyerEthAddress00000000000000000000000"

relay_proc = None


def banner():
    print(f"""
{Y}{'='*64}{X}
{O}{B}  SOST GOLD EXCHANGE — RELAY REWARD RIGHT TRADE DEMO{X}
{Y}  Relay-based: offer -> accept -> settlement -> reward split{X}
{Y}{'='*64}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*54}{X}")


def info(label, value):
    print(f"  {D}{label}:{X} {G}{value}{X}")


def state_change(old, new):
    print(f"  {Y}state:{X} {O}{old}{X} {D}->{X} {G}{new}{X}")


def derive_deal_id(offer_id, accept_id):
    return hashlib.sha256(f"{offer_id}:{accept_id}".encode()).hexdigest()[:16]


# ── Relay helpers ──

def start_relay():
    """Start the relay HTTP API as a subprocess. Returns the process or None."""
    global relay_proc
    relay_script = os.path.join(COMMS_ROOT, "src", "relay", "http_api.ts")
    if not os.path.exists(relay_script):
        return None

    env = dict(os.environ, PORT="3000")
    try:
        relay_proc = subprocess.Popen(
            ["npx", "ts-node", relay_script],
            cwd=COMMS_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(20):
            time.sleep(0.3)
            try:
                req = urllib.request.Request(f"{RELAY_URL}/health")
                resp = urllib.request.urlopen(req, timeout=2)
                if resp.status == 200:
                    return relay_proc
            except (urllib.error.URLError, ConnectionError, OSError):
                continue
        return None
    except FileNotFoundError:
        return None


def stop_relay():
    """Kill the relay subprocess."""
    global relay_proc
    if relay_proc:
        try:
            relay_proc.send_signal(signal.SIGTERM)
            relay_proc.wait(timeout=5)
        except Exception:
            relay_proc.kill()
        relay_proc = None


def relay_post(endpoint, payload):
    """POST JSON to relay."""
    url = f"{RELAY_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return json.loads(body) if body else {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def relay_get(endpoint):
    """GET from relay."""
    url = f"{RELAY_URL}{endpoint}"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def relay_available():
    """Check if relay is responding."""
    try:
        req = urllib.request.Request(f"{RELAY_URL}/health")
        resp = urllib.request.urlopen(req, timeout=2)
        return resp.status == 200
    except Exception:
        return False


def make_dummy_sig_payload(msg):
    """Create a dummy signed payload for relay submission (demo mode)."""
    msg_json = json.dumps(msg, sort_keys=True)
    msg_hash = hashlib.sha256(msg_json.encode()).hexdigest()
    return {
        "message": msg,
        "signature": msg_hash,
        "sender_pubkey_hex": "0" * 64,
    }


def run():
    audit_dir = os.path.join(PROJECT_ROOT, "data", "audit_relay_reward_trade")
    registry = PositionRegistry()
    audit = AuditLog(log_dir=audit_dir)
    transfer_engine = PositionTransferEngine(registry)
    pos_settlement = PositionSettlement(registry, transfer_engine, audit)
    deal_store = DealStore()

    use_relay = False

    # ── Step 1: Start relay ──
    step(1, "Start relay HTTP API (localhost:3000)")

    proc = start_relay()
    if proc and relay_available():
        use_relay = True
        info("relay", "STARTED (pid={})".format(proc.pid))
        health = relay_get("/health")
        info("health", json.dumps(health))
    else:
        stop_relay()
        print(f"  {Y}{B}RELAY NOT AVAILABLE — falling back to direct mode{X}")
        print(f"  {D}To use relay mode, ensure sost-comms-private is set up{X}")
        print(f"  {D}and ts-node is available: cd ../sost-comms-private && npm install{X}")

    # ── Step 2: Create position with rewards ──
    step(2, "Load position with rewards")

    position = registry.create_model_b(
        owner=SELLER_SOST,
        token="XAUT",
        amount=1_000_000_000_000_000_000,
        bond_sost=50_000_000,
        duration_seconds=365 * 86400,
        reward_total=10_000_000,
        eth_deposit_id=99,
        eth_tx="0xreward_position_tx",
    )

    info("position_id", position.position_id)
    info("owner", position.owner)
    info("reward_total", str(position.reward_total_sost))
    info("reward_remaining", str(position.reward_remaining()))
    info("right_type", position.right_type.value)

    # ── Step 3: Seller creates signed offer for POSITION_REWARD_RIGHT ──
    step(3, "Seller creates signed offer for POSITION_REWARD_RIGHT")

    reward_price = position.reward_remaining() // 2
    now = time.time()
    expiry_seconds = 3600

    offer_payload_str = (
        f"1|position_offer|POSITION_REWARD_RIGHT|{position.position_id}|"
        f"{SELLER_SOST}|{reward_price}|"
        f"{int(now + expiry_seconds)}"
    )
    offer_hash = hashlib.sha256(offer_payload_str.encode()).hexdigest()
    offer_id = offer_hash[:16]

    offer_msg = {
        "version": 1,
        "type": "trade_offer",
        "offer_id": offer_id,
        "pair": "SOST/XAUT",
        "side": "sell",
        "amount_sost": str(reward_price),
        "amount_gold": "0",
        "price": "0",
        "maker_sost_addr": SELLER_SOST,
        "maker_eth_addr": SELLER_ETH,
        "expires_at": int(now + expiry_seconds),
        "settlement_mode": "escrow_bilateral",
        "nonce": hashlib.sha256(f"nonce_offer_{offer_id}".encode()).hexdigest()[:32],
        "created_at": int(now),
        "asset_type": "POSITION_REWARD_RIGHT",
        "position_id": position.position_id,
        "price_sost": str(reward_price),
    }

    if use_relay:
        payload = make_dummy_sig_payload(offer_msg)
        result = relay_post("/submit", payload)
        info("relay_submit", json.dumps(result))
    else:
        info("direct_mode", "offer created locally")

    info("offer_id", offer_id)
    info("trade_type", "POSITION_REWARD_RIGHT")
    info("seller", SELLER_SOST)
    info("reward_price_sost", str(reward_price))
    info("canonical_hash", offer_hash[:32] + "...")

    # ── Step 4: Buyer creates signed accept ──
    step(4, "Buyer creates signed accept")

    accept_payload_str = (
        f"1|position_accept|{offer_id}|{BUYER_SOST}|"
        f"{reward_price}|{int(now)}"
    )
    accept_hash = hashlib.sha256(accept_payload_str.encode()).hexdigest()
    accept_id = accept_hash[:16]
    deal_id = derive_deal_id(offer_id, accept_id)

    accept_msg = {
        "version": 1,
        "type": "trade_accept",
        "accept_id": accept_id,
        "offer_id": offer_id,
        "deal_id": deal_id,
        "taker_sost_addr": BUYER_SOST,
        "taker_eth_addr": BUYER_ETH,
        "fill_amount_sost": str(reward_price),
        "fill_amount_gold": "0",
        "accepted_at": int(now),
        "nonce": hashlib.sha256(f"nonce_accept_{accept_id}".encode()).hexdigest()[:32],
        "asset_type": "POSITION_REWARD_RIGHT",
        "position_id": position.position_id,
    }

    if use_relay:
        payload = make_dummy_sig_payload(accept_msg)
        result = relay_post("/submit", payload)
        info("relay_submit", json.dumps(result))
    else:
        info("direct_mode", "accept created locally")

    info("accept_id", accept_id)
    info("buyer", BUYER_SOST)
    info("deal_id", deal_id)

    # ── Step 5: Exchange reads deal from relay ──
    step(5, "Exchange reads deal from relay")

    if use_relay:
        deal_data = relay_get(f"/deals/{deal_id}")
        info("relay_deal", json.dumps(deal_data))
    else:
        info("direct_mode", f"deal {deal_id} constructed locally")

    # ── Step 6: Create deal, transition to BOTH_LOCKED ──
    step(6, "Create deal, transition to BOTH_LOCKED (simulated)")

    deal = deal_store.create(
        deal_id=deal_id,
        pair="SOST/REWARD",
        side="sell",
        amount_sost=reward_price,
        amount_gold=0,
        maker_sost_addr=SELLER_SOST,
        taker_sost_addr=BUYER_SOST,
        maker_eth_addr=SELLER_ETH,
        taker_eth_addr=BUYER_ETH,
    )

    deal.transition(DealState.NEGOTIATED, "reward offer accepted via relay")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting payment lock")
    deal.mark_eth_locked("0x" + hashlib.sha256(b"reward_eth").hexdigest(), 99)
    deal.mark_sost_locked(hashlib.sha256(b"reward_sost").hexdigest())

    state_change("CREATED", "BOTH_LOCKED")
    info("deal_state", deal.state.value)

    audit.log_event(deal_id, "deal_created", f"reward_split pos={position.position_id}")
    audit.log_event(deal_id, "relay_sourced", f"deal read from relay /deals/{deal_id}")
    audit.log_event(deal_id, "both_locked", "payment confirmed")

    # ── Step 7: Execute reward split ──
    step(7, "Execute reward split via PositionSettlement.settle_reward_split()")

    parent_reward_before = position.reward_remaining()
    info("parent_reward_before", str(parent_reward_before))

    settled = pos_settlement.settle_reward_split(deal, position.position_id)
    info("settlement_result", "SUCCESS" if settled else "FAILED")

    # ── Step 8: Verify child position created with reward ──
    step(8, "Verify child position created with reward")

    buyer_positions = registry.by_owner(BUYER_SOST)
    if buyer_positions:
        child = buyer_positions[0]
        info("child_position_id", child.position_id)
        info("child_owner", child.owner)
        info("child_right_type", child.right_type.value)
        info("child_reward_total", str(child.reward_total_sost))
        info("child_parent_id", str(child.parent_position_id))

        if child.right_type == RightType.REWARD_RIGHT:
            print(f"  {G}{B}VERIFIED: Child has REWARD_RIGHT type{X}")
        else:
            print(f"  {R}{B}FAILED: Child right_type is {child.right_type.value}{X}")

        if child.reward_total_sost == parent_reward_before:
            print(f"  {G}{B}VERIFIED: Child inherited full remaining reward{X}")
        else:
            print(f"  {R}{B}MISMATCH: child={child.reward_total_sost} expected={parent_reward_before}{X}")
    else:
        print(f"  {R}{B}FAILED: No child position found for buyer{X}")

    # ── Step 9: Verify parent reward zeroed ──
    step(9, "Verify parent reward zeroed")

    parent = registry.get(position.position_id)
    info("parent_reward_total", str(parent.reward_total_sost))
    info("parent_reward_claimed", str(parent.reward_claimed_sost))
    info("parent_reward_remaining", str(parent.reward_remaining()))

    if parent.reward_remaining() == 0:
        print(f"  {G}{B}VERIFIED: Parent reward zeroed (total = claimed){X}")
    else:
        print(f"  {R}{B}FAILED: Parent still has {parent.reward_remaining()} reward remaining{X}")

    # ── Step 10: Post settlement notice to relay ──
    step(10, "Post settlement notice to relay")

    child_id = buyer_positions[0].position_id if buyer_positions else "unknown"
    notice = {
        "type": "REWARD_SPLIT_SETTLED",
        "deal_id": deal_id,
        "parent_position_id": position.position_id,
        "child_position_id": child_id,
        "seller": SELLER_SOST,
        "buyer": BUYER_SOST,
        "reward_amount": parent_reward_before,
        "price_sost": reward_price,
        "settlement_tx": deal.settlement_tx_hash,
        "timestamp": time.time(),
    }

    if use_relay:
        notice_msg = {
            "version": 1,
            "type": "settlement_notice",
            "notice_id": hashlib.sha256(f"notice_{deal_id}".encode()).hexdigest()[:16],
            "deal_id": deal_id,
            "outcome": "settled",
            "eth_tx_hash": deal.settlement_tx_hash,
            "sost_txid": None,
            "settlement_ref": position.position_id,
            "detail": f"REWARD_SPLIT {SELLER_SOST} -> {BUYER_SOST} child={child_id}",
            "issued_at": int(time.time()),
        }
        payload = make_dummy_sig_payload(notice_msg)
        result = relay_post("/submit", payload)
        info("relay_notice", json.dumps(result))
    else:
        info("direct_mode", "settlement notice emitted locally")

    print(f"  {D}{json.dumps(notice, indent=4)}{X}")

    # ── Step 11: Audit log ──
    step(11, "Complete audit log")

    for entry in audit.get_deal_history(deal_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:28s}{X} {D}{entry.detail[:60]}{X}")

    # ── Done ──
    print(f"\n{G}{'='*64}{X}")
    print(f"{G}{B}  RELAY REWARD RIGHT TRADE DEMO COMPLETE{X}")
    print(f"{G}{'='*64}{X}")

    mode_label = "relay" if use_relay else "direct (fallback)"
    transitions = len(deal.history)
    print(f"\n{D}Mode: {mode_label}{X}")
    print(f"{D}Deal {deal_id} settled in {transitions} transitions.{X}")
    print(f"{D}Reward split: parent={position.position_id} -> child={child_id}{X}\n")


if __name__ == "__main__":
    try:
        banner()
        run()
    finally:
        stop_relay()
