"""
Process Map page — visualizes Business Area > Process > Stage > Step hierarchy
with linked SOPs and decision gate rendering.

V2 fixes:
- Master Data removed (not a process)
- SOPs clickable via OneDrive link (editable by admin); file name shown as fallback
- All processes for a business area shown as expanders (no dropdown)
- Tab reset fixed: st.radio with session state key instead of st.tabs
- Admin Editor tab (restricted to authorized users) with st.data_editor + CSV save
- Graphviz flowchart for visual process visualization
"""

import streamlit as st
import pandas as pd
import altair as alt
from src.process_map.service import ProcessMapService
from src.shared.integrations.google_drive_service import GoogleDriveService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADMIN_USERS = {"sarikabhise@ambaltd.com", "tirthmehta@ambaltd.com", "devuser"}

STEP_TYPE_ICONS = {
    "Action": "▶",
    "Decision Gate": "◆",
    "IF PASS": "✓",
    "IF FAIL": "✗",
}

STEP_TYPE_COLORS = {
    "Action": ("#DBEAFE", "#3B82F6"),        # blue
    "Decision Gate": ("#FEF3C7", "#F59E0B"), # amber
    "IF PASS": ("#D1FAE5", "#10B981"),       # green
    "IF FAIL": ("#FEE2E2", "#EF4444"),       # red
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_admin() -> bool:
    user = st.session_state.get("user_info", {})
    return user.get("username", "") in ADMIN_USERS


def _get_service() -> ProcessMapService:
    spreadsheet_id = st.secrets.get("PROCESS_MAP_SHEET_ID", None)
    google_service = GoogleDriveService() if spreadsheet_id else None
    return ProcessMapService(google_service, spreadsheet_id)


@st.cache_data(ttl=300)
def _load_process_map(_service: ProcessMapService) -> pd.DataFrame:
    return _service.get_process_map()


@st.cache_data(ttl=300)
def _load_sop_index(_service: ProcessMapService) -> pd.DataFrame:
    return _service.get_sop_index()


@st.cache_data(ttl=300)
def _load_business_areas(_service: ProcessMapService) -> pd.DataFrame:
    return _service.get_business_areas()


def _build_sop_lookup(sop_idx: pd.DataFrame) -> dict:
    """Return dict mapping sop_title.upper() -> row for fast lookups.

    Also registers each title without the '_ael_sop' file-name artifact so that
    process_map.csv references like 'Job Card Creation Process' match sop_index
    entries like 'Job Card Creation Process_ael_sop'.
    """
    lookup = {}
    for _, row in sop_idx.iterrows():
        title = str(row.get("sop_title", "")).strip().upper()
        if not title:
            continue
        lookup[title] = row
        # Strip _ael_sop suffix and register the clean version too (don't
        # overwrite if a cleaner entry already occupies that key)
        clean = title.replace("_AEL_SOP", "").strip()
        if clean != title and clean not in lookup:
            lookup[clean] = row
    return lookup


def _metric_card(label: str, value: str, subtitle: str = ""):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-card-label">{label}</div>
        <div class="metric-card-value">{value}</div>
        {f'<div class="metric-card-delta">{subtitle}</div>' if subtitle else ''}
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Graphviz flowchart builder
# ---------------------------------------------------------------------------

def _sanitize_id(text: str) -> str:
    """Make a safe DOT node ID from arbitrary text."""
    return "".join(c if c.isalnum() else "_" for c in text)


def _build_process_graph(proc_df: pd.DataFrame) -> str:
    """
    Build a Graphviz DOT string for one process.

    Layout:
    - Stages (sequential) as blue rectangular nodes
    - Stages with multiple paths → amber diamond branching node + path child nodes
    - Edges connect stages in stage_order sequence
    """
    lines = [
        "digraph {",
        '  rankdir=TB;',
        '  splines=ortho;',
        '  node [fontname="Arial" fontsize=10 margin="0.15,0.1"];',
        '  edge [color="#94A3B8" arrowsize=0.7];',
        '  graph [bgcolor="#F8FAFC" pad="0.4" nodesep=0.5 ranksep=0.6];',
    ]

    stages = (
        proc_df.drop_duplicates("stage")
        .sort_values("stage_order")[["stage", "stage_order"]]
        .values.tolist()
    )

    # Track which nodes exit each stage (for connecting to the next)
    prev_exit_nodes: list[str] = []

    for i, (stage_name, _stage_order) in enumerate(stages):
        stage_df = proc_df[proc_df["stage"] == stage_name]
        paths = [p for p in stage_df["path"].unique() if str(p).strip()]
        stage_id = f"s{i}_{_sanitize_id(stage_name)}"

        if not paths:
            # Simple sequential stage
            step_count = len(stage_df)
            lines.append(
                f'  {stage_id} [label="{stage_name}\\n({step_count} steps)" '
                f'shape=box style="rounded,filled" fillcolor="#DBEAFE" color="#3B82F6" fontcolor="#1E3A5F"];'
            )
            for prev in prev_exit_nodes:
                lines.append(f"  {prev} -> {stage_id};")
            prev_exit_nodes = [stage_id]

        else:
            # Decision stage with branches
            dec_id = f"dec{i}_{_sanitize_id(stage_name)}"
            lines.append(
                f'  {dec_id} [label="{stage_name}" '
                f'shape=diamond style=filled fillcolor="#FEF3C7" color="#F59E0B" fontcolor="#78350F"];'
            )
            for prev in prev_exit_nodes:
                lines.append(f"  {prev} -> {dec_id};")

            path_exit_nodes: list[str] = []
            for j, path in enumerate(paths):
                path_df = stage_df[stage_df["path"] == path]
                path_id = f"p{i}_{j}_{_sanitize_id(path)}"
                step_count = len(path_df)
                # Shorten label: take part before "—" or ":"
                short = path.split("—")[0].split(":")[0].strip()
                if len(short) > 28:
                    short = short[:25] + "..."
                lines.append(
                    f'  {path_id} [label="{short}\\n({step_count} steps)" '
                    f'shape=box style="rounded,filled" fillcolor="#EEF2FF" color="#4A4AFF" fontcolor="#1E1B4B"];'
                )
                lines.append(f"  {dec_id} -> {path_id};")
                path_exit_nodes.append(path_id)

            prev_exit_nodes = path_exit_nodes

    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Page CSS
# ---------------------------------------------------------------------------

PAGE_CSS = """
<style>
/* Tab-style radio */
div[data-testid="stHorizontalBlock"] {}
div[role="radiogroup"][aria-label="pm_tab_label"] {}

.process-stage-header {
    background: linear-gradient(135deg, #4A4AFF 0%, #6B6BFF 100%);
    color: white;
    padding: 10px 16px;
    border-radius: 10px;
    font-weight: 600;
    font-size: 1rem;
    margin: 12px 0 8px 0;
}
.step-card {
    background: var(--surface, #fff);
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 6px;
}
.step-card.decision-gate { border-left: 4px solid #F59E0B; }
.step-card.if-pass       { border-left: 4px solid #10B981; }
.step-card.if-fail       { border-left: 4px solid #EF4444; }
.step-title {
    font-weight: 600;
    font-size: 0.92rem;
    color: var(--text-primary, #1A1A2E);
}
.step-meta {
    font-size: 0.79rem;
    color: var(--text-secondary, #94A3B8);
    margin-top: 4px;
}
.step-meta span { margin-right: 12px; }
.sop-badge {
    display: inline-block;
    background: #EEF2FF;
    color: #4A4AFF;
    padding: 2px 9px;
    border-radius: 12px;
    font-size: 0.76rem;
    font-weight: 500;
    text-decoration: none;
}
.sop-badge:hover { background: #C7D2FE; }
.sop-missing-badge {
    display: inline-block;
    background: #FEF2F2;
    color: #DC2626;
    padding: 2px 9px;
    border-radius: 12px;
    font-size: 0.76rem;
    font-weight: 500;
}
.path-label {
    font-size: 0.84rem;
    font-weight: 600;
    color: #4A4AFF;
    padding: 6px 0 4px 0;
    border-bottom: 1px dashed #CBD5E1;
    margin-bottom: 6px;
}
.legend-box {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.82rem;
    line-height: 1.8;
}
</style>
"""


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------

def _render_overview(pm: pd.DataFrame, sop_idx: pd.DataFrame, biz: pd.DataFrame):
    """Overview tab — metrics and SOP coverage chart."""
    total_steps = len(pm)
    total_processes = pm["process"].nunique() if not pm.empty else 0
    steps_with_sop = int((pm["sop_title"].astype(str).str.strip() != "").sum()) if not pm.empty else 0
    sop_gap = total_steps - steps_with_sop
    total_sops = len(sop_idx)
    coverage_pct = round(steps_with_sop / total_steps * 100) if total_steps else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _metric_card("Processes", str(total_processes))
    with c2:
        _metric_card("Total Steps", str(total_steps))
    with c3:
        _metric_card("SOPs Created", str(total_sops), f"{steps_with_sop} steps linked")
    with c4:
        _metric_card("SOP Gaps", str(sop_gap), f"{coverage_pct}% coverage")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### SOP Coverage by Business Area")

    if pm.empty:
        st.info("No process data loaded.")
        return

    area_stats = (
        pm.groupby("business_area")
        .apply(lambda g: pd.Series({
            "total": len(g),
            "with_sop": int((g["sop_title"].astype(str).str.strip() != "").sum()),
        }))
        .reset_index()
    )
    area_stats["pct"] = (area_stats["with_sop"] / area_stats["total"] * 100).round(1)

    chart = alt.Chart(area_stats).mark_bar(cornerRadiusEnd=6, color="#4A4AFF").encode(
        x=alt.X("pct:Q", title="SOP Coverage %", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("business_area:N", title="", sort="-x"),
        tooltip=["business_area", "with_sop", "total", "pct"],
    ).properties(height=max(180, len(area_stats) * 40))
    st.altair_chart(chart, use_container_width=True)

    st.markdown("#### Steps Without SOPs")
    missing = pm[pm["sop_title"].astype(str).str.strip() == ""][
        ["business_area", "process", "stage", "step_name", "responsible"]
    ].reset_index(drop=True)
    if missing.empty:
        st.success("All steps have linked SOPs!")
    else:
        st.dataframe(missing, use_container_width=True, hide_index=True, height=300)


def _render_step_card(row: pd.Series, sop_lookup: dict):
    """Render one step as a styled HTML card with clickable SOP badge."""
    step_type = str(row.get("step_type", "Action"))
    icon = STEP_TYPE_ICONS.get(step_type, "▶")
    css_class = "step-card"
    if step_type == "Decision Gate":
        css_class += " decision-gate"
    elif step_type == "IF PASS":
        css_class += " if-pass"
    elif step_type == "IF FAIL":
        css_class += " if-fail"

    step_name  = row.get("step_name", "")
    responsible = row.get("responsible", "")
    docs       = row.get("key_documents", "")
    notes      = row.get("notes", "")
    tools      = row.get("tools_used", "")
    sop_title  = str(row.get("sop_title", "")).strip()
    sop_link   = str(row.get("sop_link", "")).strip()

    # SOP badge — prefer step-level link, then sop_index onedrive_link, then file name fallback
    if sop_title:
        link = sop_link
        if not link:
            sop_info = sop_lookup.get(sop_title.upper())
            if sop_info is not None:
                link = str(sop_info.get("onedrive_link", "")).strip()

        if link:
            sop_html = f'<a href="{link}" target="_blank" class="sop-badge">📋 {sop_title}</a>'
        else:
            # Show file name so user knows where to find it
            sop_info = sop_lookup.get(sop_title.upper())
            if sop_info is not None:
                file_name = str(sop_info.get("file_name", "")).strip()
                owner = str(sop_info.get("owner_name", "")).strip()
                detail = f" — {file_name}" if file_name else ""
                by = f" by {owner}" if owner else ""
                sop_html = f'<span class="sop-badge" title="File: {file_name}{by}">📋 {sop_title}{detail}</span>'
            else:
                sop_html = f'<span class="sop-badge">📋 {sop_title}</span>'
    else:
        sop_html = '<span class="sop-missing-badge">⚠ No SOP</span>'

    meta_parts = []
    if responsible:
        meta_parts.append(f"<span>👤 {responsible}</span>")
    if docs:
        meta_parts.append(f"<span>📄 {docs}</span>")
    if tools:
        meta_parts.append(f"<span>🛠 {tools}</span>")
    meta_html = "".join(meta_parts)
    notes_html = (
        f'<div class="step-meta" style="margin-top:2px;font-style:italic;">{notes}</div>'
        if notes else ""
    )

    st.markdown(f"""
    <div class="{css_class}">
        <div class="step-title">{icon} {step_name}</div>
        <div class="step-meta">{meta_html} {sop_html}</div>
        {notes_html}
    </div>
    """, unsafe_allow_html=True)


def _render_process_flow(pm: pd.DataFrame, sop_idx: pd.DataFrame, selected_area: str):
    """Process Flow tab — all processes for the selected area as expanders with graphviz + cards."""
    if pm.empty:
        st.info("No process data loaded.")
        return

    area_df = pm[pm["business_area"] == selected_area] if selected_area != "All" else pm
    if area_df.empty:
        st.info("No processes found for this business area.")
        return

    sop_lookup = _build_sop_lookup(sop_idx)
    processes = sorted(area_df["process"].unique())

    for process in processes:
        proc_df = area_df[area_df["process"] == process]

        with st.expander(f"📋 {process}", expanded=True):
            # --- Graphviz flowchart ---
            st.markdown("**Flow Overview**")
            col_graph, col_legend = st.columns([3, 1])
            with col_graph:
                try:
                    dot_string = _build_process_graph(proc_df)
                    st.graphviz_chart(dot_string, use_container_width=True)
                except Exception:
                    st.caption("(Graph unavailable — Graphviz not installed)")
            with col_legend:
                st.markdown("""
                <div class="legend-box">
                <b>Legend</b><br>
                🔵 Sequential stage<br>
                🟡 Branching decision<br>
                🟣 Path / scenario<br><br>
                <b>Step cards:</b><br>
                ◆ Decision gate<br>
                ✓ If Pass path<br>
                ✗ If Fail path
                </div>
                """, unsafe_allow_html=True)

            st.divider()

            # --- Detailed step cards ---
            stages = (
                proc_df.drop_duplicates("stage")
                .sort_values("stage_order")["stage"]
                .tolist()
            )
            for stage_name in stages:
                stage_df = proc_df[proc_df["stage"] == stage_name].sort_values(
                    ["path", "step_order"]
                )
                st.markdown(
                    f'<div class="process-stage-header">{stage_name}</div>',
                    unsafe_allow_html=True,
                )
                for path in stage_df["path"].unique():
                    path_df = stage_df[stage_df["path"] == path]
                    if str(path).strip():
                        st.markdown(
                            f'<div class="path-label">↳ {path}</div>',
                            unsafe_allow_html=True,
                        )
                    for _, step_row in path_df.iterrows():
                        _render_step_card(step_row, sop_lookup)

                st.markdown("<br>", unsafe_allow_html=True)


def _render_sop_directory(sop_idx: pd.DataFrame, pm: pd.DataFrame):
    """SOP Directory — searchable list with clickable OneDrive links and file details."""
    st.markdown("#### All Standard Operating Procedures")

    if sop_idx.empty:
        st.info("No SOPs loaded. Check the SOP Index or local CSV.")
        return

    search = st.text_input(
        "🔍 Search SOPs",
        placeholder="Type to filter by title, owner, department...",
        key="sop_search",
    )

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        depts = ["All"] + sorted(sop_idx["department"].dropna().unique().tolist())
        sel_dept = st.selectbox("Department", depts, key="sop_dept")
    with fc2:
        owners = ["All"] + sorted(sop_idx["owner_name"].dropna().unique().tolist())
        sel_owner = st.selectbox("Owner", owners, key="sop_owner")
    with fc3:
        statuses = ["All"] + sorted(sop_idx["status"].dropna().unique().tolist())
        sel_status = st.selectbox("Status", statuses, key="sop_status")

    filtered = sop_idx.copy()
    if search:
        mask = filtered.apply(
            lambda r: search.lower() in " ".join(r.astype(str).values).lower(), axis=1
        )
        filtered = filtered[mask]
    if sel_dept != "All":
        filtered = filtered[filtered["department"] == sel_dept]
    if sel_owner != "All":
        filtered = filtered[filtered["owner_name"] == sel_owner]
    if sel_status != "All":
        filtered = filtered[filtered["status"] == sel_status]

    st.markdown(f"**{len(filtered)}** SOPs found")

    display_cols = [
        "sop_title", "department", "owner_name", "status",
        "file_name", "onedrive_link", "mapped_to_step",
    ]
    available_cols = [c for c in display_cols if c in filtered.columns]

    st.dataframe(
        filtered[available_cols].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "sop_title": st.column_config.TextColumn("SOP Title", width="large"),
            "department": st.column_config.TextColumn("Department"),
            "owner_name": st.column_config.TextColumn("Owner"),
            "status": st.column_config.TextColumn("Status"),
            "file_name": st.column_config.TextColumn("File Name", width="medium"),
            "onedrive_link": st.column_config.LinkColumn(
                "Open File",
                display_text="Open ↗",
                help="Click to open in OneDrive (link must be set by admin)",
            ),
            "mapped_to_step": st.column_config.TextColumn("Mapped To", width="large"),
        },
    )

    st.caption(
        "To add OneDrive links for SOPs, use the **Admin Editor** tab (restricted access). "
        "Once a link is set, the 'Open ↗' button becomes clickable."
    )

    unmapped = sop_idx[sop_idx["mapped_to_step"].astype(str).str.strip() == ""]
    if not unmapped.empty:
        with st.expander(f"⚠ {len(unmapped)} SOPs not mapped to any process step"):
            st.dataframe(
                unmapped[["sop_title", "owner_name", "department", "file_name"]].reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
            )


def _render_admin_editor(
    service: ProcessMapService, pm: pd.DataFrame, sop_idx: pd.DataFrame
):
    """Admin Editor — restricted to ADMIN_USERS. Edit CSVs via st.data_editor."""
    st.markdown("#### Admin Editor")
    st.info(
        "Changes are written directly to the local CSV files and take effect on next page load. "
        "Use this to update OneDrive links, fix process steps, or add/remove SOPs."
    )

    edit_choice = st.radio(
        "What to edit",
        ["Process Steps", "SOP Index"],
        horizontal=True,
        key="admin_edit_choice",
    )

    if edit_choice == "Process Steps":
        st.markdown("**Process Steps** — add, edit, or delete rows")
        edited_pm = st.data_editor(
            pm,
            use_container_width=True,
            num_rows="dynamic",
            key="admin_pm_editor",
            column_config={
                "step_type": st.column_config.SelectboxColumn(
                    "Step Type",
                    options=["Action", "Decision Gate", "IF PASS", "IF FAIL"],
                    required=True,
                ),
                "stage_order": st.column_config.NumberColumn("Stage Order", min_value=1),
                "step_order": st.column_config.NumberColumn("Step Order", min_value=1),
                "sop_link": st.column_config.LinkColumn("SOP Link (URL)"),
            },
        )
        if st.button("💾 Save Process Map", type="primary", key="save_pm"):
            service.save_process_map(edited_pm)
            st.cache_data.clear()
            st.success("Saved. Reloading data...")
            st.rerun()

    else:  # SOP Index
        st.markdown("**SOP Index** — add OneDrive links, update status, edit metadata")
        edited_sop = st.data_editor(
            sop_idx,
            use_container_width=True,
            num_rows="dynamic",
            key="admin_sop_editor",
            column_config={
                "status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["Draft", "Formatted", "Approved", "Archived"],
                ),
                "onedrive_link": st.column_config.LinkColumn(
                    "OneDrive Link",
                    help="Paste the OneDrive sharing URL here. This makes the SOP clickable everywhere.",
                ),
            },
        )
        if st.button("💾 Save SOP Index", type="primary", key="save_sop"):
            service.save_sop_index(edited_sop)
            st.cache_data.clear()
            st.success("Saved. Reloading data...")
            st.rerun()


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render():
    """Main entry point for the Process Map page."""
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    st.markdown("<h1 class='main-header'>Business Process Map</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color: var(--text-secondary);'>"
        "Navigate business processes, view steps, and access linked SOPs.</p>",
        unsafe_allow_html=True,
    )

    service = _get_service()
    pm = _load_process_map(service)
    sop_idx = _load_sop_index(service)
    biz = _load_business_areas(service)

    # --- Business Area filter (above tabs so changing it doesn't reset the tab) ---
    col_area, col_spacer = st.columns([2, 4])
    with col_area:
        if not pm.empty:
            area_options = ["All"] + sorted(pm["business_area"].unique())
        else:
            area_options = ["All"]
        selected_area = st.selectbox(
            "Business Area", area_options, key="pm_area",
            help="Filter all tabs by business area"
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Tab navigation via st.radio (session state key persists across reruns) ---
    # Using radio instead of st.tabs so that changing a selectbox inside
    # Process Flow doesn't reset you back to the Overview tab.
    tab_options = ["Overview", "Process Flow", "SOP Directory"]
    if _is_admin():
        tab_options.append("Admin Editor")

    active_tab = st.radio(
        "pm_tab_label",
        tab_options,
        horizontal=True,
        key="pm_tab",
        label_visibility="collapsed",
    )
    st.divider()

    if active_tab == "Overview":
        filtered_pm = pm[pm["business_area"] == selected_area] if selected_area != "All" else pm
        _render_overview(filtered_pm, sop_idx, biz)
    elif active_tab == "Process Flow":
        _render_process_flow(pm, sop_idx, selected_area)
    elif active_tab == "SOP Directory":
        _render_sop_directory(sop_idx, pm)
    elif active_tab == "Admin Editor":
        _render_admin_editor(service, pm, sop_idx)
