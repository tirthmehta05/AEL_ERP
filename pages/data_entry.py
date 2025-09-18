import streamlit as st

from theme.components import render_main_header

from pages.raw_material_inward_issue import render_raw_material_inward_issue_form
from pages.raw_material_used import render_raw_material_used_form

def render() -> None:
    """Renders the data entry page"""
    render_main_header("Data Entry")

    # --- Main Form Selection ---
    tab1, tab2 = st.tabs(["Raw Material Inward Issue", "Raw Material Used"])

    with tab1:
        render_raw_material_inward_issue_form()
    with tab2:
        render_raw_material_used_form()
