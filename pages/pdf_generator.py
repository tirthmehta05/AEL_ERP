import streamlit as st
import pandas as pd
from src.pdf_generator.service.pdf_service import PDFService
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService
from src.data_entry.service.sales_order_service import SalesOrderService
from src.data_entry.service.weight_receipt_service import WeightReceiptService
from datetime import datetime, timedelta
import json

def render_coil_sticker_tab():
    """Renders the UI for the Coil Sticker tab."""
    st.header("Coil Sticker Generation")
    pdf_service = PDFService()

    @st.cache_data
    def get_available_coils():
        return pdf_service.get_available_coils_for_sticker()

    available_coils_df = get_available_coils()

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
                pdf_output = pdf_service.generate_sticker_pdf(selected_coils)
                st.download_button(
                    label="Download PDF",
                    data=pdf_output,
                    file_name="coil_stickers.pdf",
                    mime="application/pdf"
                )

def render_slitting_plan_tab():
    """Renders the UI for the Slitting Plan tab."""
    st.header("Slitting Plan PDF Generation")
    
    slitting_service = SlittingPlanService()
    pdf_service = PDFService()

    @st.cache_data
    def get_printable_plans():
        return slitting_service.get_printable_plans()

    printable_plans = get_printable_plans()

    if not printable_plans:
        st.warning("No printable slitting plans found with status 'Created' or 'In Process'.")
        return

    selected_plan_id = st.selectbox("Select a Slitting Plan to Print", options=["None"] + printable_plans)

    if selected_plan_id and selected_plan_id != "None":
        plan_details = slitting_service.get_saved_plan_details(selected_plan_id)

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
                pdf_output = pdf_service.generate_slitting_plan_pdf(plan_details)
                success = slitting_service.update_plan_status(selected_plan_id, "In Process")

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

def render_delivery_challan_tab():
    """Renders the UI for the Delivery Challan tab."""
    st.header("Delivery Challan Generation")
    
    pdf_service = PDFService()
    weight_receipt_service = WeightReceiptService()
    sales_order_service = SalesOrderService()

    # --- Filters ---
    col1, col2, col3 = st.columns(3)
    with col1:
        party_names = sales_order_service.get_dropdown_data().party_names
        selected_party = st.selectbox("Select Party", options=[""] + party_names, key="dc_party")
    with col2:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30), key="dc_start_date")
    with col3:
        end_date = st.date_input("End Date", datetime.now(), key="dc_end_date")

    if selected_party:
        receipts = weight_receipt_service.get_weight_receipts_for_party_and_date_range(selected_party, start_date, end_date)
        
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
                    for job_card_number, group in receipts_df.groupby("JobCardNumber"):
                        first_row = group.iloc[0]
                        line_items = []
                        total_weight = 0
                        for _, row in group.iterrows():
                            designs = json.loads(row.get('DesignDetailsWithWeightsJSON', '[]'))
                            if isinstance(designs, list):
                                for design in designs:
                                    remark = design.get('remark', '')
                                    description = f"{design.get('width', '')} X {design.get('length', '')} X {design.get('mm_stack', '')}"
                                    if remark:
                                        description += f" ({remark})"
                                    
                                    line_items.append({
                                        "description": description,
                                        "weight": design.get('actual_weight', 0)
                                    })
                                    total_weight += design.get('actual_weight', 0)
                        
                        items.append({
                            "job_no": job_card_number,
                            "po_no": first_row.get('PONumber', ''),
                            "line_items": line_items,
                            "summary": {
                                "material": first_row.get('Material', ''),
                                "sets": first_row.get('Sets', 0),
                                "total_weight": total_weight
                            }
                        })

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
                        "items": items
                    }
                    return challan_data

                challan_data = _prepare_challan_data(selected_receipts)

                with st.spinner("Generating PDF..."):
                    pdf_output = pdf_service.generate_delivery_challan_pdf(challan_data)
                    st.download_button(
                        label="Download Delivery Challan",
                        data=pdf_output,
                        file_name="delivery_challan.pdf",
                        mime="application/pdf"
                    )


def render_pdf_generator_page():
    """Renders the main PDF Generator page with tabs."""
    st.title("📄 PDF Generator")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Coil Sticker", "Slitting Plan", "Job Card", "Delivery Challan"]) # Add new tab

    with tab1:
        render_coil_sticker_tab()
    
    with tab2:
        render_slitting_plan_tab()

    with tab3:
        render_job_card_tab()
    
    with tab4:
        render_delivery_challan_tab()

def render_job_card_tab():
    """Renders the UI for the Job Card tab."""
    st.header("Job Card PDF Generation")
    
    pdf_service = PDFService()

    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
    with col2:
        end_date = st.date_input("End Date", datetime.now())

    @st.cache_data
    def get_job_cards(start, end):
        return pdf_service.get_sales_orders_for_job_card(start_date=start, end_date=end)

    job_cards_data = get_job_cards(start_date, end_date)

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
                pdf_output = pdf_service.generate_job_card_pdf(selected_job_cards_data)
                st.download_button(
                    label="Download Job Card PDF",
                    data=pdf_output,
                    file_name="job_cards.pdf",
                    mime="application/pdf"
                )

# Entry point, called from main.py
# render_pdf_generator_page()
