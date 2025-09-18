import streamlit as st
from theme.components import render_sidebar_brand


def select_page() -> str:
    with st.sidebar:
        render_sidebar_brand("assets/logofinal.png", "Amba Enterprises Limited")
        st.markdown("---")
        page = st.radio(
            "Navigation",
            ("🏠 Home", "📝 Data Entry", "💼 Job Work", "✂️ Slitting Plan", "⚙️ Automation Workflows"),
            label_visibility="hidden"
        )
        st.markdown("---")
        st.info("© 2025 AEL ERP. All rights reserved.")
    return page
