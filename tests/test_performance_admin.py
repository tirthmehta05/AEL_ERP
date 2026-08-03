"""Admin tab and seed data, driven by an in-memory repository.

Exercises the seeded org against the real permission and validation rules
without needing a live Google Sheet, so the tab is known-good before it is
pointed at one.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.performance import seed_data
from src.performance.models.performance_models import (
    SHEET_MODELS,
    Direction,
    Employee,
    Pillar,
)
from src.performance.service.cycle_service import (
    generate_planning_tasks,
    generate_scoring_tasks,
)
from src.performance.service.org_service import OrgChart

import scripts.seed_performance_sheet as seeder


@pytest.fixture
def seeded_chart() -> OrgChart:
    """The org exactly as the seed script would write it."""
    return OrgChart(
        seeder.build_employees("admin@amba.com"), as_of=date(2026, 4, 30)
    )


# --------------------------------------------------------------------------
# Seed data integrity
# --------------------------------------------------------------------------


def test_seeded_org_matches_foundation_doc_02(seeded_chart):
    assert len(seeded_chart.all_employees()) == 12
    assert seeded_chart.root().name == "Ketan Mehta"
    assert seeded_chart.depth("E07") == 3          # Vijay, under Sneha
    assert seeded_chart.max_depth() == 3


def test_seeded_management_is_the_expected_three(seeded_chart):
    assert {e.name for e in seeded_chart.management()} == {
        "Ketan Mehta", "Sarika Bhise", "Tirth Mehta"
    }


def test_seeded_tree_is_valid_apart_from_the_deliberate_blank_emails(seeded_chart):
    """Emails are seeded blank on purpose, so only that should be flagged.

    Inventing addresses would create accounts matching nobody at sign-in;
    blanks surface in the health check instead.
    """
    problems = seeded_chart.validate_tree()
    assert all("no email" in problem for problem in problems)
    assert len(problems) == 11    # everyone except the bootstrap admin


def test_bootstrap_admin_can_sign_in_and_is_the_only_admin(seeded_chart):
    admin = seeded_chart.by_email("admin@amba.com")
    assert admin is not None and admin.emp_id == seeder.ADMIN_EMP_ID
    assert seeded_chart.is_admin(admin.emp_id)
    admins = [e for e in seeded_chart.all_employees() if seeded_chart.is_admin(e.emp_id)]
    assert len(admins) == 1


def test_every_seeded_employee_has_a_matching_role_definition():
    """The AI prompt reads Primary Ownership by designation, so a missing
    role would silently produce an unanchored draft."""
    designations = {row[2] for row in seed_data.EMPLOYEES}
    role_designations = {row[1] for row in seed_data.ROLES}
    assert designations <= role_designations


def test_kpi_library_covers_every_role_that_gets_scored(seeded_chart):
    scored = {
        e.designation for e in seeded_chart.all_employees()
        if e.emp_id != seeded_chart.root().emp_id
    }
    covered = {row[1] for row in seed_data.KPI_LIBRARY}
    assert scored <= covered


def test_lower_is_better_kpis_are_marked_as_such():
    """The whole reason direction is stored.

    Under the workbook's Actual/Target these score a miss as an
    overachievement — scrap of 10% against a 5% target hits the 120% cap.
    """
    by_name = {row[2]: row[3] for row in seed_data.KPI_LIBRARY}
    for name in (
        "Scrap Rate", "Machine Downtime", "Safety Incidents",
        "Debtor Days (DSO)", "Overdue Receivables", "Trading Overdue",
        "Production Data Accuracy", "Booking Accuracy in Tally",
        "Customer QC Query Response Time", "Suspense Entries Pending",
    ):
        assert by_name[name] is Direction.LOWER, f"{name} should be lower-is-better"

    for name in ("Production Volume", "Trading Volume", "On-Time Delivery"):
        assert by_name[name] is Direction.HIGHER


def test_kpi_library_ids_are_unique():
    ids = [row[0] for row in seed_data.KPI_LIBRARY]
    assert len(ids) == len(set(ids))


def test_seeded_kpi_default_weights_are_plausible():
    """Weights come from the Scaling Plan, where each role totals 100."""
    totals: dict[str, int] = {}
    for row in seed_data.KPI_LIBRARY:
        totals[row[1]] = totals.get(row[1], 0) + row[7]
    for role, total in totals.items():
        assert total == 100, f"{role} default weights total {total}, expected 100"


def test_behaviour_defaults_are_the_six_company_values():
    names = {name for name, _ in seed_data.BEHAVIOUR_DEFAULTS}
    assert names == {
        "Integrity", "Ownership", "Customer First",
        "Quality Without Compromise", "Drive & Discipline", "Respect & Trust",
    }


def test_knowledge_has_no_company_defaults():
    """A company-wide learning goal would invite exactly the copy-paste the
    remark rules exist to prevent."""
    baseline = seeder.build_kbd_baseline("2026-09", "E03")
    pillars = {need.pillar for need in baseline}
    assert pillars == {Pillar.BEHAVIOUR.value, Pillar.DISCIPLINE.value}
    assert all(need.is_company_default for need in baseline)


def test_cadence_parameters_cover_every_cycle_key():
    from src.performance.service.cycle_service import DEFAULT_CYCLE_PARAMS

    seeded = {key for key, _, _ in seed_data.PARAMETERS}
    assert set(DEFAULT_CYCLE_PARAMS) <= seeded


def test_seeded_parameter_keys_are_unique():
    keys = [key for key, _, _ in seed_data.PARAMETERS]
    assert len(keys) == len(set(keys))


# --------------------------------------------------------------------------
# Admin edits
# --------------------------------------------------------------------------


def test_deactivating_an_employee_removes_them_from_the_cycle(seeded_chart):
    people = seeder.build_employees("admin@amba.com")
    for employee in people:
        if employee.emp_id == "E08":
            employee.status = "inactive"
    chart = OrgChart(people, as_of=date(2026, 4, 30))

    assert "E08" not in {e.emp_id for e in chart.all_employees()}
    subjects = {t.subject_emp_id for t in generate_scoring_tasks("2026-05", chart)}
    assert "E08" not in subjects
    # Their former peers are untouched.
    assert {"E09", "E07"} <= subjects


def test_adding_an_employee_extends_the_cycle(seeded_chart):
    people = seeder.build_employees("admin@amba.com")
    people.append(Employee(
        emp_id="E13", name="New Joiner", email="new@amba.com",
        designation="Associate - Trading Support", level="Associate",
        department="Operations", reports_to_emp_id="E06", status="active",
    ))
    chart = OrgChart(people, as_of=date(2026, 4, 30))

    assert chart.depth("E13") == 3
    assert not chart.is_management("E13")
    planning = generate_planning_tasks("2026-05", chart)
    theirs = [t for t in planning if t.subject_emp_id == "E13"]
    assert theirs, "a new employee should receive cycle tasks"
    assert any(t.owner_emp_id == "E06" for t in theirs)


def test_promoting_someone_to_report_to_the_md_makes_them_management(seeded_chart):
    people = seeder.build_employees("admin@amba.com")
    for employee in people:
        if employee.emp_id == "E05":
            employee.reports_to_emp_id = "E01"
    chart = OrgChart(people, as_of=date(2026, 4, 30))

    assert chart.depth("E05") == 1
    assert chart.is_management("E05")
    # Their team moves up with them.
    assert chart.depth("E07") == 2


def test_reassignment_validation_blocks_a_cycle_before_it_is_written(seeded_chart):
    assert seeded_chart.validate_reassignment("E02", "E11") is not None
    assert seeded_chart.validate_reassignment("E11", "E05") is None


def test_second_root_is_rejected(seeded_chart):
    assert seeded_chart.validate_reassignment("E05", "") is not None


# --------------------------------------------------------------------------
# Sheet contract
# --------------------------------------------------------------------------


def test_every_model_header_maps_to_a_real_field():
    """to_row/from_row are generic over HEADERS, so a typo here would write a
    column of blanks rather than failing loudly."""
    for model in SHEET_MODELS:
        missing = [h for h in model.HEADERS if h not in model.model_fields]
        assert not missing, f"{model.__name__} headers not on the model: {missing}"


def test_sheet_names_are_unique():
    names = [model.SHEET for model in SHEET_MODELS]
    assert len(names) == len(set(names))


def test_round_trip_through_a_sheet_row_preserves_values():
    original = seeder.build_employees("admin@amba.com")[6]   # Vijay
    row = original.to_row()
    restored = Employee.from_row(dict(zip(Employee.HEADERS, row)))
    assert restored.emp_id == original.emp_id
    assert restored.reports_to_emp_id == original.reports_to_emp_id
    assert restored.is_admin == original.is_admin
    assert restored.status == original.status
