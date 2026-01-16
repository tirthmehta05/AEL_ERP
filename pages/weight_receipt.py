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
    if 'wr_core_remark' not in st.session_state:
        st.session_state.wr_core_remark = ""
    

def _render_designs_grid(designs, drafts, editable=True):
    """Helper function to render the designs grid."""
    df_data = []
    for i, design_item in enumerate(designs):
        actual_weight = st.session_state.wr_weights.get(i, drafts.get(i, {}).get('weight')) if editable else ""
        remark = st.session_state.wr_remarks.get(i, drafts.get(i, {}).get('remark', '')) if editable else ""
        df_data.append({
            "Select": st.session_state.get('last_selected_index') == i if editable else False,
            "Width": design_item.get('width', 0),
            "Length": design_item.get('length', 0),
            "Expected Wt.": design_item.get('weight', 0.0),
            "Actual Wt.": actual_weight,
            "Remark": remark,
            "original_index": i
        })
    
    ui_df = pd.DataFrame(df_data)

    is_a_row_selected = st.session_state.get('last_selected_index') is not None

    column_config = {
        "Select": st.column_config.CheckboxColumn(
            "Select", 
            help="Select one design to weigh", 
            default=False, 
            disabled=is_a_row_selected if editable else True
        ),
        "Width": st.column_config.NumberColumn(disabled=True),
        "Length": st.column_config.NumberColumn(disabled=True),
        "Expected Wt.": st.column_config.NumberColumn(format="%.2f", disabled=True),
        "Actual Wt.": st.column_config.NumberColumn(format="%.2f", disabled=True),
        "Remark": st.column_config.TextColumn(disabled=not editable),
        "original_index": None
    }

    st.markdown("<h6>Design Details:</h6>", unsafe_allow_html=True)
    edited_df = st.data_editor(
        ui_df,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        key="designs_data_editor"
    )
    return edited_df

def _sync_editor_changes_to_state(edited_df: pd.DataFrame):
    """
    Updates session state with the latest values from the data editor.
    This ensures that unsaved edits are not lost during reruns caused by other widgets.
    """
    for _, row in edited_df.iterrows():
        idx = row['original_index']
        st.session_state.wr_weights[idx] = row['Actual Wt.']
        st.session_state.wr_remarks[idx] = row['Remark']

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
            
            # --- Load Drafts and Initialize State (runs only on JC change) ---
            if st.session_state.get('current_jc_for_wr') != selected_jc_str:
                drafts, draft_sets, draft_total_weight, draft_core_remark = services.weight_receipt.get_weight_receipt_drafts(selected_jc_str)
                st.session_state.wr_draft_data = drafts or {}
                
                # When JC changes, reset the session state for weights and remarks
                st.session_state.wr_weights = {}
                st.session_state.wr_remarks = {}

                if draft_total_weight is not None:
                    st.session_state.wr_total_weight = draft_total_weight
                
                st.session_state.wr_core_remark = draft_core_remark or ""

                # Pre-fill sets for receipt from draft
                if draft_sets is not None:
                    st.session_state.wr_sets_for_receipt = draft_sets

                st.session_state.original_draft_sets = draft_sets
                st.session_state.current_jc_for_wr = selected_jc_str
                st.session_state.last_selected_index = None
                
                if drafts or draft_total_weight is not None:
                    st.toast("Loaded previously saved draft.", icon="📝")

            st.markdown("---")
            st.markdown(f"<h5>Details for {selected_jc['job_card_number']}</h5>", unsafe_allow_html=True)
            
            # --- Get Order Type ---
            order_type = services.weight_receipt.get_order_type_for_job_card(selected_jc_str)
            
            # Display order type badge
            badge_color = "🟢" if order_type == "CORE_BUILDING" else ("🟡" if order_type == "LOOSE_STRIPS" else "🔵")
            st.markdown(f"**Order Type:** {badge_color} {order_type.replace('_', ' ').title()}")
            
            # --- Set Selection UI (varies by order type) ---
            if order_type == "CORE_BUILDING":
                # Original set-based logic for core building orders
                total_sets_in_jc = int(selected_jc.get('number_of_cores', 0))
                completed_sets = services.weight_receipt.get_receipted_sets_for_job_card(selected_jc_str)
                remaining_sets = total_sets_in_jc - completed_sets

                set_col1, set_col2, set_col3 = st.columns(3)
                set_col1.metric("Total Sets in Job Card", f"{total_sets_in_jc}")
                set_col2.metric("Completed Sets", f"{completed_sets}")
                set_col3.metric("Remaining Sets", f"{remaining_sets}")

                if remaining_sets <= 0:
                    st.warning("All sets for this Job Card have already been receipted.", icon="⚠️")
                    st.stop()

                # --- Number of sets for this receipt ---
                sets_for_this_receipt_val = st.session_state.get('wr_sets_for_receipt', min(1, remaining_sets))
                if sets_for_this_receipt_val > remaining_sets:
                    st.warning(f"Draft has {sets_for_this_receipt_val} sets, but only {remaining_sets} remain. Please adjust or clear draft.", icon="⚠️")
                    if st.button("Reset Sets and Clear Draft"):
                        st.session_state.wr_sets_for_receipt = remaining_sets
                        st.session_state.wr_weights = {}
                        st.session_state.wr_remarks = {}
                        st.session_state.wr_total_weight = 0.0
                        st.session_state.wr_draft_data = {}
                        st.session_state.last_selected_index = None
                        services.weight_receipt.clear_weight_receipt_drafts(selected_jc_str)
                        st.toast("Sets reset and draft cleared.", icon="🗑️")
                        st.rerun()
                    sets_for_this_receipt_val = remaining_sets

                sets_for_this_receipt = st.number_input(
                    "Number of Sets for this Receipt",
                    min_value=1,
                    max_value=remaining_sets,
                    value=sets_for_this_receipt_val,
                    step=1,
                    key='wr_sets_for_receipt_input' 
                )

                if 'wr_sets_for_receipt' in st.session_state and st.session_state.wr_sets_for_receipt != sets_for_this_receipt:
                    st.session_state.wr_weights = {}
                    st.session_state.wr_remarks = {}
                    st.session_state.wr_total_weight = 0.0
                    st.session_state.wr_draft_data = {}
                    st.session_state.last_selected_index = None
                    services.weight_receipt.clear_weight_receipt_drafts(selected_jc_str)
                    st.toast("Number of sets changed. Previous draft cleared.", icon="🗑️")

                st.session_state.wr_sets_for_receipt = sets_for_this_receipt
            
            else:
                # Weight-based logic for loose strips and EI ready orders
                # Calculate total expected weight from designs
                original_designs = json.loads(selected_jc.get('designs_json', '[]'))
                total_expected_weight = sum(d.get('weight', 0) for d in original_designs)
                
                # Get cumulative weight already receipted
                cumulative_weight = services.weight_receipt.get_cumulative_weight_for_job_card(selected_jc_str)
                remaining_weight = total_expected_weight - cumulative_weight
                
                weight_col1, weight_col2, weight_col3 = st.columns(3)
                weight_col1.metric("Total Expected Weight", f"{total_expected_weight:.2f} kg")
                weight_col2.metric("Cumulative Receipted Weight", f"{cumulative_weight:.2f} kg")
                weight_col3.metric("Remaining Weight", f"{remaining_weight:.2f} kg")
                
                if remaining_weight <= 0:
                    st.success("✅ All weight for this Job Card has been receipted.", icon="✅")
                    st.stop()
                
                # Still track sets for record-keeping, but not enforced
                total_sets_in_jc = int(selected_jc.get('number_of_cores', 1))  # Default to 1 if 0
                completed_sets = services.weight_receipt.get_receipted_sets_for_job_card(selected_jc_str)
                
                sets_for_this_receipt_val = st.session_state.get('wr_sets_for_receipt', 1)
                sets_for_this_receipt = st.number_input(
                    "Number of Sets for this Receipt (for tracking only)",
                    min_value=1,
                    value=sets_for_this_receipt_val,
                    step=1,
                    key='wr_sets_for_receipt_input',
                    help="Sets are tracked but not enforced for partial dispatch orders"
                )
                st.session_state.wr_sets_for_receipt = sets_for_this_receipt

            original_designs = json.loads(selected_jc.get('designs_json', '[]'))
            designs = [] 
            total_sets_in_jc = int(selected_jc.get('number_of_cores', 0))

            if original_designs and total_sets_in_jc > 0 and sets_for_this_receipt > 0:
                scaling_factor = sets_for_this_receipt / total_sets_in_jc
                for design_item in original_designs:
                    scaled_design_item = design_item.copy()
                    if scaled_design_item.get('weight') is not None:
                        scaled_design_item['weight'] *= scaling_factor
                    if scaled_design_item.get('mm_stack') is not None:
                        scaled_design_item['mm_stack'] *= scaling_factor
                    if scaled_design_item.get('pcs') is not None:
                        scaled_design_item['pcs'] = int(scaled_design_item['pcs'] * scaling_factor)
                    if scaled_design_item.get('sets') is not None:
                        scaled_design_item['sets'] = int(scaled_design_item['sets'] * scaling_factor)
                    designs.append(scaled_design_item)
            else:
                designs = original_designs
            
            wr_col1, wr_col2 = st.columns(2)
            with wr_col1:
                if 'wr_number_input' not in st.session_state:
                    st.session_state.wr_number_input = services.weight_receipt.generate_weight_receipt_number()
                wr_number = st.text_input("Weight Receipt Number", value=st.session_state.wr_number_input)
            with wr_col2:
                receipt_date = st.date_input("Receipt Date", datetime.now())

            st.markdown("---")

            st.markdown("<h6>Design Details (Scaled for this Receipt)</h6>", unsafe_allow_html=True)
            
            # Auto-determine weight entry type from order type
            # Core Building orders use "Building Core" mode, others use "Loose Strips" mode
            weight_entry_type = "Building Core" if order_type == "CORE_BUILDING" else "Loose Strips"
            
            deduction = st.number_input("Deduction (kg)", value=0.0, step=0.1, key="deduction_input")
            
            drafts = st.session_state.get('wr_draft_data', {})

            if weight_entry_type == "Loose Strips":
                edited_df = _render_designs_grid(designs, drafts, editable=True)
                _sync_editor_changes_to_state(edited_df)
                
                selected_rows = edited_df[edited_df["Select"]]
                if len(selected_rows) > 1:
                    first_selected_index = selected_rows.index[0]
                    st.session_state.last_selected_index = first_selected_index
                elif len(selected_rows) == 1:
                    selected_index = selected_rows.index[0]
                    if st.session_state.get('last_selected_index') != selected_index:
                        st.session_state.last_selected_index = selected_index
                else:
                    st.session_state.last_selected_index = None

                st.markdown("---")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    get_weight_clicked = st.button("Get Weight", key="get_weight_for_selected_design")
                with col2:
                    add_weight_clicked = st.button("Add Weight", key="add_weight_for_selected_design")
                with col3:
                    save_draft_clicked = st.button("Save Draft", key="save_draft_for_selected_design")
                with col4:
                    if st.session_state.get('last_selected_index') is not None:
                        if st.button("Clear Selection", key="clear_selection"):
                            st.session_state.last_selected_index = None
                            st.rerun()

                if get_weight_clicked or add_weight_clicked:
                    idx_to_weigh = st.session_state.get('last_selected_index')
                    if idx_to_weigh is not None:
                        with st.spinner("Fetching weight..."):
                            response_data = services.weight_receipt.get_current_weight_from_scale()
                            if response_data.get("success") and response_data.get("status") == "stable":
                                weight = response_data.get("weight", 0.0)
                                original_index = edited_df.loc[idx_to_weigh, "original_index"]
                                
                                if add_weight_clicked:
                                    st.session_state.wr_weights[original_index] = st.session_state.wr_weights.get(original_index, 0.0) + weight
                                    st.toast(f"Added {weight:.2f} kg. New total: {st.session_state.wr_weights.get(original_index, 0.0):.2f} kg. Click 'Save Draft' to persist.", icon="⚖️")
                                else: # Get Weight
                                    st.session_state.wr_weights[original_index] = weight
                                    st.toast(f"Weight received: {weight:.2f} kg. Click 'Save Draft' to persist.", icon="⚖️")
                                
                                st.rerun()
                            else:
                                st.warning(f"Unstable: {response_data.get('status')}", icon="⚠️")
                    else:
                        st.warning("Please select a design to weigh by checking its box.")

                if save_draft_clicked:
                    idx_to_save = st.session_state.get('last_selected_index')
                    if idx_to_save is not None:
                        original_index = edited_df.loc[idx_to_save, "original_index"]
                        weight_to_save = st.session_state.wr_weights.get(original_index, 0.0)
                        remark_to_save = st.session_state.wr_remarks.get(original_index, "")
                        
                        with st.spinner("Saving draft..."):
                            sets_for_this_receipt = st.session_state.get('wr_sets_for_receipt', 0)
                            services.weight_receipt.save_weight_receipt_draft(
                                job_card=selected_jc_str,
                                design_index=original_index,
                                weight=weight_to_save,
                                remark=remark_to_save,
                                sets_for_this_receipt=sets_for_this_receipt
                            )
                            st.toast("Draft saved!", icon="📝")
                            st.session_state.last_selected_index = None
                            st.rerun()
                    else:
                        st.warning("Please select a design to save.", icon="⚠️")

                st.markdown("---")

                if st.button("Save Weight Receipt", key="save_wr_button_loose"):
                    weighed_designs = []
                    actual_total_weight = 0.0
                    for i, row in edited_df.iterrows():
                        actual_weight = row["Actual Wt."]
                        if actual_weight <= 0:
                            st.error(f"Please fetch a valid weight for all design items. Error at row {i+1}.")
                            st.stop()
                        
                        actual_total_weight += actual_weight
                        original_design_data = designs[row['original_index']]
                        weighed_design_data = original_design_data.copy()
                        weighed_design_data['actual_weight'] = actual_weight
                        weighed_design_data['remark'] = row["Remark"]
                        weighed_designs.append(WeighedDesignDetail(**weighed_design_data))

                    # Validate cumulative weight for partial dispatch orders
                    if order_type in ["LOOSE_STRIPS", "EI_READY"]:
                        original_designs = json.loads(selected_jc.get('designs_json', '[]'))
                        total_expected_weight = sum(d.get('weight', 0) for d in original_designs)
                        cumulative_weight = services.weight_receipt.get_cumulative_weight_for_job_card(selected_jc_str)
                        new_cumulative_weight = cumulative_weight + (actual_total_weight - deduction)
                        
                        if new_cumulative_weight > total_expected_weight:
                            st.warning(
                                f"⚠️ Cumulative weight ({new_cumulative_weight:.2f} kg) exceeds total job card weight ({total_expected_weight:.2f} kg). "
                                f"Excess: {new_cumulative_weight - total_expected_weight:.2f} kg",
                                icon="⚠️"
                            )

                    request = WeightReceiptRequest(
                        weight_receipt_number=wr_number,
                        receipt_date=receipt_date,
                        job_card_number=selected_jc_str,
                        party_name=selected_party,
                        po_no=selected_jc.get('po_no', 'N/A'),
                        material=selected_jc.get('material', 'N/A'),
                        sets=st.session_state.get('wr_sets_for_receipt', 0),
                        designs=weighed_designs,
                        weight_entry_type="Loose Strips",
                        total_weight=actual_total_weight,
                        deduction=deduction,
                        order_type=order_type
                    )

                    with st.spinner("Saving Weight Receipt..."):
                        success = services.weight_receipt.save_weight_receipt(request)
                        if success:
                            st.success(f"Weight Receipt {wr_number} saved successfully!")
                            user_id = st.session_state.get('user_info', {}).get('username', 'SYSTEM')
                            services.weight_receipt.save_to_finished_goods(
                                user_id=user_id,
                                job_card=selected_jc['job_card_number'],
                                fg_qty=actual_total_weight - deduction,
                                weight_receipt_number=wr_number
                            )
                            services.weight_receipt.clear_weight_receipt_drafts(selected_jc['job_card_number'])
                            st.session_state.wr_weights = {}
                            st.session_state.wr_remarks = {}
                            st.session_state.wr_total_weight = 0.0
                            st.session_state.wr_draft_data = {}
                            st.session_state.last_selected_index = None
                            if 'wr_number_input' in st.session_state:
                                del st.session_state['wr_number_input']
                            
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Failed to save Weight Receipt.")
            
            elif weight_entry_type == "Building Core":
                _render_designs_grid(designs, drafts, editable=False)
                st.markdown("<h6>Enter Total Actual Weight & Remark:</h6>", unsafe_allow_html=True)
                
                # --- UI for Weight and Remark Inputs ---
                core_input_col1, core_input_col2 = st.columns(2)
                with core_input_col1:
                    st.text_input(
                        "Total Actual Weight (kg)", 
                        value=f"{st.session_state.wr_total_weight:.2f}",
                        key="total_weight_display_core",
                        disabled=True
                    )
                with core_input_col2:
                    st.text_input("Core Remark", key="wr_core_remark", value=st.session_state.get('wr_core_remark', ''))

                # --- UI for Buttons ---
                core_button_col1, core_button_col2, core_button_col3 = st.columns(3)
                with core_button_col1:
                    get_weight_clicked_core = st.button("Get Weight", key="get_total_weight_core", use_container_width=True)
                with core_button_col2:
                    add_weight_clicked_core = st.button("Add Weight", key="add_total_weight_core", use_container_width=True)
                with core_button_col3:
                    save_draft_clicked_core = st.button("Save Draft", key="save_total_weight_core", use_container_width=True)


                if get_weight_clicked_core or add_weight_clicked_core:
                    with st.spinner("Fetching weight..."):
                        response_data = services.weight_receipt.get_current_weight_from_scale()
                        if response_data.get("success") and response_data.get("status") == "stable":
                            weight = response_data.get("weight", 0.0)
                            
                            if add_weight_clicked_core:
                                st.session_state.wr_total_weight += weight
                                st.toast(f"Added {weight:.2f} kg. New total: {st.session_state.wr_total_weight:.2f} kg. Click 'Save Draft' to persist.", icon="⚖️")
                            else: # Get Weight
                                st.session_state.wr_total_weight = weight
                                st.toast(f"Weight received: {weight:.2f} kg. Click 'Save Draft' to persist.", icon="⚖️")
                            
                            st.rerun()
                        else:
                            st.warning(f"Weight is unstable: {response_data.get('status')}", icon="⚠️")

                if save_draft_clicked_core:
                    with st.spinner("Saving draft..."):
                        services.weight_receipt.save_weight_receipt_draft(
                            job_card=selected_jc_str,
                            design_index=-1,
                            weight=st.session_state.wr_total_weight,
                            remark=st.session_state.get('wr_core_remark', ''),
                            sets_for_this_receipt=st.session_state.get('wr_sets_for_receipt', 0)
                        )
                        st.toast("Draft saved!", icon="📝")
                        st.rerun()
                st.markdown("---")
                if st.button("Save Weight Receipt", key="save_wr_button_core"):
                    actual_total_weight = st.session_state.get('wr_total_weight', 0.0)

                    if actual_total_weight <= 0:
                        st.error("Please fetch a valid total weight before saving.")
                        st.stop()

                    weighed_designs = []
                    for design_item in designs:
                        weighed_design_data = design_item.copy()
                        weighed_design_data['actual_weight'] = 0 
                        weighed_design_data['remark'] = st.session_state.get('wr_core_remark', '')
                        weighed_designs.append(WeighedDesignDetail(**weighed_design_data))

                    # Validate cumulative weight for partial dispatch orders
                    if order_type in ["LOOSE_STRIPS", "EI_READY"]:
                        original_designs = json.loads(selected_jc.get('designs_json', '[]'))
                        total_expected_weight = sum(d.get('weight', 0) for d in original_designs)
                        cumulative_weight = services.weight_receipt.get_cumulative_weight_for_job_card(selected_jc_str)
                        new_cumulative_weight = cumulative_weight + (actual_total_weight - deduction)
                        
                        if new_cumulative_weight > total_expected_weight:
                            st.warning(
                                f"⚠️ Cumulative weight ({new_cumulative_weight:.2f} kg) exceeds total job card weight ({total_expected_weight:.2f} kg). "
                                f"Excess: {new_cumulative_weight - total_expected_weight:.2f} kg",
                                icon="⚠️"
                            )

                    request = WeightReceiptRequest(
                        weight_receipt_number=wr_number,
                        receipt_date=receipt_date,
                        job_card_number=selected_jc_str,
                        party_name=selected_party,
                        po_no=selected_jc.get('po_no', 'N/A'),
                        material=selected_jc.get('material', 'N/A'),
                        sets=st.session_state.get('wr_sets_for_receipt', 0),
                        designs=weighed_designs,
                        weight_entry_type="Building Core",
                        total_weight=actual_total_weight,
                        deduction=deduction,
                        order_type=order_type
                    )
                    
                    with st.spinner("Saving Weight Receipt..."):
                        success = services.weight_receipt.save_weight_receipt(request)
                        if success:
                            st.success(f"Weight Receipt {wr_number} saved successfully!")
                            user_id = st.session_state.get('user_info', {}).get('username', 'SYSTEM')
                            services.weight_receipt.save_to_finished_goods(
                                user_id=user_id,
                                job_card=selected_jc['job_card_number'],
                                fg_qty=actual_total_weight - deduction,
                                weight_receipt_number=wr_number
                            )
                            services.weight_receipt.clear_weight_receipt_drafts(selected_jc['job_card_number'])
                            st.session_state.wr_weights = {}
                            st.session_state.wr_remarks = {}
                            st.session_state.wr_total_weight = 0.0
                            st.session_state.wr_draft_data = {}
                            st.session_state.last_selected_index = None
                            if 'wr_number_input' in st.session_state:
                                del st.session_state['wr_number_input']
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Failed to save Weight Receipt.")
