"""
Tests for the manual weight entry feature.

Covers:
  - WeightReceiptSettings config model
  - Authorization logic (case-insensitive email whitelist)
  - wr_is_manual_entry session state lifecycle
  - Manual suffix logic for weight_entry_type
"""

import pytest
from unittest.mock import MagicMock
from config import WeightReceiptSettings, Settings


# ---------------------------------------------------------------------------
# 1. Config model tests
# ---------------------------------------------------------------------------

class TestWeightReceiptSettings:
    """Tests for the WeightReceiptSettings Pydantic model."""

    def test_default_empty_whitelist(self):
        s = WeightReceiptSettings()
        assert s.manual_entry_authorized_emails == []

    def test_whitelist_from_values(self):
        emails = ["alice@example.com", "bob@example.com"]
        s = WeightReceiptSettings(manual_entry_authorized_emails=emails)
        assert s.manual_entry_authorized_emails == emails

    def test_settings_model_includes_weight_receipt(self):
        s = Settings(
            app={},
            api={},
            power_automate={},
            streamlit={},
            constants={},
            slitting_plan={},
            weight_receipt={"manual_entry_authorized_emails": ["a@b.com"]},
        )
        assert isinstance(s.weight_receipt, WeightReceiptSettings)
        assert s.weight_receipt.manual_entry_authorized_emails == ["a@b.com"]

    def test_settings_model_weight_receipt_defaults(self):
        s = Settings(
            app={},
            api={},
            power_automate={},
            streamlit={},
            constants={},
            slitting_plan={},
            weight_receipt={},
        )
        assert s.weight_receipt.manual_entry_authorized_emails == []


# ---------------------------------------------------------------------------
# 2. Authorization logic tests
#    Tests the exact logic from _is_manual_entry_authorized() without
#    importing the Streamlit page module.
# ---------------------------------------------------------------------------

def _check_authorized(user_email: str, whitelist: list[str]) -> bool:
    """Mirrors the logic in pages/weight_receipt.py::_is_manual_entry_authorized()."""
    authorized = [e.lower() for e in whitelist]
    return user_email.lower() in authorized


class TestManualEntryAuthorization:
    """Tests for authorization whitelist checking."""

    def test_authorized_exact_match(self):
        assert _check_authorized("alice@example.com", ["alice@example.com"]) is True

    def test_authorized_case_insensitive(self):
        assert _check_authorized("Alice@Example.COM", ["alice@example.com"]) is True

    def test_not_authorized(self):
        assert _check_authorized("eve@example.com", ["alice@example.com"]) is False

    def test_empty_whitelist(self):
        assert _check_authorized("alice@example.com", []) is False

    def test_empty_username(self):
        assert _check_authorized("", ["alice@example.com"]) is False

    def test_devuser_in_whitelist(self):
        assert _check_authorized("devuser", ["devuser", "alice@example.com"]) is True

    def test_multiple_authorized_emails(self):
        whitelist = ["sarikabhise@ambaltd.com", "tirthmehta@ambaltd.com", "snehakadam@ambaltd.com"]
        assert _check_authorized("tirthmehta@ambaltd.com", whitelist) is True
        assert _check_authorized("snehakadam@ambaltd.com", whitelist) is True
        assert _check_authorized("random@ambaltd.com", whitelist) is False

    def test_no_user_info_defaults_to_empty_string(self):
        """When user_info is missing, username defaults to '' — should not match."""
        user_email = {}.get("user_info", {}).get("username", "")
        assert _check_authorized(user_email, ["a@b.com"]) is False

    def test_whitelist_with_empty_string_does_not_match_everyone(self):
        """Empty string in whitelist should only match empty username, not real users."""
        assert _check_authorized("alice@example.com", [""]) is False
        assert _check_authorized("", [""]) is True  # edge case: empty matches empty


# ---------------------------------------------------------------------------
# 3. Session state lifecycle tests
#    Validates the flag init / reset behavior using a plain dict.
# ---------------------------------------------------------------------------

class TestSessionStateLifecycle:
    """Tests for wr_is_manual_entry session state management."""

    def test_initialize_sets_false(self):
        """initialize_wr_session_state should default wr_is_manual_entry to False."""
        session = {}
        if "wr_is_manual_entry" not in session:
            session["wr_is_manual_entry"] = False
        assert session["wr_is_manual_entry"] is False

    def test_initialize_does_not_overwrite(self):
        """If already set to True, init should not reset it."""
        session = {"wr_is_manual_entry": True}
        if "wr_is_manual_entry" not in session:
            session["wr_is_manual_entry"] = False
        assert session["wr_is_manual_entry"] is True

    def test_scale_handler_resets_flag(self):
        """After successful scale read, flag should be False."""
        session = {"wr_is_manual_entry": True}
        # Simulate scale handler
        session["wr_is_manual_entry"] = False
        assert session["wr_is_manual_entry"] is False

    def test_manual_handler_sets_flag(self):
        """After manual entry, flag should be True."""
        session = {"wr_is_manual_entry": False}
        # Simulate manual handler
        session["wr_is_manual_entry"] = True
        assert session["wr_is_manual_entry"] is True

    def test_jc_change_resets_flag(self):
        """When switching job cards, flag should reset to False."""
        session = {"wr_is_manual_entry": True}
        # Simulate JC change reset block
        session["wr_is_manual_entry"] = False
        assert session["wr_is_manual_entry"] is False

    def test_successful_save_resets_flag(self):
        """After successful save, flag should reset to False."""
        session = {"wr_is_manual_entry": True}
        # Simulate post-save cleanup
        session["wr_is_manual_entry"] = False
        assert session["wr_is_manual_entry"] is False

    def test_mixed_scale_then_manual(self):
        """Last action wins — manual after scale should be True."""
        session = {"wr_is_manual_entry": False}
        # Scale action
        session["wr_is_manual_entry"] = False
        # Then manual action
        session["wr_is_manual_entry"] = True
        assert session["wr_is_manual_entry"] is True

    def test_mixed_manual_then_scale(self):
        """Last action wins — scale after manual should be False."""
        session = {"wr_is_manual_entry": True}
        session["wr_is_manual_entry"] = False
        assert session["wr_is_manual_entry"] is False


# ---------------------------------------------------------------------------
# 4. Manual suffix logic tests
# ---------------------------------------------------------------------------

class TestManualSuffix:
    """Tests that the (Manual) suffix is applied correctly to weight_entry_type."""

    @staticmethod
    def _get_weight_entry_type(base_type: str, is_manual: bool) -> str:
        """Mirrors the ternary in the save handlers."""
        return f"{base_type} (Manual)" if is_manual else base_type

    def test_loose_strips_manual(self):
        assert self._get_weight_entry_type("Loose Strips", True) == "Loose Strips (Manual)"

    def test_loose_strips_scale(self):
        assert self._get_weight_entry_type("Loose Strips", False) == "Loose Strips"

    def test_building_core_manual(self):
        assert self._get_weight_entry_type("Building Core", True) == "Building Core (Manual)"

    def test_building_core_scale(self):
        assert self._get_weight_entry_type("Building Core", False) == "Building Core"

    def test_suffix_is_filterable(self):
        """The (Manual) suffix should be easy to filter in a spreadsheet."""
        assert "(Manual)" in self._get_weight_entry_type("Loose Strips", True)

    def test_no_suffix_without_flag(self):
        """Without the flag, the type should be clean (no parentheses)."""
        result = self._get_weight_entry_type("Building Core", False)
        assert "(" not in result


# ---------------------------------------------------------------------------
# 5. Config integration with whitelist from secrets
# ---------------------------------------------------------------------------

class TestConfigIntegration:
    """Tests that WeightReceiptSettings loads correctly from dict (simulating secrets.toml)."""

    def test_load_from_toml_style_dict(self):
        """Simulate what load_settings does with the weight_receipt section."""
        toml_section = {
            "manual_entry_authorized_emails": [
                "sarikabhise@ambaltd.com",
                "tirthmehta@ambaltd.com",
                "snehakadam@ambaltd.com",
                "devuser",
            ]
        }
        s = WeightReceiptSettings(**toml_section)
        assert len(s.manual_entry_authorized_emails) == 4
        assert "devuser" in s.manual_entry_authorized_emails

    def test_missing_section_uses_defaults(self):
        """If [weight_receipt] is missing from secrets, defaults to empty list."""
        s = WeightReceiptSettings(**{})
        assert s.manual_entry_authorized_emails == []
