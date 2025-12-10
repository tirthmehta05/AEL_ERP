import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import time
from src.services import create_services, SalesOrderService
from src.data_entry.models.weight_receipt_models import WeightReceiptRequest, WeighedDesignDetail


@st.cache_resource(ttl=600)
def load_so_dropdowns(_service: SalesOrderService):
    return _service.get_dropdown_data()


@st.cache_data
def get_cached_job_cards(_service, party, start, end):
    return _service.get_job_cards_for_party_and_date_range(party, start, end)


def render_weight_receipt_form():
    st.markdown("<h3>Create Weight Receipt</h3>", unsafe_allow_html=True)

    services = create_services()

    dropdown_data = load_so_dropdowns(services.sales_order)
    party_names = dropdown_data.party_names

    # --- Filters ---
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_party = st.selectbox("Select Party", options=[""] + party_names)
    with col2:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
    with col3:
        end_date = st.date_input("End Date", datetime.now())

    if selected_party:
        job_cards = get_cached_job_cards(services.sales_order, selected_party, start_date, end_date)
        
        if not job_cards:
            st.info("No Job Cards found for the selected party and date range.")
            return

        job_card_options = {f"{jc['job_card_number']}": jc for jc in job_cards}
        selected_jc_str = st.selectbox("Select Job Card", options=[""] + list(job_card_options.keys()))

        if selected_jc_str:
            selected_jc = job_card_options[selected_jc_str]
            
            st.markdown("---")
            st.markdown(f"<h5>Details for {selected_jc['job_card_number']}</h5>", unsafe_allow_html=True)

            # --- Weight Receipt Number ---
            st.checkbox("Enter Weight Receipt Number Manually", key="use_custom_wr_number")
            
            if not st.session_state.get("use_custom_wr_number", False):
                if 'wr_number_input' not in st.session_state or not st.session_state.wr_number_input:
                    st.session_state.wr_number_input = services.weight_receipt.generate_weight_receipt_number()
            
            if st.session_state.get("use_custom_wr_number", False):
                st.text_input("Weight Receipt Number", key="wr_number_input")
            else:
                st.text_input("Weight Receipt Number (Auto-generated)", value=st.session_state.get("wr_number_input", ""), disabled=True)


            weight_entry_type = st.radio("Select Weight Entry Type", ["Loose Strips", "Building Core"], key="weight_entry_type")

            designs = json.loads(selected_jc.get('designs_json', '[]'))
            
            if not designs:
                st.warning("This job card has no design details.")
                return

            wr_number = st.session_state.get("wr_number_input", "").strip()
            if not wr_number:
                st.error("Weight Receipt Number is required.")
                return

            # Calculate expected total weight from job card designs
            expected_total_weight = sum(float(d.get('weight', 0)) for d in designs)

            if weight_entry_type == "Loose Strips":
                # Prepare dataframe for data_editor
                df = pd.DataFrame(designs)
                df['actual_weight'] = 0.0 # Add column for weight input
                df['remark'] = "" # Add column for remark input
                
                st.markdown("<h6>Enter Actual Weights and Remarks:</h6>", unsafe_allow_html=True)
                edited_df = st.data_editor(
                    df,
                    column_config={
                        "party_job_no": "Party Job No",
                        "width": "Width",
                        "length": "Length",
                        "actual_weight": st.column_config.NumberColumn("Actual Weight (kg)", format="%.2f", required=True),
                        "remark": st.column_config.TextColumn("Remark (Optional)")
                    },
                    disabled=["party_job_no", "width", "length"],
                    hide_index=True,
                    key="weight_receipt_editor"
                )

                if st.button("Save Weight Receipt", key="save_wr_button_loose"):
                    weighed_designs = []
                    for _, row in edited_df.iterrows():
                        if row['actual_weight'] <= 0:
                            st.error("Please enter a valid weight for all design items.")
                            st.stop()
                        
                        weighed_designs.append(WeighedDesignDetail(**row))
                    
                    wr_number = st.session_state.get("wr_number_input", "").strip()
                    if not wr_number:
                        st.error("Weight Receipt Number is required.")
                        st.stop()

                    actual_total_weight = sum(wd.actual_weight for wd in weighed_designs)
                    
                    variance_percent = 0.0
                    if expected_total_weight > 0:
                        variance_percent = abs(actual_total_weight - expected_total_weight) / expected_total_weight * 100

                    if expected_total_weight > 0 and variance_percent > 5:
                        warning_message = f"Weight variance ({variance_percent:.2f}%) exceeds 5% (Expected: {expected_total_weight:.2f} kg, Actual: {actual_total_weight:.2f} kg). Proceeding with save."
                        st.warning(warning_message)
                    
                    designs_from_jc = json.loads(selected_jc.get('designs_json', '[]'))
                    material_type = designs_from_jc[0].get('type', '') if designs_from_jc else ''
                    thk = designs_from_jc[0].get('thk', 0) if designs_from_jc else 0
                    material = f"{material_type} {thk}"

                    request = WeightReceiptRequest(
                        weight_receipt_number=wr_number,
                        receipt_date=datetime.now().date(),
                        job_card_number=selected_jc['job_card_number'],
                        party_name=selected_jc['party_name'],
                        po_no=selected_jc.get('po_no'),
                        material=material,
                        sets=selected_jc.get('number_of_cores', 0),
                        designs=weighed_designs,
                        weight_entry_type="Loose Strips",
                        total_weight=None
                    )

                    with st.spinner("Saving Weight Receipt..."):
                        success = services.weight_receipt.save_weight_receipt(request)
                        if success:
                            st.success(f"Weight Receipt {wr_number} saved successfully!")
                            # Clear state
                            if 'wr_number_input' in st.session_state:
                                del st.session_state['wr_number_input']
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Failed to save Weight Receipt.")


            elif weight_entry_type == "Building Core":
                st.markdown("<h6>Job Card Designs:</h6>", unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(designs).drop(columns=['actual_weight', 'remark'], errors='ignore'))

                total_weight = st.number_input("Total Actual Weight (kg)", min_value=0.01, format="%.2f", key="total_core_weight")
                core_remark = st.text_input("Remark (Optional)", key="core_remark")

                if st.button("Save Weight Receipt", key="save_wr_button_core"):
                    if total_weight <= 0:
                        st.error("Please enter a valid total weight.")
                        st.stop()
                    
                    weighed_designs = [WeighedDesignDetail(**d, remark=core_remark) for d in designs]
                    
                    wr_number = st.session_state.get("wr_number_input", "").strip()
                    if not wr_number:
                        st.error("Weight Receipt Number is required.")
                        st.stop()

                    actual_total_weight = total_weight
                    
                    variance_percent = 0.0
                    if expected_total_weight > 0:
                        variance_percent = abs(actual_total_weight - expected_total_weight) / expected_total_weight * 100

                    if expected_total_weight > 0 and variance_percent > 5:
                        warning_message = f"Weight variance ({variance_percent:.2f}%) exceeds 5% (Expected: {expected_total_weight:.2f} kg, Actual: {actual_total_weight:.2f} kg). Proceeding with save."
                        st.warning(warning_message)
                    
                    designs_from_jc = json.loads(selected_jc.get('designs_json', '[]'))
                    material_type = designs_from_jc[0].get('type', '') if designs_from_jc else ''
                    thk = designs_from_jc[0].get('thk', 0) if designs_from_jc else 0
                    material = f"{material_type} {thk}"

                    request = WeightReceiptRequest(
                        weight_receipt_number=wr_number,
                        receipt_date=datetime.now().date(),
                        job_card_number=selected_jc['job_card_number'],
                        party_name=selected_jc['party_name'],
                        po_no=selected_jc.get('po_no'),
                        material=material,
                        sets=selected_jc.get('number_of_cores', 0),
                        designs=weighed_designs,
                        weight_entry_type="Building Core",
                        total_weight=total_weight
                    )

                    with st.spinner("Saving Weight Receipt..."):
                        success = services.weight_receipt.save_weight_receipt(request)
                        if success:
                            st.success(f"Weight Receipt {wr_number} saved successfully!")
                            # Clear state
                            if 'wr_number_input' in st.session_state:
                                del st.session_state['wr_number_input']
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Failed to save Weight Receipt.")
