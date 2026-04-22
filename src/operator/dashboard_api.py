#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator Dashboard API

Minimal Flask REST API for operational monitoring.

Usage:
  python3 -m src.operator.dashboard_api
  python3 -m src.operator.dashboard_api --port 8080

Endpoints:
  GET /health                  — service health with component status
  GET /deals                   — list all deals
  GET /deals/<deal_id>         — single deal with history
  GET /deals/live              — non-terminal deals only
  GET /positions               — list all positions
  GET /positions/<id>/lifecycle — lifecycle stage and timing for a position
  GET /audit/<deal_id>         — audit entries for a deal
  GET /sepolia                 — deployed contract addresses and deposit status
  GET /alpha/status            — alpha mode info, limits, participant count
  GET /relay/status            — relay health (placeholder)
  GET /watchers/status         — watcher poll times and error counts
"""

import json
import os
import sys
import argparse
import time
from dataclasses import asdict

# Ensure project root is on sys.path for both direct and -m invocation
_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_this_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.settlement.deal_state_machine import DealStore
from src.positions.position_registry import PositionRegistry
from src.operator.audit_log import AuditLog

try:
    from flask import Flask, jsonify, abort, request
except ImportError:
    print("ERROR: Flask is required. Install with: pip install flask")
    sys.exit(1)


# ── Configuration ──

PROJECT_ROOT = _project_root
DEALS_PATH = os.path.join(PROJECT_ROOT, "data", "deals.json")
POSITIONS_PATH = os.path.join(PROJECT_ROOT, "data", "positions.json")
AUDIT_DIR = os.path.join(PROJECT_ROOT, "data", "audit")

app = Flask(__name__)


# ── CORS ──

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ── Config loading ──

def _load_exchange_config() -> dict:
    """Load exchange config from app.config or from file."""
    cfg = app.config.get("exchange_config")
    if cfg:
        return cfg
    config_path = os.path.join(PROJECT_ROOT, "configs", "live_alpha.local.json")
    if not os.path.exists(config_path):
        config_path = os.path.join(PROJECT_ROOT, "configs", "live_alpha.example.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


# ── Stores (loaded on startup, refreshed per-request for simplicity) ──

def _load_deals():
    store = DealStore()
    if os.path.exists(DEALS_PATH):
        try:
            store.load(DEALS_PATH)
        except Exception:
            pass
    return store


def _load_positions():
    registry = PositionRegistry()
    if os.path.exists(POSITIONS_PATH):
        try:
            registry.load(POSITIONS_PATH)
        except Exception:
            pass
    return registry


def _load_audit():
    audit = AuditLog(log_dir=AUDIT_DIR)
    audit.load()
    return audit


# ── Routes ──

@app.route("/health")
def health():
    deals = _load_deals()
    positions = _load_positions()

    # Use health monitor if available (injected by start_alpha_service)
    health_monitor = app.config.get("health_monitor")
    if health_monitor:
        monitor_data = health_monitor.get_health()
    else:
        monitor_data = {"status": "ok", "components": {}}

    config = _load_exchange_config()
    return jsonify({
        "status": monitor_data["status"],
        "mode": config.get("mode", "alpha"),
        "deals": len(deals._deals),
        "positions": len(positions._positions),
        "uptime_seconds": monitor_data.get("uptime_seconds"),
        "components": monitor_data.get("components", {}),
        "timestamp": time.time(),
    })


@app.route("/sepolia")
def sepolia():
    config = _load_exchange_config()
    eth = config.get("ethereum", {})

    result = {
        "chain_id": eth.get("chain_id"),
        "rpc_url": eth.get("rpc_url"),
        "escrow_address": eth.get("escrow_address"),
        "xaut_address": eth.get("xaut_address"),
        "paxg_address": eth.get("paxg_address"),
        "confirmations": eth.get("confirmations"),
        "poll_interval_seconds": eth.get("poll_interval_seconds", eth.get("poll_interval")),
    }

    # Try to query deposit status from chain
    rpc_url = eth.get("rpc_url")
    escrow = eth.get("escrow_address")
    if rpc_url and escrow:
        try:
            import urllib.request
            # Query getDeposit(0) — selector 0x9a7c4b71
            data = "0x9a7c4b71" + "0" * 64
            payload = json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "method": "eth_call",
                "params": [{"to": escrow, "data": data}, "latest"],
            }).encode()
            req = urllib.request.Request(
                rpc_url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                rpc_result = json.loads(resp.read())
            hex_data = rpc_result.get("result", "0x")
            if hex_data and len(hex_data) > 66:
                depositor = "0x" + hex_data[26:66]
                amount = int(hex_data[130:194], 16) if len(hex_data) >= 194 else 0
                result["first_deposit"] = {
                    "depositor": depositor,
                    "amount_wei": amount,
                }
            else:
                result["first_deposit"] = None
        except Exception as e:
            result["first_deposit"] = {"error": str(e)}

    return jsonify(result)


@app.route("/deals")
def list_deals():
    store = _load_deals()
    result = []
    for deal in store._deals.values():
        d = deal.to_dict()
        d["is_terminal"] = deal.is_terminal()
        d["is_expired"] = deal.is_expired()
        result.append(d)
    return jsonify(result)


@app.route("/deals/<deal_id>")
def show_deal(deal_id):
    store = _load_deals()
    deal = store.get(deal_id)

    # Try prefix match
    if not deal:
        matches = [d for did, d in store._deals.items() if did.startswith(deal_id)]
        if len(matches) == 1:
            deal = matches[0]

    if not deal:
        abort(404, description=f"Deal '{deal_id}' not found")

    audit = _load_audit()
    entries = audit.get_deal_history(deal.deal_id)

    result = deal.to_dict()
    result["is_terminal"] = deal.is_terminal()
    result["is_expired"] = deal.is_expired()
    result["audit"] = [asdict(e) for e in entries]
    return jsonify(result)


@app.route("/positions")
def list_positions():
    registry = _load_positions()
    result = []
    for pos in registry._positions.values():
        d = pos.to_dict()
        d["is_active"] = pos.is_active()
        d["is_matured"] = pos.is_matured()
        d["reward_remaining"] = pos.reward_remaining()
        d["time_remaining"] = pos.time_remaining()
        d["pct_complete"] = round(pos.pct_complete(), 2)
        result.append(d)
    return jsonify(result)


@app.route("/deals/live")
def live_deals():
    store = _load_deals()
    result = []
    for deal in store._deals.values():
        if not deal.is_terminal():
            d = deal.to_dict()
            d["is_terminal"] = False
            d["is_expired"] = deal.is_expired()
            result.append(d)
    return jsonify(result)


@app.route("/positions/<position_id>/lifecycle")
def position_lifecycle(position_id):
    registry = _load_positions()
    pos = registry.get(position_id)

    # Try prefix match
    if not pos:
        matches = [(pid, p) for pid, p in registry._positions.items()
                    if pid.startswith(position_id)]
        if len(matches) == 1:
            pos = matches[0][1]

    if not pos:
        abort(404, description=f"Position '{position_id}' not found")

    # Determine lifecycle stage
    status = pos.status.value
    if status == "REDEEMED":
        stage = "REDEEMED"
    elif status == "SLASHED":
        stage = "SLASHED"
    elif status == "MATURED" or pos.is_matured():
        stage = "MATURE"
    elif pos.time_remaining() < 7 * 86400:
        stage = "NEARING_EXPIRY"
    else:
        stage = "ACTIVE"

    return jsonify({
        "position_id": pos.position_id,
        "stage": stage,
        "status": status,
        "time_remaining": pos.time_remaining(),
        "pct_complete": round(pos.pct_complete(), 2),
        "start_time": pos.start_time,
        "expiry_time": pos.expiry_time,
        "is_matured": pos.is_matured() or status == "MATURED",
        "reward_total_sost": pos.reward_total_sost,
        "reward_claimed_sost": pos.reward_claimed_sost,
        "reward_remaining_sost": pos.reward_remaining(),
    })


@app.route("/alpha/status")
def alpha_status():
    config = _load_exchange_config()
    mode = config.get("mode", "unknown")

    # Load alpha limits
    alpha_path = os.path.join(PROJECT_ROOT, "configs", "limited_public_alpha.json")
    limits = {}
    if os.path.exists(alpha_path):
        with open(alpha_path) as f:
            alpha_cfg = json.load(f)
        limits = alpha_cfg.get("limits", {})

    # Count participants from positions
    registry = _load_positions()
    owners = set(p.owner for p in registry._positions.values())

    return jsonify({
        "mode": mode,
        "is_alpha": "alpha" in mode.lower(),
        "limits": limits,
        "participant_count": len(owners),
        "position_count": len(registry._positions),
        "timestamp": time.time(),
    })


@app.route("/relay/status")
def relay_status():
    health_monitor = app.config.get("health_monitor")
    if health_monitor:
        health_data = health_monitor.get_health()
        relay_comp = health_data.get("components", {}).get("relay")
        if relay_comp:
            return jsonify({
                "running": True,
                "last_poll": relay_comp.get("last_poll"),
                "age_seconds": relay_comp.get("age_seconds"),
                "stale": relay_comp.get("stale", False),
                "errors": relay_comp.get("errors", 0),
            })
    return jsonify({
        "running": False,
        "message": "Relay not registered with health monitor",
    })


@app.route("/watchers/status")
def watchers_status():
    health_monitor = app.config.get("health_monitor")
    if not health_monitor:
        return jsonify({
            "status": "unknown",
            "message": "Health monitor not available",
        })

    health_data = health_monitor.get_health()
    components = health_data.get("components", {})

    watcher_names = ["eth_watcher", "sost_watcher"]
    watchers = {}
    for name in watcher_names:
        comp = components.get(name)
        if comp:
            watchers[name] = {
                "last_poll": comp.get("last_poll"),
                "age_seconds": comp.get("age_seconds"),
                "expected_interval": comp.get("expected_interval"),
                "stale": comp.get("stale", False),
                "errors": comp.get("errors", 0),
            }
        else:
            watchers[name] = {"registered": False}

    return jsonify({
        "status": health_data.get("status", "unknown"),
        "watchers": watchers,
    })


@app.route("/audit/<deal_id>")
def deal_audit(deal_id):
    audit = _load_audit()
    entries = audit.get_deal_history(deal_id)

    # Try prefix match if no exact match
    if not entries:
        all_entries = audit.get_all()
        entries = [e for e in all_entries if e.deal_id.startswith(deal_id)]

    if not entries:
        abort(404, description=f"No audit entries for deal '{deal_id}'")

    return jsonify([asdict(e) for e in entries])


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="SOST Operator Dashboard API")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--config", default="", help="Config JSON path")
    args = parser.parse_args()

    # Load config from file if provided
    if args.config and os.path.exists(args.config):
        with open(args.config) as f:
            app.config["exchange_config"] = json.load(f)

    print(f"SOST Gold Exchange — Operator Dashboard")
    print(f"  Listening on http://{args.host}:{args.port}")
    print(f"  Deals:     {DEALS_PATH}")
    print(f"  Positions: {POSITIONS_PATH}")
    print(f"  Audit:     {AUDIT_DIR}")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
