import json
import streamlit as st
import pandas as pd
from pages.shared.utils import get_services
from src.services import AppServices
from datetime import datetime, timedelta
from io import BytesIO

# --- Top-level Cached Functions ---

@st.cache_data
def get_available_coils(_services: AppServices, start, end):
    """Cached function to fetch available coils."""
    return _services.pdf.get_available_coils_for_sticker(start_date=start, end_date=end)

@st.cache_data
def get_printable_plans(_services: AppServices):
    """Cached function to fetch printable slitting plans."""
    return _services.slitting_plan.get_printable_plans()

@st.cache_data
def get_job_cards(_services: AppServices, start, end):
    """Cached function to fetch job card data."""
    return _services.pdf.get_sales_orders_for_job_card(start_date=start, end_date=end)

@st.cache_resource
def get_sales_order_dropdown_data(_services: AppServices):
    """Cached function to fetch dropdown data for sales orders."""
    return _services.sales_order.get_dropdown_data()

@st.cache_data
def get_weight_receipts(_services: AppServices, party_name: str, start_date, end_date):
    """Cached function to fetch weight receipt data."""
    return _services.weight_receipt.get_weight_receipts_for_party_and_date_range(party_name, start_date, end_date)

# --- Tab Rendering Functions ---

def _prepare_challan_data(receipts_df):
        items = []
        grand_total_weight = 0

        for _, receipt_row in receipts_df.iterrows():
            line_items = []
            receipt_total_weight = 0
            receipt_total_deduction = float(receipt_row.get('Deduction', 0) or 0)

            try:
                designs = json.loads(receipt_row.get('DesignDetailsWithWeightsJSON', '[]') or '[]')
            except:
                designs = []

            if isinstance(designs, list):
                for design in designs:
                    weight = float(design.get('actual_weight', 0) or 0)
                    deduction = float(design.get('design_deduction', 0) or 0)

                    if weight > 0:
                        description = f"{design.get('width', '')} X {design.get('length', '')}"

                        if design.get('mm_stack'):
                            description += f" X {design.get('mm_stack', '')}"

                        line_items.append({
                            "description": description,
                            "remark": design.get('remark', ''),
                            "weight": weight,
                            "deduction": deduction,
                            "net_weight": weight - deduction,
                            "hsn": receipt_row.get("HSN", ""),
                            "rate": receipt_row.get("Rate", 0),
                            "value": receipt_row.get("Value", 0)
                        })
                        receipt_total_weight += weight

            if line_items:
                grand_total_weight += receipt_total_weight

                items.append({
                    "job_no": receipt_row.get('JobCardNumber', ''),
                    "po_no": receipt_row.get('PONumber', ''),
                    "line_items": line_items,
                    "summary": {
                        "material": receipt_row.get('Material', ''),
                        "sets": receipt_row.get('Sets', 0),
                        "total_weight": receipt_total_weight,
                        "total_deduction": receipt_total_deduction,
                        "net_total_weight": receipt_total_weight - receipt_total_deduction
                    }
                })

        if not items:
            return None

        challan_data = {
            "challan_details": {
                "to_customer": receipts_df.iloc[0].get('PartyName', ''),
                "from_company": {
                    "name": "AMBA ENTERPRISE LTD. (UNIT I)",
                    "address": "S. No 132 , H.No 1/4/1, Premraj Ind Est, Shed No B-1/2/3/4, Dalvi Wadi, Nanded Phata, Dhairy, Pune 411041"
                },
                "challan_no": "UI",
                "challan_date": datetime.now().strftime("%d/%m/%Y"),
                "vehicle_no": ""
            },
            "items": items,
            "grand_total_weight": grand_total_weight,
            "receipts": receipts_df
        }

        return challan_data


def render_coil_sticker_tab(services: AppServices):
    """Renders the UI for the Coil Sticker tab."""
    st.header("Coil Sticker Generation")

    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30), key="coil_sticker_start_date")
    with col2:
        end_date = st.date_input("End Date", datetime.now(), key="coil_sticker_end_date")

    # Fetch data (cached)
    available_coils_df = get_available_coils(services, start_date, end_date)

    if available_coils_df.empty:
        st.warning("No available coils found for the selected date range.")
        return

    # Render st.dataframe with selection_mode
    st.dataframe(
        available_coils_df,
        on_select="rerun",
        selection_mode="multi-row",
        column_order=["Coil Number", "available_weight", "grade", "thickness", "width", "coating", "coil_supplier"],
        hide_index=True,
        key="coil_sticker_df_selection" # Key for st.dataframe component
    )

    # Retrieve selected rows using the session state of the st.dataframe component
    selected_indices = st.session_state.coil_sticker_df_selection.selection.rows
    selected_coils = available_coils_df.iloc[selected_indices] # Use iloc on the original df

    if not selected_coils.empty:
        st.write(f"{len(selected_coils)} coil(s) selected.")
        if st.button("Generate Stickers (PDF)", key="generate_coil_stickers_pdf"):
            with st.spinner("Generating PDF..."):
                pdf_output = services.pdf.generate_sticker_pdf(selected_coils)
                st.download_button(
                    label="Download PDF",
                    data=pdf_output,
                    file_name="coil_stickers.pdf",
                    mime="application/pdf"
                )

def render_slitting_plan_tab(services: AppServices):
    """Renders the UI for the Slitting Plan tab."""
    st.header("Slitting Plan PDF Generation")
    
    printable_plans = get_printable_plans(services)

    if not printable_plans:
        st.warning("No printable slitting plans found with status 'Created' or 'In Process'.")
        return

    selected_plan_id = st.selectbox("Select a Slitting Plan to Print", options=["None"] + printable_plans)

    if selected_plan_id and selected_plan_id != "None":
        plan_details = services.slitting_plan.get_saved_plan_details(selected_plan_id)

        if not plan_details:
            st.error(f"Could not retrieve details for plan {selected_plan_id}.")
            return

        st.markdown(f"**Date:** {plan_details.get('date')}")
        st.markdown("**Raw Materials:**")
        st.dataframe(pd.DataFrame(plan_details.get('raw_materials', [])))
        st.markdown("**Slit Details:**")
        st.dataframe(pd.DataFrame(plan_details.get('slit_details', [])))

        if st.button("Generate PDF for this Plan", key="generate_slitting_plan_pdf"):
            with st.spinner("Generating PDF and updating status..."):
                pdf_output = services.pdf.generate_slitting_plan_pdf(plan_details)
                success = services.slitting_plan.update_plan_status(selected_plan_id, "In Process")

                if success:
                    st.success("Status updated to 'In Process'.")
                    get_printable_plans.clear() # Refresh the list
                else:
                    st.error("Failed to update plan status.")

                st.download_button(
                    label="Download PDF",
                    data=pdf_output,
                    file_name=f"{selected_plan_id}.pdf",
                    mime="application/pdf"
                )

def render_delivery_challan_tab(services: AppServices):
    """Enhanced Delivery Challan with Weight + Unused Coil modes"""
    st.header("Delivery Challan Generation")

    # =========================
    # MODE SELECTION
    # =========================
    generation_mode = st.radio(
        "Generation Mode",
        ["⚖️ Weight Challan", "📦 Unused Coils"],
        horizontal=True,
        key="dc_mode"
    )

    if generation_mode == "📦 Unused Coils":
        sub_mode = st.radio(
            "Select Method",
            ["🔢 From Coil Number", "🏢 From Party"],
            horizontal=True,
            key="dc_sub_mode"
        )

    st.markdown("---")

    
    # ============================================================
    # 🟢 MODE 1 — ORIGINAL WEIGHT CHALLAN (UNCHANGED)
    # ============================================================
    if generation_mode == "⚖️ Weight Challan":

        col1, col2, col3 = st.columns(3)

        with col1:
            party_names = get_sales_order_dropdown_data(services).party_names
            selected_party = st.selectbox("Select Party", options=[""] + party_names)

        with col2:
            start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))

        with col3:
            end_date = st.date_input("End Date", datetime.now())

        if selected_party:
            receipts = services.weight_receipt.get_weight_receipts_for_party_and_date_range(
                selected_party, start_date, end_date
            )

            if not receipts:
                st.info("No Weight Receipts found.")
                return

            df = pd.DataFrame(receipts)

            st.dataframe(
                df,
                on_select="rerun",
                selection_mode="multi-row",
                hide_index=True,
                key="dc_receipt_df"
            )

            selected_idx = st.session_state.get("dc_receipt_df", {}).get("selection", {}).get("rows", [])
            selected_df = df.iloc[selected_idx]

            if not selected_df.empty:
                if st.button("Generate Delivery Challan"):

                    challan_data = _prepare_challan_data(selected_df)

                    if challan_data is None:
                        st.error("No valid data to generate challan.")
                        st.stop()

                    pdf = services.pdf.generate_delivery_challan_pdf(challan_data)

                    st.download_button(
                        "Download PDF",
                        pdf,
                        "delivery_challan.pdf",
                        "application/pdf"
                    )

    # ============================================================
    # 🟢 MODE 2 — UNUSED COILS
    # ============================================================
    elif generation_mode == "📦 Unused Coils":

        # =========================
        # GET UNUSED COILS
        # =========================
        def get_unused_coils():
            # Fetch already computed available coils (inward - used)
            df = services.pdf.get_available_coils_for_sticker(
                start_date=datetime.now() - timedelta(days=3650),
                end_date=datetime.now()
            )

            df = pd.DataFrame(df)

            if df.empty:
                return df

            # Ensure column exists
            if "available_weight" in df.columns:
                df["remaining_weight"] = df["available_weight"]
            else:
                df["remaining_weight"] = 0

            # Keep only coils with remaining weight
            df = df[df["remaining_weight"] > 0]

            return df


        df = get_unused_coils()

        if df.empty:
            st.warning("No unused coils available.")
            return

        # =========================
        # SUB MODE FILTERING
        # =========================
        if sub_mode == "🔢 From Coil Number":

            selected_coils = st.multiselect(
                "Select Coil Number",
                options=df["Coil Number"].unique()
            )

            if selected_coils:
                df = df[df["Coil Number"].isin(selected_coils)]

        elif sub_mode == "🏢 From Party":

            col1, col2, col3 = st.columns(3)

            with col1:
                parties = df["coil_supplier"].dropna().unique()
                selected_party = st.selectbox("Select Party", options=[""] + list(parties))

            with col2:
                start_date = st.date_input(
                    "Start Date",
                    datetime.now() - timedelta(days=30),
                    key="unused_start_date"
                )

            with col3:
                end_date = st.date_input(
                    "End Date",
                    datetime.now(),
                    key="unused_end_date"
                )

            # Apply filters
            if selected_party:
                df = df[df["coil_supplier"] == selected_party]

            # OPTIONAL: if your data has date column
            if "inward_date" in df.columns:
                df = df[
                    (pd.to_datetime(df["inward_date"]) >= pd.to_datetime(start_date)) &
                    (pd.to_datetime(df["inward_date"]) <= pd.to_datetime(end_date))
                ]

        # =========================
        # DISPLAY
        # =========================
        display_cols = [col for col in ["Coil Number", "remaining_weight", "grade", "width", "coil_supplier"] if col in df.columns]

        st.dataframe(
            df[display_cols],
            on_select="rerun",
            selection_mode="multi-row",
            hide_index=True,
            key="unused_df"
        )

        # SAFE selection (same as weight challan)
        selected_idx = st.session_state.get("unused_df", {}).get("selection", {}).get("rows", [])
        selected_df = df.iloc[selected_idx]

        if len(selected_idx) > 0:
            st.write(f"{len(selected_idx)} coil(s) selected.")

        # =========================
        # EXCEL FALLBACK (IMPROVED)
        # =========================
        if not selected_df.empty:

            # --- Step 1: Detect missing data properly ---
            required_fields = {
                "coil_supplier": "Party Name",
                "remaining_weight": "Weight",
                "width": "Width",
            }

            missing_data = []

            for field, label in required_fields.items():
                if field not in selected_df.columns:
                    missing_data.append(label)
                elif selected_df[field].isnull().any():
                    missing_data.append(label)

            # Optional business fields
            optional_fields = ["rate", "hsn"]

            for field in optional_fields:
                if field not in selected_df.columns or selected_df[field].isnull().any():
                    missing_data.append(field.upper())

            # --- Step 2: If missing → generate structured Excel ---
            uploaded = None
            if missing_data:

                st.warning(f"Missing fields: {', '.join(missing_data)}")

                def generate_missing_excel(df):
                    rows = []  # ✅ MUST be inside function

                    for _, r in df.iterrows():
                        rows.append({
                            "Coil Number": r.get("Coil Number", ""),
                            "Party Name": r.get("coil_supplier", ""),
                            "Width": r.get("width", ""),
                            "Weight (kg)": r.get("remaining_weight", ""),
                            "HSN Code": r.get("hsn", ""),
                            "Rate per MT": r.get("rate", ""),
                            "Value": ""
                        })

                    export_df = pd.DataFrame(rows)  # ✅ inside function

                    buffer = BytesIO()
                    export_df.to_excel(buffer, index=False, sheet_name="Challan Data")

                    return buffer.getvalue()

                excel_bytes = generate_missing_excel(selected_df)

                st.download_button(
                    "Download Excel (Fill Missing Data)",
                    excel_bytes,
                    "delivery_challan_missing.xlsx"
                )

                uploaded = st.file_uploader("Upload Filled Excel", type=["xlsx"])

            if uploaded:
                filled_df = pd.read_excel(uploaded)

                # Normalize columns
                selected_df = filled_df.rename(columns={
                    "Party Name": "coil_supplier",
                    "Weight (kg)": "remaining_weight",
                    "HSN Code": "hsn",
                    "Rate per MT": "rate",
                    "Coil Number": "Coil Number"
                })

                # 🔥 Ensure numeric conversion
                selected_df["remaining_weight"] = pd.to_numeric(selected_df["remaining_weight"], errors="coerce")
                selected_df["rate"] = pd.to_numeric(selected_df.get("rate", 0), errors="coerce")

                # 🔥 Calculate value
                selected_df["value"] = (
                    selected_df["remaining_weight"] / 1000
                ) * selected_df.get("rate", 0)

                st.success("Excel uploaded successfully. Data updated.")


        # =========================
        # CONVERT → RECEIPT FORMAT
        # =========================
        def convert_to_receipt(df):
            rows = []

            for _, r in df.iterrows():
                rows.append({
                    "WeightReceiptNumber": "",
                    "Date": datetime.now(),
                    "JobCardNumber": r.get("Coil Number", ""),
                    "WeightEntryType": "Loose",
                    "TotalWeight": r["remaining_weight"],
                    "Deduction": 0,
                    "HSN": r.get("hsn", ""),
                    "Rate": r.get("rate", 0),
                    "Value": r.get("value", 0),
                    "DesignDetailsWithWeightsJSON": json.dumps([{
                        "width": r.get("width", ""),
                        "length": "",
                        "actual_weight": r["remaining_weight"],
                        "design_deduction": 0,
                        "remark": "Unused Coil"
                    }]),
                    "PartyName": r.get("coil_supplier", "")
                })

            return pd.DataFrame(rows)

        # =========================
        # GENERATE PDF
        # =========================
        if not selected_df.empty:
            if st.button("Generate Delivery Challan"):

                receipt_df = convert_to_receipt(selected_df)

                challan_data = _prepare_challan_data(receipt_df)

                if challan_data is None:
                    st.error("No valid data to generate challan. Check selected rows.")
                    st.stop()

                pdf = services.pdf.generate_delivery_challan_pdf(challan_data)

                st.download_button(
                    "Download PDF",
                    pdf,
                    "delivery_challan.pdf",
                    "application/pdf"
                )

def render_job_card_tab(services: AppServices):
    """Renders the UI for the Job Card tab."""
    st.header("Job Card PDF Generation")
    
    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30), key="job_card_start_date")
    with col2:
        end_date = st.date_input("End Date", datetime.now(), key="job_card_end_date")

    job_cards_data = get_job_cards(services, start_date, end_date)

    if not job_cards_data:
        st.warning("No job cards found for the selected date range.")
        return

    job_cards_df = pd.DataFrame(job_cards_data)
    
    # Create a view for the data editor without the JSON column
    display_df = job_cards_df.drop(columns=['designs_json'], errors='ignore')

    st.dataframe(
        display_df,
        on_select="rerun",
        selection_mode="multi-row",
        column_order=["job_card_number", "party_name", "order_date", "delivery_date"],
        hide_index=True,
        key="job_card_selection_df", # Unique key for this dataframe
    )

    selected_selection_indices = st.session_state.job_card_selection_df.selection.rows

    if len(selected_selection_indices) > 0:
        st.write(f"{len(selected_selection_indices)} job card(s) selected.")
        if st.button("Generate Job Card PDF", key="generate_job_card_pdf"):
            with st.spinner("Generating PDF..."):
                selected_job_cards_data = job_cards_df.iloc[selected_selection_indices].to_dict('records')
                pdf_output = services.pdf.generate_job_card_pdf(selected_job_cards_data)
                st.download_button(
                    label="Download Job Card PDF",
                    data=pdf_output,
                    file_name="job_cards.pdf",
                    mime="application/pdf"
                )


def render_weight_receipt_tab(services: AppServices):
    """Renders the UI for the Weight Receipt tab."""
    st.header("Weight Receipt PDF Generation")
    
    # --- Filters ---
    col1, col2, col3 = st.columns(3)
    with col1:
        party_names = get_sales_order_dropdown_data(services).party_names
        selected_party = st.selectbox("Select Party", options=[""] + party_names, key="wr_party")
    with col2:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30), key="wr_start_date")
    with col3:
        end_date = st.date_input("End Date", datetime.now(), key="wr_end_date")

    if selected_party:
        receipts = get_weight_receipts(services, selected_party, start_date, end_date)
        
        if not receipts:
            st.info("No Weight Receipts found for the selected party and date range.")
            return

        df = pd.DataFrame(receipts)
            
        st.dataframe(
            df,
            on_select="rerun",
            selection_mode="multi-row",
            column_order=["WeightReceiptNumber", "Date", "JobCardNumber"],
            hide_index=True,
            key="wr_receipt_selection_df"
        )

        selected_indices = st.session_state.wr_receipt_selection_df.selection.rows
        selected_receipts = df.iloc[selected_indices]

        if not selected_receipts.empty:
            st.write(f"{len(selected_receipts)} receipt(s) selected.")
            if st.button("Generate Weight Receipt PDF", key="generate_weight_receipt_pdf"):
                with st.spinner("Generating PDF..."):
                    selected_receipts_data = selected_receipts.to_dict('records')
                    pdf_output = services.pdf.generate_weight_receipt_pdf(selected_receipts_data)
                    st.download_button(
                        label="Download Weight Receipt PDF",
                        data=pdf_output,
                        file_name="weight_receipts.pdf",
                        mime="application/pdf"
                    )

def render_pdf_generator_page():
    """Renders the main PDF Generator page with state-aware tabs."""
    st.title("📄 PDF Generator")

    services = get_services()

    # Map tabs to the cache functions they depend on.
    # This allows for targeted cache clearing.
    TABS = {
        "Coil Sticker": [get_available_coils],
        "Slitting Plan": [get_printable_plans],
        "Job Card": [get_job_cards],
        "Delivery Challan": [get_sales_order_dropdown_data, get_weight_receipts],
        "Weight Receipt": [get_sales_order_dropdown_data, get_weight_receipts]
    }
    tab_names = list(TABS.keys())

    # --- State and Cache Management ---

    # Determine the index for the radio button.
    try:
        radio_index = tab_names.index(st.session_state.pdf_generator_active_tab)
    except (AttributeError, ValueError):
        radio_index = 0 # Default for the very first load

    # Check for a refresh request.
    cache_clear_data = st.session_state.get('cache_to_clear')
    if cache_clear_data and cache_clear_data.get('page') == 'pdf_generator':
        tab_to_clear = cache_clear_data.get('tab')
        st.session_state.pop('cache_to_clear') # Consume the flag

        if tab_to_clear:
            # Clear caches for the specific tab
            caches_to_clear = TABS.get(tab_to_clear, [])
            for cache_func in caches_to_clear:
                cache_func.clear()
            st.toast(f"Cache for '{tab_to_clear}' tab cleared!")
                
            # Ensure the UI stays on the cleared tab
            if tab_to_clear in tab_names:
                radio_index = tab_names.index(tab_to_clear)
            else:
                # If no specific tab is targeted, clear all for the page (optional)
                for cache_list in TABS.values():
                    for cache_func in cache_list:
                        cache_func.clear()
                st.toast("Cache for PDF Generator page cleared!")

    # --- UI Rendering ---

    active_tab = st.radio(
        "Select PDF Type:",
        tab_names,
        index=radio_index,
        horizontal=True,
        key="pdf_generator_active_tab",
        label_visibility="collapsed"
    )

    # Render the content for the selected tab.
    if active_tab == "Coil Sticker":
        render_coil_sticker_tab(services)   
    elif active_tab == "Slitting Plan":
        render_slitting_plan_tab(services)
    elif active_tab == "Job Card":
        render_job_card_tab(services)
    elif active_tab == "Delivery Challan":
        render_delivery_challan_tab(services)
    elif active_tab == "Weight Receipt":
        render_weight_receipt_tab(services)
