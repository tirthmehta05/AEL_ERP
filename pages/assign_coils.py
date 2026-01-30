import streamlit as st
import pandas as pd
from pages.shared.utils import get_services
from src.data_entry.models.sales_order_models import AssignedCoil
from pages.sales_order_components import render_coil_assignment_fields, render_assigned_coils_table
import json

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

        if st.button("Save Coil Assignment"):
            if not st.session_state.so_assigned_coils:
                st.error("Please assign at least one coil.")
                return

            # Weight validation
            total_design_weight = sum(d.get('weight', 0) for d in designs)
            total_coil_weight = sum(c.get('weight_used', 0) for c in st.session_state.so_assigned_coils)
            
            lower_bound = total_design_weight * 0.99
            upper_bound = total_design_weight * 1.01

            if not (lower_bound <= total_coil_weight <= upper_bound):
                st.error(f"Weight Mismatch: Total assigned coil weight ({total_coil_weight:.2f} kg) is not within 1% of the total design weight ({total_design_weight:.2f} kg).")
                return

            with st.spinner("Saving coil assignment..."):
                assigned_coils = [AssignedCoil(**c) for c in st.session_state.so_assigned_coils]
                success = services.sales_order.assign_coils_to_sales_order(
                    job_card_number=selected_order['job_card_number'],
                    assigned_coils=assigned_coils
                )
                if success:
                    st.success("Coil assignment saved successfully!")
                    st.session_state.so_assigned_coils = []
                    st.session_state.selected_so_for_assignment = None
                    st.rerun()
                else:
                    st.error("Failed to save coil assignment.")
