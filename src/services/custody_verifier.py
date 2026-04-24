"""
SOST Gold Exchange — Custody Verifier for Model A

Verifies that Model A (autocustody) positions still hold the declared
XAUT/PAXG balance in the user's Ethereum wallet.

In alpha mode: uses simulated balance checks.
In live mode: queries Ethereum RPC for actual token balances.

If verification fails:
  - flags position for operator review
  - after configured grace period, triggers automatic slashing

Depends on:
  - position_registry (to read positions)
  - audit_log (to record all verification attempts)
"""

import time
import logging
from typing import Optional
from dataclasses import dataclass, field

from src.positions.position_registry import PositionRegistry
from src.positions.position_schema import (
    ContractType, PositionStatus, LifecycleStatus,
)
from src.operator.audit_log import AuditLog

log = logging.getLogger("custody-verifier")

# ── Configuration ────────────────────────────────────────────────

ALPHA_MODE = True  # When True, always passes verification (no RPC)
GRACE_PERIOD_SECONDS = 7 * 86400  # 7 days before auto-slash after failure
MIN_BALANCE_RATIO = 0.95  # Allow 5% rounding/fee tolerance


# ── Verification Result ──────────────────────────────────────────

@dataclass
class VerificationResult:
    position_id: str
    passed: bool
    expected_amount: int  # wei or mg
    actual_amount: Optional[int]  # None if check failed
    reason: str
    timestamp: float = field(default_factory=time.time)
    epoch: int = 0


# ── Custody Verifier ─────────────────────────────────────────────

class CustodyVerifier:
    def __init__(
        self,
        registry: PositionRegistry,
        audit: AuditLog,
        alpha_mode: bool = True,
        eth_rpc_url: str = "",
    ):
        self.registry = registry
        self.audit = audit
        self.alpha_mode = alpha_mode
        self.eth_rpc_url = eth_rpc_url
        self._results: list[VerificationResult] = []
        self._failed_positions: dict[str, float] = {}  # pid → first_failure_time

    def get_model_a_positions(self) -> list[str]:
        """Get all active Model A positions that need verification."""
        result = []
        for pid, pos in self.registry._positions.items():
            ct = pos.contract_type.value if hasattr(pos.contract_type, 'value') else pos.contract_type
            st = pos.status.value if hasattr(pos.status, 'value') else pos.status
            ls = pos.lifecycle_status.value if hasattr(pos.lifecycle_status, 'value') else pos.lifecycle_status
            if (
                ct == ContractType.MODEL_A_CUSTODY.value
                and st == PositionStatus.ACTIVE.value
                and ls in (
                    LifecycleStatus.ACTIVE.value,
                    LifecycleStatus.NEARING_MATURITY.value,
                )
            ):
                result.append(pid)
        return result

    def verify_position(self, position_id: str, epoch: int = 0) -> VerificationResult:
        """Verify custody for a single Model A position.

        In alpha mode: always returns PASSED (simulated).
        In live mode: queries Ethereum RPC for token balance.
        """
        pos = self.registry.get(position_id)
        if not pos:
            return VerificationResult(
                position_id=position_id,
                passed=False,
                expected_amount=0,
                actual_amount=None,
                reason="position_not_found",
                epoch=epoch,
            )

        expected = pos.reference_amount

        if self.alpha_mode:
            # Alpha mode: simulate successful verification
            result = VerificationResult(
                position_id=position_id,
                passed=True,
                expected_amount=expected,
                actual_amount=expected,  # simulated
                reason="alpha_mode_simulated_pass",
                epoch=epoch,
            )
            self._record_result(result)
            return result

        # Live mode: query Ethereum RPC
        actual = self._query_token_balance(pos)

        if actual is None:
            result = VerificationResult(
                position_id=position_id,
                passed=False,
                expected_amount=expected,
                actual_amount=None,
                reason="rpc_query_failed",
                epoch=epoch,
            )
        elif actual >= int(expected * MIN_BALANCE_RATIO):
            result = VerificationResult(
                position_id=position_id,
                passed=True,
                expected_amount=expected,
                actual_amount=actual,
                reason="balance_verified",
                epoch=epoch,
            )
            # Clear failure tracking on success
            self._failed_positions.pop(position_id, None)
        else:
            result = VerificationResult(
                position_id=position_id,
                passed=False,
                expected_amount=expected,
                actual_amount=actual,
                reason=f"balance_insufficient: expected>={expected * MIN_BALANCE_RATIO}, got={actual}",
                epoch=epoch,
            )
            # Track failure for grace period
            if position_id not in self._failed_positions:
                self._failed_positions[position_id] = time.time()

        self._record_result(result)
        return result

    def verify_all(self, epoch: int = 0) -> list[VerificationResult]:
        """Verify all active Model A positions."""
        positions = self.get_model_a_positions()
        results = []
        for pid in positions:
            result = self.verify_position(pid, epoch)
            results.append(result)
        return results

    def check_slash_eligible(self) -> list[str]:
        """Positions that have been failing verification past the grace period."""
        now = time.time()
        eligible = []
        for pid, first_failure in self._failed_positions.items():
            if now - first_failure >= GRACE_PERIOD_SECONDS:
                eligible.append(pid)
        return eligible

    def execute_slashes(self) -> list[str]:
        """Slash positions that exceeded the grace period.

        Returns list of slashed position IDs.
        """
        eligible = self.check_slash_eligible()
        slashed = []
        for pid in eligible:
            pos = self.registry.get(pid)
            pos_status = pos.status.value if hasattr(pos.status, 'value') else pos.status
            if pos and pos_status == PositionStatus.ACTIVE.value:
                success = self.registry.slash(
                    pid,
                    f"custody_verification_failed_after_{GRACE_PERIOD_SECONDS}s_grace"
                )
                if success:
                    slashed.append(pid)
                    self.audit.log_event(
                        pid, "auto_slashed",
                        f"custody verification failed past grace period ({GRACE_PERIOD_SECONDS}s)"
                    )
                    log.warning("Position %s: AUTO-SLASHED — custody verification failure", pid)
                    self._failed_positions.pop(pid, None)
        return slashed

    def _query_token_balance(self, pos) -> Optional[int]:
        """Query actual token balance from Ethereum RPC.

        Returns balance in wei, or None on failure.
        """
        if not self.eth_rpc_url:
            log.error("No Ethereum RPC URL configured for live verification")
            return None

        # Token contract addresses
        token_contracts = {
            "XAUT": "0x68749665FF8D2d112Fa859AA293F07A622782F38",
            "PAXG": "0x45804880De22913dAFE09f4980848ECE6EcbAf78",
        }

        contract = token_contracts.get(pos.token_symbol)
        if not contract:
            log.error("Unknown token symbol: %s", pos.token_symbol)
            return None

        # The owner's ETH address for Model A is either eth_beneficiary or
        # derived from backing_proof_hash. In Model A, the user keeps gold
        # in their own wallet — we need their ETH address.
        eth_address = pos.eth_beneficiary
        if not eth_address:
            log.error("No ETH address for Model A position %s", pos.position_id)
            return None

        try:
            import urllib.request
            import json

            # ERC-20 balanceOf(address) call
            # Function selector: 0x70a08231
            padded_addr = eth_address.lower().replace("0x", "").zfill(64)
            data = "0x70a08231" + padded_addr

            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [
                    {"to": contract, "data": data},
                    "latest"
                ],
                "id": 1,
            }).encode()

            req = urllib.request.Request(
                self.eth_rpc_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if "result" in result:
                    return int(result["result"], 16)
                else:
                    log.error("RPC error: %s", result.get("error", "unknown"))
                    return None

        except Exception as e:
            log.error("ETH RPC call failed: %s", e)
            return None

    def _record_result(self, result: VerificationResult):
        """Record verification result to audit log."""
        self._results.append(result)
        status = "PASS" if result.passed else "FAIL"
        self.audit.log_event(
            result.position_id,
            f"custody_verification_{status.lower()}",
            f"epoch={result.epoch} expected={result.expected_amount} "
            f"actual={result.actual_amount} reason={result.reason}",
        )
        pos = self.registry.get(result.position_id)
        if pos:
            pos.record_event(
                f"custody_verified_{status.lower()}",
                f"epoch={result.epoch} reason={result.reason}",
            )

    def get_results(self, position_id: str = None) -> list[VerificationResult]:
        """Get verification history, optionally filtered by position."""
        if position_id:
            return [r for r in self._results if r.position_id == position_id]
        return self._results.copy()

    def get_stats(self) -> dict:
        """Get verification statistics."""
        total = len(self._results)
        passed = sum(1 for r in self._results if r.passed)
        failed = total - passed
        pending_slash = len(self.check_slash_eligible())
        return {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "pending_slash": pending_slash,
            "tracked_failures": len(self._failed_positions),
        }
