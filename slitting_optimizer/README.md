# Slitting Optimizer — API Service

Auction slitting-plan optimizer for CRNO coil auctions, exposed as a standalone
HTTP API. Given an auction sheet + customer requirements it returns, per lot, a
**max-bid price** (≥8% margin), the slitting plan, and — as lots are won/lost
during the auction — re-prices the remaining lots so you never overbid.

The optimization engine (`engine/`) is the **validated** core: an item-MILP
(OR-Tools CP-SAT) + sequential-auction incremental re-pricer + tiered monthly
holding. Its behavior is pinned by `validate/validate_incremental.py` (39/39,
two-sided: safety + usefulness). It is a byte-faithful copy of the proven
prototypes — copied, never moved; the originals in the ERP tree are untouched.

## Layout

```
engine/      pure solver (domain core) — no IO, no web
app/
  controllers/  FastAPI routers (HTTP only)
  services/     orchestration (pricing, auction session, won/lost reprice)
  repository/   parse auction .xlsx + customer workbook; session store
  core/         config, security (MSAL/JWT), background-job runner
  schemas/      Pydantic DTOs
validate/    the 39-check harness (imports engine only)
tools/       make_sample_customer_workbook.py
tests/       API integration tests
data/        git-ignored (uploads, sessions, samples)
```

## Inputs

- **Auction**: the raw `CRNO <date>.xlsx` (one sheet per lot) — uploaded as-is.
- **Customers**: one workbook, **one tab per customer** (tab name = customer).
  Columns: `Width(mm) | MonthlyQty(MT) | Rate(₹/kg) | Grades | Coatings |
  Thickness(mm) | MinCoilQty(kg) | Notes`. Grades/Coatings/Thickness are
  explicit pipe-separated lists (no substitution logic — what you type is what
  is matched). `MonthlyQty` is the monthly run-rate (drives demand and the
  holding-slice width).

## Run

Dependencies are managed with **uv** (single source of truth:
`pyproject.toml` + `uv.lock`).

```bash
uv sync                                   # create .venv + install deps

# prove the engine is intact in this repo (must print 39 passed, 0 failed)
SLIT_TIME_LIMIT=20 uv run python -m validate.validate_incremental

# repository ↔ engine equivalence (must print ALL PASS)
uv run python -m tools.check_repos

# dev server (auth off)
AUTH_DISABLED=true uv run uvicorn app.main:app --reload

# tests
uv run pytest -q

# or containerized (deps from uv.lock)
docker compose up --build
```

## Tunable operation parameters

Business knobs are env-driven — **no code edit, no image rebuild**. Set them
in `.env` (or compose / real env), then `docker compose up -d --force-recreate`.
Unset = the validated defaults (behaviour unchanged → the 39/39 harness still
holds). Live values are reported at `GET /health` → `params`.

| Env | Default | Meaning |
|---|---|---|
| `SLIT_KNIFE_MAX` | 12 | max strips/cuts per coil (slitter knife limit) |
| `SLIT_EDGE_TRIM_MM` | 3 | min edge trim when slitting, mm |
| `SLIT_SCRAP_RATE` | 34 | ₹/kg scrap sells for |
| `SLIT_SLITTING_COST` | 4 | ₹/kg slitting cost |
| `SLIT_HOLDING_FACTOR_PCT` | 95 | month-1 held-stock value % |
| `SLIT_HOLDING_STEP_PCT` | 5 | extra % lost per additional month |
| `SLIT_TARGET_MARGIN` | 0.08 | margin used to derive the max-bid |
| `SLIT_TIME_LIMIT` | 300 | per-lot CP-SAT solve budget, seconds |
| `SLIT_BAND_MM` | 650 | boundary mm; ≤band = narrow, >band = wide |
| `SLIT_KNIFE_MAX_WIDE` | =narrow | wide-band override (unset = flat) |
| `SLIT_EDGE_TRIM_MM_WIDE` | =narrow | wide-band override |
| `SLIT_SLITTING_COST_WIDE` | =narrow | wide-band override |
| `SLIT_SALVAGE` | _empty_ | per-coating whole-coil dump at `lot_start − ₹`, e.g. `C6L:2,C3H:2,C3L:2,UC:4` |

The engine reads these from `os.environ` directly (stays a pure module); the
config layer mirrors them only for the `/health` report.

## Auth

The API is a **resource server**: the ERP signs the user in via MSAL/Entra,
acquires a token for this API's exposed scope, and forwards it as
`Authorization: Bearer …`. The API validates signature (tenant JWKS), `iss`,
`aud`, `exp`. Set `AUTH_DISABLED=true` for local dev. Production env vars:
`ENTRA_TENANT_ID`, `ENTRA_API_AUDIENCE`.

Entra admin one-time setup: register this API + expose a scope; grant the
existing ERP app registration delegated permission to that scope + admin
consent; restrict to the bidding users. No login endpoint here.

## Out of scope (Phase 2b)

ERP Streamlit page + MSAL token-forwarding wiring (lives in the ERP repo),
production host/VM selection, real customer rates.
