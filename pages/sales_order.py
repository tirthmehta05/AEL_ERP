import streamlit as st
from datetime import datetime
from pydantic import ValidationError
import pandas as pd
import time
import json

from src.services import create_services

from src.services import create_services, SalesOrderService
from src.data_entry.models.sales_order_models import SalesOrderRequest, DesignDetail, AssignedCoil
from config import settings
from pages.sales_order_components import render_coil_assignment_fields, render_assigned_coils_table

# --- FM Data ---
FM_DATA = {
    "T-3": {"width": 55.2, "length": 127.0},
    "T-15": {"width": 76.2, "length": 101.6},
    "T-16": {"width": 114.2, "length": 152.4},
    "T-43": {"width": 152.4, "length": 203.2},
    "T-180": {"width": 180.0, "length": 240.0},
    "T-12": {"width": 47.6, "length": 63.5},
    "T-23": {"width": 57.1, "length": 76.2},
    "T-30 (P)": {"width": 60.0, "length": 80.0},
    "T-74": {"width": 53.9, "length": 69.85},
    "T-30 (H)": {"width": 60.0, "length": 80.0},
    "T-17": {"width": 38.0, "length": 50.8},
    "T-8B": {"width": 235.0, "length": 317.5},
    "T-6": {"width": 127.0, "length": 190.5},
    "T-8": {"width": 184.0, "length": 292.0},
    "T-31": {"width": 66.6, "length": 88.9},
    "T-33": {"width": 44.0, "length": 112.0},
    "T-41": {"width": 41.2, "length": 53.9},
}

# --- Helper Functions --- #

def initialize_session_state():
    """Initialize session state variables for the form."""
    if 'so_designs' not in st.session_state:
        st.session_state.so_designs = []
    if 'so_assigned_coils' not in st.session_state:
        st.session_state.so_assigned_coils = []
    if 'so_job_card_number' not in st.session_state:
        st.session_state.so_job_card_number = ""
    if 'so_party_job_no' not in st.session_state:
        st.session_state.so_party_job_no = ""
    if 'so_type' not in st.session_state:
        st.session_state.so_type = "CRNO"
    if 'so_grade' not in st.session_state:
        st.session_state.so_grade = ""
    if 'so_coating' not in st.session_state:
        st.session_state.so_coating = ""
    if 'so_is_ready_entry' not in st.session_state:
        st.session_state.so_is_ready_entry = False

    # Initialize design keys to prevent errors on first run
    design_keys = ['design_width', 'design_length', 'design_weight', 
                   'design_sets', 'design_thk', 'design_hole', 
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

    # New keys for ready entry form
    ready_keys = ['ready_card_no', 'ready_fm_name']
    for key in ready_keys:
        if key not in st.session_state:
            st.session_state[key] = ""
    
    if 'ready_thk' not in st.session_state:
        st.session_state.ready_thk = 0.0
    if 'ready_weight' not in st.session_state:
        st.session_state.ready_weight = 0.0

# Define material type options globally for reuse
material_type_options = ["CR COIL", "CRGO EI", "CRNO", "CRNO COIL", "CRNO EI", "CRNO EI TRD", "CRNO TL"]

def render_header_fields(dropdown_data):
    """Renders the main header fields for the sales order form."""
    st.markdown("<h5>Order Details</h5>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.date_input("Order Date", key="so_order_date")
        st.text_input("PO No. (Optional)", key="so_po_no")
        st.selectbox("Party Name", options=dropdown_data.party_names, index=None, placeholder="Select a Party", key="so_party_name", accept_new_options=True)
        st.text_input("Party Job No. (Optional)", key="so_party_job_no")
    with col2:
        st.date_input("Delivery Date", key="so_delivery_date")
        st.number_input("Rate (per Kg)", min_value=0.0, step=0.01, format="%.2f", key="so_rate_per_kg")
        default_hole_size = 16
        hole_size_options = dropdown_data.hole_sizes
        default_index = hole_size_options.index(default_hole_size) if default_hole_size in hole_size_options else 0
        st.selectbox("Hole Size (mm)", options=hole_size_options, index=default_index, key="so_hole_size")
        st.selectbox("Type", options=material_type_options, key="so_type", accept_new_options=True)
    with col3:
        st.number_input("Number of Cores", min_value=1, step=1, key="so_num_cores")
        st.number_input("Header Core Stack (mm)", min_value=0.0, step=1.0, format="%.1f", key="so_header_core_stack")
        st.text_input("Grade (Optional)", key="so_grade")
        st.selectbox("Coating (Optional)", options=dropdown_data.coatings, index=None, placeholder="Select a Coating", key="so_coating")

def render_design_entry_fields():
    """Renders the fields for adding a single design detail."""
    st.markdown("--- ")
    st.markdown("<h5>Add Design Details</h5>", unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.number_input("Width (mm)", min_value=0.0, step=1.0, format="%.2f", key="design_width")
        st.number_input("Set", min_value=1, step=1, key="design_sets")
    with col2:
        st.number_input("Length (mm)", min_value=0.0, step=1.0, format="%.2f", key="design_length")
        is_loose = st.checkbox("Loose Core", key="design_is_loose")
    with col3:
        st.selectbox("Hole", options=["Plain", "Centre", "Both Side", "Side", "3-Hole", "5-Hole", "Daimond", "V-Noch"], key="design_hole")
        st.number_input("Thickness (mm)", min_value=0.0, step=0.01, format="%.2f", key="design_thk")
        st.number_input("Weight (kg)", min_value=0.0, step=1.0, format="%.2f", key="design_weight", disabled=not is_loose)
    with col4:
        is_loose = st.session_state.design_is_loose

        if is_loose:
            # Set the session state. The widget will pick this up via its key.
            st.session_state.design_remark = "Loose"
        elif st.session_state.get("design_remark") == "Loose":
            # If the box was just unchecked, clear the auto-filled value.
            st.session_state.design_remark = ""

        # The widget's value is now determined *only* by st.session_state.design_remark.
        # The `disabled` parameter is determined by the checkbox state.
        st.text_input(
            "Remark (Optional)",
            key="design_remark",
            disabled=is_loose
        )
        st.number_input("Stack (mm)", min_value=0.0, step=1.0, format="%.1f", key="design_mm_stack", disabled=is_loose)

    # Live Calculation Display
    try:
        calc_text = ""
        num_sets = st.session_state.design_sets
        if st.session_state.design_is_loose:
            if st.session_state.design_width > 0 and st.session_state.design_length > 0 and settings.constants.steel_density > 0:
                weight_per_set = st.session_state.design_weight
                total_weight = weight_per_set * num_sets
                
                width_m = st.session_state.design_width / 1000
                length_m = st.session_state.design_length / 1000
                density_kg_m3 = settings.constants.steel_density * 1000
                
                stack_per_set_m = (weight_per_set / (width_m * length_m * density_kg_m3))
                total_stack_mm = (stack_per_set_m * 1000) * num_sets
                calc_text = f"**Total Stack:** `{total_stack_mm:.2f} mm` | **Total Weight:** `{total_weight:.2f} kg`"
        else:
            if st.session_state.design_width > 0 and st.session_state.design_length > 0 and st.session_state.design_mm_stack > 0:
                stack_per_set_mm = st.session_state.design_mm_stack
                total_stack_mm = stack_per_set_mm * num_sets

                width_m = st.session_state.design_width / 1000
                length_m = st.session_state.design_length / 1000
                total_stack_m = total_stack_mm / 1000
                density_kg_m3 = settings.constants.steel_density * 1000
                total_weight = (width_m * length_m * total_stack_m * density_kg_m3)
                calc_text = f"**Total Stack:** `{total_stack_mm:.2f} mm` | **Total Weight:** `{total_weight:.2f} kg`"
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
        num_sets = st.session_state.design_sets
        mm_stack, weight = 0, 0

        if is_loose:
            weight_per_set = st.session_state.design_weight
            weight = weight_per_set * num_sets

            width_m = st.session_state.design_width / 1000
            length_m = st.session_state.design_length / 1000
            density_kg_m3 = settings.constants.steel_density * 1000
            if width_m * length_m * density_kg_m3 == 0: raise ValueError("Width, Length, and Density must be non-zero.")
            
            stack_per_set_m = (weight_per_set / (width_m * length_m * density_kg_m3))
            mm_stack = (stack_per_set_m * 1000) * num_sets
        else:
            stack_per_set_mm = st.session_state.design_mm_stack
            mm_stack = stack_per_set_mm * num_sets

            width_m = st.session_state.design_width / 1000
            length_m = st.session_state.design_length / 1000
            stack_m = mm_stack / 1000
            density_kg_m3 = settings.constants.steel_density * 1000
            weight = (width_m * length_m * stack_m * density_kg_m3)

        if thk_mm == 0: raise ValueError("Thickness cannot be zero.")
        pcs = int(mm_stack / thk_mm)

        design = DesignDetail(
            party_job_no=st.session_state.so_party_job_no or None,
            width=st.session_state.design_width, length=st.session_state.design_length,
            mm_stack=mm_stack, weight=weight, sets=st.session_state.design_sets,
            type=st.session_state.so_type, thk=st.session_state.design_thk,
            grade=st.session_state.so_grade or None, hole=st.session_state.design_hole,
            pcs=pcs, coating=st.session_state.so_coating or None
        )
        st.session_state.so_designs.append(design.model_dump())
        st.success("Design added to the Job Card.")
    except (ValueError, ZeroDivisionError) as e:
        st.error(f"Calculation Error: {e}")
    except Exception as e:
        st.error(f"An error occurred: {e}")

def add_ready_design_to_state(width, length):
    """Validates the current ready design and adds it to the session state list."""
    try:
        weight = st.session_state.ready_weight
        if weight <= 0: raise ValueError("Weight must be greater than zero.")
        
        thk_mm = st.session_state.ready_thk
        if thk_mm <= 0: raise ValueError("Thickness must be greater than zero.")
        
        if width <= 0 or length <= 0: raise ValueError("Width and Length must be selected via FM Name.")

        design = DesignDetail(
            party_job_no=st.session_state.ready_card_no or f"RN-{int(time.time())}",
            fm_name=st.session_state.ready_fm_name,
            width=width, 
            length=length,
            weight=weight, 
            thk=thk_mm,
            type=st.session_state.so_type, 
            # Set other required fields to sensible defaults for "Ready" type
            mm_stack=None,
            pcs=0,
            hole="Ready Entry",
            sets=1,
            grade=st.session_state.so_grade or None,
            coating=st.session_state.so_coating or None,
        )
        st.session_state.so_designs.append(design.model_dump())
        st.success("Ready Design added to the Job Card.")
    except (ValueError, ZeroDivisionError) as e:
        st.error(f"Calculation Error: {e}")
    except Exception as e:
        st.error(f"An error occurred: {e}")

def render_ready_design_entry_fields():
    """Renders the fields for adding a single ready design detail."""
    st.markdown("--- ")
    st.markdown("<h5>Add Design Details (Ready)</h5>", unsafe_allow_html=True)

    # Fetch the next ready card number if it's not already in the session
    if 'ready_card_no_generated' not in st.session_state:
        services = create_services()
        # Ensure so_type is available, default to "CRNO" if not set yet (e.g., first run)
        material_type_for_ready = st.session_state.so_type if 'so_type' in st.session_state else "CRNO"
        st.session_state.ready_card_no_generated = services.sales_order.get_next_ready_card_number(material_type_for_ready)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.text_input("Card No.", value=st.session_state.ready_card_no_generated, key="ready_card_no", disabled=True)
        fm_name = st.selectbox("FM Name", options=[""] + list(FM_DATA.keys()), key="ready_fm_name")

    width = 0.0
    length = 0.0
    if fm_name:
        width = FM_DATA[fm_name]["width"]
        length = FM_DATA[fm_name]["length"]

    with col2:
        st.number_input("Width (mm)", value=width, disabled=True, format="%.2f", key="ready_width_display")
        st.number_input("Length (mm)", value=length, disabled=True, format="%.2f", key="ready_length_display")

    with col3:
        st.number_input("Thickness (mm)", min_value=0.0, step=0.01, format="%.2f", key="ready_thk")
        st.number_input("Weight (kg)", min_value=0.0, step=1.0, format="%.2f", key="ready_weight")

    if st.button("Add Ready Design to Order"):
        add_ready_design_to_state(width, length)

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



def handle_final_submission(service: SalesOrderService):
    """Handles the final submission of the entire sales order."""
    if not st.session_state.so_designs:
        st.error("Please add at least one design.")
        return

    # If coils are assigned, validate the weight
    if st.session_state.so_assigned_coils:
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
            coating=st.session_state.so_coating or None,
            designs=[DesignDetail(**d) for d in st.session_state.so_designs],
            assigned_coils=[AssignedCoil(**c) for c in st.session_state.so_assigned_coils]
        )
        with st.spinner("Saving full order..."):
            success = service.save_sales_order(request)
        if success:
            st.success(f"Sales Order {request.job_card_number} saved successfully!")
            service.invoke_power_automate_flow(request)
            time.sleep(2)
            load_dropdowns.clear()
            # Clear all relevant session state keys
            keys_to_clear = [key for key in st.session_state.keys() if key.startswith('so_') or key.startswith('design_') or key.startswith('assign_') or key.startswith('ready_')]
            for key in keys_to_clear:
                if key in st.session_state: del st.session_state[key]
            st.rerun()
        else:
            st.error("Failed to save the sales order.")
    except ValidationError as e:
        st.error(f"Final validation failed: {e}")

def render_full_coil_sale_form(service: SalesOrderService, dropdown_data):
    """Renders the form for Full Coil Sale."""
    st.markdown("<h5>Full Coil Sale Details</h5>", unsafe_allow_html=True)
    
    # Load dropdowns from RM Inward service
    @st.cache_resource(ttl=600)
    def load_rm_inward_dropdowns(_service: SalesOrderService):
        # We need to get the rm_inward_service from the AppServices
        app_services = create_services()
        return app_services.rm_inward.get_dropdown_data()

    rm_inward_dropdowns = load_rm_inward_dropdowns(service)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.checkbox("Enter Job Card Manually", key="fcs_manual_job_card")
        if not st.session_state.fcs_manual_job_card:
            if 'fcs_job_card_generated' not in st.session_state:
                # Ensure fcs_material_type is available, default to "CR COIL" if not set yet
                fcs_material_type = st.session_state.get('fcs_material_type', "CR COIL")
                st.session_state.fcs_job_card_generated = service.generate_full_coil_sale_job_card_number(fcs_material_type)
            st.text_input("Job Card", value=st.session_state.fcs_job_card_generated, key="fcs_job_card", disabled=True)
        else:
            st.text_input("Job Card", key="fcs_job_card")
        
        st.date_input("Order Entry Date", key="fcs_order_date")
        st.text_input("PO No. (Optional)", key="fcs_po_no")
        st.selectbox("Party Name", options=dropdown_data.party_names, index=None, placeholder="Select a Party", key="fcs_party_name", accept_new_options=True)
        
        material_type_options = ["CR COIL", "CRGO EI", "CRNO", "CRNO COIL", "CRNO EI", "CRNO EI TRD", "CRNO TL"]
        st.selectbox("Material Type", options=material_type_options, index=None, placeholder="Select or type a Material Type", key="fcs_material_type", accept_new_options=True)

    with col2:
        st.selectbox("Width (mm)", options=rm_inward_dropdowns.widths, index=None, placeholder="Select or type a Width", key="fcs_width", accept_new_options=True)
        st.number_input("Quantity (kg)", min_value=0.0, step=1.00, format="%.2f", key="fcs_qty")
        st.selectbox("Thk (mm)", options=rm_inward_dropdowns.thks, index=None, placeholder="Select or type a Thk", key="fcs_thk", accept_new_options=True)
        st.number_input("Rate (per Kg)", min_value=0.0, step=1.00, format="%.2f", key="fcs_rate")
        
    with col3:
        st.date_input("Delivery Date", key="fcs_delivery_date")
        st.selectbox("Grade", options=rm_inward_dropdowns.grades, index=None, placeholder="Select or type a Grade", key="fcs_grade", accept_new_options=True)
        st.selectbox("Coating (Optional)", options=rm_inward_dropdowns.coatings, index=None, placeholder="Select a Coating", key="fcs_coating", accept_new_options=True)
        st.text_input("Remark (Optional)", key="fcs_remark")

    st.markdown("---")
    if st.button("Save Full Coil Sale"):
        try:
            from src.data_entry.models.sales_order_models import FullCoilSaleRequest
            
            job_card = st.session_state.fcs_job_card_generated if not st.session_state.fcs_manual_job_card else st.session_state.fcs_job_card

            request = FullCoilSaleRequest(
                job_card=job_card,
                order_date=st.session_state.fcs_order_date,
                po_no=st.session_state.fcs_po_no,
                party_name=st.session_state.fcs_party_name,
                width=float(st.session_state.fcs_width),
                qty=st.session_state.fcs_qty,
                material_type=st.session_state.fcs_material_type,
                thk=float(st.session_state.fcs_thk),
                rate=st.session_state.fcs_rate,
                delivery_date=st.session_state.fcs_delivery_date,
                remark=st.session_state.fcs_remark,
                grade=st.session_state.fcs_grade,
                coating=st.session_state.fcs_coating
            )
            with st.spinner("Saving Full Coil Sale order..."):
                success = service.save_full_coil_sale(request)
            if success:
                st.success(f"Full Coil Sale {request.job_card} saved successfully!")
                time.sleep(2)
                # Clear relevant session state keys for FCS
                keys_to_clear = [key for key in st.session_state.keys() if key.startswith('fcs_')]
                for key in keys_to_clear:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()
            else:
                st.error("Failed to save the Full Coil Sale order.")
        except ValidationError as e:
            st.error(f"Validation failed: {e}")
        except Exception as e:
            st.error(f"An error occurred: {e}")


@st.cache_resource(ttl=600)
def load_dropdowns(_service: SalesOrderService):
    return _service.get_dropdown_data()

def render_sales_order_form() -> None:
    """Renders the main Sales Order entry form."""
    # if st.session_state.get('clear_cache_for_data_entry'):
    #     st.session_state['clear_cache_for_data_entry'] = False
    #     try:
    #         load_dropdowns.clear()
    #         st.toast("Sales Order cache cleared!")
    #     except NameError:
    #         pass

    services = create_services()
    initialize_session_state()

    dropdown_data = load_dropdowns(services.sales_order)

    st.subheader("Sales Order Entry")
    order_type = st.radio(
        "Select Order Type",
        ("Standard Manufacturing", "Full Coil Sale"),
        key="order_type_selector",
        horizontal=True
    )

    if order_type == "Standard Manufacturing":
        render_header_fields(dropdown_data)
        
        st.checkbox("Entry Type: Ready", key="so_is_ready_entry")
        
        if st.session_state.get("so_party_name"):
            if st.session_state.so_is_ready_entry:
                render_ready_design_entry_fields()
            else:
                render_design_entry_fields()
            
            render_designs_table()
            
            st.markdown("---")
            if st.checkbox("Show/Hide Coil Assignment", key="so_show_coil_assigner"):
                render_coil_assignment_fields(services.slitting_plan)
                render_assigned_coils_table()
            
            st.markdown("---")
            if st.button("Save Full Sales Order"):
                handle_final_submission(services.sales_order)
    elif order_type == "Full Coil Sale":
        render_full_coil_sale_form(services.sales_order, dropdown_data)