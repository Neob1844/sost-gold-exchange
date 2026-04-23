"""
SOST Gold Exchange — Beneficiary Sync

Syncs the ETH escrow beneficiary after position trades. When a position's
principal_owner changes via a SOST-side trade, the on-chain beneficiary in
EscrowV2 must be updated to match.

In alpha mode: generates and logs the cast command.
In live mode: would execute updateBeneficiary via RPC.
"""

import time
import logging
from typing import Optional

from src.positions.position_registry import PositionRegistry
from src.operator.audit_log import AuditLog

log = logging.getLogger("beneficiary-sync")


class BeneficiarySync:
    def __init__(self, registry: PositionRegistry, eth_config: dict, audit: AuditLog):
        self.registry = registry
        self.eth_config = eth_config
        self.audit = audit

    def _build_cast_command(self, deposit_id: int, new_beneficiary: str) -> str:
        """Build cast command to call updateBeneficiary on EscrowV2."""
        escrow = self.eth_config.get("escrow_address", "")
        rpc_url = self.eth_config.get("rpc_url", "")
        return (
            f'cast send {escrow} '
            f'"updateBeneficiary(uint256,address)" {deposit_id} {new_beneficiary} '
            f'--rpc-url {rpc_url}'
        )

    def sync_beneficiary(self, position_id: str) -> Optional[str]:
        """Sync on-chain beneficiary to match registry's principal_owner ETH address.

        In alpha mode: logs the cast command.
        In live mode: would execute via RPC.
        Returns tx hash string or None.
        """
        pos = self.registry.get(position_id)
        if not pos:
            log.warning("Position %s not found", position_id)
            return None

        deposit_id = pos.eth_escrow_deposit_id
        if deposit_id is None:
            log.warning("Position %s has no eth_escrow_deposit_id", position_id)
            return None

        new_beneficiary = pos.eth_beneficiary
        if not new_beneficiary:
            log.warning("Position %s has no eth_beneficiary set", position_id)
            return None

        cast_cmd = self._build_cast_command(deposit_id, new_beneficiary)
        log.info("Beneficiary sync for %s: %s", position_id, cast_cmd)

        # Simulate tx hash (in live mode from RPC response)
        import hashlib
        simulated_tx = "0x" + hashlib.sha256(
            f"beneficiary_sync:{position_id}:{deposit_id}:{new_beneficiary}:{time.time()}".encode()
        ).hexdigest()

        pos.record_event(
            "beneficiary_synced",
            f"deposit_id={deposit_id} beneficiary={new_beneficiary} tx={simulated_tx}",
        )
        self.audit.log_event(
            position_id, "beneficiary_synced",
            f"deposit_id={deposit_id} new_beneficiary={new_beneficiary}",
        )

        log.info(
            "Position %s: beneficiary synced to %s (tx=%s)",
            position_id, new_beneficiary, simulated_tx[:18],
        )
        return simulated_tx

    def check_pending_syncs(self) -> list[str]:
        """Returns positions where principal_owner changed but eth_beneficiary
        may not yet be synced on-chain.

        Heuristic: if the position has a principal_owner that differs from owner,
        or if eth_beneficiary is set but no beneficiary_synced event exists.
        """
        pending = []
        for pid, pos in self.registry._positions.items():
            if pos.eth_escrow_deposit_id is None:
                continue
            if not pos.eth_beneficiary:
                continue

            # Check if there's already a sync event for the current beneficiary
            already_synced = False
            for h in reversed(pos.history):
                if h.get("event") == "beneficiary_synced":
                    if pos.eth_beneficiary in h.get("detail", ""):
                        already_synced = True
                        break

            if not already_synced:
                pending.append(pid)

        return pending
