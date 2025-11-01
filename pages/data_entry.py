import streamlit as st

from theme.components import render_main_header

from pages.raw_material_inward_issue import render_raw_material_inward_issue_form
from pages.raw_material_used import render_raw_material_used_form
from pages.sales_order import render_sales_order_form
from pages.assign_coils import render_assign_coils_form
from pages.weight_receipt import render_weight_receipt_form

def render() -> None:
    """Renders the data entry page"""
    render_main_header("Data Entry")

    # --- Main Form Selection ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Raw Material Inward Issue", "Raw Material Used", "Sales Order", "Assign Coils", "Weight Receipt"])

    with tab1:
        render_raw_material_inward_issue_form()
    with tab2:
        render_raw_material_used_form()
    with tab3:
        render_sales_order_form()
    with tab4:
        render_assign_coils_form()
    with tab5:
        render_weight_receipt_form()
