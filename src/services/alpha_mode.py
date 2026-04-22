"""
SOST Gold Exchange — Alpha Mode Configuration

Loads the alpha/limited-public-alpha config and provides guard functions
that enforce deal, position, and transfer limits.

Usage:
    from src.services.alpha_mode import AlphaMode

    alpha = AlphaMode("configs/limited_public_alpha.json")
    ok, reason = alpha.can_create_deal(amount_sost=5_000_000_000, amount_gold_mg=50_000)
"""

import json
import os
import logging
from typing import Tuple

log = logging.getLogger("alpha-mode")

# Defaults used when keys are missing from config
_DEFAULT_LIMITS = {
    "max_concurrent_deals": 5,
    "max_position_size_sost": 50_000_000_000,
    "max_gold_amount_mg": 311_035,
    "max_deal_value_usd_equiv": 5_000,
    "operator_approval_required": True,
    "mainnet_enabled": False,
    "reward_right_transfers_enabled": False,
    "public_api_exposed": False,
    "max_participants": 3,
}

_DEFAULT_RESTRICTIONS = {
    "only_model_b": True,
    "only_xaut": True,
    "min_lock_duration_days": 28,
    "max_lock_duration_days": 90,
}


class AlphaMode:
    """Alpha mode configuration loader and limit enforcer."""

    def __init__(self, config_path: str = ""):
        self.config: dict = {}
        self.limits: dict = dict(_DEFAULT_LIMITS)
        self.restrictions: dict = dict(_DEFAULT_RESTRICTIONS)
        self.operator: dict = {}

        if config_path:
            self.load(config_path)

    # ── Loading ──

    def load(self, config_path: str):
        """Load and validate a JSON config file."""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Alpha config not found: {config_path}")

        with open(config_path) as f:
            self.config = json.load(f)

        self.limits.update(self.config.get("limits", {}))
        self.restrictions.update(self.config.get("restrictions", {}))
        self.operator = self.config.get("operator", {})

        self._validate()
        log.info("Alpha mode loaded: %s", self.get_mode())

    def _validate(self):
        """Basic sanity checks on loaded config."""
        lim = self.limits
        if lim["max_concurrent_deals"] < 1:
            raise ValueError("max_concurrent_deals must be >= 1")
        if lim["max_position_size_sost"] <= 0:
            raise ValueError("max_position_size_sost must be > 0")
        if lim["max_gold_amount_mg"] <= 0:
            raise ValueError("max_gold_amount_mg must be > 0")

        res = self.restrictions
        if res["min_lock_duration_days"] > res["max_lock_duration_days"]:
            raise ValueError("min_lock_duration_days exceeds max_lock_duration_days")

    # ── Query functions ──

    def get_mode(self) -> str:
        """Return the current mode string."""
        return self.config.get("mode", "mock")

    def is_mainnet_enabled(self) -> bool:
        return bool(self.limits.get("mainnet_enabled", False))

    def requires_operator_approval(self) -> bool:
        return bool(self.limits.get("operator_approval_required", True))

    # ── Guard functions ──

    def can_create_deal(
        self,
        amount_sost: int,
        amount_gold_mg: int,
        current_deal_count: int = 0,
    ) -> Tuple[bool, str]:
        """Check whether a new deal is allowed under alpha limits.

        Returns (allowed, reason).  reason is empty on success.
        """
        lim = self.limits

        if current_deal_count >= lim["max_concurrent_deals"]:
            return False, (
                f"concurrent deal limit reached "
                f"({current_deal_count}/{lim['max_concurrent_deals']})"
            )

        if amount_sost > lim["max_position_size_sost"]:
            return False, (
                f"SOST amount {amount_sost} exceeds max "
                f"{lim['max_position_size_sost']}"
            )

        if amount_gold_mg > lim["max_gold_amount_mg"]:
            return False, (
                f"gold amount {amount_gold_mg} mg exceeds max "
                f"{lim['max_gold_amount_mg']} mg"
            )

        return True, ""

    def can_create_position(self, gold_amount_mg: int) -> Tuple[bool, str]:
        """Check whether a new position with the given gold amount is allowed."""
        if gold_amount_mg > self.limits["max_gold_amount_mg"]:
            return False, (
                f"gold amount {gold_amount_mg} mg exceeds max "
                f"{self.limits['max_gold_amount_mg']} mg"
            )
        return True, ""

    def can_transfer_position(self) -> Tuple[bool, str]:
        """Check whether reward-right transfers are enabled."""
        if not self.limits.get("reward_right_transfers_enabled", False):
            return False, "reward-right transfers are disabled in alpha mode"
        return True, ""

    def check_lock_duration(self, days: int) -> Tuple[bool, str]:
        """Validate lock duration against restrictions."""
        res = self.restrictions
        min_d = res["min_lock_duration_days"]
        max_d = res["max_lock_duration_days"]
        if days < min_d:
            return False, f"lock duration {days}d is below minimum {min_d}d"
        if days > max_d:
            return False, f"lock duration {days}d exceeds maximum {max_d}d"
        return True, ""

    def to_dict(self) -> dict:
        """Serialize current config for API responses."""
        return {
            "mode": self.get_mode(),
            "limits": dict(self.limits),
            "restrictions": dict(self.restrictions),
            "operator": dict(self.operator),
        }
