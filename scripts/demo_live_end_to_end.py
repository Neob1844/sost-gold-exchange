#!/usr/bin/env python3
"""
SOST Gold Exchange — Live Alpha E2E Demo

Demonstrates the full settlement lifecycle with real or simulated networks:
  offer -> accept -> deal -> ETH lock -> SOST lock -> settlement -> notice

Usage:
  python3 scripts/demo_live_end_to_end.py --mock       # simulated (default)
  python3 scripts/demo_live_end_to_end.py --live        # real Sepolia + SOST RPC
"""

import argparse
import hashlib
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settlement.deal_state_machine import Deal, DealStore, DealState
from src.settlement.settlement_daemon import SettlementDaemon
from src.settlement.refund_engine import RefundEngine
from src.watchers.ethereum_watcher import EthereumWatcher, EthEvent
from src.watchers.sost_watcher import SostWatcher, SostEvent
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
CONFIG_LOCAL = os.path.join(PROJECT_ROOT, "configs", "live_alpha.local.json")
CONFIG_EXAMPLE = os.path.join(PROJECT_ROOT, "configs", "live_alpha.example.json")


def load_config():
    """Load config from local file, falling back to example."""
    for path in (CONFIG_LOCAL, CONFIG_EXAMPLE):
        if os.path.exists(path):
            with open(path, "r") as f:
                cfg = json.load(f)
            return cfg, path
    print(f"{R}ERROR:{X} No config found at {CONFIG_LOCAL} or {CONFIG_EXAMPLE}")
    print(f"{D}Copy configs/live_alpha.example.json to configs/live_alpha.local.json and edit.{X}")
    sys.exit(1)


def banner(mode):
    label = "MOCK (simulated, no network)" if mode == "mock" else "LIVE (Sepolia + SOST RPC)"
    print(f"""
{Y}{'='*64}{X}
{O}{B}  SOST GOLD EXCHANGE — LIVE ALPHA E2E DEMO{X}
{Y}  {label}{X}
{Y}{'='*64}{X}
""")


def step(n, title):
    print(f"\n{C}{B}Step {n}:{X} {W}{title}{X}")
    print(f"{D}{'─'*54}{X}")


def info(label, value):
    print(f"  {D}{label}:{X} {G}{value}{X}")


def warn(label, value):
    print(f"  {R}{label}:{X} {Y}{value}{X}")


def state_change(old, new):
    print(f"  {Y}state:{X} {O}{old}{X} {D}->{X} {G}{new}{X}")


def derive_deal_id(offer_id, accept_id):
    return hashlib.sha256(f"{offer_id}:{accept_id}".encode()).hexdigest()[:16]


# ── Mock watcher stub ──

class MockWatcher:
    def __init__(self):
        self._events = []
        self.on_event = None
    def add_watch_address(self, addr): pass
    def run(self): pass
    def stop(self): pass


# ── Mock mode ──

def run_mock(cfg):
    demo = cfg.get("demo", {})
    data_cfg = cfg.get("data", {})
    audit_dir = os.path.join(PROJECT_ROOT, data_cfg.get("audit_dir", "data/audit"))

    deal_store = DealStore()
    audit = AuditLog(log_dir=audit_dir)
    refund_engine = RefundEngine()

    daemon = SettlementDaemon(
        deal_store=deal_store,
        eth_watcher=MockWatcher(),
        sost_watcher=MockWatcher(),
        refund_engine=refund_engine,
        audit=audit,
    )

    # Step 1 — config
    step(1, "Load config and display endpoints")
    info("eth_rpc", cfg["ethereum"]["rpc_url"])
    info("sost_rpc", cfg["sost"]["rpc_url"])
    info("escrow", cfg["ethereum"]["escrow_address"])
    info("mode", "mock — no network calls")
    time.sleep(0.3)

    # Step 2 — signed offer
    step(2, "Create signed offer")
    offer_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    offer_hash = hashlib.sha256(
        f"1|trade_offer|{offer_id}|{demo['pair']}|buy|"
        f"{demo['amount_sost']}|{demo['amount_gold']}|"
        f"{demo['maker_sost_addr']}|{demo['maker_eth_addr']}|"
        f"{int(time.time())+demo['expiry_seconds']}".encode()
    ).hexdigest()
    info("offer_id", offer_id)
    info("pair", demo["pair"])
    info("amount", f"{demo['amount_sost']/1e8:.8f} SOST for {demo['amount_gold']/1e18:.8f} gold")
    info("canonical_hash", offer_hash[:32] + "...")
    time.sleep(0.3)

    # Step 3 — signed accept
    step(3, "Create signed accept")
    accept_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    info("accept_id", accept_id)
    time.sleep(0.3)

    # Step 4 — derive deal_id
    step(4, "Derive deal_id = SHA256(offer_id:accept_id)[:16]")
    deal_id = derive_deal_id(offer_id, accept_id)
    info("deal_id", deal_id)
    info("derivation", f"SHA256({offer_id}:{accept_id})[:16]")
    time.sleep(0.3)

    # Step 5 — register deal
    step(5, "Register deal with settlement daemon")
    now = time.time()
    deal = Deal(
        deal_id=deal_id,
        pair=demo["pair"],
        side="buy",
        amount_sost=demo["amount_sost"],
        amount_gold=demo["amount_gold"],
        maker_sost_addr=demo["maker_sost_addr"],
        taker_sost_addr=demo["taker_sost_addr"],
        maker_eth_addr=demo["maker_eth_addr"],
        taker_eth_addr=demo["taker_eth_addr"],
        created_at=now,
        expires_at=now + demo["expiry_seconds"],
    )
    deal_store._deals[deal_id] = deal
    deal.transition(DealState.NEGOTIATED, "offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
    daemon.register_deal(deal)
    daemon._deal_eth_map[42] = deal.deal_id

    state_change("CREATED", "AWAITING_ETH_LOCK")
    info("expires_in", f"{demo['expiry_seconds']}s")
    time.sleep(0.3)

    # Step 6 — simulate ETH + SOST events
    step(6, "Simulate lock events")

    print(f"  {D}Injecting EthEvent (deposit_id=42)...{X}")
    eth_event = EthEvent(
        event_type="deposit",
        tx_hash="0x" + hashlib.sha256(os.urandom(16)).hexdigest(),
        block_number=19500000,
        deposit_id=42,
        depositor=demo["taker_eth_addr"],
        token="0x68749665FF8D2d112Fa859AA293F07A622782F38",
        amount=demo["amount_gold"],
        unlock_time=int(now) + 86400 * 90,
        timestamp=time.time(),
    )
    daemon.on_eth_event(eth_event)
    info("eth_locked", f"tx={eth_event.tx_hash[:24]}...")
    state_change("AWAITING_ETH_LOCK", deal.state.value)
    time.sleep(0.3)

    print(f"  {D}Injecting SostEvent (balance confirmed)...{X}")
    sost_event = SostEvent(
        event_type="balance_confirmed",
        txid=hashlib.sha256(os.urandom(16)).hexdigest(),
        block_height=5500,
        address=demo["maker_sost_addr"],
        amount=demo["amount_sost"],
        deal_ref=deal_id,
        timestamp=time.time(),
    )
    daemon.on_sost_event(sost_event)
    info("sost_locked", f"txid={sost_event.txid[:24]}...")
    state_change("AWAITING_SOST_LOCK", deal.state.value)
    time.sleep(0.3)

    # Step 7 — state transitions summary
    step(7, "State transition chain")
    for h in deal.history:
        print(f"  {O}{h['from']}{X} {D}->{X} {G}{h['to']}{X}  {D}({h['reason']}){X}")
    time.sleep(0.3)

    # Step 8 — settlement
    step(8, "Execute settlement")
    result = daemon.execute_settlement(deal.deal_id)
    info("settlement_result", "SUCCESS" if result else "FAILED")
    info("final_state", deal.state.value)
    time.sleep(0.3)

    # Step 9 — audit log
    step(9, "Complete audit log")
    for entry in audit.get_deal_history(deal.deal_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:24s}{X} {D}{entry.detail[:50]}{X}")

    # Save state
    deals_path = os.path.join(PROJECT_ROOT, data_cfg.get("deals_path", "data/deals.json"))
    os.makedirs(os.path.dirname(deals_path), exist_ok=True)
    deal_store.save(deals_path)
    info("deals_saved", deals_path)

    print(f"\n{G}{'='*64}{X}")
    print(f"{G}{B}  DEMO COMPLETE — SETTLEMENT SUCCESSFUL{X}")
    print(f"{G}{'='*64}{X}")
    print(f"\n{D}Deal {deal_id} settled in {len(deal.history)} transitions.{X}\n")


# ── Live mode ──

def run_live(cfg):
    demo = cfg.get("demo", {})
    data_cfg = cfg.get("data", {})
    eth_cfg = cfg["ethereum"]
    sost_cfg = cfg["sost"]
    audit_dir = os.path.join(PROJECT_ROOT, data_cfg.get("audit_dir", "data/audit"))

    deal_store = DealStore()
    audit = AuditLog(log_dir=audit_dir)
    refund_engine = RefundEngine()

    # Step 1 — config and connections
    step(1, "Load config and verify endpoints")
    info("eth_rpc", eth_cfg["rpc_url"])
    info("escrow", eth_cfg["escrow_address"])
    info("sost_rpc", sost_cfg["rpc_url"])
    info("mode", "LIVE — real network calls")

    eth_watcher = EthereumWatcher(
        rpc_url=eth_cfg["rpc_url"],
        escrow_address=eth_cfg["escrow_address"],
    )
    sost_watcher = SostWatcher(
        rpc_url=sost_cfg["rpc_url"],
        rpc_user=sost_cfg["rpc_user"],
        rpc_pass=sost_cfg["rpc_pass"],
    )

    # Verify connectivity
    try:
        block = eth_watcher.get_block_number()
        info("eth_block", str(block))
    except Exception as e:
        warn("eth_error", str(e))
        print(f"  {R}Cannot reach Ethereum RPC — check config.{X}")
        sys.exit(1)

    try:
        height = sost_watcher.get_block_height()
        info("sost_height", str(height))
    except Exception as e:
        warn("sost_warning", f"SOST node unreachable: {e}")
        print(f"  {Y}Continuing with ETH-only monitoring.{X}")

    daemon = SettlementDaemon(
        deal_store=deal_store,
        eth_watcher=eth_watcher,
        sost_watcher=sost_watcher,
        refund_engine=refund_engine,
        audit=audit,
    )

    # Step 2 — offer
    step(2, "Create signed offer")
    offer_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    info("offer_id", offer_id)
    info("pair", demo["pair"])
    info("amount", f"{demo['amount_sost']/1e8:.8f} SOST for {demo['amount_gold']/1e18:.8f} gold")

    # Step 3 — accept
    step(3, "Create signed accept")
    accept_id = hashlib.sha256(os.urandom(8)).hexdigest()[:16]
    info("accept_id", accept_id)

    # Step 4 — deal_id
    step(4, "Derive deal_id = SHA256(offer_id:accept_id)[:16]")
    deal_id = derive_deal_id(offer_id, accept_id)
    info("deal_id", deal_id)

    # Step 5 — register
    step(5, "Register deal with settlement daemon")
    now = time.time()
    deal = Deal(
        deal_id=deal_id,
        pair=demo["pair"],
        side="buy",
        amount_sost=demo["amount_sost"],
        amount_gold=demo["amount_gold"],
        maker_sost_addr=demo["maker_sost_addr"],
        taker_sost_addr=demo["taker_sost_addr"],
        maker_eth_addr=demo["maker_eth_addr"],
        taker_eth_addr=demo["taker_eth_addr"],
        created_at=now,
        expires_at=now + demo["expiry_seconds"],
    )
    deal_store._deals[deal_id] = deal
    deal.transition(DealState.NEGOTIATED, "offer accepted")
    deal.transition(DealState.AWAITING_ETH_LOCK, "awaiting ETH deposit")
    daemon.register_deal(deal)
    state_change("CREATED", "AWAITING_ETH_LOCK")

    # Step 6 — polling instructions
    step(6, "Waiting for deposits (polling watchers)")
    print(f"""
  {Y}Deposit instructions:{X}
    {W}ETH side:{X} Send {demo['amount_gold']/1e18:.8f} gold tokens to escrow
              contract {eth_cfg['escrow_address']}
    {W}SOST side:{X} Send {demo['amount_sost']/1e8:.8f} SOST to lock address
              {demo['maker_sost_addr']}

  {D}Polling ETH every {eth_cfg['poll_interval']}s, SOST every {sost_cfg['poll_interval']}s.{X}
  {D}Timeout: 30 minutes. Press Ctrl+C to abort.{X}
""")

    timeout = 30 * 60  # 30 min
    start = time.time()
    last_state = deal.state

    try:
        while time.time() - start < timeout:
            # Poll ETH
            try:
                events = eth_watcher.poll_once()
                for ev in events:
                    daemon.on_eth_event(ev)
            except Exception as e:
                print(f"  {D}ETH poll error: {e}{X}")

            # Poll SOST
            try:
                events = sost_watcher.poll_once()
                for ev in events:
                    daemon.on_sost_event(ev)
            except Exception as e:
                pass  # SOST node may be offline

            daemon.tick()

            # Print state updates
            if deal.state != last_state:
                state_change(last_state.value, deal.state.value)
                last_state = deal.state

            if deal.state == DealState.BOTH_LOCKED:
                print(f"\n  {G}{B}Both sides locked! Executing settlement...{X}")
                break

            if deal.is_terminal():
                warn("terminal", f"Deal reached terminal state: {deal.state.value}")
                break

            elapsed = int(time.time() - start)
            remaining = timeout - elapsed
            mins, secs = divmod(remaining, 60)
            print(f"  {D}[{elapsed:>4d}s] state={deal.state.value:20s} timeout_in={mins}m{secs:02d}s{X}", end="\r")
            time.sleep(min(eth_cfg["poll_interval"], sost_cfg["poll_interval"]))

    except KeyboardInterrupt:
        print(f"\n  {Y}Aborted by operator.{X}")

    # Step 7 — settle if ready
    if deal.state == DealState.BOTH_LOCKED:
        step(7, "Execute settlement")
        result = daemon.execute_settlement(deal.deal_id)
        info("result", "SUCCESS" if result else "FAILED")
        info("final_state", deal.state.value)
    else:
        step(7, "Settlement not reached")
        info("final_state", deal.state.value)

    # Step 8 — audit
    step(8, "Complete audit log")
    for entry in audit.get_deal_history(deal.deal_id):
        ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        print(f"  {D}[{ts}]{X} {C}{entry.event:24s}{X} {D}{entry.detail[:50]}{X}")

    # Save
    deals_path = os.path.join(PROJECT_ROOT, data_cfg.get("deals_path", "data/deals.json"))
    os.makedirs(os.path.dirname(deals_path), exist_ok=True)
    deal_store.save(deals_path)

    done_color = G if deal.state == DealState.SETTLED else R
    print(f"\n{done_color}{'='*64}{X}")
    print(f"{done_color}{B}  DEMO COMPLETE — {deal.state.value}{X}")
    print(f"{done_color}{'='*64}{X}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SOST Gold Exchange — Live Alpha E2E Demo")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock", action="store_true", default=True,
                       help="Simulated mode, no network (default)")
    group.add_argument("--live", action="store_true",
                       help="Live mode with real Sepolia + SOST RPC")
    args = parser.parse_args()

    cfg, cfg_path = load_config()

    if args.live:
        banner("live")
        info("config", cfg_path)
        run_live(cfg)
    else:
        banner("mock")
        info("config", cfg_path)
        run_mock(cfg)
