"""
SOST Gold Exchange — Reward Settlement Daemon

Credits SOST rewards to the reward_owner at maturity. Runs on a periodic
tick and processes positions that are matured/withdrawn but have not yet
had their rewards settled.

Lifecycle transition:
  MATURED|WITHDRAWN -> REWARD_SETTLED
"""

import time
import logging
from typing import Optional

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import LifecycleStatus
from src.operator.audit_log import AuditLog

log = logging.getLogger("reward-settlement")

TICK_INTERVAL = 60  # seconds


class RewardSettlementDaemon:
    def __init__(self, registry: PositionRegistry, audit: AuditLog):
        self.registry = registry
        self.audit = audit
        self._last_tick: Optional[float] = None

    def check_settleable(self) -> list[str]:
        """Returns position IDs where:
        - lifecycle_status in (MATURED, WITHDRAWN)
        - reward_settled == False
        """
        result = []
        for pid, pos in self.registry._positions.items():
            if (pos.lifecycle_status in (
                    LifecycleStatus.MATURED.value,
                    LifecycleStatus.WITHDRAWN.value,
                ) and not pos.reward_settled):
                result.append(pid)
        return result

    def settle_reward(self, position_id: str) -> bool:
        """Credits reward to reward_owner and updates lifecycle.

        Sets reward_settled = True, updates lifecycle_status to REWARD_SETTLED.
        Returns True on success, False on failure.
        """
        pos = self.registry.get(position_id)
        if not pos:
            log.warning("Position %s not found", position_id)
            return False

        if pos.lifecycle_status not in (
            LifecycleStatus.MATURED.value,
            LifecycleStatus.WITHDRAWN.value,
        ):
            log.warning(
                "Position %s not in MATURED/WITHDRAWN state (is %s)",
                position_id, pos.lifecycle_status,
            )
            return False

        if pos.reward_settled:
            log.warning("Position %s already settled", position_id)
            return False

        # Determine the reward recipient
        reward_owner = pos.reward_owner or pos.principal_owner or pos.owner
        reward_amount = pos.reward_remaining()

        # Credit the reward (mark claimed)
        pos.reward_claimed_sost = pos.reward_total_sost
        pos.reward_settled = True
        pos.lifecycle_status = LifecycleStatus.REWARD_SETTLED.value

        pos.record_event(
            "lifecycle_reward_settled",
            f"reward={reward_amount} recipient={reward_owner}",
        )
        self.audit.log_event(
            position_id, "reward_settled",
            f"amount={reward_amount} recipient={reward_owner}",
        )

        log.info(
            "Position %s: reward settled — %d SOST to %s",
            position_id, reward_amount, reward_owner,
        )
        return True

    def tick(self):
        """Periodic check + settle rewards."""
        self._last_tick = time.time()
        settleable = self.check_settleable()
        settled = []
        for pid in settleable:
            if self.settle_reward(pid):
                settled.append(pid)
        if settled:
            log.info("Reward settlement: settled %d position(s)", len(settled))
        return settled
