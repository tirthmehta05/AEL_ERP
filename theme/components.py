import streamlit as st


def render_main_header(text: str) -> None:
    st.markdown(f"<div class='main-header'>{text}</div>", unsafe_allow_html=True)


def begin_card() -> None:
    st.markdown("<div class='card'>", unsafe_allow_html=True)


def end_card() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def render_sidebar_brand(logo_path: str, title: str, subtitle: str | None = None) -> None:
    st.image(logo_path)
    st.markdown("<div class='sidebar-brand'>", unsafe_allow_html=True)
    st.markdown(f"<div class='sidebar-title'>{title}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='sidebar-subtitle'>{subtitle}</div>", unsafe_allow_html=True)
