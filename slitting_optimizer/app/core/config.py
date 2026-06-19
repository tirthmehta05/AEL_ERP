"""Typed, env-driven service config (pydantic-settings) — consistent with the
pydantic DTO layer.

The ENGINE reads its operation parameters (knife max, scrap rate, etc.)
directly from os.environ so it stays a pure module. The mirrored fields below
exist ONLY so the service can REPORT the running config (e.g. /health) — they
must keep the same env aliases and defaults as engine/optimizer.py.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# slitting-optimizer/  (this file is app/core/config.py → parents[2])
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # storage
    DATA_DIR: Path = Field(default=REPO_ROOT / "data",
                           validation_alias="SLIT_DATA_DIR")

    # auth — resource-server validation of the ERP-forwarded MSAL token
    AUTH_DISABLED: bool = Field(default=True,           # off for local dev
                                validation_alias="AUTH_DISABLED")
    ENTRA_TENANT_ID: str | None = Field(default=None,
                                        validation_alias="ENTRA_TENANT_ID")
    ENTRA_API_AUDIENCE: str | None = Field(
        default=None, validation_alias="ENTRA_API_AUDIENCE")

    # ---- engine operation parameters: MIRROR ONLY (for /health reporting).
    # The engine reads these env vars itself; defaults MUST match
    # engine/optimizer.py so the report reflects reality.
    SOLVE_TIME_LIMIT_S: int = Field(default=300,
                                    validation_alias="SLIT_TIME_LIMIT")
    BAND_MM: int = Field(default=650, validation_alias="SLIT_BAND_MM")
    # narrow-band (≤ BAND_MM) values reuse the existing env names
    KNIFE_MAX: int = Field(default=12, validation_alias="SLIT_KNIFE_MAX")
    EDGE_TRIM_MM: int = Field(default=3,
                              validation_alias="SLIT_EDGE_TRIM_MM")
    SLITTING_COST: float = Field(default=4,
                                 validation_alias="SLIT_SLITTING_COST")
    # wide-band (> BAND_MM); None ⇒ fall back to narrow ⇒ flat behaviour
    KNIFE_MAX_WIDE: int | None = Field(
        default=None, validation_alias="SLIT_KNIFE_MAX_WIDE")
    EDGE_TRIM_MM_WIDE: int | None = Field(
        default=None, validation_alias="SLIT_EDGE_TRIM_MM_WIDE")
    SLITTING_COST_WIDE: float | None = Field(
        default=None, validation_alias="SLIT_SLITTING_COST_WIDE")
    SCRAP_RATE: int = Field(default=34, validation_alias="SLIT_SCRAP_RATE")
    HOLDING_FACTOR_PCT: int = Field(
        default=95, validation_alias="SLIT_HOLDING_FACTOR_PCT")
    HOLDING_STEP_PCT: int = Field(
        default=5, validation_alias="SLIT_HOLDING_STEP_PCT")
    TARGET_MARGIN: float = Field(
        default=0.08, validation_alias="SLIT_TARGET_MARGIN")
    SALVAGE_RAW: str = Field(default="", validation_alias="SLIT_SALVAGE")
    # Cap on inventory months PER ORDER, only for orders whose coatings are
    # entirely salvage-eligible. Default 999 ⇒ effectively no cap ⇒ today's
    # behaviour preserved. Set to 1-2 in production to prevent over-stocking
    # at premium tier rates when real customer absorption is limited.
    MAX_INV_MONTHS: int = Field(default=999,
                                validation_alias="SLIT_MAX_INV_MONTHS")

    @property
    def SESSIONS_DIR(self) -> Path:
        return self.DATA_DIR / "sessions"

    @property
    def salvage_map(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for part in self.SALVAGE_RAW.split(","):
            part = part.strip()
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            try:
                out[k.strip()] = float(v)
            except ValueError:
                pass
        return out

    @property
    def operation_params(self) -> dict:
        """What the engine is actually running with — surfaced at /health.
        Wide-band fields fall back to narrow when unset (= flat behaviour)."""
        return {
            "band_mm": self.BAND_MM,
            "knife_max": {
                "narrow": self.KNIFE_MAX,
                "wide": self.KNIFE_MAX_WIDE if self.KNIFE_MAX_WIDE
                is not None else self.KNIFE_MAX,
            },
            "edge_trim_mm": {
                "narrow": self.EDGE_TRIM_MM,
                "wide": self.EDGE_TRIM_MM_WIDE if self.EDGE_TRIM_MM_WIDE
                is not None else self.EDGE_TRIM_MM,
            },
            "slitting_cost_per_kg": {
                "narrow": self.SLITTING_COST,
                "wide": self.SLITTING_COST_WIDE if self.SLITTING_COST_WIDE
                is not None else self.SLITTING_COST,
            },
            "scrap_rate_per_kg": self.SCRAP_RATE,
            "holding_factor_pct": self.HOLDING_FACTOR_PCT,
            "holding_step_pct": self.HOLDING_STEP_PCT,
            "target_margin": self.TARGET_MARGIN,
            "solve_time_limit_s": self.SOLVE_TIME_LIMIT_S,
            "salvage": self.salvage_map,        # {coating: rs-below-lot-start}
            "max_inv_months_for_salvage_only_orders": self.MAX_INV_MONTHS,
        }


settings = Settings()
settings.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
