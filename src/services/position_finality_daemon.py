"""
SOST Gold Exchange — Position Finality Daemon

Handles the final lifecycle transitions:
  REWARD_SETTLED -> CLOSED (with bond release)

This closes the full lifecycle loop. Once a position reaches CLOSED,
it is considered fully completed — gold withdrawn, rewards settled,
bond returned, no further actions possible.

Lifecycle (complete):
  ACTIVE → NEARING_MATURITY → MATURED → WITHDRAWN → REWARD_SETTLED → CLOSED
"""

import time
import logging
from typing import Optional

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import LifecycleStatus, PositionStatus
from src.operator.audit_log import AuditLog

log = logging.getLogger("position-finality")

TICK_INTERVAL = 60  # seconds


class PositionFinalityDaemon:
    def __init__(self, registry: PositionRegistry, audit: AuditLog):
        self.registry = registry
        self.audit = audit
        self._last_tick: Optional[float] = None
        self._processed: set[str] = set()  # idempotency guard

    def check_closeable(self) -> list[str]:
        """Returns position IDs where:
        - lifecycle_status == REWARD_SETTLED
        - status != CLOSED (not already closed)
        - not already processed in this daemon instance
        """
        result = []
        for pid, pos in self.registry._positions.items():
            if (
                pos.lifecycle_status == LifecycleStatus.REWARD_SETTLED.value
                and pos.status != PositionStatus.REDEEMED.value
                and pid not in self._processed
            ):
                result.append(pid)
        return result

    def close_position(self, position_id: str) -> bool:
        """Transition REWARD_SETTLED → CLOSED and release bond.

        Returns True on success, False on failure.
        Idempotent: calling twice on same position returns False second time.
        """
        if position_id in self._processed:
            log.info("Position %s already processed (idempotent skip)", position_id)
            return False

        pos = self.registry.get(position_id)
        if not pos:
            log.warning("Position %s not found", position_id)
            return False

        if pos.lifecycle_status != LifecycleStatus.REWARD_SETTLED.value:
            log.warning(
                "Position %s not in REWARD_SETTLED state (is %s)",
                position_id, pos.lifecycle_status,
            )
            return False

        # Release bond
        bond_amount = pos.bond_amount_sost
        bond_recipient = pos.principal_owner or pos.owner

        # Mark position as fully closed
        pos.lifecycle_status = LifecycleStatus.CLOSED.value
        pos.status = PositionStatus.REDEEMED.value

        # Record events
        pos.record_event(
            "bond_released",
            f"amount={bond_amount} recipient={bond_recipient}",
        )
        pos.record_event(
            "lifecycle_closed",
            "position lifecycle fully complete",
        )
        self.audit.log_event(
            position_id, "bond_released",
            f"amount={bond_amount} recipient={bond_recipient}",
        )
        self.audit.log_event(
            position_id, "lifecycle_closed",
            "REWARD_SETTLED → CLOSED",
        )

        # Mark as processed for idempotency
        self._processed.add(position_id)

        log.info(
            "Position %s: CLOSED — bond %d SOST released to %s",
            position_id, bond_amount, bond_recipient,
        )
        return True

    def tick(self):
        """Periodic check + close positions."""
        self._last_tick = time.time()
        closeable = self.check_closeable()
        closed = []
        for pid in closeable:
            if self.close_position(pid):
                closed.append(pid)
        if closed:
            log.info("Position finality: closed %d position(s)", len(closed))
        return closed
