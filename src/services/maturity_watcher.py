"""
SOST Gold Exchange — Maturity Watcher

Monitors positions for maturity transitions:
  ACTIVE -> NEARING_MATURITY (< 7 days to expiry)
  NEARING_MATURITY -> MATURED (past expiry_time)

Runs on a periodic tick (every 60s by default), logs transitions
to the audit log, and saves the registry when changes occur.
"""

import time
import logging
from typing import Optional

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import LifecycleStatus
from src.operator.audit_log import AuditLog

log = logging.getLogger("maturity-watcher")

NEARING_MATURITY_THRESHOLD = 7 * 86400  # 7 days in seconds
TICK_INTERVAL = 60  # seconds


class MaturityWatcher:
    def __init__(self, registry: PositionRegistry, audit: AuditLog):
        self.registry = registry
        self.audit = audit
        self._last_tick: Optional[float] = None

    def check_all(self) -> list[str]:
        """Check all positions for maturity transitions.

        Returns list of position IDs that transitioned.
        """
        transitioned = []
        now = time.time()

        for pid, pos in self.registry._positions.items():
            old_status = pos.lifecycle_status

            # ACTIVE -> NEARING_MATURITY
            if old_status == LifecycleStatus.ACTIVE.value:
                remaining = pos.expiry_time - now
                if remaining <= 0:
                    # Jumped straight past nearing — go to MATURED
                    pos.lifecycle_status = LifecycleStatus.MATURED.value
                    pos.record_event("lifecycle_matured", "past expiry_time")
                    self.audit.log_event(
                        pid, "lifecycle_matured",
                        f"expiry={pos.expiry_time:.0f} now={now:.0f}",
                    )
                    transitioned.append(pid)
                    log.info("Position %s: ACTIVE -> MATURED", pid)
                elif remaining < NEARING_MATURITY_THRESHOLD:
                    pos.lifecycle_status = LifecycleStatus.NEARING_MATURITY.value
                    pos.record_event(
                        "lifecycle_nearing_maturity",
                        f"remaining={remaining:.0f}s ({remaining / 86400:.1f}d)",
                    )
                    self.audit.log_event(
                        pid, "lifecycle_nearing_maturity",
                        f"remaining={remaining:.0f}s",
                    )
                    transitioned.append(pid)
                    log.info("Position %s: ACTIVE -> NEARING_MATURITY (%.1fd left)", pid, remaining / 86400)

            # NEARING_MATURITY -> MATURED
            elif old_status == LifecycleStatus.NEARING_MATURITY.value:
                if now >= pos.expiry_time:
                    pos.lifecycle_status = LifecycleStatus.MATURED.value
                    pos.record_event("lifecycle_matured", "past expiry_time")
                    self.audit.log_event(
                        pid, "lifecycle_matured",
                        f"expiry={pos.expiry_time:.0f} now={now:.0f}",
                    )
                    transitioned.append(pid)
                    log.info("Position %s: NEARING_MATURITY -> MATURED", pid)

        return transitioned

    def tick(self):
        """Called periodically. Runs check_all and saves registry if changes."""
        self._last_tick = time.time()
        transitioned = self.check_all()
        if transitioned:
            log.info("Maturity watcher: %d position(s) transitioned", len(transitioned))
        return transitioned
