"""
SOST Gold Exchange — Watcher Service Integration Tests
"""

import json
import os
import sys
import time
import threading
import unittest
from unittest.mock import patch, MagicMock

_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_this_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.services.health_monitor import HealthMonitor
from src.services.watcher_service import load_config, WatcherService


class TestConfigLoads(unittest.TestCase):
    def test_config_loads_correctly(self):
        """Config loads from live_alpha.local.json and has required keys."""
        config = load_config(os.path.join(_project_root, "configs", "live_alpha.local.json"))
        self.assertEqual(config["mode"], "live-alpha")
        self.assertIn("ethereum", config)
        self.assertIn("sost", config)
        self.assertIn("rpc_url", config["ethereum"])
        self.assertIn("escrow_address", config["ethereum"])
        self.assertEqual(config["ethereum"]["chain_id"], 11155111)
        self.assertIn("rpc_url", config["sost"])


class TestHealthMonitor(unittest.TestCase):
    def test_health_monitor_tracks_polls(self):
        """Health monitor records polls and reports them correctly."""
        hm = HealthMonitor()
        hm.register("eth", 15)
        hm.register("sost", 10)

        # Initially healthy (within grace period)
        self.assertTrue(hm.is_healthy())

        hm.record_poll("eth")
        hm.record_poll("sost")

        health = hm.get_health()
        self.assertEqual(health["status"], "healthy")
        self.assertIn("eth", health["components"])
        self.assertIn("sost", health["components"])
        self.assertIsNotNone(health["components"]["eth"]["last_poll"])
        self.assertIsNotNone(health["components"]["sost"]["last_poll"])
        self.assertEqual(health["components"]["eth"]["errors"], 0)

    def test_health_monitor_detects_stale(self):
        """Health monitor detects stale components after 2x interval."""
        hm = HealthMonitor()
        # Backdate start time so grace period has expired
        hm._start_time = time.time() - 120
        hm.register("eth", 15)

        # Record a poll long ago
        hm.record_poll("eth")
        hm._last_poll["eth"] = time.time() - 60  # 60s ago, threshold is 30s

        self.assertFalse(hm.is_healthy())
        health = hm.get_health()
        self.assertEqual(health["status"], "degraded")
        self.assertTrue(health["components"]["eth"]["stale"])

    def test_health_monitor_error_counting(self):
        """Health monitor accumulates error counts."""
        hm = HealthMonitor()
        hm.register("eth", 15)
        hm.record_error("eth")
        hm.record_error("eth")
        hm.record_error("eth")
        health = hm.get_health()
        self.assertEqual(health["components"]["eth"]["errors"], 3)


class TestServiceCreatesComponents(unittest.TestCase):
    def test_service_creates_components(self):
        """WatcherService creates all required sub-components from config."""
        config = load_config(os.path.join(_project_root, "configs", "live_alpha.local.json"))
        health = HealthMonitor()
        service = WatcherService(config, health)

        self.assertIsNotNone(service.eth_watcher)
        self.assertIsNotNone(service.sost_watcher)
        self.assertIsNotNone(service.daemon)
        self.assertIsNotNone(service.deal_store)
        self.assertIsNotNone(service.audit)
        self.assertIsNotNone(service.refund_engine)

        self.assertEqual(service.eth_watcher.rpc_url, config["ethereum"]["rpc_url"])
        self.assertEqual(service.eth_watcher.escrow_address, config["ethereum"]["escrow_address"])
        self.assertEqual(service.sost_watcher.rpc_url, config["sost"]["rpc_url"])


class TestGracefulShutdown(unittest.TestCase):
    def test_graceful_shutdown(self):
        """Service starts threads and stops them cleanly."""
        config = load_config(os.path.join(_project_root, "configs", "live_alpha.local.json"))
        health = HealthMonitor()
        service = WatcherService(config, health)

        # Mock the poll methods to avoid real network calls
        service.eth_watcher.poll_once = MagicMock(return_value=[])
        service.sost_watcher.poll_once = MagicMock(return_value=[])

        service.start()
        # Verify threads are running
        self.assertTrue(len(service._threads) >= 3)
        alive = [t for t in service._threads if t.is_alive()]
        self.assertTrue(len(alive) >= 3)

        # Stop and verify clean shutdown
        service.stop()
        time.sleep(0.5)
        alive_after = [t for t in service._threads if t.is_alive()]
        self.assertEqual(len(alive_after), 0)


if __name__ == "__main__":
    unittest.main()
