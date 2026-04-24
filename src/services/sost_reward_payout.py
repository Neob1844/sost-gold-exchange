"""
SOST Gold Exchange — Real On-Chain Reward Payout

Executes actual SOST transfers for reward settlements via RPC.
Supports dry-run mode (calculate + log, no broadcast) and live mode
(actual tx broadcast + confirmation tracking).

Security:
  - Idempotent: checks payout_txid before broadcasting
  - No double pay: lock per position_id
  - Confirmation policy: configurable min confirmations
  - Reconciliation: detect mismatches between DB and chain
  - Retry-safe: only retries if no txid recorded

Depends on:
  - SOST node RPC (sost-cli or direct HTTP RPC)
  - reward_settlement_daemon.py (calls this module)
  - position_registry.py (position data)
  - audit_log.py (evidence trail)
"""

import time
import json
import logging
import urllib.request
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from src.operator.audit_log import AuditLog

log = logging.getLogger("sost-payout")


# ── Configuration ────────────────────────────────────────────────

class PayoutMode(Enum):
    DRY_RUN = "dry_run"       # Calculate + log, no broadcast
    LIVE = "live"             # Real broadcast + confirmation

DEFAULT_RPC_URL = "http://127.0.0.1:18232"
DEFAULT_RPC_USER = ""
DEFAULT_RPC_PASS = ""
MIN_CONFIRMATIONS = 6         # Blocks before considering payout final
POOL_ADDRESS = "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"  # PoPC Pool
PROTOCOL_FEE_ADDRESS = "sost1059d1ef8639bcf47ec35e9299c17dc0452c3df33"


# ── Payout State ─────────────────────────────────────────────────

class PayoutStatus(Enum):
    PENDING = "PENDING"
    READY = "READY"
    BROADCASTING = "BROADCASTING"
    BROADCASTED = "BROADCASTED"
    CONFIRMED = "CONFIRMED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"


@dataclass
class PayoutRecord:
    payout_id: str
    position_id: str
    model: str                    # "A" or "B"
    reward_owner: str
    gross_reward: int             # satoshis
    protocol_fee: int             # satoshis
    net_reward: int               # satoshis
    fee_rate: float               # 0.03 or 0.08
    status: PayoutStatus = PayoutStatus.PENDING
    reward_txid: Optional[str] = None
    fee_txid: Optional[str] = None
    broadcast_at: Optional[float] = None
    confirmed_at: Optional[float] = None
    confirmations: int = 0
    retry_count: int = 0
    failure_reason: Optional[str] = None
    created_at: float = field(default_factory=time.time)


# ── RPC Client ───────────────────────────────────────────────────

class SOSTRpcClient:
    def __init__(self, url=DEFAULT_RPC_URL, user="", password=""):
        self.url = url
        self.user = user
        self.password = password

    def call(self, method, params=None):
        """Call SOST node RPC."""
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or [],
        }).encode()

        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        if self.user and self.password:
            import base64
            cred = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            req.add_header("Authorization", f"Basic {cred}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                if "error" in result and result["error"]:
                    raise Exception(f"RPC error: {result['error']}")
                return result.get("result")
        except Exception as e:
            log.error("RPC call %s failed: %s", method, e)
            raise

    def get_balance(self, address=None):
        """Get wallet balance in satoshis."""
        result = self.call("getinfo")
        # Balance is returned as string "X.XXXXXXXX"
        bal_str = result.get("balance", "0")
        return int(float(bal_str) * 1e8)

    def send(self, to_address, amount_sost):
        """Send SOST. Amount in decimal string (e.g. "97.00000000").
        Returns txid string."""
        result = self.call("send", [to_address, amount_sost])
        return result  # txid

    def get_transaction(self, txid):
        """Get transaction details including confirmations."""
        return self.call("gettransaction", [txid])

    def get_block_count(self):
        """Get current block height."""
        return self.call("getblockcount")


# ── Payout Engine ────────────────────────────────────────────────

class RewardPayoutEngine:
    def __init__(
        self,
        audit: AuditLog,
        rpc: Optional[SOSTRpcClient] = None,
        mode: PayoutMode = PayoutMode.DRY_RUN,
        min_confirmations: int = MIN_CONFIRMATIONS,
    ):
        self.audit = audit
        self.rpc = rpc or SOSTRpcClient()
        self.mode = mode
        self.min_confirmations = min_confirmations
        self._payouts: dict[str, PayoutRecord] = {}  # position_id → PayoutRecord
        self._locks: set[str] = set()  # positions currently being processed

    def create_payout(
        self,
        position_id: str,
        model: str,
        reward_owner: str,
        gross_reward: int,
        protocol_fee: int,
        fee_rate: float,
    ) -> PayoutRecord:
        """Create a payout record. Idempotent — returns existing if already created."""
        if position_id in self._payouts:
            existing = self._payouts[position_id]
            log.info("Payout already exists for %s (status=%s)", position_id, existing.status.value)
            return existing

        payout_id = f"payout-{position_id}-{int(time.time())}"
        record = PayoutRecord(
            payout_id=payout_id,
            position_id=position_id,
            model=model,
            reward_owner=reward_owner,
            gross_reward=gross_reward,
            protocol_fee=protocol_fee,
            net_reward=gross_reward - protocol_fee,
            fee_rate=fee_rate,
            status=PayoutStatus.READY,
        )
        self._payouts[position_id] = record

        self.audit.log_event(
            position_id, "payout_created",
            f"payout_id={payout_id} gross={gross_reward} fee={protocol_fee} "
            f"net={record.net_reward} to={reward_owner} mode={self.mode.value}",
        )

        return record

    def execute_payout(self, position_id: str) -> PayoutRecord:
        """Execute the payout. In dry-run, logs only. In live, broadcasts tx."""
        record = self._payouts.get(position_id)
        if not record:
            raise ValueError(f"No payout record for {position_id}")

        # Idempotency: already broadcasted or settled
        if record.status in (PayoutStatus.BROADCASTED, PayoutStatus.CONFIRMED, PayoutStatus.SETTLED):
            log.info("Payout %s already in %s state — skipping", record.payout_id, record.status.value)
            return record

        # Lock to prevent concurrent execution
        if position_id in self._locks:
            log.warning("Payout %s locked — concurrent execution blocked", position_id)
            return record
        self._locks.add(position_id)

        try:
            if self.mode == PayoutMode.DRY_RUN:
                return self._execute_dry_run(record)
            else:
                return self._execute_live(record)
        finally:
            self._locks.discard(position_id)

    def _execute_dry_run(self, record: PayoutRecord) -> PayoutRecord:
        """Dry run: calculate everything, log, but don't broadcast."""
        record.status = PayoutStatus.BROADCASTING

        net_sost = f"{record.net_reward / 1e8:.8f}"
        fee_sost = f"{record.protocol_fee / 1e8:.8f}"

        log.info(
            "[DRY-RUN] Payout %s: would send %s SOST to %s + fee %s SOST to %s",
            record.payout_id, net_sost, record.reward_owner,
            fee_sost, PROTOCOL_FEE_ADDRESS,
        )

        record.reward_txid = f"dry-run-{record.payout_id}-reward"
        record.fee_txid = f"dry-run-{record.payout_id}-fee"
        record.broadcast_at = time.time()
        record.status = PayoutStatus.CONFIRMED
        record.confirmed_at = time.time()
        record.confirmations = self.min_confirmations

        self.audit.log_event(
            record.position_id, "payout_dry_run",
            f"net={net_sost} to={record.reward_owner} fee={fee_sost} "
            f"to={PROTOCOL_FEE_ADDRESS} model={record.model}",
        )

        return record

    def _execute_live(self, record: PayoutRecord) -> PayoutRecord:
        """Live: actually broadcast transactions."""
        record.status = PayoutStatus.BROADCASTING

        net_sost = f"{record.net_reward / 1e8:.8f}"
        fee_sost = f"{record.protocol_fee / 1e8:.8f}"

        # 1. Check balance
        try:
            balance = self.rpc.get_balance()
            needed = record.net_reward + record.protocol_fee + 1000  # + tx fee margin
            if balance < needed:
                record.status = PayoutStatus.FAILED
                record.failure_reason = f"insufficient_balance: have={balance} need={needed}"
                log.error("Payout %s: insufficient balance (%d < %d)", record.payout_id, balance, needed)
                self.audit.log_event(record.position_id, "payout_failed", record.failure_reason)
                return record
        except Exception as e:
            record.status = PayoutStatus.FAILED
            record.failure_reason = f"balance_check_failed: {e}"
            log.error("Payout %s: balance check failed: %s", record.payout_id, e)
            return record

        # 2. Send reward to user
        try:
            log.info("Broadcasting reward: %s SOST to %s", net_sost, record.reward_owner)
            reward_txid = self.rpc.send(record.reward_owner, net_sost)
            record.reward_txid = reward_txid
            record.broadcast_at = time.time()
            log.info("Reward txid: %s", reward_txid)
        except Exception as e:
            record.status = PayoutStatus.FAILED
            record.failure_reason = f"reward_send_failed: {e}"
            record.retry_count += 1
            log.error("Payout %s: reward send failed: %s", record.payout_id, e)
            self.audit.log_event(record.position_id, "payout_failed", record.failure_reason)
            return record

        # 3. Send protocol fee
        if record.protocol_fee > 0:
            try:
                log.info("Broadcasting fee: %s SOST to %s", fee_sost, PROTOCOL_FEE_ADDRESS)
                fee_txid = self.rpc.send(PROTOCOL_FEE_ADDRESS, fee_sost)
                record.fee_txid = fee_txid
                log.info("Fee txid: %s", fee_txid)
            except Exception as e:
                # Fee send failed but reward was sent — log but don't fail the payout
                log.error("Fee send failed (reward already sent): %s", e)
                record.fee_txid = f"FAILED: {e}"

        record.status = PayoutStatus.BROADCASTED

        self.audit.log_event(
            record.position_id, "payout_broadcasted",
            f"reward_txid={record.reward_txid} fee_txid={record.fee_txid} "
            f"net={net_sost} fee={fee_sost} to={record.reward_owner}",
        )

        return record

    def check_confirmations(self, position_id: str) -> PayoutRecord:
        """Check if a broadcasted payout has enough confirmations."""
        record = self._payouts.get(position_id)
        if not record or record.status != PayoutStatus.BROADCASTED:
            return record

        if not record.reward_txid or record.reward_txid.startswith("dry-run"):
            record.status = PayoutStatus.CONFIRMED
            record.confirmed_at = time.time()
            return record

        try:
            tx = self.rpc.get_transaction(record.reward_txid)
            if tx and isinstance(tx, dict):
                confs = tx.get("confirmations", 0)
                record.confirmations = confs
                if confs >= self.min_confirmations:
                    record.status = PayoutStatus.CONFIRMED
                    record.confirmed_at = time.time()
                    log.info(
                        "Payout %s confirmed (%d confirmations)",
                        record.payout_id, confs,
                    )
                    self.audit.log_event(
                        record.position_id, "payout_confirmed",
                        f"txid={record.reward_txid} confirmations={confs}",
                    )
        except Exception as e:
            log.warning("Confirmation check failed for %s: %s", record.payout_id, e)

        return record

    def finalize(self, position_id: str) -> bool:
        """Mark payout as SETTLED after confirmation. Returns True if finalized."""
        record = self._payouts.get(position_id)
        if not record:
            return False
        if record.status == PayoutStatus.SETTLED:
            return True
        if record.status != PayoutStatus.CONFIRMED:
            return False

        record.status = PayoutStatus.SETTLED
        self.audit.log_event(
            record.position_id, "payout_settled",
            f"payout_id={record.payout_id} reward_txid={record.reward_txid} "
            f"fee_txid={record.fee_txid} net={record.net_reward} "
            f"confirmations={record.confirmations}",
        )
        log.info("Payout %s: SETTLED (txid=%s)", record.payout_id, record.reward_txid)
        return True

    # ── Reconciliation ───────────────────────────────────────────

    def reconcile(self) -> list[dict]:
        """Detect and report inconsistencies."""
        issues = []
        for pid, record in self._payouts.items():
            if record.status == PayoutStatus.BROADCASTING:
                # Stuck in broadcasting — no txid
                if not record.reward_txid:
                    issues.append({
                        "position_id": pid,
                        "issue": "stuck_broadcasting_no_txid",
                        "payout_id": record.payout_id,
                        "action": "retry or manual check",
                    })
            elif record.status == PayoutStatus.BROADCASTED:
                # Has txid but not confirmed yet
                age = time.time() - (record.broadcast_at or 0)
                if age > 3600:  # > 1 hour without confirmation
                    issues.append({
                        "position_id": pid,
                        "issue": "broadcasted_no_confirmation_1h",
                        "txid": record.reward_txid,
                        "age_seconds": int(age),
                        "action": "check chain for txid",
                    })
            elif record.status == PayoutStatus.FAILED:
                if record.retry_count < 3:
                    issues.append({
                        "position_id": pid,
                        "issue": "failed_retryable",
                        "reason": record.failure_reason,
                        "retries": record.retry_count,
                        "action": "auto-retry possible",
                    })
        return issues

    def get_payout(self, position_id: str) -> Optional[PayoutRecord]:
        return self._payouts.get(position_id)

    def get_all_payouts(self) -> list[PayoutRecord]:
        return list(self._payouts.values())

    def get_stats(self) -> dict:
        stats = {"total": 0, "pending": 0, "broadcasted": 0, "confirmed": 0, "settled": 0, "failed": 0}
        for r in self._payouts.values():
            stats["total"] += 1
            if r.status == PayoutStatus.SETTLED: stats["settled"] += 1
            elif r.status == PayoutStatus.CONFIRMED: stats["confirmed"] += 1
            elif r.status == PayoutStatus.BROADCASTED: stats["broadcasted"] += 1
            elif r.status == PayoutStatus.FAILED: stats["failed"] += 1
            else: stats["pending"] += 1
        return stats
