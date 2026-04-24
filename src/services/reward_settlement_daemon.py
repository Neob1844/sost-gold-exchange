"""
SOST Gold Exchange — Reward Settlement Daemon

Credits SOST rewards to the reward_owner at maturity, after deducting
the constitutional protocol fee (3% Model A, 8% Model B).

Fee is calculated at settlement time and credited to the protocol
operational address. The user receives (reward - fee).

Lifecycle transition:
  MATURED|WITHDRAWN -> REWARD_SETTLED
"""

import time
import logging
from typing import Optional

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import LifecycleStatus, ContractType
from src.operator.audit_log import AuditLog

log = logging.getLogger("reward-settlement")

TICK_INTERVAL = 60  # seconds

# Constitutional protocol fees (immutable)
PROTOCOL_FEE_MODEL_A = 0.03  # 3% of reward
PROTOCOL_FEE_MODEL_B = 0.08  # 8% of reward
PROTOCOL_FEE_ADDRESS = "sost1059d1ef8639bcf47ec35e9299c17dc0452c3df33"  # protocol operational


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
        gross_reward = pos.reward_remaining()

        # Calculate protocol fee (constitutional: 3% Model A, 8% Model B)
        ct = pos.contract_type.value if hasattr(pos.contract_type, 'value') else pos.contract_type
        if ct == ContractType.MODEL_A_CUSTODY.value:
            fee_rate = PROTOCOL_FEE_MODEL_A
        else:
            fee_rate = PROTOCOL_FEE_MODEL_B

        protocol_fee = int(gross_reward * fee_rate)
        user_reward = gross_reward - protocol_fee

        # Credit the reward (mark claimed)
        pos.reward_claimed_sost = pos.reward_total_sost
        pos.reward_settled = True
        pos.lifecycle_status = LifecycleStatus.REWARD_SETTLED.value

        pos.record_event(
            "lifecycle_reward_settled",
            f"gross={gross_reward} fee={protocol_fee} ({fee_rate*100:.0f}%) "
            f"net={user_reward} recipient={reward_owner} "
            f"fee_to={PROTOCOL_FEE_ADDRESS}",
        )
        self.audit.log_event(
            position_id, "reward_settled",
            f"gross={gross_reward} fee={protocol_fee} net={user_reward} "
            f"recipient={reward_owner} fee_to={PROTOCOL_FEE_ADDRESS}",
        )
        if protocol_fee > 0:
            self.audit.log_event(
                position_id, "protocol_fee_collected",
                f"amount={protocol_fee} rate={fee_rate*100:.0f}% "
                f"model={'A' if fee_rate == PROTOCOL_FEE_MODEL_A else 'B'} "
                f"address={PROTOCOL_FEE_ADDRESS}",
            )

        log.info(
            "Position %s: reward settled — gross=%d fee=%d (%.0f%%) net=%d SOST to %s, fee to %s",
            position_id, gross_reward, protocol_fee, fee_rate*100,
            user_reward, reward_owner, PROTOCOL_FEE_ADDRESS,
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
