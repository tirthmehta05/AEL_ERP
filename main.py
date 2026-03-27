import streamlit as st
from theme import apply_theme
from navigation import select_page
from pages import home, process_map, data_entry, automation, slitting_plan, forms, pdf_generator
from streamlit_msal import Msal
from config import settings

# --- Development Mode Flag ---
DEV_MODE = settings.app.dev_mode

# --- Page Configuration ---
st.set_page_config(
    page_title="AEL ERP",
    page_icon="assets/logofinal.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Styling ---
apply_theme()

# --- Main App ---
def run_app(user_info: dict):
    st.session_state['user_info'] = user_info
    st.sidebar.write(f"Welcome, {user_info['name']}!")
    page = select_page()

    if page == "🏠 Home":
        home.render()
    elif page == "📋 Process Map":
        process_map.render()
    elif page == "📝 Data Entry":
        data_entry.render()

    elif page == "✂️ Slitting Plan":
        slitting_plan.render()
    elif page == "📄 PDF Generator":
        pdf_generator.render_pdf_generator_page()
    elif page == "⚙️ Automation Workflows":
        automation.render()
    elif page == "📊 Forms":
        forms.page()


# --- App Initialization ---
if DEV_MODE:
    # In development mode, simulate a user and run the app directly
    mock_user = {"name": "Dev User", "username": "devuser"}
    run_app(mock_user)
else:
    # In production, use MSAL authentication
    auth_data = Msal.initialize(
        client_id=st.secrets["CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{st.secrets['TENANT_ID']}",
        scopes=[],
    )

    if not auth_data or not auth_data.get("account"):
        if st.sidebar.button("Sign in"):
            Msal.sign_in()
        st.info("Please sign in to access the application.")
    else:
        st.session_state['auth_data'] = auth_data
        if st.sidebar.button("Sign out"):
            Msal.sign_out()
        run_app(auth_data["account"])
