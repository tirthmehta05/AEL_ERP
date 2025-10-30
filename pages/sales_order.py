import streamlit as st
from datetime import datetime
from pydantic import ValidationError
import pandas as pd
import time

from src.data_entry.service.sales_order_service import SalesOrderService
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService
from src.data_entry.models.sales_order_models import SalesOrderRequest, DesignDetail, AssignedCoil
from config import settings

# --- Helper Functions --- #

def initialize_session_state():
    """Initialize session state variables for the form."""
    if 'so_designs' not in st.session_state:
        st.session_state.so_designs = []
    if 'so_assigned_coils' not in st.session_state:
        st.session_state.so_assigned_coils = []
    if 'so_job_card_number' not in st.session_state:
        st.session_state.so_job_card_number = ""
    # Initialize design keys to prevent errors on first run
    design_keys = ['design_party_job_no', 'design_width', 'design_length', 'design_weight', 
                   'design_sets', 'design_type', 'design_thk', 'design_grade', 'design_hole', 
                   'design_is_loose', 'design_mm_stack']
    for key in design_keys:
        if key not in st.session_state:
            if 'is_loose' in key:
                st.session_state[key] = False
            elif any(s in key for s in ['width', 'length', 'weight', 'mm_stack', 'thk']):
                st.session_state[key] = 0.0
            elif 'sets' in key:
                st.session_state[key] = 1
            else:
                st.session_state[key] = ""

def render_header_fields(dropdown_data):
    """Renders the main header fields for the sales order form."""
    st.markdown("<h5>Order Details</h5>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.date_input("Order Date", key="so_order_date")
        st.text_input("PO No. (Optional)", key="so_po_no")
        st.selectbox("Party Name", options=dropdown_data.party_names, index=None, placeholder="Select a Party", key="so_party_name")
    with col2:
        st.date_input("Delivery Date", key="so_delivery_date")
        st.number_input("Rate (per Kg)", min_value=0.0, step=0.01, format="%.2f", key="so_rate_per_kg")
        default_hole_size = 16
        hole_size_options = dropdown_data.hole_sizes
        default_index = hole_size_options.index(default_hole_size) if default_hole_size in hole_size_options else 0
        st.selectbox("Hole Size (mm)", options=hole_size_options, index=default_index, key="so_hole_size")
    with col3:
        st.number_input("Number of Cores", min_value=1, step=1, key="so_num_cores")
        st.number_input("Header Core Stack (mm)", min_value=0.0, step=1.0, format="%.1f", key="so_header_core_stack")

def render_design_entry_fields():
    """Renders the fields for adding a single design detail."""
    st.markdown("--- ")
    st.markdown("<h5>Add Design Details</h5>", unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.text_input("Party Job No. (Optional)", key="design_party_job_no")
        st.number_input("Width (mm)", min_value=0.0, step=1.0, format="%.2f", key="design_width")
        st.number_input("Set", min_value=1, step=1, key="design_sets")
    with col2:
        st.selectbox("Type", options=["CRNO", "CRNGO"], key="design_type")
        st.number_input("Length (mm)", min_value=0.0, step=1.0, format="%.2f", key="design_length")
        is_loose = st.checkbox("Loose Core", key="design_is_loose")
    with col3:
        st.selectbox("Hole", options=["Plain", "Centre", "Both Side", "Side", "3-Hole", "Daimond", "V-Noch"], key="design_hole")
        st.number_input("Thickness (mm)", min_value=0.0, step=0.01, format="%.2f", key="design_thk")
        st.number_input("Weight (kg)", min_value=0.0, step=1.0, format="%.2f", key="design_weight", disabled=not is_loose)
    with col4:
        st.text_input("Grade (Optional)", key="design_grade")
        st.text_input("Remark (Optional)", key="design_remark")
        st.number_input("Stack (mm)", min_value=0.0, step=1.0, format="%.1f", key="design_mm_stack", disabled=is_loose)

    # Live Calculation Display
    try:
        calc_text = ""
        if st.session_state.design_is_loose:
            if st.session_state.design_width > 0 and st.session_state.design_length > 0 and settings.constants.steel_density > 0:
                weight_calc = st.session_state.design_weight
                width_m = st.session_state.design_width / 1000
                length_m = st.session_state.design_length / 1000
                density_kg_m3 = settings.constants.steel_density * 1000
                stack_m = (weight_calc / (width_m * length_m * density_kg_m3))
                calc_text = f"**Calculated Stack:** `{stack_m * 1000:.2f} mm`"
        else:
            if st.session_state.design_width > 0 and st.session_state.design_length > 0 and st.session_state.design_mm_stack > 0:
                width_m = st.session_state.design_width / 1000
                length_m = st.session_state.design_length / 1000
                stack_m = st.session_state.design_mm_stack / 1000
                density_kg_m3 = settings.constants.steel_density * 1000
                weight_calc = (width_m * length_m * stack_m * density_kg_m3)
                calc_text = f"**Calculated Weight:** `{weight_calc:.2f} kg`"
        if calc_text:
            st.info(calc_text)
    except Exception: pass

    if st.button("Add Design to Order"):
        add_design_to_state()

def add_design_to_state():
    """Validates the current design and adds it to the session state list."""
    try:
        is_loose = st.session_state.design_is_loose
        thk_mm = st.session_state.design_thk
        mm_stack, weight = 0, 0
        if is_loose:
            weight = st.session_state.design_weight
            width_m = st.session_state.design_width / 1000
            length_m = st.session_state.design_length / 1000
            density_kg_m3 = settings.constants.steel_density * 1000
            if width_m * length_m * density_kg_m3 == 0: raise ValueError("Width, Length, and Density must be non-zero.")
            mm_stack = (weight / (width_m * length_m * density_kg_m3)) * 1000
        else:
            mm_stack = st.session_state.design_mm_stack
            width_m = st.session_state.design_width / 1000
            length_m = st.session_state.design_length / 1000
            stack_m = mm_stack / 1000
            density_kg_m3 = settings.constants.steel_density * 1000
            weight = (width_m * length_m * stack_m * density_kg_m3)
        if thk_mm == 0: raise ValueError("Thickness cannot be zero.")
        pcs = int((mm_stack / thk_mm) * st.session_state.design_sets)

        design = DesignDetail(
            party_job_no=st.session_state.design_party_job_no or None,
            width=st.session_state.design_width, length=st.session_state.design_length,
            mm_stack=mm_stack, weight=weight, sets=st.session_state.design_sets,
            type=st.session_state.design_type, thk=st.session_state.design_thk,
            grade=st.session_state.design_grade or None, hole=st.session_state.design_hole,
            pcs=pcs, is_loose=is_loose
        )
        st.session_state.so_designs.append(design.model_dump())
        st.success("Design added to the Job Card.")
    except (ValueError, ZeroDivisionError) as e:
        st.error(f"Calculation Error: {e}")
    except Exception as e:
        st.error(f"An error occurred: {e}")

def render_designs_table():
    """Renders the table of added designs."""
    if st.session_state.so_designs:
        st.markdown("--- ")
        st.markdown("<h5>Added Designs</h5>", unsafe_allow_html=True)
        df = pd.DataFrame(st.session_state.so_designs)
        
        total_design_weight = df['weight'].sum()
        st.metric(label="Total Design Weight (kg)", value=f"{total_design_weight:.2f}")

        edited_df = st.data_editor(df, num_rows="dynamic", key="designs_editor", use_container_width=True,
            column_config={
                "party_job_no": "Party Job No", "width": "Width (mm)", "length": "Length (mm)",
                "mm_stack": "Stack (mm)", "weight": "Weight (kg)", "sets": "Sets", "type": "Type",
                "thk": "Thickness (mm)", "grade": "Grade", "hole": "Hole", "pcs": "Pieces", "is_loose": "Loose"
            })
        if len(edited_df) != len(st.session_state.so_designs):
            st.session_state.so_designs = edited_df.to_dict('records')
            st.rerun()

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

def add_assigned_coil_to_state(coil_options, selected_coil_str):
    """Validates and adds the selected coil to the assigned list."""
    weight_to_use = st.session_state.assign_coil_weight
    selected_coil_data = coil_options[selected_coil_str]
    available_weight = selected_coil_data['available_weight']
    if weight_to_use <= 0: st.error("Weight to use must be positive."); return
    if weight_to_use > available_weight: st.error(f"Weight to use ({weight_to_use}) exceeds available weight ({available_weight:.2f})."); return
    st.session_state.so_assigned_coils.append({"coil_no": selected_coil_data['Coil Number'], "weight_used": weight_to_use})
    st.success(f"Assigned {weight_to_use} kg from coil {selected_coil_data['Coil Number']}.")

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

def handle_final_submission(service: SalesOrderService):
    """Handles the final submission of the entire sales order."""
    if not st.session_state.so_designs: st.error("Please add at least one design."); return
    if not st.session_state.so_assigned_coils: st.error("Please assign at least one coil."); return

    total_design_weight = sum(d.get('weight', 0) for d in st.session_state.so_designs)
    total_coil_weight = sum(c.get('weight_used', 0) for c in st.session_state.so_assigned_coils)
    
    lower_bound = total_design_weight * 0.99
    upper_bound = total_design_weight * 1.01

    if not (lower_bound <= total_coil_weight <= upper_bound):
        st.error(f"Weight Mismatch: Total assigned coil weight ({total_coil_weight:.2f} kg) is not within 1% of the total design weight ({total_design_weight:.2f} kg).")
        return

    try:
        request = SalesOrderRequest(
            order_date=st.session_state.so_order_date, po_no=st.session_state.so_po_no,
            party_name=st.session_state.so_party_name, delivery_date=st.session_state.so_delivery_date,
            job_card_number=st.session_state.so_job_card_number, hole_size=st.session_state.so_hole_size,
            number_of_cores=st.session_state.so_num_cores, rate_per_kg=st.session_state.so_rate_per_kg,
            header_core_stack=st.session_state.so_header_core_stack,
            designs=[DesignDetail(**d) for d in st.session_state.so_designs],
            assigned_coils=[AssignedCoil(**c) for c in st.session_state.so_assigned_coils]
        )
        with st.spinner("Saving full order..."):
            success = service.save_sales_order(request)
        if success:
            st.success(f"Sales Order {request.job_card_number} saved successfully!")
            time.sleep(2)
            keys_to_clear = [key for key in st.session_state.keys() if key.startswith('so_') or key.startswith('design_') or key.startswith('assign_')]
            for key in keys_to_clear:
                if key in st.session_state: del st.session_state[key]
            st.rerun()
        else:
            st.error("Failed to save the sales order.")
    except ValidationError as e:
        st.error(f"Final validation failed: {e}")

def render_sales_order_form() -> None:
    """Renders the main Sales Order entry form."""
    sales_order_service = SalesOrderService()
    slitting_service = SlittingPlanService()
    initialize_session_state()

    @st.cache_data
    def load_dropdowns(_service: SalesOrderService):
        return _service.get_dropdown_data()

    dropdown_data = load_dropdowns(sales_order_service)

    render_header_fields(dropdown_data)
    
    if st.session_state.get("so_party_name"):
        render_design_entry_fields()
        render_designs_table()
        
        st.markdown("---")
        if st.checkbox("Show/Hide Coil Assignment", key="so_show_coil_assigner"):
            render_coil_assignment_fields(slitting_service)
            render_assigned_coils_table()
        
        st.markdown("---")
        if st.button("Save Full Sales Order"):
            handle_final_submission(sales_order_service)