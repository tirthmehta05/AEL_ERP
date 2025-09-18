import streamlit as st
import pandas as pd
import altair as alt
from src.data_entry.service.rm_inward_service import RMInwardService
from src.data_entry.service.rm_used_service import RMUsedService

def render_metric_card(label, value, delta=None):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-card-label">{label}</div>
        <div class="metric-card-value">{value}</div>
        {f'<div class="metric-card-delta">{delta}</div>' if delta else ''}
    </div>
    """, unsafe_allow_html=True)

def render():
    """Render the home page dashboard."""
    inward_service = RMInwardService()
    used_service = RMUsedService()

    inward_records = inward_service.get_existing_records(limit=1000)
    used_records = used_service.get_existing_records(limit=1000)

    st.markdown("<h1 class='main-header'>Sales Overview</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: var(--text-secondary);'>Let's see the current statistic perfomance.</p>", unsafe_allow_html=True)

    # --- Top Level Tabs ---
    overview_tab, perf_tab, activity_tab, product_tab = st.tabs(["Overview", "Performance", "Activity", "Product"])

    with overview_tab:
        # --- Metric Cards ---
        total_inward = len(inward_records)
        total_used = len(used_records)
        unique_coils = pd.DataFrame(inward_records)['Coil Number'].nunique() if inward_records else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            render_metric_card("Overall Revenue", "$25,912", "+1.9% Than last month")
        with col2:
            render_metric_card("Total Insight", "129,521", "+1.2% Than last month")
        with col3:
            render_metric_card("Total Inward Records", f"{total_inward}")

        st.markdown("<br>", unsafe_allow_html=True)

        # --- Sales Summary Chart ---
        st.markdown("<h4>Sales Summary</h4>", unsafe_allow_html=True)
        
        # Sample data for the chart
        chart_data = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2025-08-01", "2025-08-02", "2025-08-03", "2025-08-04", "2025-08-05"]),
                "Sales": [50, 60, 70, 80, 90],
                "Insight": [40, 50, 60, 70, 80],
            }
        )

        chart = alt.Chart(chart_data).mark_area(
            line={'color': '#4A4AFF'},
            color=alt.Gradient(
                gradient='linear',
                stops=[alt.GradientStop(color='white', offset=0), alt.GradientStop(color='#E6E6FF', offset=1)],
                x1=1, x2=1, y1=1, y2=0
            )
        ).encode(
            x='Date:T',
            y='Sales:Q'
        ).properties(
            height=300
        )

        st.altair_chart(chart, use_container_width=True)

    
