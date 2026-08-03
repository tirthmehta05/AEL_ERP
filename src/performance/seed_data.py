"""Initial content for a fresh performance spreadsheet.

Transcribed from the Foundation documents so the system starts with Amba's
real structure rather than placeholder data:

* org tree and Primary Ownership - `02_Organization_Structure.docx`
* KPI library - `06_Scaling_Plan_FY26-27.xlsx`, "Employee KPIs"
* pillar weights, curves, gates - `04_Performance_Master.xlsx`, "Parameters"
* Behaviour rubric - the six Values in `01_Vision_Mission_Values.docx`
* Discipline rubric - `04_Performance_Master.xlsx`, "Rating Guide"

Two transcription notes:

1. The Scaling Plan names the trading associate "Rhea"; Org Doc 02 names her
   "Riya Telawade". Doc 02 is the org authority, so that is what is seeded.
2. `direction` is assigned per KPI here, which is the whole point of the
   rewrite. The Performance Master computes Actual/Target for everything,
   which scores a missed scrap or DSO target as an overachievement. Every
   lower-is-better KPI below is marked LOWER so scoring inverts the ratio.
"""

from __future__ import annotations

from src.performance.models.performance_models import (
    AccountabilityLayer as Layer,
    Direction,
    OutcomeType,
    Pillar,
)

# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------

# key, value, description
PARAMETERS: list[tuple[str, str, str]] = [
    # -- pillar weights (Performance Master Parameters section 3)
    ("pillar.result", "0.60", "Result weight in the monthly score"),
    ("pillar.knowledge", "0.20", "Knowledge weight"),
    ("pillar.behaviour", "0.10", "Behaviour weight"),
    ("pillar.discipline", "0.10", "Discipline weight"),
    # -- scoring rules
    ("score.achievement_cap", "120", "Max % credit for a single KPI"),
    ("score.pillar_floor_rating", "2",
     "K/B/D rolled-up rating below this caps the monthly score"),
    ("score.pillar_floor_cap", "70", "Cap applied when the pillar floor trips"),
    ("score.min_remark_chars", "100",
     "Minimum characters for a scoring remark"),
    # -- card quality gate
    ("card.min_kpis", "3", "Minimum Result KPIs on a card"),
    ("card.max_kpis", "6",
     "Maximum Result KPIs — the Performance Master has six slots"),
    ("card.max_single_weight", "40", "Warn above this weight on one KPI"),
    ("card.min_single_weight", "10", "Warn below this weight on one KPI"),
    ("card.min_outcome_weight_pct", "60",
     "Warn if less than this share of weight is Outcome or Output"),
    # -- cadence (mirrors DEFAULT_CYCLE_PARAMS in cycle_service)
    ("cycle.publish_needs_day", "18", "Business needs published for next month"),
    ("cycle.set_cards_days", "1:20,2:23,3:25,4:27",
     "Card-setting deadline by subject depth, day of the preceding month"),
    ("cycle.acknowledge_day", "28", "Employee acknowledges their card"),
    ("cycle.exception_review_day", "29", "Management exception review"),
    ("cycle.check_in_day", "16", "Mid-month check-in, inside the live month"),
    ("cycle.amendment_close_day", "10",
     "Last day a live card may be amended, with one-level-up approval"),
    ("cycle.self_score_day", "2", "Employee self-scores the closed month"),
    ("cycle.manager_score_days", "1:5,2:4,3:3,4:3",
     "Manager scoring deadline by subject depth — deepest first, so a "
     "manager's Direct Reports' Avg Score can be computed before their own"),
    ("cycle.calibrate_day", "6", "Management calibration"),
    ("cycle.lock_day", "7", "Month locked, scorecards published"),
    ("cycle.quarterly_review_day", "15", "Quarterly 1:1 completed"),
    ("cycle.quarter_validate_day", "18", "Management validates the quarter"),
    # -- alerts
    ("alert.reminder_days_before", "2", "First nudge, days before due"),
    ("alert.escalate_after_days", "3",
     "Days overdue before escalation to management"),
]

# --------------------------------------------------------------------------
# Levels — Performance Master Parameters section 2 (Year 1 reduced rates)
# --------------------------------------------------------------------------

# level, rank, variable_pct, company_share, individual_share
LEVELS: list[tuple[str, int, float, float, float]] = [
    ("MD", 1, 0.00, 0.00, 0.00),
    ("Director", 2, 0.10, 0.60, 0.40),
    ("VP", 3, 0.08, 0.50, 0.50),
    ("Sr. Associate", 4, 0.05, 0.35, 0.65),
    ("Associate", 5, 0.03, 0.20, 0.80),
]

# --------------------------------------------------------------------------
# Employees — Org Doc 02, April 2026
# --------------------------------------------------------------------------

# emp_id, name, designation, level, department, reports_to
EMPLOYEES: list[tuple[str, str, str, str, str, str]] = [
    ("E01", "Ketan Mehta", "Managing Director", "MD", "Executive", ""),
    ("E02", "Sarika Bhise", "Director - Operations & Corporate Services",
     "Director", "Operations", "E01"),
    ("E03", "Tirth Mehta", "VP - Strategy & Business Development",
     "VP", "Strategy & BD", "E01"),
    ("E04", "Dhara Bhavsar", "VP - Corporate Services",
     "VP", "Corporate Services", "E02"),
    ("E05", "Sneha Kadam", "Sr. Associate - Manufacturing",
     "Sr. Associate", "Operations", "E02"),
    ("E06", "Pranay Shinde", "Sr. Associate - Trading",
     "Sr. Associate", "Operations", "E02"),
    ("E07", "Vijay", "Sr. Associate - Shop Floor (Nanded)",
     "Sr. Associate", "Operations", "E05"),
    ("E08", "Pravin Mhade", "Associate - Manufacturing (IC)",
     "Associate", "Operations", "E05"),
    ("E09", "Jagruti Sutar", "Associate - Manufacturing Support",
     "Associate", "Operations", "E05"),
    ("E10", "Riya Telawade", "Associate - Trading Support",
     "Associate", "Operations", "E06"),
    ("E11", "Aditi Patel", "Associate - Accounts (Senior)",
     "Associate", "Corporate Services", "E04"),
    ("E12", "Akshay Sawant", "Associate - Accounts (Junior)",
     "Associate", "Corporate Services", "E04"),
]

# --------------------------------------------------------------------------
# Roles — Primary Ownership, Org Doc 02. Feeds the AI prompt builder.
# --------------------------------------------------------------------------

# role_id, designation, level, department, primary_ownership, not_responsible_for
ROLES: list[tuple[str, str, str, str, str, str]] = [
    ("R01", "Managing Director", "MD", "Executive",
     "Strategic direction and long-term health of Amba. Company P&L, capital "
     "allocation and shareholder value. Key OEM customer relationships and the "
     "Kapson partnership. Strategic purchase of CRNO and CRGO coils - pricing, "
     "mill selection and commercial terms. Final authority on material business "
     "decisions and senior hiring.",
     "Departmental execution; day-to-day operational errors; tactical decisions "
     "within agreed budget and plan."),
    ("R02", "Director - Operations & Corporate Services", "Director", "Operations",
     "End-to-end delivery of Operations and Corporate Services. Integrity and "
     "timeliness of the monthly review rhythm. Process design, SOPs and "
     "checkpoints across her departments. Development and performance of Sr. "
     "Associates and VPs reporting to her. Systemic and design-level failures.",
     "Individual Associate transactional errors on first occurrence; functions "
     "outside her department; strategic calls reserved for MD."),
    ("R03", "VP - Strategy & Business Development", "VP", "Strategy & BD",
     "Growth beyond the current customer base. Development of new manufacturing "
     "capacity, capability, business lines and strategic partnerships. Architect "
     "and custodian of the performance-management system. IT and Systems across "
     "Amba. Execution of strategic projects assigned by the MD.",
     "Operational decisions outside his function; strategic business calls; "
     "errors of people outside his reporting line."),
    ("R04", "VP - Corporate Services", "VP", "Corporate Services",
     "Statutory and regulatory standing - GST, TDS, Income Tax, ROC, BSE listing, "
     "labour and payroll compliance. Financial discipline and cashflow visibility. "
     "Health of receivables and credit control. Integrity of Kapson commercial "
     "reconciliation and IRR. Audit and disclosure readiness. HR operations and "
     "office administration.",
     "Operational decisions outside her function; strategic business calls."),
    ("R05", "Sr. Associate - Manufacturing", "Sr. Associate", "Operations",
     "Manufacturing output of the Pune plant - on-plan, on-spec, on-time "
     "production and dispatch. Availability of raw material and semi-finished "
     "stock. In-house quality and the QC interface with customers. Physical stock "
     "accuracy across coils and EI. Supervision and development of the "
     "manufacturing team.",
     "Individual Associate errors on first occurrence; process or role design."),
    ("R06", "Sr. Associate - Trading", "Sr. Associate", "Operations",
     "Trading business result - volumes, margins, collection and customer "
     "satisfaction on CRNO / CRGO. Operational relationships with mills including "
     "auction and MOU discipline. Day-to-day Kapson operational flow on the "
     "trading side. Trading outstanding and collection discipline. Supervision and "
     "development of the trading team.",
     "Individual Associate errors on first occurrence; process or role design."),
    ("R07", "Sr. Associate - Shop Floor (Nanded)", "Sr. Associate", "Operations",
     "Execution of the daily production plan on the Nanded shop floor. Discipline, "
     "attendance and productivity of the floor team. Machine-level first-pass "
     "quality and safe, clean working conditions. Timely escalation of machine, "
     "material and manpower issues.",
     "Process or role design; decisions outside his supervisory scope."),
    ("R08", "Associate - Manufacturing (IC)", "Associate", "Operations",
     "Customer relationship and QC follow-through on manufacturing orders. "
     "Co-ownership of in-house QC discipline. Smooth administration of the Pune "
     "office. Timely resolution of customer quality queries and complaints.",
     "Other people's work; process design; outcomes dependent on inputs he does "
     "not control."),
    ("R09", "Associate - Manufacturing Support", "Associate", "Operations",
     "Second-line support across day-to-day manufacturing operations. Accuracy and "
     "timeliness of the manufacturing data management relies on. Integrity of "
     "floor-level records - coil-cutting books, weighing, despatch reconciliation. "
     "Reliability of document filing, bill preparation and sales-order execution.",
     "Other people's work; process design; outcomes dependent on inputs she does "
     "not control."),
    ("R10", "Associate - Trading Support", "Associate", "Operations",
     "Second-line support across day-to-day trading operations. Accuracy and "
     "timeliness of the trading data management relies on. Integrity of trading "
     "booking in Tally across Shivshakti and major mills. Reliability of trading "
     "document filing and the weekly office attendance update.",
     "Other people's work; process design; outcomes dependent on inputs she does "
     "not control."),
    ("R11", "Associate - Accounts (Senior)", "Associate", "Corporate Services",
     "Timeliness and accuracy of the monthly statutory compliance cycle - TDS "
     "working, GSTR-1, GSTR-2B matching, GSTR-3B, CA coordination. Reliability of "
     "day-to-day accounting control. Accurate daily/weekly drive-sheet position "
     "for SAIL and JSW. Smooth administration of the Mumbai office.",
     "Other people's work; process design; decisions outside her task scope."),
    ("R12", "Associate - Accounts (Junior)", "Associate", "Corporate Services",
     "Accuracy and completeness of day-to-day transactional accounting - Kapson "
     "entries, inter-bank updates, cheque deposits, creditor payment processing. "
     "Reliability of the Kapson operational accounting set. Integrity of invoice "
     "printing and attachment discipline. Monthly hygiene - suspense clearance, "
     "bank-statement printing.",
     "Other people's work; process design; decisions outside his task scope."),
]

# --------------------------------------------------------------------------
# KPI library — Scaling Plan "Employee KPIs"
# --------------------------------------------------------------------------
# kpi_id, applies_to, name, direction, unit, measurement_method, data_source,
# default_weight, outcome_type, accountability_layer

_H, _L, _B = Direction.HIGHER, Direction.LOWER, Direction.BINARY
_OUT, _OTP, _ACT = OutcomeType.OUTCOME, OutcomeType.OUTPUT, OutcomeType.ACTIVITY
_EXE, _SUP, _DES = Layer.EXECUTION, Layer.SUPERVISION, Layer.DESIGN

KPI_LIBRARY: list[tuple] = [
    # -- Director (Sarika)
    ("K001", "Director - Operations & Corporate Services",
     "Direct Reports' Average Score", _H, "score",
     "Average of direct reports' Result pillar scores",
     "Performance Master Monthly Scoring", 20, _OUT, _SUP),
    ("K002", "Director - Operations & Corporate Services",
     "Production Plan Adherence", _H, "%",
     "Planned tonnes vs actual tonnes produced",
     "Production records + Monthly Targets", 20, _OUT, _SUP),
    ("K003", "Director - Operations & Corporate Services",
     "Manufacturing Margin per Tonne", _H, "Rs/tonne",
     "Revenue per tonne minus cost per tonne", "Tally P&L + production data",
     15, _OUT, _SUP),
    ("K004", "Director - Operations & Corporate Services",
     "SOP Completion", _H, "count",
     "SOPs finalised and filed on OneDrive", "SOP Index tracker", 15, _OTP, _DES),
    ("K005", "Director - Operations & Corporate Services",
     "Monthly Ops Report - On Time", _B, "yes/no",
     "Report submitted to MD by the 5th", "Email/file timestamp", 10, _OTP, _EXE),
    ("K006", "Director - Operations & Corporate Services",
     "Delegation Effectiveness", _H, "count",
     "Tasks previously done by the Director now done by department heads",
     "Task log", 10, _OUT, _SUP),
    ("K007", "Director - Operations & Corporate Services",
     "Review Rhythm Integrity", _H, "%",
     "Scheduled reviews held with agenda and follow-up tracked",
     "Meeting log", 10, _ACT, _SUP),

    # -- VP Strategy & BD (Tirth)
    ("K010", "VP - Strategy & Business Development",
     "ERP Implementation Progress", _B, "milestone",
     "Did the month's ERP milestone happen?", "ERP project tracker", 30, _OTP, _DES),
    ("K011", "VP - Strategy & Business Development",
     "Performance System Compliance", _H, "%",
     "Employees scored on time as a share of headcount",
     "Performance Master", 20, _OUT, _DES),
    ("K012", "VP - Strategy & Business Development",
     "Capacity Expansion - Project Tracking", _B, "milestone",
     "Monthly milestone on schedule, no slippage from coordination gaps",
     "Capacity project tracker", 15, _OTP, _DES),
    ("K013", "VP - Strategy & Business Development",
     "TReDS + Insurance Setup", _B, "milestone",
     "Platform registered, first invoice discounted, policy issued",
     "TReDS platform + insurance docs", 15, _OTP, _DES),
    ("K014", "VP - Strategy & Business Development",
     "Industry Learning Milestones", _H, "rating",
     "Self plus MD assessment against the month's learning plan",
     "Learning log + MD feedback", 20, _ACT, _EXE),

    # -- VP Corporate Services (Dhara)
    ("K020", "VP - Corporate Services", "Statutory Compliance - On Time", _H, "%",
     "Filings submitted before the regulatory deadline",
     "Filing acknowledgments", 20, _OUT, _SUP),
    ("K021", "VP - Corporate Services", "Debtor Days (DSO)", _L, "days",
     "Average receivable days across the book", "Tally aging report", 20, _OUT, _SUP),
    ("K022", "VP - Corporate Services", "Overdue Receivables", _L, "Rs Lakhs",
     "Total receivables past agreed payment terms",
     "Tally aging report", 20, _OUT, _SUP),
    ("K023", "VP - Corporate Services", "PDC Collection Tracking", _H, "%",
     "Dispatches with a tracked and followed-up PDC", "PDC register", 10, _ACT, _SUP),
    ("K024", "VP - Corporate Services", "Direct Reports' Average Score", _H, "score",
     "Average of direct reports' Result pillar scores",
     "Performance Master Monthly Scoring", 15, _OUT, _SUP),
    ("K025", "VP - Corporate Services", "Management Skills", _H, "rating",
     "Structured written task handoffs, coaching evidence",
     "Director's assessment", 15, _ACT, _SUP),

    # -- Sr. Associate Manufacturing (Sneha)
    ("K030", "Sr. Associate - Manufacturing", "Production Volume", _H, "tonnes",
     "Total despatched tonnage for the month",
     "Production + dispatch records", 25, _OUT, _SUP),
    ("K031", "Sr. Associate - Manufacturing", "On-Time Delivery", _H, "%",
     "Orders delivered by committed date / total orders",
     "Dispatch log vs order dates", 15, _OUT, _SUP),
    ("K032", "Sr. Associate - Manufacturing", "QC First-Pass Yield", _H, "%",
     "Lots passing QC on first inspection / total lots", "QC records", 15, _OUT, _SUP),
    # Lower-is-better. Under the workbook formula a 10% actual against a 5%
    # target scored the 120% cap; here it correctly scores 50%.
    ("K033", "Sr. Associate - Manufacturing", "Scrap Rate", _L, "%",
     "Scrap weight / total input weight", "Production records", 10, _OUT, _SUP),
    ("K034", "Sr. Associate - Manufacturing", "Existing Customer Reorders", _H, "count",
     "Manufacturing orders from existing customers", "Order book", 10, _OUT, _EXE),
    ("K035", "Sr. Associate - Manufacturing", "Direct Reports' Average Score", _H, "score",
     "Average of direct reports' Result pillar scores",
     "Performance Master Monthly Scoring", 15, _OUT, _SUP),
    ("K036", "Sr. Associate - Manufacturing", "Stock Accuracy", _H, "%",
     "Physical stock count vs system records",
     "Stock verification report", 10, _OUT, _SUP),

    # -- Sr. Associate Trading (Pranay)
    ("K040", "Sr. Associate - Trading", "Trading Volume", _H, "tonnes",
     "Total trading tonnes despatched", "Sales register", 20, _OUT, _EXE),
    ("K041", "Sr. Associate - Trading", "Trading Revenue", _H, "Rs Cr",
     "Total trading revenue for the month", "Tally sales report", 15, _OUT, _EXE),
    ("K042", "Sr. Associate - Trading", "Avg Trading Margin per Tonne", _H, "Rs/tonne",
     "(Trading revenue - trading cost) / tonnes", "Tally P&L", 20, _OUT, _EXE),
    ("K043", "Sr. Associate - Trading", "PDC Collected Before Dispatch", _H, "%",
     "Dispatches with a valid dated PDC / total dispatches",
     "PDC register + dispatch log", 15, _ACT, _EXE),
    ("K044", "Sr. Associate - Trading", "Trading Overdue", _L, "Rs Lakhs",
     "Trading receivables past payment terms",
     "Tally aging report (trading)", 10, _OUT, _EXE),
    ("K045", "Sr. Associate - Trading", "Direct Reports' Average Score", _H, "score",
     "Average of direct reports' Result pillar scores",
     "Performance Master Monthly Scoring", 20, _OUT, _SUP),

    # -- Sr. Associate Shop Floor (Vijay)
    ("K050", "Sr. Associate - Shop Floor (Nanded)", "Daily Production Target Hit",
     _H, "tonnes/day", "Total output weight vs the morning plan",
     "Weighing records", 35, _OUT, _EXE),
    ("K051", "Sr. Associate - Shop Floor (Nanded)", "Labour Attendance & Discipline",
     _H, "%", "Workers present / workers expected, tracked daily",
     "Attendance register", 25, _OUT, _SUP),
    ("K052", "Sr. Associate - Shop Floor (Nanded)", "Machine Downtime",
     _L, "hours", "Hours of unplanned machine downtime", "Downtime log", 20, _OUT, _EXE),
    ("K053", "Sr. Associate - Shop Floor (Nanded)", "Safety Incidents",
     _L, "count", "Safety incidents plus housekeeping checks",
     "Incident register + inspection", 20, _OUT, _EXE),

    # -- Associate Manufacturing IC (Pravin)
    ("K060", "Associate - Manufacturing (IC)", "Customer QC Query Response Time",
     _L, "hours", "Time from customer query to response sent",
     "Email/WhatsApp log", 30, _OUT, _EXE),
    ("K061", "Associate - Manufacturing (IC)", "Factory Admin Tasks - On Time",
     _H, "%", "Assigned admin tasks completed by deadline",
     "Manager's task tracker", 25, _OTP, _EXE),
    ("K062", "Associate - Manufacturing (IC)", "Support Tasks - First-Attempt Success",
     _H, "%", "Production support tasks done right first time",
     "Manager's assessment", 25, _OTP, _EXE),
    ("K063", "Associate - Manufacturing (IC)", "Pune Office Administration",
     _L, "count", "Admin issues escalated beyond the role",
     "Manager feedback", 20, _OUT, _EXE),

    # -- Associate Manufacturing Support (Jagruti)
    ("K070", "Associate - Manufacturing Support", "Production Data Accuracy",
     _L, "errors", "Errors found in production data during verification",
     "Production records vs verification", 30, _OUT, _EXE),
    ("K071", "Associate - Manufacturing Support", "Dispatch Documentation Completeness",
     _H, "%", "Packing list, challan and weighment slip all present",
     "Dispatch file audit", 25, _OTP, _EXE),
    ("K072", "Associate - Manufacturing Support", "Coil-Cutting Book Mismatches",
     _L, "count", "Book entries vs physical weight, spot-checked weekly",
     "Coil-cutting book + weighing records", 25, _OUT, _EXE),
    ("K073", "Associate - Manufacturing Support", "Sales Order Processing Time",
     _L, "hours", "Time from sales order receipt to documents prepared",
     "Sales order log", 20, _OUT, _EXE),

    # -- Associate Trading Support (Riya)
    ("K080", "Associate - Trading Support", "Booking Accuracy in Tally",
     _L, "errors", "Booking errors found during reconciliation",
     "Tally entries vs source docs", 30, _OUT, _EXE),
    ("K081", "Associate - Trading Support", "Same-Day Booking Completion",
     _H, "%", "Transactions booked by end of day / transactions received",
     "Tally entry log", 25, _OTP, _EXE),
    ("K082", "Associate - Trading Support", "Collection Update Timeliness",
     _H, "%", "Collection data updated in the tracker by 4 PM",
     "Collection tracker timestamp", 25, _ACT, _EXE),
    ("K083", "Associate - Trading Support", "Trading Document Filing",
     _H, "%", "Trading documents filed within the same week",
     "Filing audit", 20, _ACT, _EXE),

    # -- Associate Accounts Senior (Aditi)
    ("K090", "Associate - Accounts (Senior)", "GST Filing - On Time",
     _H, "%", "Filings submitted before the regulatory deadline",
     "GST portal acknowledgments", 25, _OUT, _EXE),
    ("K091", "Associate - Accounts (Senior)", "TDS Working - Rework",
     _L, "count", "TDS returns requiring correction after submission",
     "CA feedback + return records", 20, _OUT, _EXE),
    ("K092", "Associate - Accounts (Senior)", "Creditor Payment On Schedule",
     _H, "%", "Payments made by due date / total payments due",
     "Tally payment report", 20, _OTP, _EXE),
    ("K093", "Associate - Accounts (Senior)", "Drive Sheet Position (SAIL/JSW)",
     _L, "count", "Errors or delays against Tally reconciliation",
     "Drive sheet vs Tally", 15, _OUT, _EXE),
    ("K094", "Associate - Accounts (Senior)", "Mumbai Office Administration",
     _L, "count", "Admin issues escalated rather than resolved",
     "Self-report + manager feedback", 10, _OUT, _EXE),
    ("K095", "Associate - Accounts (Senior)", "Independent Task Completion",
     _H, "%", "Tasks completed without escalating / total assigned",
     "Manager's assessment", 10, _ACT, _EXE),

    # -- Associate Accounts Junior (Akshay)
    ("K100", "Associate - Accounts (Junior)", "Daily Bank Update",
     _H, "%", "Bank entries updated in Tally by 11 AM",
     "Tally entry timestamps", 25, _OTP, _EXE),
    ("K101", "Associate - Accounts (Junior)", "Kapson Purchase/Sales Import",
     _H, "%", "Kapson data imported same day as received",
     "Tally entry log", 20, _OTP, _EXE),
    ("K102", "Associate - Accounts (Junior)", "Invoice & E-Invoice Compliance",
     _H, "%", "Invoices and e-invoice/e-way bills generated same day",
     "Invoice log + e-invoice portal", 20, _OTP, _EXE),
    ("K103", "Associate - Accounts (Junior)", "Cheque Deposit - Same Day",
     _H, "%", "Cheques deposited on the day received",
     "Deposit slips vs receipt log", 15, _OTP, _EXE),
    ("K104", "Associate - Accounts (Junior)", "Suspense Entries Pending",
     _L, "count", "Suspense entries outstanding at month end",
     "Tally suspense report", 20, _OUT, _EXE),
]

# --------------------------------------------------------------------------
# Behaviour & Discipline baseline
# --------------------------------------------------------------------------
# Published as company-default business needs each month, then carried onto
# every card automatically. A manager may add per-person items on top, and may
# delete a default — which is allowed but surfaced in the exception review.

BEHAVIOUR_DEFAULTS: list[tuple[str, str]] = [
    ("Integrity", "We do what we said we would. We speak the truth even when "
                  "it costs us. No two sets of books, two faces, or two standards."),
    ("Ownership", "I own the outcome, not just the task. If something falls "
                  "between two people, I pick it up. I do not wait to be told."),
    ("Customer First", "The customer's deadline is our deadline. The customer's "
                       "quality bar is our minimum bar."),
    ("Quality Without Compromise", "We reject our own work before the customer "
                                   "has to. Right the first time, every time."),
    ("Drive & Discipline", "We show up, measure ourselves, and improve every "
                           "month. Consistency beats intensity."),
    ("Respect & Trust", "We treat every person - employee, vendor, customer, "
                        "shop-floor worker - with dignity."),
]

DISCIPLINE_DEFAULTS: list[tuple[str, str]] = [
    ("Attendance & Punctuality", "On time, with valid reason for any exception."),
    ("EOD Reporting", "Daily status report submitted every working day."),
    ("Process & SOP Adherence", "Documented SOPs followed; deviations raised, "
                                "not improvised."),
    ("Data Compliance", "Records accurate, entered on time, and reconcilable."),
    ("Review Rhythm", "Check-ins, scoring and acknowledgements completed by "
                      "their deadlines."),
]

# Knowledge is deliberately not seeded with defaults: a learning goal is
# personal by nature, and a company-wide default would invite the exact
# copy-paste behaviour the remark rules exist to prevent.
