import streamlit as st
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService
from pages.slitting_plan_components import (
    render_filters,
    render_coil_selection,
    render_slitting_plan_editor_and_summary,
    render_summary_expanders,
)

# --- Data Caching ---
@st.cache_data
def get_cached_available_coils(_service):
    return _service.get_available_coils()

@st.cache_data
def get_cached_material_type_options(_service):
    return _service.get_material_type_options()

@st.cache_data
def get_cached_sales_order_summary(_service, start_date, end_date, material_type):
    return _service.get_sales_order_summary(start_date, end_date, material_type)

def render():
    """Renders the main Slitting Plan page."""
    cache_clear_data = st.session_state.get('cache_to_clear')
    if cache_clear_data and cache_clear_data.get('page') == 'slitting_plan':
        st.session_state.pop('cache_to_clear') # Consume the flag
        try:
            get_cached_available_coils.clear()
            get_cached_material_type_options.clear()
            get_cached_sales_order_summary.clear()
            st.toast("Slitting Plan cache cleared!")
        except NameError:
            pass

    st.markdown("<h1 class='main-header'>Slitting Plan</h1>", unsafe_allow_html=True)

    service = SlittingPlanService()
    available_coils_df = get_cached_available_coils(service)

    if available_coils_df.empty:
        st.warning("No available coils found.")
        return

    filtered_df, slitter = render_filters(available_coils_df)
    selected_coils = render_coil_selection(filtered_df)
    render_slitting_plan_editor_and_summary(service, filtered_df, selected_coils, slitter, get_cached_available_coils)
    render_summary_expanders(service, available_coils_df, get_cached_material_type_options, get_cached_sales_order_summary)