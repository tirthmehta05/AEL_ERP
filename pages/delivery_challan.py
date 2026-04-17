import streamlit as st
import pandas as pd
import time
from datetime import datetime
from pydantic import ValidationError

from src.data_entry.service.delivery_challan_service import DeliveryChallanService
from src.data_entry.models.delivery_challan_models import (
    DeliveryChallanRequest,
    DeliveryChallanItem,
)
from theme.components import render_main_header


@st.cache_resource(ttl=600)
def _get_service():
    return DeliveryChallanService()


@st.cache_data(ttl=300)
def _load_coil_numbers(_svc):
    return _svc.get_coil_numbers()


@st.cache_data(ttl=300)
def _load_parties(_svc):
    return _svc.get_rm_parties()


@st.cache_data(ttl=300)
def _load_consignees(_svc):
    return [c.get("Party Name", "") for c in _svc.get_consignees()]


def _clear_dc_caches():
    _load_coil_numbers.clear()
    _load_parties.clear()
    _load_consignees.clear()


# ──────────────────────────────────────────────────
# Shared helper: create challan + handle missing data
# ──────────────────────────────────────────────────

def _handle_challan_generation(service: DeliveryChallanService, request: DeliveryChallanRequest):
    """
    Validates for missing fields. If any are missing, offers an Excel download.
    Otherwise creates the challan, saves to Sheets, and provides the PDF download.
    """
    missing = service.check_missing_fields(request)

    if missing:
        st.warning(
            f"⚠️ **{len(missing)} missing field(s) detected.** "
            "The PDF cannot be generated until these are filled in."
        )

        missing_df = pd.DataFrame([
            {"Field": m.display_name, "Source": m.source}
            for m in missing
        ])
        st.dataframe(missing_df, use_container_width=True, hide_index=True)

        excel_bytes = service.generate_missing_excel(request, missing)
        st.download_button(
            label="📥 Download Missing Fields Excel",
            data=excel_bytes,
            file_name=f"missing_fields_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        return

    # No missing fields — proceed with challan creation
    with st.spinner("Creating Delivery Challan..."):
        try:
            challan_number = service.create_delivery_challan(request)
            st.success(f"✅ Challan **{challan_number}** created and saved to Google Sheets!")

            pdf_bytes = service.generate_challan_pdf(challan_number)
            st.download_button(
                label="📄 Download Challan PDF",
                data=pdf_bytes,
                file_name=f"DC_{challan_number.replace('/', '_')}.pdf",
                mime="application/pdf",
                type="primary",
            )
        except Exception as e:
            st.error(f"❌ Failed to create challan: {e}")


# ──────────────────────────────────────────────────
# Coil Item Editor (shared between modes)
# ──────────────────────────────────────────────────

def _render_item_editor(items: list, key_prefix: str):
    """Displays a data editor for coil items and returns the edited items list."""
    if not items:
        st.info("No coil items added yet.")
        return items

    df = pd.DataFrame([item.dict() for item in items])

    display_cols = [
        "coil_number", "grade", "width", "thk", "coating",
        "weight_kg", "weight_mt", "nature_of_processing",
        "hsn_code", "rate_per_mt", "value",
    ]
    display_df = df[[c for c in display_cols if c in df.columns]].copy()

    col_config = {
        "coil_number": st.column_config.TextColumn("Coil No", disabled=True),
        "grade": st.column_config.TextColumn("Grade", disabled=True),
        "width": st.column_config.NumberColumn("Width", disabled=True),
        "thk": st.column_config.NumberColumn("Thk", disabled=True),
        "coating": st.column_config.TextColumn("Coating", disabled=True),
        "weight_kg": st.column_config.NumberColumn("Wt (kg)", disabled=True, format="%.2f"),
        "weight_mt": st.column_config.NumberColumn("Wt (MT)", disabled=True, format="%.3f"),
        "nature_of_processing": st.column_config.TextColumn("Process"),
        "hsn_code": st.column_config.TextColumn("HSN"),
        "rate_per_mt": st.column_config.NumberColumn("Rate/MT", format="%.2f"),
        "value": st.column_config.NumberColumn("Value", format="%.2f"),
    }

    edited_df = st.data_editor(
        display_df,
        column_config=col_config,
        use_container_width=True,
        hide_index=True,
        key=f"{key_prefix}_items_editor",
    )

    # Apply edits back to item objects
    updated_items = []
    for i, item in enumerate(items):
        item_dict = item.dict()
        if i < len(edited_df):
            row = edited_df.iloc[i]
            item_dict["nature_of_processing"] = row.get("nature_of_processing", item.nature_of_processing)
            item_dict["hsn_code"] = row.get("hsn_code", item.hsn_code)
            item_dict["rate_per_mt"] = float(row.get("rate_per_mt", item.rate_per_mt))
            item_dict["value"] = float(row.get("value", item.value))
        updated_items.append(DeliveryChallanItem(**item_dict))

    return updated_items


def _render_common_fields(key_prefix: str, consignee_names: list, default_party: str = ""):
    """Render the common challan fields (type, party, vehicle, etc.)."""
    col1, col2 = st.columns(2)

    with col1:
        challan_type = st.selectbox(
            "Challan Type",
            options=["job_work", "return"],
            format_func=lambda x: "Job Work" if x == "job_work" else "Return",
            key=f"{key_prefix}_challan_type",
        )

        # Try to find default party index
        party_index = None
        if default_party:
            try:
                party_index = consignee_names.index(default_party)
            except ValueError:
                party_index = None

        party_name = st.selectbox(
            "Party Name (from Consignee Master)",
            options=consignee_names,
            index=party_index,
            placeholder="Select a party",
            key=f"{key_prefix}_party_name",
        )

        challan_date = st.date_input(
            "Challan Date",
            value=datetime.now().date(),
            key=f"{key_prefix}_challan_date",
        )

    with col2:
        vehicle_no = st.text_input("Vehicle No", key=f"{key_prefix}_vehicle_no")
        ewaybill_no = st.text_input("E-Waybill No", key=f"{key_prefix}_ewaybill_no")
        hsn_code = st.text_input("HSN Code", value="7208", key=f"{key_prefix}_hsn_code")

    col3, col4 = st.columns(2)
    with col3:
        rounded_off = st.number_input("Rounded Off", value=0.0, step=0.01, format="%.2f", key=f"{key_prefix}_rounded_off")
    with col4:
        remarks = st.text_input("Remarks", key=f"{key_prefix}_remarks")

    return {
        "challan_type": challan_type,
        "party_name": party_name or "",
        "challan_date": challan_date,
        "vehicle_no": vehicle_no,
        "ewaybill_no": ewaybill_no,
        "hsn_code": hsn_code,
        "rounded_off": rounded_off,
        "remarks": remarks,
    }


# ══════════════════════════════════════════════════
# MODE 1: Manual Entry
# ══════════════════════════════════════════════════

def _render_manual_mode(service: DeliveryChallanService, consignee_names: list):
    """Manual coil-by-coil entry mode (existing functionality)."""
    st.markdown("### 📝 Manual Entry")
    st.info("Add coils manually and generate a Delivery Challan.")

    if "dc_manual_items" not in st.session_state:
        st.session_state.dc_manual_items = []

    # --- Add Coil Form ---
    with st.expander("➕ Add Coil Item", expanded=not st.session_state.dc_manual_items):
        col1, col2 = st.columns(2)
        with col1:
            coil_number = st.text_input("Coil Number", key="dc_manual_coil_number")
            grade = st.text_input("Grade", key="dc_manual_grade")
            width = st.number_input("Width (mm)", min_value=0.0, step=0.1, key="dc_manual_width")
            thk = st.number_input("Thk (mm)", min_value=0.0, step=0.01, key="dc_manual_thk")
        with col2:
            coating = st.text_input("Coating", key="dc_manual_coating")
            weight_kg = st.number_input("Weight (kg)", min_value=0.0, step=0.01, key="dc_manual_weight_kg")
            rate_per_mt = st.number_input("Rate per MT", min_value=0.0, step=0.01, key="dc_manual_rate")
            nature_of_processing = st.selectbox("Process", options=["Slitting", "Other"], key="dc_manual_process")

        hsn_code_item = st.text_input("HSN Code", value="7208", key="dc_manual_hsn_item")

        if st.button("Add Coil", key="dc_manual_add_btn"):
            if not coil_number.strip():
                st.warning("Please enter a Coil Number.")
            elif weight_kg <= 0:
                st.warning("Weight must be greater than 0.")
            else:
                weight_mt = weight_kg / 1000
                value = weight_mt * rate_per_mt
                item = DeliveryChallanItem(
                    coil_number=coil_number,
                    description=grade,
                    grade=grade,
                    width=width,
                    thk=thk,
                    coating=coating,
                    weight_kg=weight_kg,
                    weight_mt=weight_mt,
                    nature_of_processing=nature_of_processing,
                    hsn_code=hsn_code_item,
                    rate_per_mt=rate_per_mt,
                    value=value,
                )
                st.session_state.dc_manual_items.append(item)
                st.success(f"Coil **{coil_number}** added!")
                st.rerun()

    # --- Display & Edit Items ---
    if st.session_state.dc_manual_items:
        st.markdown("#### Coils in Challan")
        st.session_state.dc_manual_items = _render_item_editor(
            st.session_state.dc_manual_items, "dc_manual"
        )

        if st.button("🗑️ Clear All Coils", key="dc_manual_clear"):
            st.session_state.dc_manual_items = []
            st.rerun()

        st.markdown("---")
        st.markdown("#### Challan Details")
        fields = _render_common_fields("dc_manual", consignee_names)

        if st.button("🚀 Generate Delivery Challan", type="primary", key="dc_manual_generate"):
            if not fields["party_name"]:
                st.warning("Please select a Party Name.")
                return

            request = DeliveryChallanRequest(
                challan_type=fields["challan_type"],
                challan_date=fields["challan_date"],
                party_name=fields["party_name"],
                vehicle_no=fields["vehicle_no"] or None,
                ewaybill_no=fields["ewaybill_no"] or None,
                hsn_code=fields["hsn_code"],
                rounded_off=fields["rounded_off"],
                remarks=fields["remarks"] or None,
                items=st.session_state.dc_manual_items,
            )
            _handle_challan_generation(service, request)


# ══════════════════════════════════════════════════
# MODE 2: From Coil Number
# ══════════════════════════════════════════════════

def _render_coil_mode(service: DeliveryChallanService, consignee_names: list, coil_numbers: list):
    """Generate challan by selecting coil number(s) from RM Inward."""
    st.markdown("### 🔢 From Coil Number")
    st.info("Select coil(s) from RM Inward to auto-populate the challan.")

    selected_coils = st.multiselect(
        "Select Coil Number(s)",
        options=coil_numbers,
        key="dc_coil_selected",
    )

    if not selected_coils:
        return

    # Build request from coils
    try:
        request = service.build_request_from_coils(selected_coils)
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return

    st.markdown("#### Auto-populated Coil Items")
    st.caption("Edit Rate per MT and Value below. Other fields are from RM Inward.")

    if "dc_coil_items" not in st.session_state or st.session_state.get("dc_coil_last_selection") != selected_coils:
        st.session_state.dc_coil_items = list(request.items)
        st.session_state.dc_coil_last_selection = list(selected_coils)

    st.session_state.dc_coil_items = _render_item_editor(
        st.session_state.dc_coil_items, "dc_coil"
    )

    st.markdown("---")
    st.markdown("#### Challan Details")
    fields = _render_common_fields("dc_coil", consignee_names, default_party=request.party_name)

    if st.button("🚀 Generate Delivery Challan", type="primary", key="dc_coil_generate"):
        if not fields["party_name"]:
            st.warning("Please select a Party Name.")
            return

        final_request = DeliveryChallanRequest(
            challan_type=fields["challan_type"],
            challan_date=fields["challan_date"],
            party_name=fields["party_name"],
            vehicle_no=fields["vehicle_no"] or None,
            ewaybill_no=fields["ewaybill_no"] or None,
            hsn_code=fields["hsn_code"],
            rounded_off=fields["rounded_off"],
            remarks=fields["remarks"] or None,
            items=st.session_state.dc_coil_items,
        )
        _handle_challan_generation(service, final_request)


# ══════════════════════════════════════════════════
# MODE 3: From Party
# ══════════════════════════════════════════════════

def _render_party_mode(service: DeliveryChallanService, consignee_names: list, parties: list):
    """Generate challan by selecting a party first, then its coils."""
    st.markdown("### 🏢 From Party")
    st.info("Select a party (supplier), then select coils belonging to that party.")

    selected_party = st.selectbox(
        "Select Party",
        options=parties,
        index=None,
        placeholder="Choose a party...",
        key="dc_party_selected",
    )

    if not selected_party:
        return

    party_coils = service.get_coils_by_party(selected_party)
    if not party_coils:
        st.warning(f"No coils found for party **{selected_party}** in RM Inward.")
        return

    selected_coils = st.multiselect(
        "Select Coil Number(s)",
        options=party_coils,
        key="dc_party_coils_selected",
    )

    if not selected_coils:
        return

    try:
        request = service.build_request_from_coils(selected_coils, party_name=selected_party)
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return

    st.markdown("#### Auto-populated Coil Items")

    if "dc_party_items" not in st.session_state or st.session_state.get("dc_party_last_selection") != selected_coils:
        st.session_state.dc_party_items = list(request.items)
        st.session_state.dc_party_last_selection = list(selected_coils)

    st.session_state.dc_party_items = _render_item_editor(
        st.session_state.dc_party_items, "dc_party"
    )

    st.markdown("---")
    st.markdown("#### Challan Details")
    fields = _render_common_fields("dc_party", consignee_names, default_party=selected_party)

    if st.button("🚀 Generate Delivery Challan", type="primary", key="dc_party_generate"):
        if not fields["party_name"]:
            st.warning("Please select a Party Name.")
            return

        final_request = DeliveryChallanRequest(
            challan_type=fields["challan_type"],
            challan_date=fields["challan_date"],
            party_name=fields["party_name"],
            vehicle_no=fields["vehicle_no"] or None,
            ewaybill_no=fields["ewaybill_no"] or None,
            hsn_code=fields["hsn_code"],
            rounded_off=fields["rounded_off"],
            remarks=fields["remarks"] or None,
            items=st.session_state.dc_party_items,
        )
        _handle_challan_generation(service, final_request)


# ══════════════════════════════════════════════════
# MODE 4: Unused Coils (Year-End)
# ══════════════════════════════════════════════════

def _render_unused_coils_mode(service: DeliveryChallanService, consignee_names: list):
    """Generate challan for coils that have not been used (Year-End feature)."""
    st.markdown("### 📦 Unused Coils (Year-End)")
    st.info("Shows coils from RM Inward that are not found in RM Used. Select coils to generate a Delivery Challan.")

    if st.button("🔍 Fetch Unused Coils", key="dc_unused_fetch"):
        with st.spinner("Cross-referencing RM Inward vs RM Used..."):
            unused_df = service.get_unused_coils()
            st.session_state.dc_unused_df = unused_df

    if "dc_unused_df" not in st.session_state:
        return

    unused_df = st.session_state.dc_unused_df

    if unused_df.empty:
        st.success("🎉 No unused coils found — all coils have been used!")
        return

    st.markdown(f"#### Found **{len(unused_df)}** unused coil(s)")

    # Display columns
    display_cols = [c for c in ["Coil Number", "Grade", "Width", "Thk", "Coil Weight", "Coating", "Coil Supplier"] if c in unused_df.columns]
    st.dataframe(unused_df[display_cols], use_container_width=True, hide_index=True)

    # Select coils
    coil_options = unused_df["Coil Number"].dropna().astype(str).str.strip().tolist()
    selected_coils = st.multiselect(
        "Select Coils for Challan",
        options=coil_options,
        key="dc_unused_selected",
    )

    if not selected_coils:
        return

    try:
        request = service.build_request_from_coils(selected_coils)
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return

    st.markdown("#### Auto-populated Coil Items")

    if "dc_unused_items" not in st.session_state or st.session_state.get("dc_unused_last_selection") != selected_coils:
        st.session_state.dc_unused_items = list(request.items)
        st.session_state.dc_unused_last_selection = list(selected_coils)

    st.session_state.dc_unused_items = _render_item_editor(
        st.session_state.dc_unused_items, "dc_unused"
    )

    st.markdown("---")
    st.markdown("#### Challan Details")
    fields = _render_common_fields("dc_unused", consignee_names, default_party=request.party_name)

    if st.button("🚀 Generate Delivery Challan", type="primary", key="dc_unused_generate"):
        if not fields["party_name"]:
            st.warning("Please select a Party Name.")
            return

        final_request = DeliveryChallanRequest(
            challan_type=fields["challan_type"],
            challan_date=fields["challan_date"],
            party_name=fields["party_name"],
            vehicle_no=fields["vehicle_no"] or None,
            ewaybill_no=fields["ewaybill_no"] or None,
            hsn_code=fields["hsn_code"],
            rounded_off=fields["rounded_off"],
            remarks=fields["remarks"] or "Year-End Unused Coils",
            items=st.session_state.dc_unused_items,
        )
        _handle_challan_generation(service, final_request)


# ══════════════════════════════════════════════════
# Re-upload Missing Fields Excel
# ══════════════════════════════════════════════════

def _render_reupload_section(service: DeliveryChallanService):
    """Allow users to re-upload a filled Missing Fields Excel to generate the PDF."""
    with st.expander("📤 Re-upload Missing Fields Excel", expanded=False):
        st.caption(
            "If you previously downloaded a Missing Fields Excel, fill in the values "
            "and upload it here to generate the PDF."
        )
        uploaded = st.file_uploader(
            "Upload filled Excel",
            type=["xlsx"],
            key="dc_reupload_excel",
        )

        if uploaded:
            try:
                challan_df = pd.read_excel(uploaded, sheet_name="Challan Data")
                items_df = pd.read_excel(uploaded, sheet_name="Coil Items")

                if challan_df.empty or items_df.empty:
                    st.error("The uploaded Excel is missing data in 'Challan Data' or 'Coil Items' sheets.")
                    return

                row = challan_df.iloc[0]

                items = []
                for _, item_row in items_df.iterrows():
                    items.append(DeliveryChallanItem(
                        coil_number=str(item_row.get("Coil Number", "")),
                        description=str(item_row.get("Description", "")),
                        grade=str(item_row.get("Grade", "")),
                        width=float(item_row.get("Width", 0) or 0),
                        thk=float(item_row.get("Thk", 0) or 0),
                        coating=str(item_row.get("Coating", "")),
                        weight_kg=float(item_row.get("Weight (kg)", 0) or 0),
                        weight_mt=float(item_row.get("Weight (MT)", 0) or 0),
                        nature_of_processing=str(item_row.get("Process", "Slitting")),
                        hsn_code=str(item_row.get("HSN Code", "7208")),
                        rate_per_mt=float(item_row.get("Rate per MT", 0) or 0),
                        value=float(item_row.get("Value", 0) or 0),
                    ))

                request = DeliveryChallanRequest(
                    challan_type=str(row.get("Challan Type", "job_work")),
                    challan_date=pd.to_datetime(row.get("Challan Date", datetime.now().date())).date(),
                    party_name=str(row.get("Party Name", "")),
                    vehicle_no=str(row.get("Vehicle No", "")) or None,
                    ewaybill_no=str(row.get("E-Waybill No", "")) or None,
                    hsn_code=str(row.get("HSN Code", "7208")),
                    rounded_off=float(row.get("Rounded Off", 0) or 0),
                    remarks=str(row.get("Remarks", "")) or None,
                    items=items,
                )

                st.success("✅ Excel parsed successfully! Review and generate:")
                _handle_challan_generation(service, request)

            except Exception as e:
                st.error(f"❌ Failed to parse uploaded Excel: {e}")


# ══════════════════════════════════════════════════
# Main Page Render
# ══════════════════════════════════════════════════

def render_delivery_challan_form() -> None:
    """Main render function for the Delivery Challan page."""
    service = _get_service()
    coil_numbers = _load_coil_numbers(service)
    parties = _load_parties(service)
    consignee_names = _load_consignees(service)

    # Mode selector
    mode = st.radio(
        "Generation Mode",
        options=["📝 Manual", "🔢 From Coil Number", "🏢 From Party", "📦 Unused Coils"],
        horizontal=True,
        key="dc_mode",
        label_visibility="collapsed",
    )

    st.markdown("---")

    if mode == "📝 Manual":
        _render_manual_mode(service, consignee_names)
    elif mode == "🔢 From Coil Number":
        _render_coil_mode(service, consignee_names, coil_numbers)
    elif mode == "🏢 From Party":
        _render_party_mode(service, consignee_names, parties)
    elif mode == "📦 Unused Coils":
        _render_unused_coils_mode(service, consignee_names)

    # Re-upload section (available in all modes)
    st.markdown("---")
    _render_reupload_section(service)
