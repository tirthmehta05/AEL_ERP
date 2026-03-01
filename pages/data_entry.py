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
    tab_names = list(TABS.keys())

    # Determine the index for the radio button.
    # Default to 0, but respect the existing state if it's available.
    try:
        radio_index = tab_names.index(st.session_state.data_entry_active_tab)
    except (AttributeError, ValueError):
        radio_index = 0 # Default for the very first load

    # --- Cache Clearing and State Restoration ---
    cache_clear_data = st.session_state.get('cache_to_clear')
    if cache_clear_data:
        # Pop the whole dict to consume the flag
        st.session_state.pop('cache_to_clear') 
        
        # Check if it's the dict structure or a simple string for backward compatibility
        if isinstance(cache_clear_data, dict):
            tab_to_clear = cache_clear_data.get('tab')
        else:
            tab_to_clear = cache_clear_data
            
        cache_to_clear_func = TABS.get(tab_to_clear)
        if cache_to_clear_func:
            if isinstance(cache_to_clear_func, list):
                for cache_func in cache_to_clear_func:
                    cache_func.clear()
            else:
                cache_to_clear_func.clear()

            if tab_to_clear == "Raw Material Inward Issue":
                st.session_state.pop('coil_number_input', None)

            st.toast(f"Cache for '{tab_to_clear}' cleared!")

        # Override the index ONLY for this refresh run
        if tab_to_clear in tab_names:
            radio_index = tab_names.index(tab_to_clear)

    # --- Main Form Selection ---
    active_tab = st.radio(
        "Select Form:",
        tab_names,
        index=radio_index,  # Use the calculated index
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
