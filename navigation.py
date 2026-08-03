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
            ("🏠 Home", "📋 Process Map", "📝 Data Entry", "✂️ Slitting Plan", "🎯 Bid Optimizer", "👥 Performance", "📄 PDF Generator", "⚙️ Automation Workflows", "📊 Forms"),
            label_visibility="hidden"
        )

        if st.button("🔄 Refresh Page", use_container_width=True):
            page_key = _sanitize_page_name(page)
            active_tab_name = None

            # For pages with tabs, find the active tab.
            if page_key in ['data_entry', 'pdf_generator', 'performance']:
                active_tab_key = f'{page_key}_active_tab'  # e.g., 'data_entry_active_tab'
                active_tab_name = st.session_state.get(active_tab_key)

            # Set a structured object for the cache clearing logic to use.
            st.session_state['cache_to_clear'] = {
                "page": page_key,
                "tab": active_tab_name
            }
            st.rerun()

        st.markdown("---")
        st.info("© 2025 AEL ERP. All rights reserved.")
    return page
