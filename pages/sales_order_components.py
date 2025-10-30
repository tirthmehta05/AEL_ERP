import streamlit as st
import pandas as pd
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService

def add_assigned_coil_to_state(coil_options, selected_coil_str):
    """Validates and adds the selected coil to the assigned list."""
    weight_to_use = st.session_state.assign_coil_weight
    selected_coil_data = coil_options[selected_coil_str]
    available_weight = selected_coil_data['available_weight']
    if weight_to_use <= 0:
        st.error("Weight to use must be positive.")
        return
    if weight_to_use > available_weight:
        st.error(f"Weight to use ({weight_to_use}) exceeds available weight ({available_weight:.2f}).")
        return
    st.session_state.so_assigned_coils.append({"coil_no": selected_coil_data['Coil Number'], "weight_used": weight_to_use})
    st.success(f"Assigned {weight_to_use} kg from coil {selected_coil_data['Coil Number']}.")

def render_coil_assignment_fields(slitting_service: SlittingPlanService):
    """Renders the UI for assigning coils to the order using a filterable table."""
    st.markdown("--- ")
    st.markdown("<h5>Assign Raw Material Coils</h5>", unsafe_allow_html=True)

    available_coils = slitting_service.get_available_coils()
    if available_coils.empty:
        st.warning("No available raw material coils found.")
        return

    # --- Filters for the coil table ---
    st.markdown("<h6>Filter Available Coils</h6>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        grades = ["All"] + sorted(available_coils['grade'].unique().tolist())
        selected_grade = st.selectbox("Filter by Grade", options=grades, key="filter_grade")
    with col2:
        thicknesses = ["All"] + sorted(available_coils['thickness'].unique().tolist())
        selected_thk = st.selectbox("Filter by Thickness", options=thicknesses, key="filter_thk")
    with col3:
        widths = ["All"] + sorted(available_coils['width'].unique().tolist())
        selected_width = st.selectbox("Filter by Width", options=widths, key="filter_width")

    filtered_coils = available_coils.copy()
    if selected_grade != "All":
        filtered_coils = filtered_coils[filtered_coils['grade'] == selected_grade]
    if selected_thk != "All":
        filtered_coils = filtered_coils[filtered_coils['thickness'] == selected_thk]
    if selected_width != "All":
        filtered_coils = filtered_coils[filtered_coils['width'] == selected_width]

    st.dataframe(filtered_coils, use_container_width=True)

    # --- Selection based on filtered results ---
    if not filtered_coils.empty:
        st.markdown("<h6>Select and Assign Coil</h6>", unsafe_allow_html=True)
        coil_options = {f"{row['Coil Number']} ({row['available_weight']:.2f} kg)": row for _, row in filtered_coils.iterrows()}
        col1, col2, col3 = st.columns([2,1,1])
        with col1:
            selected_coil_str = st.selectbox("Select Coil to Assign", options=[""] + list(coil_options.keys()), key="assign_coil_select")
        with col2:
            st.number_input("Weight to Use (kg)", min_value=0.0, step=1.0, format="%.2f", key="assign_coil_weight")
        with col3:
            st.write("&nbsp;", unsafe_allow_html=True) # Spacer for alignment
            if st.button("Assign Coil"):
                if selected_coil_str:
                    add_assigned_coil_to_state(coil_options, selected_coil_str)
    else:
        st.info("No coils match the current filter criteria.")

def render_assigned_coils_table():
    """Renders the table of assigned coils."""
    if st.session_state.so_assigned_coils:
        st.markdown("<h6>Assigned Coils</h6>", unsafe_allow_html=True)
        df = pd.DataFrame(st.session_state.so_assigned_coils)
        
        total_assigned_weight = df['weight_used'].sum()
        st.metric(label="Total Assigned Coil Weight (kg)", value=f"{total_assigned_weight:.2f}")

        edited_df = st.data_editor(df, num_rows="dynamic", key="assigned_coils_editor", use_container_width=True,
            column_config={"coil_no": "Coil Number", "weight_used": "Weight Used (kg)"})
        if len(edited_df) != len(st.session_state.so_assigned_coils):
            st.session_state.so_assigned_coils = edited_df.to_dict('records')
            st.rerun()
