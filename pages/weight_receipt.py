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


def initialize_wr_session_state():
    if 'wr_weights' not in st.session_state:
        st.session_state.wr_weights = {}
    if 'wr_remarks' not in st.session_state:
        st.session_state.wr_remarks = {}
    if 'wr_total_weight' not in st.session_state:
        st.session_state.wr_total_weight = 0.0
    if 'current_jc_for_wr' not in st.session_state:
        st.session_state.current_jc_for_wr = None

def render_weight_receipt_form():
    st.markdown("<h3>Create Weight Receipt</h3>", unsafe_allow_html=True)

    services = create_services()
    initialize_wr_session_state() # Call the new initialization function

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
                st.markdown("<h6>Enter Actual Weights and Remarks:</h6>", unsafe_allow_html=True)

                # Reset state if a new job card is selected
                if st.session_state.get('current_jc_for_wr') != selected_jc_str:
                    st.session_state.wr_weights = {i: 0.0 for i in range(len(designs))}
                    st.session_state.wr_remarks = {i: "" for i in range(len(designs))}
                    st.session_state.current_jc_for_wr = selected_jc_str

                # --- Header for the list ---
                st.divider()
                c1, c2, c3, c4, c5 = st.columns([3, 1.5, 1.5, 1, 2.5])
                c1.markdown("**Design Info**")
                c2.markdown("**Expected**")
                c3.markdown("**Actual**")
                c4.markdown(" ") # For button
                c5.markdown("**Remark**")
                
                for i, design_item in enumerate(designs):
                    col1, col2, col3, col4, col5 = st.columns([3, 1.5, 1.5, 1, 2.5])
                    
                    with col1:
                        st.markdown(f"**W:** {design_item.get('width', '-')}mm, **L:** {design_item.get('length', '-')}mm")
                        st.caption(f"P/N: {design_item.get('party_job_no', 'N/A')}")
                    
                    with col2:
                        st.text_input("Expected Wt.", value=f"{float(design_item.get('weight', 0)):.2f} kg", disabled=True, key=f"exp_weight_{selected_jc_str}_{i}", label_visibility="collapsed")

                    with col3:
                        st.text_input("Actual Wt.", value=f"{st.session_state.wr_weights.get(i, 0.0):.2f} kg", disabled=True, key=f"act_weight_{selected_jc_str}_{i}", label_visibility="collapsed")
                    
                    with col4:
                        if st.button("Get", key=f"get_weight_{selected_jc_str}_{i}"):
                            with st.spinner("Fetching..."):
                                try:
                                    response_data = services.weight_receipt.get_current_weight_from_scale()
                                    if response_data.get("success") and response_data.get("status") == "stable":
                                        st.session_state.wr_weights[i] = response_data.get("weight", 0.0)
                                        st.toast(f"Weight received: {response_data.get('weight', 0.0):.2f} kg")
                                        st.rerun() # Rerun to update the 'Actual Wt.' field
                                    else:
                                        st.warning(f"Unstable: {response_data.get('status')}", icon="⚠️")
                                except Exception as e:
                                    st.error(f"API Error", icon="🚨")
                    
                    with col5:
                        st.session_state.wr_remarks[i] = st.text_input(
                            "Remark", 
                            value=st.session_state.wr_remarks.get(i, ""), 
                            key=f"remark_design_{selected_jc_str}_{i}",
                            label_visibility="collapsed"
                        )
                    st.divider()
                st.markdown("---")

                if st.button("Save Weight Receipt", key="save_wr_button_loose"):
                    weighed_designs = []
                    for i, design_data in enumerate(designs):
                        actual_weight = st.session_state.wr_weights.get(i, 0.0)
                        if actual_weight <= 0:
                            st.error(f"Please fetch a valid weight for all design items (Design {i+1}).")
                            st.stop()
                        
                        # Create a new dict for WeighedDesignDetail, ensuring all fields are present
                        weighed_design_data = design_data.copy()
                        weighed_design_data['actual_weight'] = actual_weight
                        weighed_design_data['remark'] = st.session_state.wr_remarks.get(i, "")
                        
                        weighed_designs.append(WeighedDesignDetail(**weighed_design_data))
                    
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

                # Reset total weight if a new job card is selected
                if st.session_state.get('current_jc_for_wr') != selected_jc_str:
                    st.session_state.wr_total_weight = 0.0
                    st.session_state.current_jc_for_wr = selected_jc_str
                
                col1, col2 = st.columns([0.7, 0.3])
                with col1:
                    st.text("Total Actual Weight (kg)")
                    st.metric(label=" ", value=f"{st.session_state.wr_total_weight:.2f}")
                with col2:
                    st.text(" ") # For spacing
                    if st.button("Get Total Weight", key=f"get_total_weight_{selected_jc_str}"):
                        with st.spinner("Fetching total weight..."):
                            try:
                                response_data = services.weight_receipt.get_current_weight_from_scale()
                                if response_data.get("success") and response_data.get("status") == "stable":
                                    st.session_state.wr_total_weight = response_data.get("weight", 0.0)
                                    st.toast(f"Total weight received: {response_data.get('weight', 0.0):.2f} kg")
                                else:
                                    st.warning(f"Could not get stable total weight. Status: {response_data.get('status', 'unknown')}. Please try again.")
                            except Exception as e:
                                st.error(f"Error fetching total weight: {e}")

                core_remark = st.text_input("Remark (Optional)", key="core_remark")

                if st.button("Save Weight Receipt", key="save_wr_button_core"):
                    total_weight = st.session_state.wr_total_weight
                    if total_weight <= 0:
                        st.error("Please fetch a valid total weight.")
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
