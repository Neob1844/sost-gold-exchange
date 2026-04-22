#!/usr/bin/env python3
"""
SOST Gold Exchange — Operator Dashboard API

Minimal Flask REST API for operational monitoring.

Usage:
  python3 -m src.operator.dashboard_api
  python3 -m src.operator.dashboard_api --port 8080

Endpoints:
  GET /health           — status, deal count, position count
  GET /deals            — list all deals
  GET /deals/<deal_id>  — single deal with history
  GET /positions        — list all positions
  GET /audit/<deal_id>  — audit entries for a deal
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
    from flask import Flask, jsonify, abort
except ImportError:
    print("ERROR: Flask is required. Install with: pip install flask")
    sys.exit(1)


# ── Configuration ──

PROJECT_ROOT = _project_root
DEALS_PATH = os.path.join(PROJECT_ROOT, "data", "deals.json")
POSITIONS_PATH = os.path.join(PROJECT_ROOT, "data", "positions.json")
AUDIT_DIR = os.path.join(PROJECT_ROOT, "data", "audit")

app = Flask(__name__)

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
    return jsonify({
        "status": "ok",
        "mode": "alpha",
        "deals": len(deals._deals),
        "positions": len(positions._positions),
        "timestamp": time.time(),
    })


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
    args = parser.parse_args()

    print(f"SOST Gold Exchange — Operator Dashboard")
    print(f"  Listening on http://{args.host}:{args.port}")
    print(f"  Deals:     {DEALS_PATH}")
    print(f"  Positions: {POSITIONS_PATH}")
    print(f"  Audit:     {AUDIT_DIR}")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
