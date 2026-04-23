"""
SOST Gold Exchange — Auto-Withdraw Daemon

Executes ETH escrow withdrawals for matured positions that have
auto_withdraw enabled. In alpha mode, generates the cast command
and logs it. In live mode, would execute the withdraw via RPC.

Lifecycle transitions:
  MATURED -> WITHDRAW_PENDING -> WITHDRAWN
"""

import time
import logging
from typing import Optional

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import LifecycleStatus
from src.operator.audit_log import AuditLog

log = logging.getLogger("auto-withdraw")

TICK_INTERVAL = 60  # seconds


class AutoWithdrawDaemon:
    def __init__(self, registry: PositionRegistry, eth_config: dict, audit: AuditLog):
        self.registry = registry
        self.eth_config = eth_config
        self.audit = audit
        self._last_tick: Optional[float] = None

    def check_withdrawable(self) -> list[str]:
        """Returns position IDs where:
        - lifecycle_status == MATURED
        - auto_withdraw == True
        - withdraw_tx is None
        """
        result = []
        for pid, pos in self.registry._positions.items():
            if (pos.lifecycle_status == LifecycleStatus.MATURED.value
                    and pos.auto_withdraw
                    and pos.withdraw_tx is None):
                result.append(pid)
        return result

    def _build_cast_command(self, deposit_id: int) -> str:
        """Build the cast send command for withdrawing from EscrowV2."""
        escrow = self.eth_config.get("escrow_address", "")
        rpc_url = self.eth_config.get("rpc_url", "")
        return (
            f'cast send {escrow} '
            f'"withdraw(uint256)" {deposit_id} '
            f'--rpc-url {rpc_url}'
        )

    def execute_withdraw(self, position_id: str) -> Optional[str]:
        """Execute withdrawal for a single position.

        In alpha mode: generates the cast command and logs it.
        In live mode: would execute the withdraw via RPC.

        Returns tx hash string or None on failure.
        Updates lifecycle_status to WITHDRAW_PENDING then WITHDRAWN.
        """
        pos = self.registry.get(position_id)
        if not pos:
            log.warning("Position %s not found", position_id)
            return None

        if pos.lifecycle_status != LifecycleStatus.MATURED.value:
            log.warning("Position %s not in MATURED state (is %s)", position_id, pos.lifecycle_status)
            return None

        if pos.withdraw_tx is not None:
            log.warning("Position %s already has withdraw_tx", position_id)
            return None

        deposit_id = pos.eth_escrow_deposit_id
        if deposit_id is None:
            log.warning("Position %s has no eth_escrow_deposit_id", position_id)
            return None

        # Transition to WITHDRAW_PENDING
        pos.lifecycle_status = LifecycleStatus.WITHDRAW_PENDING.value
        pos.record_event("lifecycle_withdraw_pending", f"deposit_id={deposit_id}")
        self.audit.log_event(
            position_id, "withdraw_pending",
            f"deposit_id={deposit_id}",
        )

        # In alpha mode: generate cast command, simulate tx hash
        cast_cmd = self._build_cast_command(deposit_id)
        log.info("Withdraw command for %s: %s", position_id, cast_cmd)

        # Simulate a tx hash (in live mode this would come from the RPC response)
        import hashlib
        simulated_tx = "0x" + hashlib.sha256(
            f"withdraw:{position_id}:{deposit_id}:{time.time()}".encode()
        ).hexdigest()

        pos.withdraw_tx = simulated_tx
        pos.lifecycle_status = LifecycleStatus.WITHDRAWN.value
        pos.record_event("lifecycle_withdrawn", f"tx={simulated_tx}")
        self.audit.log_event(
            position_id, "withdrawn",
            f"tx={simulated_tx} deposit_id={deposit_id}",
        )

        log.info("Position %s: MATURED -> WITHDRAWN (tx=%s)", position_id, simulated_tx[:18])
        return simulated_tx

    def tick(self):
        """Periodic check + execute withdrawals."""
        self._last_tick = time.time()
        withdrawable = self.check_withdrawable()
        results = []
        for pid in withdrawable:
            tx = self.execute_withdraw(pid)
            if tx:
                results.append((pid, tx))
        if results:
            log.info("Auto-withdraw: executed %d withdrawal(s)", len(results))
        return results
