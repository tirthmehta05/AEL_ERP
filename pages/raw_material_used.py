import streamlit as st
from datetime import datetime
from pydantic import ValidationError

from src.data_entry.service.rm_used_service import RMUsedService
from src.data_entry.models.rm_used_models import RMUsedRequest
from theme.components import render_main_header, end_card


@st.cache_resource
def load_dropdowns(_service: RMUsedService):
    return _service.get_dropdown_data()


def render_raw_material_used_form() -> None:
    """Renders the Raw Material Used form with interactive coil selection."""
    data_service = RMUsedService()

    # This block resets the form fields upon successful submission
    if st.session_state.get("form_submitted_successfully", False):
        st.session_state.rm_used_date = datetime.now().date()
        st.session_state.card_no = ""
        st.session_state.coil_no = None
        st.session_state.weight = ""
        st.session_state.machine = None
        st.session_state.remarks = None
        st.session_state.no_of_boxes = 0
        st.session_state.available_weight = 0.0
        st.session_state.form_submitted_successfully = False

    dropdowns = load_dropdowns(data_service)

    if 'available_weight' not in st.session_state:
        st.session_state.available_weight = 0.0

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Raw Material Used Form</div>", unsafe_allow_html=True)
    st.markdown("<div class='card-body'>", unsafe_allow_html=True) # Added for better spacing

    # --- Step 1: Interactive Coil Selection (Outside the form) ---
    st.selectbox(
        "Coil No",
        options=dropdowns.coil_nos,
        index=None,
        placeholder="Select a Coil No to see available weight",
        key="coil_no"
    )

    # --- Step 2: Display Available Weight (Outside the form) ---
    if st.session_state.coil_no:
        st.session_state.available_weight = data_service.get_available_weight(st.session_state.coil_no)
        st.info(f"Available weight for coil **{st.session_state.coil_no}**: **{st.session_state.available_weight:.2f} kg**")
    
    # --- Step 3: The rest of the form for data entry ---
    with st.form("raw_material_used_form", clear_on_submit=False):
        
        # Displaying the selected coil number inside the form for context, but disabled
        st.text_input("Selected Coil No", value=st.session_state.get("coil_no", ""), disabled=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.date_input("Date", key="rm_used_date")
            st.selectbox("Card No", options=dropdowns.job_cards, index=None, placeholder="Select a Job Card", key="card_no")
            st.number_input("Weight to Use", min_value=0.0, step=1.0, format="%.2f", key="weight")

        with col2:
            st.selectbox("Machine", options=dropdowns.machines, index=None, placeholder="Select or type a Machine", key="machine", help="The machine where the material was used.", accept_new_options=True)
            st.selectbox("Remarks", options=dropdowns.remarks, index=None, placeholder="Select or type a Remark", key="remarks", help="Any remarks or customer name.", accept_new_options=True)
            st.number_input("No Of Boxes (Optional)", min_value=0, step=1, key="no_of_boxes")

        submitted = st.form_submit_button("Submit Used Entry")
        
        if submitted:
            errors = []
            if st.session_state.rm_used_date > datetime.now().date():
                errors.append("Date cannot be in the future.")

            # Required fields validation (Coil No is checked separately)
            required_fields = {
                "Card No": st.session_state.card_no, 
                "Weight to Use": st.session_state.weight, 
                "Machine": st.session_state.machine, 
            }
            if not st.session_state.coil_no:
                errors.append("Please select a 'Coil No' before submitting.")

            for field_name, value in required_fields.items():
                if not value:
                    errors.append(f"Please enter a value for '{field_name}'.")
            
            # Weight validation
            weight_float = 0.0
            try:
                weight_float = float(st.session_state.weight)
                if weight_float <= 0:
                    errors.append("'Weight to Use' must be a positive number.")
            except (ValueError, TypeError):
                errors.append("'Weight to Use' must be a valid number.")

            # Available weight check
            if not errors and st.session_state.coil_no:
                if weight_float > st.session_state.available_weight:
                    errors.append(f"Entered weight ({weight_float:.2f} kg) exceeds available weight ({st.session_state.available_weight:.2f} kg).")

            if errors:
                st.warning("Please correct the following errors:\n\n" + "\n".join([f"- {e}" for e in errors]))
            else:
                try:
                    request_data = {
                        "rm_used_date": st.session_state.rm_used_date,
                        "card_no": st.session_state.card_no,
                        "coil_no": st.session_state.coil_no,
                        "weight": weight_float,
                        "machine": st.session_state.machine,
                        "remarks": st.session_state.remarks or "",
                        "no_of_boxes": st.session_state.no_of_boxes or 0,
                    }
                    with st.spinner("Processing your request..."):
                        request_obj = RMUsedRequest(**request_data)
                        success = data_service.create_rm_used(request_obj)
                    
                    if success:
                        st.success("Raw Material Used entry submitted successfully!")
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

    st.markdown("</div>", unsafe_allow_html=True) # Close card-body
    st.markdown("</div>", unsafe_allow_html=True) # Close card

if __name__ == "__main__":
    render_raw_material_used_form()
