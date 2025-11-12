import streamlit as st
from theme.components import render_sidebar_brand

def _sanitize_page_name(page_name: str) -> str:
    """Converts a page name like '📄 PDF Generator' to 'pdf_generator'."""
    try:
        # Split by space, take the second part, replace spaces with underscores, and lowercase.
        return page_name.split(" ", 1)[1].replace(" ", "_").lower()
    except IndexError:
        # Handle cases like "Home" or other formats without an emoji and space.
        return page_name.lower()

def select_page() -> str:
    with st.sidebar:
        render_sidebar_brand("assets/logofinal.png", "Amba Enterprises Limited")
        
        page = st.radio(
            "Navigation",
            ("🏠 Home", "📝 Data Entry", "✂️ Slitting Plan", "📄 PDF Generator", "⚙️ Automation Workflows", "📊 Forms"),
            label_visibility="hidden"
        )

        if st.button("🔄 Refresh Page", use_container_width=True):
            page_key = _sanitize_page_name(page)
            st.session_state[f'clear_cache_for_{page_key}'] = True
            st.rerun()

        st.markdown("---")
        st.info("© 2025 AEL ERP. All rights reserved.")
    return page
