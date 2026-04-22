#!/usr/bin/env python3
"""
SOST Gold Exchange — Alpha Service Launcher

Starts the watcher service and dashboard API together in a single process.

Usage:
    python3 scripts/start_alpha_service.py
    python3 scripts/start_alpha_service.py --config configs/live_alpha.local.json
    python3 scripts/start_alpha_service.py --port 8080
"""

import os
import sys
import signal
import argparse
import logging
import threading

# Ensure project root on sys.path
_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_this_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.services.watcher_service import (
    load_config, setup_logging, WatcherService, C_BOLD, C_OK, C_RESET,
)
from src.services.health_monitor import HealthMonitor

log = logging.getLogger("launcher")


def start_dashboard(config: dict, health: HealthMonitor, host: str, port: int):
    """Import and run the Flask dashboard in a daemon thread."""
    # Patch dashboard module globals before starting
    from src.operator import dashboard_api as dash

    data_cfg = config.get("data", {})
    dash.DEALS_PATH = os.path.join(_project_root, data_cfg.get("deals_path", "data/deals.json"))
    dash.POSITIONS_PATH = os.path.join(_project_root, data_cfg.get("positions_path", "data/positions.json"))
    dash.AUDIT_DIR = os.path.join(_project_root, data_cfg.get("audit_dir", "data/audit"))

    # Inject health monitor and config into the app
    dash.app.config["health_monitor"] = health
    dash.app.config["exchange_config"] = config

    log.info("Dashboard API on http://%s:%d", host, port)
    dash.app.run(host=host, port=port, debug=False, use_reloader=False)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="SOST Alpha Service Launcher")
    parser.add_argument("--config", default="", help="Config JSON path")
    parser.add_argument("--port", type=int, default=8080, help="Dashboard port (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard host (default: 127.0.0.1)")
    args = parser.parse_args()

    config = load_config(args.config)
    health = HealthMonitor()

    print(f"\n{C_BOLD}{C_OK}SOST Gold Exchange — Alpha Service{C_RESET}")
    print(f"  Mode:      {config.get('mode', 'unknown')}")
    print(f"  Dashboard: http://{args.host}:{args.port}")
    print(f"  ETH RPC:   {config['ethereum']['rpc_url']}")
    print(f"  Escrow:    {config['ethereum']['escrow_address']}")
    print()

    # Start watcher service
    service = WatcherService(config, health)
    service.start()

    # Start dashboard in daemon thread
    dash_thread = threading.Thread(
        target=start_dashboard,
        args=(config, health, args.host, args.port),
        name="dashboard",
        daemon=True,
    )
    dash_thread.start()

    # Handle shutdown
    def _signal_handler(sig, frame):
        log.info("Received signal %s — shutting down", sig)
        service.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    service.wait()


if __name__ == "__main__":
    main()
