"""Shared test configuration — adds project root to sys.path and
pre-mocks heavy dependencies so modules can be imported without a running app."""

import sys
import os
from unittest.mock import MagicMock

# Add project root to path so `config`, `pages`, `src` are importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Mock streamlit and other heavy deps before any project module imports them.
# config.py does `import streamlit as st` and calls `st.secrets` at module level.
_mock_st = MagicMock()
_mock_st.secrets.get.return_value = {}
sys.modules.setdefault("streamlit", _mock_st)
sys.modules.setdefault("streamlit_msal", MagicMock())
sys.modules.setdefault("gspread", MagicMock())
sys.modules.setdefault("gspread.exceptions", MagicMock())
sys.modules.setdefault("google.auth", MagicMock())
sys.modules.setdefault("google.oauth2", MagicMock())
sys.modules.setdefault("google.oauth2.service_account", MagicMock())
sys.modules.setdefault("google.auth.transport", MagicMock())
sys.modules.setdefault("google.auth.transport.requests", MagicMock())
sys.modules.setdefault("reportlab", MagicMock())
sys.modules.setdefault("reportlab.lib", MagicMock())
sys.modules.setdefault("reportlab.lib.pagesizes", MagicMock())
sys.modules.setdefault("reportlab.pdfgen", MagicMock())
sys.modules.setdefault("fpdf", MagicMock())
sys.modules.setdefault("qrcode", MagicMock())
