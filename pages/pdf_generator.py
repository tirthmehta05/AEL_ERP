import json
import streamlit as st
import pandas as pd
from src.services import create_services, AppServices
from datetime import datetime, timedelta

# --- Top-level Cached Functions ---

@st.cache_data
def get_available_coils(_services: AppServices):
    """Cached function to fetch available coils."""
    return _services.pdf.get_available_coils_for_sticker()

@st.cache_data
def get_printable_plans(_services: AppServices):
    """Cached function to fetch printable slitting plans."""
    return _services.slitting_plan.get_printable_plans()

@st.cache_data
def get_job_cards(_services: AppServices, start, end):
    """Cached function to fetch job card data."""
    return _services.pdf.get_sales_orders_for_job_card(start_date=start, end_date=end)

@st.cache_data
def get_sales_order_dropdown_data(_services: AppServices):
    """Cached function to fetch dropdown data for sales orders."""
    return _services.sales_order.get_dropdown_data()

@st.cache_data
def get_weight_receipts(_services: AppServices, party_name: str, start_date, end_date):
    """Cached function to fetch weight receipt data."""
    return _services.weight_receipt.get_weight_receipts_for_party_and_date_range(party_name, start_date, end_date)

# --- Tab Rendering Functions ---

def render_coil_sticker_tab(services: AppServices):
    """Renders the UI for the Coil Sticker tab."""
    st.header("Coil Sticker Generation")

    available_coils_df = get_available_coils(services)

    if available_coils_df.empty:
        st.warning("No available coils found.")
        return

    available_coils_df["Select"] = False
    edited_df = st.data_editor(
        available_coils_df,
        column_order=["Select", "Coil Number", "available_weight", "grade", "thickness", "width", "coating", "coil_supplier"],
        disabled=["Coil Number", "available_weight", "grade", "thickness", "width", "coating", "coil_supplier"],
        hide_index=True,
    )
    selected_coils = edited_df[edited_df["Select"]]

    if not selected_coils.empty:
        st.write(f"{len(selected_coils)} coil(s) selected.")
        if st.button("Generate Stickers (PDF)"):
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

        if st.button("Generate PDF for this Plan"):
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
    """Renders the UI for the Delivery Challan tab."""
    st.header("Delivery Challan Generation")
    
    # --- Filters ---
    col1, col2, col3 = st.columns(3)
    with col1:
        party_names = get_sales_order_dropdown_data(services).party_names
        selected_party = st.selectbox("Select Party", options=[""] + party_names, key="dc_party")
    with col2:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30), key="dc_start_date")
    with col3:
        end_date = st.date_input("End Date", datetime.now(), key="dc_end_date")

    if selected_party:
        receipts = services.weight_receipt.get_weight_receipts_for_party_and_date_range(selected_party, start_date, end_date)
        
        if not receipts:
            st.info("No Weight Receipts found for the selected party and date range.")
            return

        df = pd.DataFrame(receipts)
        df["Select"] = False
        
        edited_df = st.data_editor(
            df,
            column_order=["Select", "WeightReceiptNumber", "Date", "JobCardNumber"],
            disabled=["WeightReceiptNumber", "Date", "JobCardNumber", "PartyName", "DesignDetailsWithWeightsJSON"],
            hide_index=True,
            key="dc_receipt_editor"
        )

        selected_receipts = edited_df[edited_df["Select"]]

        if not selected_receipts.empty:
            st.write(f"{len(selected_receipts)} receipt(s) selected.")
            if st.button("Generate Delivery Challan"):
                
                # --- Data Transformation Logic ---
                def _prepare_challan_data(receipts_df):
                    items = []
                    grand_total_weight = 0
                    # Group by JobCardNumber to consolidate items
                    for job_card_number, group in receipts_df.groupby("JobCardNumber"):
                        first_row = group.iloc[0]
                        line_items = []
                        total_job_card_weight = 0

                        # Each row in the group is a Weight Receipt
                        for _, receipt_row in group.iterrows():
                            is_core_building = receipt_row.get('WeightEntryType') == 'Building Core'
                            
                            if is_core_building:
                                core_weight = float(receipt_row.get('TotalWeight') or 0)
                                if core_weight > 0:
                                    designs = json.loads(receipt_row.get('DesignDetailsWithWeightsJSON', '[]'))
                                    
                                    if isinstance(designs, list):
                                        for design in designs:
                                            description = f"{design.get('width', '')} X {design.get('length', '')}"
                                            if design.get('mm_stack'):
                                                description += f" X {design.get('mm_stack', '')}"
                                            
                                            line_items.append({
                                                "description": description,
                                                "remark": design.get('remark', ''),
                                                "weight": None # No individual weight for core building
                                            })
                                    total_job_card_weight += core_weight
                            else:
                                # Legacy or "Loose Strips" logic
                                designs = json.loads(receipt_row.get('DesignDetailsWithWeightsJSON', '[]'))
                                if isinstance(designs, list):
                                    for design in designs:
                                        weight = float(design.get('actual_weight') or 0)
                                        if weight > 0:
                                            remark = design.get('remark', '')
                                            description = f"{design.get('width', '')} X {design.get('length', '')}"
                                            if design.get('mm_stack'):
                                                description += f" X {design.get('mm_stack', '')}"
                                            
                                            line_items.append({
                                                "description": description,
                                                "remark": remark,
                                                "weight": weight
                                            })
                                            total_job_card_weight += weight
                        
                        if line_items:
                            grand_total_weight += total_job_card_weight
                            items.append({
                                "job_no": job_card_number,
                                "po_no": first_row.get('PONumber', ''),
                                "line_items": line_items,
                                "summary": {
                                    "material": first_row.get('Material', ''),
                                    "sets": first_row.get('Sets', 0),
                                    "total_weight": total_job_card_weight
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
                            "challan_no": "UI", # Placeholder
                            "challan_date": datetime.now().strftime("%d/%m/%Y"),
                            "vehicle_no": ""
                        },
                        "items": items,
                        "grand_total_weight": grand_total_weight
                    }
                    return challan_data

                challan_data = _prepare_challan_data(selected_receipts)

                with st.spinner("Generating PDF..."):
                    pdf_output = services.pdf.generate_delivery_challan_pdf(challan_data)
                    st.download_button(
                        label="Download Delivery Challan",
                        data=pdf_output,
                        file_name="delivery_challan.pdf",
                        mime="application/pdf"
                    )

def render_job_card_tab(services: AppServices):
    """Renders the UI for the Job Card tab."""
    st.header("Job Card PDF Generation")
    
    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
    with col2:
        end_date = st.date_input("End Date", datetime.now())

    job_cards_data = get_job_cards(services, start_date, end_date)

    if not job_cards_data:
        st.warning("No job cards found for the selected date range.")
        return

    job_cards_df = pd.DataFrame(job_cards_data)
    
    # Create a view for the data editor without the JSON column
    display_df = job_cards_df.drop(columns=['designs_json'], errors='ignore')
    display_df["Select"] = False

    edited_df = st.data_editor(
        display_df,
        column_order=["Select", "job_card_number", "party_name", "order_date", "delivery_date"],
        disabled=["job_card_number", "party_name", "order_date", "delivery_date"],
        hide_index=True,
    )

    selected_indices = edited_df[edited_df["Select"]].index

    if len(selected_indices) > 0:
        st.write(f"{len(selected_indices)} job card(s) selected.")
        if st.button("Generate Job Card PDF"):
            with st.spinner("Generating PDF..."):
                selected_job_cards_data = job_cards_df.loc[selected_indices].to_dict('records')
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

        receipt_options = {r['WeightReceiptNumber']: r for r in receipts}
        selected_receipt_number = st.selectbox(
            "Select Weight Receipt to Print", 
            options=[""] + list(receipt_options.keys())
        )

        if selected_receipt_number:
            selected_receipt = receipt_options[selected_receipt_number]
            
            st.markdown(f"**Receipt Number:** {selected_receipt.get('WeightReceiptNumber')}")
            st.markdown(f"**Date:** {selected_receipt.get('Date')}")
            st.markdown(f"**Job Card No:** {selected_receipt.get('JobCardNumber')}")

            is_core_building = selected_receipt.get('WeightEntryType') == 'Building Core'
            
            if is_core_building:
                st.markdown(f"**Weight Entry Type:** Building Core")
                st.markdown(f"**Total Weight:** {float(selected_receipt.get('TotalWeight', 0.0) or 0.0):.2f} kg")

            designs = json.loads(selected_receipt.get('DesignDetailsWithWeightsJSON', '[]'))
            st.markdown("**Designs:**")
            
            df = pd.DataFrame(designs)
            if is_core_building:
                # For core building, actual_weight is not relevant per design
                st.dataframe(df.drop(columns=['actual_weight'], errors='ignore'))
            else:
                st.dataframe(df)

            if st.button("Generate PDF for this Weight Receipt"):
                with st.spinner("Generating PDF..."):
                    pdf_output = services.pdf.generate_weight_receipt_pdf(selected_receipt)
                    st.download_button(
                        label="Download PDF",
                        data=pdf_output,
                        file_name=f"{selected_receipt_number}.pdf",
                        mime="application/pdf"
                    )

def render_pdf_generator_page():
    """Renders the main PDF Generator page with tabs."""
    st.title("📄 PDF Generator")

    if st.session_state.get('clear_cache_for_pdf_generator'):
        st.session_state['clear_cache_for_pdf_generator'] = False
        try:
            get_available_coils.clear()
            get_printable_plans.clear()
            get_job_cards.clear()
            get_sales_order_dropdown_data.clear()
            get_weight_receipts.clear()
            st.toast("PDF Generator cache cleared!")
        except NameError: # Functions might not be defined if tabs are not rendered
            pass

    services = create_services()
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Coil Sticker", "Slitting Plan", "Job Card", "Delivery Challan", "Weight Receipt"])

    with tab1:
        render_coil_sticker_tab(services)
    
    with tab2:
        render_slitting_plan_tab(services)

    with tab3:
        render_job_card_tab(services)
    
    with tab4:
        render_delivery_challan_tab(services)
    
    with tab5:
        render_weight_receipt_tab(services)
