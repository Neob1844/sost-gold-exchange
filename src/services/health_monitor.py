"""
SOST Gold Exchange — Health Monitor

Tracks liveness of each subsystem (ETH watcher, SOST watcher, settlement
daemon) and exposes a simple health dict for the dashboard API.
"""

import time
import threading
import logging

log = logging.getLogger("health")


class HealthMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._last_poll: dict[str, float] = {}      # component -> epoch
        self._intervals: dict[str, float] = {}       # component -> expected seconds
        self._error_counts: dict[str, int] = {}      # component -> cumulative errors
        self._start_time = time.time()

    def register(self, component: str, expected_interval: float):
        with self._lock:
            self._intervals[component] = expected_interval
            self._error_counts.setdefault(component, 0)

    def record_poll(self, component: str):
        with self._lock:
            self._last_poll[component] = time.time()

    def record_error(self, component: str):
        with self._lock:
            self._error_counts[component] = self._error_counts.get(component, 0) + 1

    def is_healthy(self) -> bool:
        with self._lock:
            now = time.time()
            for comp, interval in self._intervals.items():
                last = self._last_poll.get(comp)
                if last is None:
                    # Component never polled — unhealthy only after 2x interval
                    if now - self._start_time > interval * 2:
                        return False
                    continue
                if now - last > interval * 2:
                    return False
            return True

    def get_health(self) -> dict:
        with self._lock:
            now = time.time()
            components = {}
            for comp, interval in self._intervals.items():
                last = self._last_poll.get(comp)
                age = round(now - last, 1) if last else None
                stale = False
                if last is None and now - self._start_time > interval * 2:
                    stale = True
                elif last is not None and now - last > interval * 2:
                    stale = True
                components[comp] = {
                    "last_poll": last,
                    "age_seconds": age,
                    "expected_interval": interval,
                    "stale": stale,
                    "errors": self._error_counts.get(comp, 0),
                }

            healthy = all(not c["stale"] for c in components.values())
            return {
                "status": "healthy" if healthy else "degraded",
                "uptime_seconds": round(now - self._start_time, 1),
                "components": components,
            }
