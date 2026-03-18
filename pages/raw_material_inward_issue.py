import streamlit as st
from datetime import datetime
from pydantic import ValidationError
import pandas as pd
import time

from src.data_entry.service.rm_inward_service import RMInwardService
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService
from src.data_entry.models.rm_inward_models import RMInwardIssueRequest
from theme.components import render_main_header, end_card


@st.cache_resource(ttl=600)
def load_dropdowns(_service: RMInwardService):
    return _service.get_dropdown_data()

@st.dialog("Confirm Coil Entries", width="large")
def _show_single_entry_confirmation_dialog(entries: list, data_service: RMInwardService):
    """Shows a modal to confirm single coil entries before saving."""
    st.markdown("Please review the coil entries below before submitting.")
    st.markdown("---")
    
    df = pd.DataFrame(entries)
    # Reorder/rename columns for better display
    display_cols = ['coil_number', 'rm_type', 'width', 'thk', 'coil_weight', 'coil_supplier', 'coil_location']
    display_df = df[[c for c in display_cols if c in df.columns]].copy()
    display_df.columns = ['Coil Number', 'RM Type', 'Width (mm)', 'Thk (mm)', 'Weight (kg)', 'Supplier', 'Location']
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Confirm Submit", type="primary", use_container_width=True):
            st.session_state.rm_inward_submit_confirmed = True
            st.rerun()
    with col2:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.rm_inward_submit_confirmed = False
            st.session_state.rm_inward_submit_lock = 0
            st.rerun()

@st.dialog("Confirm Bulk Upload", width="large")
def _show_bulk_upload_confirmation_dialog(valid_requests: list):
    """Shows a modal to confirm bulk upload entries before saving."""
    st.markdown(f"**{len(valid_requests)}** valid records are ready to be submitted.")
    st.markdown("Please review the preview below before confirming.")
    st.markdown("---")
    
    # Create a DataFrame from the Pydantic models for preview
    preview_data = [req.model_dump() for req in valid_requests]
    df = pd.DataFrame(preview_data)

    # Reorder/rename all columns for display
    col_map = {
        'coil_number': 'Coil Number',
        'rm_receipt_date': 'Receipt Date',
        'rm_type': 'RM Type',
        'grade': 'Grade',
        'thk': 'Thk (mm)',
        'width': 'Width (mm)',
        'coating': 'Coating',
        'coil_weight': 'Weight (kg)',
        'coil_supplier': 'Supplier',
        'slit_ready': 'Slit/Ready',
        'rate': 'Rate',
        'po_number': 'PO Number',
        'coil_location': 'Location',
    }
    display_df = df[[c for c in col_map if c in df.columns]].rename(columns=col_map)
    
    # Show at most 10 records for preview
    st.dataframe(display_df.head(10), use_container_width=True, hide_index=True)
    if len(valid_requests) > 10:
        st.info(f"... and {len(valid_requests) - 10} more records.")
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Confirm Upload", type="primary", use_container_width=True):
            st.session_state.rm_inward_bulk_submit_confirmed = True
            st.rerun()
    with col2:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.rm_inward_bulk_submit_confirmed = False
            st.session_state.rm_inward_bulk_lock = 0
            st.rerun()


def render_raw_material_inward_issue_form() -> None:
    """Renders the Raw Material Inward Issue page with single and bulk entry options."""
    data_service = RMInwardService()
    slitting_service = SlittingPlanService()

    if 'rm_inward_entries' not in st.session_state:
        st.session_state.rm_inward_entries = []

    # --- Recovery: interrupted save ---
    # If the save HTTP call completed server-side but Streamlit interrupted the script
    # before post-save cleanup (clear form, rerun), recover here on the next render.
    if st.session_state.pop('rm_inward_save_completed', False):
        st.session_state.rm_inward_entries = []
        st.session_state.pop('coil_number_input', None)
        st.session_state.rm_inward_submit_lock = 0
        load_dropdowns.clear()
        st.toast("Entries submitted successfully!")
        st.rerun()

    if st.session_state.get("form_submitted_successfully", False):
        # Clear single entry form state
        keys_to_clear = ['receipt_date', 'rm_type', 'coil_number', 'coil_weight', 'po_number', 
                         'grade', 'thk', 'width', 'coating', 'supplier', 'coil_location', 'slit_ready', 'rate']
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.form_submitted_successfully = False

    @st.cache_data(ttl=3600)
    def get_cached_mapping_templates():
        return data_service.get_mapping_templates()
    
    @st.cache_data
    def get_printable_plans():
        return slitting_service.get_printable_plans()

    dropdowns = load_dropdowns(data_service)

    with st.expander("Coil Entry", expanded=True):
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='card-header'>Add Raw Material Coil</div>", unsafe_allow_html=True)

        st.checkbox("Enter Coil Number Manually", key="use_custom_coil_number")
        
        col1, col2 = st.columns(2)
        with col1:
            st.date_input("RM Receipt Date", key="receipt_date")
            st.selectbox("RM Type", options=dropdowns.rm_types, index=None, placeholder="Select or type a RM Type", key="rm_type", accept_new_options=True)
            
            if not st.session_state.get("use_custom_coil_number", False):
                # Automatically generate coil number if not manually entered
                # Only generate if coil_number_input is not already set or is empty
                if 'coil_number_input' not in st.session_state or not st.session_state.coil_number_input:
                    st.session_state.coil_number_input = data_service.generate_coil_number()
            
            if st.session_state.get("use_custom_coil_number", False):
                st.text_input("Coil Number", key="coil_number_input")
            else:
                st.text_input("Coil Number (Auto-generated)", value=st.session_state.get("coil_number_input", ""), disabled=True)

            st.number_input("Coil Weight (kg)", min_value=0.01, step=0.01, format="%.2f", key="coil_weight")
            st.selectbox("PO Number (Optional)", options=[], index=None, placeholder="Type a PO Number", accept_new_options=True, key="po_number")

        with col2:
            st.selectbox("Grade", options=dropdowns.grades, index=None, placeholder="Select or type a Grade", key="grade", accept_new_options=True)
            st.selectbox("Thk (mm)", options=dropdowns.thks, index=None, placeholder="Select or type a Thk", key="thk", accept_new_options=True)
            st.selectbox("Width (mm)", options=dropdowns.widths, index=None, placeholder="Select or type a Width", key="width", accept_new_options=True)
            st.selectbox("Coating", options=dropdowns.coatings, index=None, placeholder="Select or type a Coating", key="coating", accept_new_options=True)
            st.selectbox("Coil Supplier", options=dropdowns.suppliers, index=None, placeholder="Select or type a Supplier", key="supplier", accept_new_options=True)
            st.selectbox("Slit / Ready", options=["Ready", "Slit"], index=0, key="slit_ready")
            st.number_input("Rate (per Kg)", min_value=0.0, step=0.01, format="%.2f", key="rate")

        st.selectbox("Coil Location", options=["AEL Pune", "TAIIN"], index=0, key="coil_location")

        if st.button("Add Coil to List"):
            validation_state = dict(st.session_state)
            validation_state['coil_number'] = st.session_state.get("coil_number_input", "")
            errors = data_service.validate_single_entry(validation_state)

            if errors:
                st.warning("Please correct the following errors:\n\n" + "\n".join([f"- {e}" for e in errors]))
            else:
                entry = {
                    "rm_receipt_date": st.session_state.receipt_date,
                    "rm_type": st.session_state.rm_type,
                    "coil_number": st.session_state.coil_number_input,
                    "grade": st.session_state.grade,
                    "thk": float(st.session_state.thk),
                    "width": float(st.session_state.width),
                    "coating": st.session_state.coating,
                    "coil_weight": st.session_state.coil_weight,
                    "po_number": st.session_state.po_number or None,
                    "coil_supplier": st.session_state.supplier,
                    "slit_ready": st.session_state.slit_ready,
                    "rate": st.session_state.rate,
                    "coil_location": st.session_state.coil_location,
                }
                st.session_state.rm_inward_entries.append(entry)
                st.success("Coil added to the list.")

        st.markdown("</div>", unsafe_allow_html=True)

        # --- Validation against Slitting Plan ---
        st.markdown("---")
        st.markdown("<h5>Validate against Slitting Plan (Optional)</h5>", unsafe_allow_html=True)
        st.checkbox("Enable Validation", key="coil_entry_validate_against_plan", value=False)

        if st.session_state.get("coil_entry_validate_against_plan"):
            printable_plans = get_printable_plans()
            st.multiselect(
                "Select Slitting Plan(s) to Validate Against", 
                options=printable_plans, 
                key="coil_entry_selected_plans"
            )

            if st.button("Validate Coils against Plan"):
                if not st.session_state.rm_inward_entries:
                    st.warning("Please add at least one coil to the list before validating.")
                elif not st.session_state.get("coil_entry_selected_plans"):
                    st.error("Please select at least one slitting plan to validate against.")
                else:
                    with st.spinner("Validating..."):
                        entries_df = pd.DataFrame(st.session_state.rm_inward_entries)
                        
                        mapping = {'width': 'width', 'coil_weight': 'coil_weight'}

                        results = slitting_service.validate_packing_list(
                            packing_list_df=entries_df,
                            plan_ids=st.session_state.coil_entry_selected_plans,
                            mapping=mapping
                        )
                        st.session_state.coil_entry_validation_results = results
                        st.session_state.coil_entry_validation_successful = results.get("validation_passed", False)

        if "coil_entry_validation_results" in st.session_state:
            st.markdown("<h6>Validation Results</h6>", unsafe_allow_html=True)
            results = st.session_state.coil_entry_validation_results
            st.dataframe(results.get("comparison_df"))
            if results.get("validation_passed"):
                st.success("Validation successful! You can now submit the entries.")
            else:
                st.error(f"Validation failed: {results.get('message', 'Please check the discrepancies.')}")

        # --- Display table of entries ---
        if st.session_state.rm_inward_entries:
            st.markdown("---")
            st.markdown("<h5>Coils to be Submitted</h5>", unsafe_allow_html=True)
            
            df = pd.DataFrame(st.session_state.rm_inward_entries)
            df_to_display = df.copy()
            df_to_display['Select'] = False
            
            edited_df = st.data_editor(
                df_to_display, 
                column_order=["Select"] + [col for col in df.columns if col != 'user_id'],
                disabled=[col for col in df.columns if col != 'Select'],
                hide_index=True,
                key="inward_entries_editor"
            )

            if st.button("Remove Selected"):
                selected_indices = edited_df[edited_df['Select']].index
                if list(selected_indices):
                    st.session_state.rm_inward_entries = [
                        entry for i, entry in enumerate(st.session_state.rm_inward_entries) 
                        if i not in selected_indices
                    ]
                    st.rerun()

        # --- Final submission ---
        if st.session_state.rm_inward_entries:
            st.markdown("---")
            process_disabled = (
                st.session_state.get("coil_entry_validate_against_plan", False) and 
                not st.session_state.get("coil_entry_validation_successful", False)
            )
            
            # If the user has explicitly confirmed in the dialog
            if st.session_state.pop("rm_inward_submit_confirmed", False):
                with st.spinner("Submitting entries..."):
                    try:
                        requests = [RMInwardIssueRequest(**entry) for entry in st.session_state.rm_inward_entries]
                        st.session_state.rm_inward_save_completed = True
                        success = data_service.create_rm_inward_issues_bulk(requests)
                        if success:
                            st.success(f"Successfully submitted {len(requests)} entries!")
                            st.session_state.rm_inward_entries = []
                            st.session_state.pop('coil_number_input', None)
                            st.session_state.pop('rm_inward_save_completed', None)
                            load_dropdowns.clear()
                            st.session_state.rm_inward_submit_lock = 0
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.session_state.pop('rm_inward_save_completed', None)
                            st.session_state.rm_inward_submit_lock = 0
                            st.error("Failed to submit entries. Please check application logs.")
                    except Exception as e:
                        st.session_state.pop('rm_inward_save_completed', None)
                        st.session_state.rm_inward_submit_lock = 0
                        st.error(f"An error occurred during submission: {e}")

            elif st.button("Submit All Entries", disabled=process_disabled):
                current_time = time.time()
                if current_time - st.session_state.get('rm_inward_submit_lock', 0) < 30:
                    st.warning("Save already in progress. Please wait...")
                    st.stop()
                st.session_state.rm_inward_submit_lock = current_time
                
                # Open the confirmation dialog
                _show_single_entry_confirmation_dialog(st.session_state.rm_inward_entries, data_service)

    with st.expander("Bulk Upload from Excel", expanded=(st.session_state.get('bulk_upload_file') is not None)):
        st.info("This feature allows you to upload multiple coil entries at once using an Excel file.")
        uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx", "xls"], key="bulk_upload_file")

        if uploaded_file:
            try:
                st.session_state.uploaded_df = pd.read_excel(uploaded_file)
                keys_to_clear_on_new_upload = ['grouped_df', 'validation_results', 'validation_successful']
                for key in keys_to_clear_on_new_upload:
                    if key in st.session_state:
                        del st.session_state[key]
            except Exception as e:
                st.error(f"Error reading the Excel file: {e}")
                if "uploaded_df" in st.session_state:
                    del st.session_state.uploaded_df
        
        if "uploaded_df" in st.session_state and st.session_state.uploaded_df is not None:
            df = st.session_state.uploaded_df
            excel_cols = df.columns.tolist()

            st.markdown("##### Options")
            st.checkbox("Validate against Slitting Plan", key="validate_against_plan", value=False)
            
            if st.session_state.get("validate_against_plan"):
                printable_plans = get_printable_plans()
                st.multiselect("Select Slitting Plan(s) to Validate Against", options=printable_plans, key="selected_plans_for_validation")

            col1, col2 = st.columns(2)
            group_by_is_active = st.session_state.get("group_by_column") is not None
            with col1:
                st.checkbox("Auto-generate Coil Numbers", value=st.session_state.get("bulk_auto_generate_coil", False) or group_by_is_active, key="bulk_auto_generate_coil", disabled=group_by_is_active)
            with col2:
                st.selectbox("Group By Column (Optional)", options=[None] + excel_cols, key="group_by_column")

            st.dataframe(df.head())

            st.markdown("---")
            templates = get_cached_mapping_templates()
            template_names = ["None"] + list(templates.keys())
            col1, _, col3 = st.columns([2,2,1])
            with col1:
                selected_template = st.selectbox("Load Saved Template", options=template_names)
            with col3:
                if st.button("Load"):
                    if selected_template != "None":
                        loaded_mapping = templates[selected_template]
                        for field_key, mapped_col in loaded_mapping.items():
                            st.session_state[f"mapping_{field_key}"] = mapped_col
                        st.success(f"Template '{selected_template}' loaded!")
                        st.rerun()

            st.markdown("#### Map Excel Columns to Application Fields")
            app_fields = {
                "rm_receipt_date": "RM Receipt Date", "rm_type": "RM Type", "coil_number": "Coil Number",
                "grade": "Grade", "thk": "Thk (mm)", "width": "Width (mm)", "coating": "Coating",
                "coil_weight": "Coil Weight (kg)", "coil_supplier": "Coil Supplier",
                "slit_ready": "Slit / Ready", "rate": "Rate",
                "po_number": "PO Number (Optional)", "coil_location": "Coil Location"
            }
            if 'column_mapping' not in st.session_state:
                st.session_state.column_mapping = {}
            st.markdown("<div class='card p-3'>", unsafe_allow_html=True)
            mapping_cols = st.columns(4)
            auto_generate_is_active = st.session_state.get('bulk_auto_generate_coil', False)
            for i, (field_key, field_label) in enumerate(app_fields.items()):
                if field_key == 'coil_number' and auto_generate_is_active:
                    st.session_state.column_mapping['coil_number'] = 'auto-generate'
                    continue
                with mapping_cols[i % 4]:
                    selected_col = st.selectbox(field_label, options=[None] + excel_cols, key=f"mapping_{field_key}")
                    st.session_state.column_mapping[field_key] = selected_col
            st.markdown("</div>", unsafe_allow_html=True)

            group_by_col = st.session_state.get("group_by_column")
            if group_by_col:
                if st.button("Preview Grouped Data"):
                    with st.spinner("Grouping data..."):
                        mapping = st.session_state.get("column_mapping", {})
                        st.session_state.grouped_df = data_service.group_df_by_key(df, group_by_col, mapping)
            if "grouped_df" in st.session_state and st.session_state.grouped_df is not None:
                st.markdown("#### Preview of Grouped Data")
                st.dataframe(st.session_state.grouped_df)
                if st.button("Clear Grouping"):
                    del st.session_state.grouped_df
                    st.rerun()

            st.markdown("---")
            col1, col2 = st.columns([3,1])
            with col1:
                new_template_name = st.text_input("Save Current Mapping as Template (enter name):")
            with col2:
                if st.button("Save Template"):
                    if new_template_name and st.session_state.get("column_mapping"):
                        data_service.save_mapping_template(new_template_name, st.session_state.column_mapping)
                        get_cached_mapping_templates.clear()
                        st.success(f"Template '{new_template_name}' saved!")
                    else:
                        st.warning("Please enter a template name and map at least one field.")

            st.markdown("---")
            if st.session_state.get("validate_against_plan"):
                if st.button("Validate Packing List"):
                    selected_plans = st.session_state.get("selected_plans_for_validation")
                    mapping = st.session_state.get("column_mapping", {})
                    if not selected_plans:
                        st.error("Please select at least one slitting plan to validate against.")
                    else:
                        with st.spinner("Validating against selected plan(s)..."):
                            results = slitting_service.validate_packing_list(df, selected_plans, mapping)
                            st.session_state.validation_results = results
                            st.session_state.validation_successful = results.get("validation_passed", False)
                if "validation_results" in st.session_state:
                    st.markdown("#### Validation Results")
                    results = st.session_state.validation_results
                    st.dataframe(results.get("comparison_df"))
                    if results.get("validation_passed"):
                        st.success("Validation successful! You can now process the upload.")
                    else:
                        st.error(f"Validation failed: {results.get('message', 'Please check the discrepancies.')}")

            process_disabled = st.session_state.get("validate_against_plan", False) and not st.session_state.get("validation_successful", False)
            
            # If the user has explicitly confirmed in the dialog
            if st.session_state.pop("rm_inward_bulk_submit_confirmed", False):
                valid_requests = st.session_state.get("pending_valid_requests", [])
                failed_records = st.session_state.get("pending_failed_records", [])
                
                if valid_requests:
                    with st.spinner("Submitting to Google Sheets..."):
                        success = data_service.create_rm_inward_issues_bulk(valid_requests)
                        if success:
                            st.success(f"Successfully submitted {len(valid_requests)} records in a single batch!")
                            load_dropdowns.clear()
                            st.session_state.rm_inward_bulk_lock = 0
                            keys_to_clear = ['uploaded_df', 'grouped_df', 'bulk_upload_file', 'column_mapping', 'validation_results', 'validation_successful', 'pending_valid_requests', 'pending_failed_records']
                            for key in st.session_state.keys():
                                if key.startswith('mapping_'):
                                    keys_to_clear.append(key)
                            for key in keys_to_clear:
                                if key in st.session_state:
                                    del st.session_state[key]
                            st.rerun()
                        else:
                            st.session_state.rm_inward_bulk_lock = 0
                            st.error("Failed to submit the bulk data. The entire batch was rejected by the API.")
                            for req in valid_requests:
                                failed_records.append({"Row": "N/A", "Coil Number": str(req.coil_number), "Error": "Failed during bulk submission."})
                else:
                    st.session_state.rm_inward_bulk_lock = 0
            
            elif st.button("Process Bulk Upload", key="process_bulk_upload", disabled=process_disabled):
                current_time = time.time()
                if current_time - st.session_state.get('rm_inward_bulk_lock', 0) < 30:
                    st.warning("Save already in progress. Please wait...")
                    st.stop()
                st.session_state.rm_inward_bulk_lock = current_time

                if group_by_col:
                    if "grouped_df" in st.session_state and st.session_state.grouped_df is not None:
                        processing_df = st.session_state.grouped_df
                    else:
                        with st.spinner("Grouping data..."):
                            mapping = st.session_state.get("column_mapping", {})
                            processing_df = data_service.group_df_by_key(df, group_by_col, mapping)
                else:
                    processing_df = df

                mapping = st.session_state.get("column_mapping", {})
                auto_generate_coil = st.session_state.get('bulk_auto_generate_coil', False)
                user_email = st.session_state['user_info']['username']
                options = {"user_email": user_email, "auto_generate_coil": auto_generate_coil, "group_by_col": group_by_col}
                existing_coils = set(c.lower() for c in dropdowns.coil_numbers)
                valid_requests, failed_records = data_service.process_bulk_upload_df(processing_df, mapping, options, existing_coils)
                
                # Store processed records in session state for the dialog to use
                st.session_state.pending_valid_requests = valid_requests
                st.session_state.pending_failed_records = failed_records
                
                if valid_requests:
                    _show_bulk_upload_confirmation_dialog(valid_requests)
                else:
                    st.session_state.rm_inward_bulk_lock = 0
                    if failed_records:
                        st.warning(f"Found {len(failed_records)} records with validation errors. None were valid for submission.")
                        failed_df = pd.DataFrame(failed_records)
                        failed_df['Row'] = failed_df['Row'].astype(str)
                        st.dataframe(failed_df)
