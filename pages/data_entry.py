import streamlit as st

from theme.components import render_main_header

# Import render functions
from pages.raw_material_inward_issue import render_raw_material_inward_issue_form
from pages.raw_material_used import render_raw_material_used_form
from pages.sales_order import render_sales_order_form
from pages.assign_coils import render_assign_coils_form
from pages.weight_receipt import render_weight_receipt_form

# Import cache-clearing functions
from pages.raw_material_inward_issue import load_dropdowns as rm_inward_dropdowns
from pages.raw_material_used import load_dropdowns as rm_used_dropdowns
from pages.sales_order import load_dropdowns as sales_order_dropdowns
from pages.weight_receipt import load_so_dropdowns as wr_so_dropdowns, get_cached_job_cards as wr_job_cards
# assign_coils has no cache to clear


def render() -> None:
    """Renders the data entry page"""
    render_main_header("Data Entry")

    TABS = {
        "Raw Material Inward Issue": rm_inward_dropdowns,
        "Raw Material Used": rm_used_dropdowns,
        "Sales Order": sales_order_dropdowns,
        "Assign Coils": None,  # No cache function
        "Weight Receipt": [wr_so_dropdowns, wr_job_cards],  # Has multiple caches
    }

    # Check for refresh signal BEFORE rendering the radio button
    if st.session_state.get('clear_cache_for_data_entry'):
        st.session_state['clear_cache_for_data_entry'] = False

        # Get the active tab name from session state
        active_tab_name = st.session_state.get('data_entry_active_tab', list(TABS.keys())[0])

        cache_to_clear = TABS.get(active_tab_name)

        if cache_to_clear:
            if isinstance(cache_to_clear, list):
                for cache_func in cache_to_clear:
                    cache_func.clear()
            else:
                cache_to_clear.clear()
            st.toast(f"Cache for '{active_tab_name}' cleared!")

    # --- Main Form Selection ---
    # tab1, tab2, tab3, tab4, tab5 = st.tabs(["Raw Material Inward Issue", "Raw Material Used", "Sales Order", "Assign Coils", "Weight Receipt"])

    # with tab1:
    #     render_raw_material_inward_issue_form()
    # with tab2:
    #     render_raw_material_used_form()
    # with tab3:
    #     render_sales_order_form()
    # with tab4:
    #     render_assign_coils_form()
    # with tab5:
    #     render_weight_receipt_form()
    
    active_tab = st.radio(
        "Select Form:",
        list(TABS.keys()),
        horizontal=True,
        key="data_entry_active_tab",
        label_visibility="collapsed"
    )

    if active_tab == "Raw Material Inward Issue":
        render_raw_material_inward_issue_form()
    elif active_tab == "Raw Material Used":
        render_raw_material_used_form()
    elif active_tab == "Sales Order":
        render_sales_order_form()
    elif active_tab == "Assign Coils":
        render_assign_coils_form()
    elif active_tab == "Weight Receipt":
        render_weight_receipt_form()
