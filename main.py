import streamlit as st
from theme import apply_theme
from navigation import select_page
from pages import home, data_entry, automation

# --- Page Configuration ---
st.set_page_config(
    page_title="AEL ERP",
    page_icon="/assets/logofinal.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Styling ---
apply_theme()

# --- Main App ---
def run_app():
    page = select_page()

    if page == "Home":
        home.render()
    elif page == "Data Entry":
        data_entry.render()
    elif page == "Automation Workflows":
        automation.render()


# --- App Initialization ---
run_app()
