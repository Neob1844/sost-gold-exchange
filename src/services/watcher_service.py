"""
SOST Gold Exchange — Watcher Service

Persistent service that runs both chain watchers and the settlement daemon.
Loads configuration, manages threads, handles graceful shutdown, and
persists state on exit.

Entry point:
    python3 -m src.services.watcher_service
"""

import json
import os
import sys
import signal
import time
import logging
import threading
from pathlib import Path

# Ensure project root on sys.path
_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_this_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.watchers.ethereum_watcher import EthereumWatcher
from src.watchers.sost_watcher import SostWatcher
from src.settlement.settlement_daemon import SettlementDaemon
from src.settlement.deal_state_machine import DealStore
from src.settlement.refund_engine import RefundEngine
from src.operator.audit_log import AuditLog
from src.services.health_monitor import HealthMonitor

log = logging.getLogger("watcher-service")

# ── ANSI colors ──
C_RESET = "\033[0m"
C_TIME = "\033[90m"       # grey
C_INFO = "\033[36m"       # cyan
C_WARN = "\033[33m"       # yellow
C_ERR = "\033[31m"        # red
C_OK = "\033[32m"         # green
C_BOLD = "\033[1m"

CONFIG_DEFAULT = os.path.join(_project_root, "configs", "live_alpha.local.json")
CONFIG_FALLBACK = os.path.join(_project_root, "configs", "live_alpha.example.json")


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: C_TIME,
        logging.INFO: C_INFO,
        logging.WARNING: C_WARN,
        logging.ERROR: C_ERR,
        logging.CRITICAL: C_ERR + C_BOLD,
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, C_RESET)
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        ms = f"{record.created % 1:.3f}"[1:]
        return (
            f"{C_TIME}{ts}{ms}{C_RESET} "
            f"{color}{record.levelname:<7}{C_RESET} "
            f"[{record.name}] {record.getMessage()}"
        )


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def load_config(path: str = "") -> dict:
    if path and os.path.exists(path):
        config_path = path
    elif os.path.exists(CONFIG_DEFAULT):
        config_path = CONFIG_DEFAULT
    elif os.path.exists(CONFIG_FALLBACK):
        config_path = CONFIG_FALLBACK
    else:
        raise FileNotFoundError(
            f"No config found. Tried: {path or '(none)'}, {CONFIG_DEFAULT}, {CONFIG_FALLBACK}"
        )
    log.info("Loading config from %s", config_path)
    with open(config_path) as f:
        return json.load(f)


class WatcherService:
    def __init__(self, config: dict, health: HealthMonitor):
        self.config = config
        self.health = health
        self._shutdown = threading.Event()
        self._threads: list[threading.Thread] = []

        eth_cfg = config["ethereum"]
        sost_cfg = config["sost"]
        data_cfg = config.get("data", {})

        # Data paths
        self.deals_path = os.path.join(_project_root, data_cfg.get("deals_path", "data/deals.json"))
        self.positions_path = os.path.join(_project_root, data_cfg.get("positions_path", "data/positions.json"))
        audit_dir = os.path.join(_project_root, data_cfg.get("audit_dir", "data/audit"))

        # Ensure directories
        os.makedirs(os.path.dirname(self.deals_path), exist_ok=True)
        os.makedirs(audit_dir, exist_ok=True)

        # Components
        self.deal_store = DealStore()
        if os.path.exists(self.deals_path):
            try:
                self.deal_store.load(self.deals_path)
                log.info("Loaded %d deals from %s", len(self.deal_store._deals), self.deals_path)
            except Exception as e:
                log.warning("Failed to load deals: %s", e)

        self.audit = AuditLog(log_dir=audit_dir)
        self.audit.load()

        self.refund_engine = RefundEngine()

        # Watch addresses from demo config
        watch_addrs = []
        demo = config.get("demo", {})
        for key in ("maker_sost_addr", "taker_sost_addr"):
            addr = demo.get(key, "")
            if addr and not addr.endswith("_placeholder"):
                watch_addrs.append(addr)

        self.eth_watcher = EthereumWatcher(
            rpc_url=eth_cfg["rpc_url"],
            escrow_address=eth_cfg["escrow_address"],
        )

        self.sost_watcher = SostWatcher(
            rpc_url=sost_cfg["rpc_url"],
            rpc_user=sost_cfg.get("rpc_user", "sost"),
            rpc_pass=sost_cfg.get("rpc_pass", ""),
            watch_addresses=watch_addrs,
        )

        self.daemon = SettlementDaemon(
            deal_store=self.deal_store,
            eth_watcher=self.eth_watcher,
            sost_watcher=self.sost_watcher,
            refund_engine=self.refund_engine,
            audit=self.audit,
        )

        # Register health intervals
        self.health.register("eth_watcher", eth_cfg.get("poll_interval_seconds", eth_cfg.get("poll_interval", 15)))
        self.health.register("sost_watcher", sost_cfg.get("poll_interval_seconds", sost_cfg.get("poll_interval", 10)))
        self.health.register("daemon_tick", 5)

    def _run_eth_watcher(self):
        backoff = 1
        while not self._shutdown.is_set():
            try:
                events = self.eth_watcher.poll_once()
                self.health.record_poll("eth_watcher")
                backoff = 1  # reset on success
                for ev in events:
                    self.daemon.on_eth_event(ev)
            except Exception as e:
                self.health.record_error("eth_watcher")
                log.error("ETH watcher error (retry in %ds): %s", backoff, e)
                self._shutdown.wait(backoff)
                backoff = min(backoff * 2, 120)
                continue

            interval = self.config["ethereum"].get(
                "poll_interval_seconds",
                self.config["ethereum"].get("poll_interval", 15),
            )
            self._shutdown.wait(interval)

    def _run_sost_watcher(self):
        backoff = 1
        while not self._shutdown.is_set():
            try:
                events = self.sost_watcher.poll_once()
                self.health.record_poll("sost_watcher")
                backoff = 1
                for ev in events:
                    self.daemon.on_sost_event(ev)
            except Exception as e:
                self.health.record_error("sost_watcher")
                log.error("SOST watcher error (retry in %ds): %s", backoff, e)
                self._shutdown.wait(backoff)
                backoff = min(backoff * 2, 120)
                continue

            interval = self.config["sost"].get(
                "poll_interval_seconds",
                self.config["sost"].get("poll_interval", 10),
            )
            self._shutdown.wait(interval)

    def _run_daemon_tick(self):
        while not self._shutdown.is_set():
            try:
                self.daemon.tick()
                self.health.record_poll("daemon_tick")
            except Exception as e:
                self.health.record_error("daemon_tick")
                log.error("Daemon tick error: %s", e)
            self._shutdown.wait(5)

    def start(self):
        log.info("%s%sSOST Gold Exchange — Watcher Service%s", C_BOLD, C_OK, C_RESET)
        log.info("Mode: %s", self.config.get("mode", "unknown"))
        log.info("ETH RPC:  %s", self.config["ethereum"]["rpc_url"])
        log.info("Escrow:   %s", self.config["ethereum"]["escrow_address"])
        log.info("SOST RPC: %s", self.config["sost"]["rpc_url"])

        threads = [
            ("eth-watcher", self._run_eth_watcher),
            ("sost-watcher", self._run_sost_watcher),
            ("daemon-tick", self._run_daemon_tick),
        ]
        for name, target in threads:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
            log.info("Started thread: %s", name)

    def stop(self):
        log.info("Shutting down watcher service...")
        self._shutdown.set()
        self.eth_watcher.stop()
        self.sost_watcher.stop()
        self.daemon.stop()

        for t in self._threads:
            t.join(timeout=5)

        self._save_state()
        log.info("%sWatcher service stopped.%s", C_OK, C_RESET)

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.deals_path), exist_ok=True)
            self.deal_store.save(self.deals_path)
            log.info("Saved %d deals to %s", len(self.deal_store._deals), self.deals_path)
        except Exception as e:
            log.error("Failed to save deals: %s", e)

    def wait(self):
        """Block until shutdown signal."""
        try:
            while not self._shutdown.is_set():
                self._shutdown.wait(1)
        except KeyboardInterrupt:
            pass


def main():
    setup_logging()

    import argparse
    parser = argparse.ArgumentParser(description="SOST Watcher Service")
    parser.add_argument("--config", default="", help="Path to config JSON")
    args = parser.parse_args()

    config = load_config(args.config)
    health = HealthMonitor()
    service = WatcherService(config, health)

    def _signal_handler(sig, frame):
        log.info("Received signal %s", sig)
        service.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    service.start()
    service.wait()


if __name__ == "__main__":
    main()
