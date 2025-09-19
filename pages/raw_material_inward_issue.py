import streamlit as st
from datetime import datetime
from pydantic import ValidationError

from src.data_entry.service.rm_inward_service import RMInwardService
from src.data_entry.models.rm_inward_models import RMInwardIssueRequest
from theme.components import render_main_header, end_card

def render_raw_material_inward_issue_form() -> None:
    """Renders the Raw Material Inward Issue form"""
    data_service = RMInwardService()

    # Get user email from session state
    user_email = ""
    if 'user_info' in st.session_state and st.session_state['user_info']:
        user_email = st.session_state['user_info'].get('username')

    if st.session_state.get("form_submitted_successfully", False):
        st.session_state.receipt_date = datetime.now().date()
        st.session_state.rm_type = None
        st.session_state.coil_number = ""
        st.session_state.coil_weight = 0.01
        st.session_state.po_number = None
        st.session_state.grade = None
        st.session_state.thk = None
        st.session_state.width = None
        st.session_state.coating = None
        st.session_state.supplier = None
        st.session_state.coil_location = "Amba" # Reset to default
        st.session_state.form_submitted_successfully = False

    @st.cache_resource
    def load_dropdowns(_service: RMInwardService):
        return _service.get_dropdown_data()

    dropdowns = load_dropdowns(data_service)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Raw Material Inward Issue Form</div>", unsafe_allow_html=True)

    with st.form("raw_material_inward_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            st.date_input("RM Receipt Date", key="receipt_date")
            st.selectbox("RM Type", options=dropdowns.rm_types, index=None, placeholder="Select or type a RM Type", accept_new_options=True, key="rm_type")
            st.text_input("Coil Number", key="coil_number")
            st.number_input("Coil Weight (kg)", min_value=0.01, step=0.01, format="%.2f", key="coil_weight")
            st.selectbox("PO Number (Optional)", options=[], index=None, placeholder="Type a PO Number", accept_new_options=True, key="po_number")

        with col2:
            st.selectbox("Grade", options=dropdowns.grades, index=None, placeholder="Select or type a Grade", accept_new_options=True, key="grade")
            st.selectbox("Thk (mm)", options=dropdowns.thks, index=None, placeholder="Select or type a Thk", accept_new_options=True, key="thk")
            st.selectbox("Width (mm)", options=dropdowns.widths, index=None, placeholder="Select or type a Width", accept_new_options=True, key="width")
            st.selectbox("Coating", options=dropdowns.coatings, index=None, placeholder="Select or type a Coating", accept_new_options=True, key="coating")
            st.selectbox("Coil Supplier", options=dropdowns.suppliers, index=None, placeholder="Select or type a Supplier", accept_new_options=True, key="supplier")

        st.selectbox("Coil Location", options=["Amba", "Tenth"], index=0, key="coil_location")

        submitted = st.form_submit_button("Submit Inward Entry")
        
        if submitted:
            errors = []
            if st.session_state.receipt_date > datetime.now().date():
                errors.append("Receipt Date cannot be in the future.")

            required_fields = {
                "RM Type": st.session_state.rm_type, 
                "Grade": st.session_state.grade, 
                "Thk (mm)": st.session_state.thk, 
                "Width (mm)": st.session_state.width, 
                "Coating": st.session_state.coating, 
                "Coil Supplier": st.session_state.supplier
            }
            for field_name, value in required_fields.items():
                if not value:
                    errors.append(f"Please select or enter a value for '{field_name}'.")

            if not st.session_state.coil_number.strip(): errors.append("Please enter a Coil Number.")
            if st.session_state.coil_weight <= 0: errors.append("Coil Weight must be greater than zero.")
            
            thk_float, width_int = 0.0, 0
            try:
                if st.session_state.thk: thk_float = float(st.session_state.thk)
            except (ValueError, TypeError):
                errors.append("Thk must be a valid number.")
            try:
                if st.session_state.width: width_int = int(st.session_state.width)
            except (ValueError, TypeError):
                errors.append("Width must be a valid number.")

            if not errors:
                is_unique = data_service.is_coil_number_unique(st.session_state.coil_number.strip())
                if not is_unique:
                    errors.append(f"Coil Number '{st.session_state.coil_number}' already exists.")

            if errors:
                st.warning("Please correct the following errors:\n\n" + "\n".join([f"- {e}" for e in errors]))
            else:
                try:
                    request_data = {
                        "user_id": user_email or "",
                        "rm_receipt_date": st.session_state.receipt_date,
                        "rm_type": st.session_state.rm_type,
                        "coil_number": st.session_state.coil_number,
                        "grade": st.session_state.grade,
                        "thk": thk_float,
                        "width": width_int,
                        "coating": st.session_state.coating,
                        "coil_weight": st.session_state.coil_weight,
                        "po_number": st.session_state.po_number or "",
                        "coil_supplier": st.session_state.supplier,
                        "coil_location": st.session_state.coil_location,
                    }
                    with st.spinner("Processing your request..."):
                        request_obj = RMInwardIssueRequest(**request_data)
                        success = data_service.create_rm_inward_issue(request_obj)
                    
                    if success:
                        st.success("Raw Material Inward entry submitted successfully!")
                        load_dropdowns.clear()
                        st.session_state.form_submitted_successfully = True
                        st.rerun()
                    else:
                        st.error("Failed to save the entry. Please check application logs.")

                except ValidationError as e:
                    error_msgs = [f"- **{err['loc'][0]}**: {err['msg']}" for err in e.errors()]
                    st.error("Data validation failed:\n" + "\n".join(error_msgs))
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
    st.markdown("</div>", unsafe_allow_html=True)
