import streamlit as st
from src.services import create_services, AppServices

@st.cache_resource
def get_services() -> AppServices:
    """
    Cached factory function to create and reuse application services
    across Streamlit reruns. This keeps the backend `create_services`
    free of Streamlit dependencies.
    """
    return create_services()
