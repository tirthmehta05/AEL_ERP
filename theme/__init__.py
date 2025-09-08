from pathlib import Path
import streamlit as st


def apply_theme() -> None:
    """Inject the global CSS theme into the Streamlit app."""
    theme_dir = Path(__file__).parent
    css_file = theme_dir / "styles.css"
    if css_file.exists():
        css_content = css_file.read_text(encoding="utf-8")
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
    else:
        st.warning("Theme styles.css not found. Using default Streamlit styles.")

