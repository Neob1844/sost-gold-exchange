"""
SOST Gold Exchange — Epoch Audit Daemon

Runs periodic custody audits for Model A positions based on epoch boundaries.
An epoch is a fixed time window (default: 7 days). At each epoch boundary,
all active Model A positions are verified for continued gold custody.

Audit results are logged to the audit trail. Positions that fail verification
are tracked with a grace period before automatic slashing.

Lifecycle:
  epoch_start → verify_all_model_a → log_results → check_slashes → epoch_end

Depends on:
  - custody_verifier.py (verification logic)
  - position_registry (position data)
  - audit_log (persistence)
"""

import time
import json
import logging
from pathlib import Path
from typing import Optional

from src.services.custody_verifier import CustodyVerifier
from src.positions.position_registry import PositionRegistry
from src.operator.audit_log import AuditLog

log = logging.getLogger("epoch-audit")

# ── Configuration ────────────────────────────────────────────────

DEFAULT_EPOCH_DURATION = 7 * 86400  # 7 days
STATE_FILE = "data/epoch_audit_state.json"


class EpochAuditDaemon:
    def __init__(
        self,
        registry: PositionRegistry,
        audit: AuditLog,
        verifier: CustodyVerifier,
        epoch_duration: int = DEFAULT_EPOCH_DURATION,
        state_file: str = STATE_FILE,
    ):
        self.registry = registry
        self.audit = audit
        self.verifier = verifier
        self.epoch_duration = epoch_duration
        self.state_file = Path(state_file)

        # State
        self.current_epoch: int = 0
        self.last_epoch_time: float = 0.0
        self.next_epoch_time: float = 0.0
        self.epoch_history: list[dict] = []

        self._load_state()

    # ── State Persistence ────────────────────────────────────────

    def _load_state(self):
        """Load epoch state from disk."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self.current_epoch = data.get("current_epoch", 0)
                self.last_epoch_time = data.get("last_epoch_time", 0.0)
                self.next_epoch_time = data.get("next_epoch_time", 0.0)
                self.epoch_history = data.get("epoch_history", [])
                log.info("Loaded epoch state: epoch=%d, next=%s",
                         self.current_epoch,
                         time.strftime("%Y-%m-%d %H:%M", time.localtime(self.next_epoch_time)))
            except Exception as e:
                log.warning("Failed to load epoch state: %s", e)
                self._init_first_epoch()
        else:
            self._init_first_epoch()

    def _init_first_epoch(self):
        """Initialize first epoch from now."""
        self.current_epoch = 0
        self.last_epoch_time = time.time()
        self.next_epoch_time = self.last_epoch_time + self.epoch_duration
        self._save_state()

    def _save_state(self):
        """Persist epoch state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "current_epoch": self.current_epoch,
            "last_epoch_time": self.last_epoch_time,
            "next_epoch_time": self.next_epoch_time,
            "epoch_history": self.epoch_history[-100:],  # keep last 100
        }
        self.state_file.write_text(json.dumps(data, indent=2))

    # ── Epoch Logic ──────────────────────────────────────────────

    def is_epoch_due(self) -> bool:
        """Check if it's time for a new epoch audit."""
        return time.time() >= self.next_epoch_time

    def run_epoch(self) -> dict:
        """Execute a full epoch audit cycle.

        1. Increment epoch counter
        2. Verify all Model A positions
        3. Log results
        4. Check for slash-eligible positions
        5. Execute slashes if past grace period
        6. Record epoch summary
        7. Schedule next epoch

        Returns epoch summary dict.
        """
        self.current_epoch += 1
        epoch_start = time.time()

        log.info("=== EPOCH %d START ===", self.current_epoch)

        # 1. Verify all Model A positions
        results = self.verifier.verify_all(epoch=self.current_epoch)

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)

        log.info("Epoch %d: verified %d positions — %d passed, %d failed",
                 self.current_epoch, len(results), passed, failed)

        # 2. Check and execute slashes
        slashed = self.verifier.execute_slashes()
        if slashed:
            log.warning("Epoch %d: %d position(s) slashed", self.current_epoch, len(slashed))

        # 3. Record epoch summary
        epoch_end = time.time()
        summary = {
            "epoch": self.current_epoch,
            "start_time": epoch_start,
            "end_time": epoch_end,
            "duration_seconds": epoch_end - epoch_start,
            "positions_checked": len(results),
            "passed": passed,
            "failed": failed,
            "slashed": len(slashed),
            "slashed_ids": slashed,
        }

        self.epoch_history.append(summary)

        # 4. Log to audit
        self.audit.log_event(
            "system", "epoch_audit_complete",
            f"epoch={self.current_epoch} checked={len(results)} "
            f"passed={passed} failed={failed} slashed={len(slashed)}",
        )

        # 5. Schedule next epoch
        self.last_epoch_time = epoch_start
        self.next_epoch_time = epoch_start + self.epoch_duration
        self._save_state()

        log.info("=== EPOCH %d END — next epoch at %s ===",
                 self.current_epoch,
                 time.strftime("%Y-%m-%d %H:%M", time.localtime(self.next_epoch_time)))

        return summary

    def tick(self) -> Optional[dict]:
        """Periodic check — runs epoch if due.

        Returns epoch summary if an epoch was run, None otherwise.
        """
        if self.is_epoch_due():
            return self.run_epoch()
        return None

    def get_status(self) -> dict:
        """Get current epoch daemon status."""
        now = time.time()
        return {
            "current_epoch": self.current_epoch,
            "last_epoch_time": self.last_epoch_time,
            "next_epoch_time": self.next_epoch_time,
            "seconds_until_next": max(0, self.next_epoch_time - now),
            "total_epochs_run": len(self.epoch_history),
            "verifier_stats": self.verifier.get_stats(),
        }
