import streamlit as st
import pandas as pd
from pages.shared.utils import get_services
from src.data_entry.models.sales_order_models import AssignedCoil
from pages.sales_order_components import render_coil_assignment_fields, render_assigned_coils_table
import json
import time

@st.dialog("Confirm Coil Assignment", width="large")
def _show_assign_coils_confirmation_dialog(job_card_number: str, assigned_coils: list, total_design_weight: float, total_coil_weight: float, is_weight_mismatched: bool):
    """Shows a modal to confirm coil assignments before saving."""
    st.markdown(f"**Job Card:** {job_card_number}")
    st.markdown("Please review the assigned coils below.")
    st.markdown("---")
    
    # Display assigned coils preview
    df = pd.DataFrame(assigned_coils)
    display_cols_mapping = {
        'coil_number': 'Coil Number',
        'weight_used': 'Weight Assigned (kg)',
        'location': 'Location'
    }
    
    # Only keep columns that actually exist in the dataframe
    existing_cols = [c for c in display_cols_mapping.keys() if c in df.columns]
    display_df = df[existing_cols].copy()
    
    # Rename only the existing columns
    display_df.rename(columns={k: display_cols_mapping[k] for k in existing_cols}, inplace=True)
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Design Weight", f"{total_design_weight:.2f} kg")
    with col2:
        st.metric("Total Assigned Coil Weight", f"{total_coil_weight:.2f} kg", 
                  delta=f"{total_coil_weight - total_design_weight:.2f} kg" if not is_weight_mismatched else "Mismatch (>1%)",
                  delta_color="normal" if not is_weight_mismatched else "inverse")
        
    if is_weight_mismatched:
        st.error(f"Weight Mismatch: Total assigned coil weight ({total_coil_weight:.2f} kg) is not within 1% of the total design weight ({total_design_weight:.2f} kg).")
        
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Confirm Assignment", type="primary", use_container_width=True, disabled=is_weight_mismatched):
            st.session_state.assign_coils_submit_confirmed = True
            st.rerun()
    with c2:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.assign_coils_submit_confirmed = False
            st.session_state.assign_coils_save_lock = 0
            st.rerun()

def render_assign_coils_form():
    st.markdown("<h3>Assign Coils to Sales Order</h3>", unsafe_allow_html=True)

    services = get_services()

    pending_orders = services.sales_order.get_pending_sales_orders()

    if not pending_orders:
        st.info("No sales orders are pending coil assignment.")
        return

    order_options = {f"{order['job_card_number']} - {order['party_name']}": order for order in pending_orders}
    selected_order_str = st.selectbox("Select a Sales Order to Assign Coils", options=[""] + list(order_options.keys()))

    if selected_order_str:
        selected_order = order_options[selected_order_str]
        
        if 'selected_so_for_assignment' not in st.session_state or st.session_state.selected_so_for_assignment['job_card_number'] != selected_order['job_card_number']:
            st.session_state.selected_so_for_assignment = selected_order
            st.session_state.so_assigned_coils = [] # Clear coils when a new order is selected

        st.markdown("---")
        st.markdown(f"<h5>Details for {selected_order['job_card_number']}</h5>", unsafe_allow_html=True)
        
        designs = json.loads(selected_order.get('designs_json', '[]'))
        if designs:
            st.dataframe(pd.DataFrame(designs))
            total_design_weight = sum(d.get('weight', 0) for d in designs)
            st.metric("Total Design Weight (kg)", f"{total_design_weight:.2f}")

        render_coil_assignment_fields(services.slitting_plan)
        render_assigned_coils_table()

        # If user explicitly confirmed in the dialog
        if st.session_state.pop("assign_coils_submit_confirmed", False) and "pending_assign_request" in st.session_state:
            request_data = st.session_state.pop("pending_assign_request")
            try:
                with st.spinner("Saving coil assignment..."):
                    assigned_coils_models = [AssignedCoil(**c) for c in request_data['assigned_coils']]
                    success = services.sales_order.assign_coils_to_sales_order(
                        job_card_number=request_data['job_card_number'],
                        assigned_coils=assigned_coils_models
                    )
                    if success:
                        st.success("Coil assignment saved successfully!")
                        st.session_state.assign_coils_save_lock = 0
                        st.session_state.so_assigned_coils = []
                        st.session_state.selected_so_for_assignment = None
                        st.rerun()
                    else:
                        st.session_state.assign_coils_save_lock = 0
                        st.error("Failed to save coil assignment.")
            except Exception as e:
                st.session_state.assign_coils_save_lock = 0
                st.error(f"A temporary error occurred: {e}. Please try saving again.")

        elif st.button("Save Coil Assignment"):
            current_time = time.time()
            if current_time - st.session_state.get('assign_coils_save_lock', 0) < 30:
                st.warning("Save already in progress. Please wait...")
                st.stop()
            st.session_state.assign_coils_save_lock = current_time

            if not st.session_state.so_assigned_coils:
                st.session_state.assign_coils_save_lock = 0
                st.error("Please assign at least one coil.")
                return

            # Weight validation
            total_design_weight = sum(d.get('weight', 0) for d in designs)
            total_coil_weight = sum(c.get('weight_used', 0) for c in st.session_state.so_assigned_coils)

            lower_bound = total_design_weight * 0.99
            upper_bound = total_design_weight * 1.01
            is_weight_mismatched = not (lower_bound <= total_coil_weight <= upper_bound)

            request_data = {
                "job_card_number": selected_order['job_card_number'],
                "assigned_coils": st.session_state.so_assigned_coils
            }
            
            st.session_state.pending_assign_request = request_data
            _show_assign_coils_confirmation_dialog(request_data['job_card_number'], request_data['assigned_coils'], total_design_weight, total_coil_weight, is_weight_mismatched)
