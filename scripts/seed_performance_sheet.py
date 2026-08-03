#!/usr/bin/env python
"""Create and populate a performance spreadsheet.

Idempotent: creates any missing tab, and skips seeding a tab that already has
rows unless --force is given. Safe to re-run after adding a tab.

    # look, change nothing
    python scripts/seed_performance_sheet.py --dry-run --admin-email you@amba.com

    # create tabs and seed reference data
    python scripts/seed_performance_sheet.py --admin-email you@amba.com

    # against a scratch copy rather than whatever secrets.toml points at
    python scripts/seed_performance_sheet.py --admin-email you@amba.com \
        --spreadsheet-id 1AbC...

Employee emails are seeded blank on purpose. Guessing addresses would create
accounts that silently match nobody at sign-in; a blank is flagged by the
Admin tab's health check, which is a visible problem rather than a hidden one.
The one exception is --admin-email, which bootstraps a single admin who can
then fill in the rest through the UI.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.performance import seed_data  # noqa: E402
from src.performance.models.performance_models import (  # noqa: E402
    SHEET_MODELS,
    BusinessNeed,
    Employee,
    KPILibraryEntry,
    LevelConfig,
    Parameter,
    Pillar,
    Role,
    new_id,
)
from src.performance.repository.performance_repository import (  # noqa: E402
    PerformanceRepository,
    PerformanceRepositoryError,
)

ADMIN_EMP_ID = "E03"  # VP Strategy & BD — custodian of the performance system


def _log(message: str) -> None:
    print(message, flush=True)


def build_parameters() -> list[Parameter]:
    return [
        Parameter(key=key, value=value, description=description)
        for key, value, description in seed_data.PARAMETERS
    ]


def build_levels() -> list[LevelConfig]:
    return [
        LevelConfig(
            level=level, rank=rank, variable_pct=variable,
            company_share=co, individual_share=ind,
        )
        for level, rank, variable, co, ind in seed_data.LEVELS
    ]


def build_employees(admin_email: str) -> list[Employee]:
    out: list[Employee] = []
    for emp_id, name, designation, level, department, manager in seed_data.EMPLOYEES:
        is_admin = emp_id == ADMIN_EMP_ID
        out.append(Employee(
            emp_id=emp_id,
            name=name,
            # Only the bootstrap admin gets an address; the rest are filled in
            # through the Admin tab so nobody invents a mailbox.
            email=admin_email if is_admin else "",
            designation=designation,
            level=level,
            department=department,
            reports_to_emp_id=manager,
            status="active",
            is_admin=is_admin,
        ))
    return out


def build_roles() -> list[Role]:
    return [
        Role(
            role_id=role_id, designation=designation, level=level,
            department=department, primary_ownership=ownership,
            not_responsible_for=not_responsible, active=True,
        )
        for role_id, designation, level, department, ownership, not_responsible
        in seed_data.ROLES
    ]


def build_kpi_library() -> list[KPILibraryEntry]:
    out: list[KPILibraryEntry] = []
    for (kpi_id, applies_to, name, direction, unit, method, source,
         weight, outcome, layer) in seed_data.KPI_LIBRARY:
        out.append(KPILibraryEntry(
            kpi_id=kpi_id,
            pillar=Pillar.RESULT.value,
            applies_to=applies_to,
            name=name,
            direction=direction.value,
            unit=unit,
            measurement_method=method,
            data_source=source,
            default_weight=weight,
            outcome_type=outcome.value,
            accountability_layer=layer.value,
            active=True,
        ))
    return out


def build_kbd_baseline(period: str, actor: str) -> list[BusinessNeed]:
    """The company-wide Behaviour and Discipline items for a month.

    Published as business needs so they cascade onto every card the same way
    numeric targets do, rather than being hardcoded in the scoring screen.
    """
    stamp = datetime.now().isoformat(timespec="seconds")
    out: list[BusinessNeed] = []
    for pillar, defaults in (
        (Pillar.BEHAVIOUR, seed_data.BEHAVIOUR_DEFAULTS),
        (Pillar.DISCIPLINE, seed_data.DISCIPLINE_DEFAULTS),
    ):
        for metric, note in defaults:
            out.append(BusinessNeed(
                need_id=new_id("BN"),
                period=period,
                pillar=pillar.value,
                area="Company-wide",
                metric=metric,
                note=note,
                is_company_default=True,
                published_by=actor,
                published_at=stamp,
            ))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-email", required=True,
        help="Microsoft account that bootstraps admin access (set on E03).",
    )
    parser.add_argument(
        "--spreadsheet-id",
        help="Target sheet. Defaults to [performance].performance_sheets_id.",
    )
    parser.add_argument(
        "--baseline-period",
        help="Seed the Behaviour/Discipline baseline for this YYYY-MM period.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-seed tabs that already contain rows (appends duplicates).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be written without touching the sheet.",
    )
    args = parser.parse_args()

    repo = PerformanceRepository(spreadsheet_id=args.spreadsheet_id)

    if args.dry_run:
        _log("DRY RUN — nothing will be written.\n")
        _log(f"Target spreadsheet : {repo.spreadsheet_id or '(not configured)'}")
        _log(f"Bootstrap admin    : {args.admin_email} -> {ADMIN_EMP_ID}\n")
        _log(f"Tabs ({len(SHEET_MODELS)}):")
        for model in SHEET_MODELS:
            _log(f"  {model.SHEET:<20} {len(model.HEADERS):>2} columns")
        _log("\nSeed volumes:")
        _log(f"  Parameters   {len(build_parameters()):>3}")
        _log(f"  Levels       {len(build_levels()):>3}")
        _log(f"  Employees    {len(build_employees(args.admin_email)):>3}")
        _log(f"  Roles        {len(build_roles()):>3}")
        _log(f"  KPILibrary   {len(build_kpi_library()):>3}")
        if args.baseline_period:
            _log(f"  BusinessNeeds{len(build_kbd_baseline(args.baseline_period, '')):>3}"
                 f"  (B/D baseline for {args.baseline_period})")
        return 0

    ok, message = repo.health_check()
    if not ok:
        _log(f"ERROR: {message}")
        return 1
    _log(f"Connected to {repo.spreadsheet_id}\n")

    _log("Ensuring tabs...")
    for sheet, created in repo.ensure_tabs().items():
        _log(f"  {'ok ' if created else 'FAILED'} {sheet}")

    def seed(label: str, existing: list, write) -> None:
        if existing and not args.force:
            _log(f"  skip {label} — {len(existing)} rows already present")
            return
        write()
        _log(f"  ok   {label}")

    _log("\nSeeding reference data...")
    try:
        seed("Parameters", list(repo.get_parameters().items()),
             lambda: [repo.save_parameter(p.key, p.value, p.description)
                      for p in build_parameters()])
        seed("Levels", repo.get_levels(),
             lambda: [repo._upsert(lvl) for lvl in build_levels()])
        seed("Employees", repo.get_employees(),
             lambda: [repo.save_employee(emp)
                      for emp in build_employees(args.admin_email)])
        seed("Roles", repo.get_roles(),
             lambda: [repo._upsert(role) for role in build_roles()])
        seed("KPILibrary", repo.get_kpi_library(active_only=False),
             lambda: [repo.save_kpi_library_entry(e) for e in build_kpi_library()])

        if args.baseline_period:
            needs = build_kbd_baseline(args.baseline_period, ADMIN_EMP_ID)
            seed(f"BusinessNeeds ({args.baseline_period})",
                 repo.get_business_needs(args.baseline_period),
                 lambda: repo.save_business_needs(needs))
    except PerformanceRepositoryError as exc:
        _log(f"\nERROR: {exc}")
        return 1

    _log("\nDone.\n")
    _log("Next steps:")
    _log(f"  1. Sign in as {args.admin_email} and open Performance > Admin.")
    _log("  2. Fill in every employee's Microsoft email — until then they")
    _log("     cannot sign in, and the health check will flag them.")
    _log("  3. Confirm the org tree matches reality, then publish business")
    _log("     needs for the first month.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
