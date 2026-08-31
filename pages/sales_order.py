import streamlit as st
from datetime import datetime
from pydantic import ValidationError
import pandas as pd
import time
import json

from pages.shared.utils import get_services
from src.services import SalesOrderService
from src.data_entry.models.sales_order_models import SalesOrderRequest, DesignDetail, AssignedCoil
from config import settings
from pages.sales_order_components import render_coil_assignment_fields, render_assigned_coils_table
from src.shared.utils.logger_config import setup_logger
from src.pdf_generator import hole_layout

logger = setup_logger(__name__)

CUSTOM_HOLE_LABEL = "Custom count..."

# Shortcuts only. The job card PDF draws any "<n>-Hole" value, so a count that
# is not listed here still renders — this list is what people reach for most.
HOLE_OPTIONS = [
    "Plain", "Centre", "Both Side", "Side",
    "3-Hole", "4-Hole", "5-Hole",
    "Daimond", "V-Noch",
    CUSTOM_HOLE_LABEL,
]


def _resolve_hole(selection_key: str) -> str:
    """Read a hole selection back out of session state as a storable value.

    The dropdown itself holds the literal "Custom count..." label, which must
    never reach the sheet — the count beside it is the real answer.
    """
    selection = st.session_state.get(selection_key, "Plain")
    if selection != CUSTOM_HOLE_LABEL:
        return selection

    count = st.session_state.get(f"{selection_key}_count", 4)
    return f"{int(count)}-Hole"


def _render_hole_selector(selection_key: str) -> str:
    """Hole dropdown, plus the count input that the Custom option reveals."""
    st.selectbox("Hole", options=HOLE_OPTIONS, key=selection_key)
    if st.session_state.get(selection_key) == CUSTOM_HOLE_LABEL:
        st.number_input(
            "Number of holes",
            min_value=1, max_value=hole_layout.MAX_HOLES, value=4, step=1,
            key=f"{selection_key}_count",
            help=(
                f"1 to {hole_layout.MAX_HOLES}. Drawn evenly across the plate on "
                "the job card; above about seven the circles shrink to fit."
            ),
        )
    return _resolve_hole(selection_key)

@st.dialog("Confirm Sales Order Save", width="large")
def _show_sales_order_confirmation_dialog(service: SalesOrderService, request_data: dict, total_design_weight: float, total_coil_weight: float, is_weight_mismatched: bool):
    """Shows a modal to confirm sales order details before saving."""
    st.markdown("Please review the Sales Order details before submitting.")
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Job Card:** {request_data.get('job_card_number')}")
        st.markdown(f"**Party:** {request_data.get('party_name')}")
        st.markdown(f"**Order Date:** {request_data.get('order_date')}")
        st.markdown(f"**Designs:** {len(request_data.get('designs', []))}")
    with col2:
        st.metric("Total Design Weight", f"{total_design_weight:.2f} kg")
        if request_data.get('assigned_coils'):
            st.metric("Assigned Coil Weight", f"{total_coil_weight:.2f} kg", 
                      delta=f"{total_coil_weight - total_design_weight:.2f} kg" if not is_weight_mismatched else "Mismatch (>1%)",
                      delta_color="normal" if not is_weight_mismatched else "inverse")
            
    if is_weight_mismatched:
        st.error(f"Weight Mismatch: Total assigned coil weight ({total_coil_weight:.2f} kg) is not within 1% of the total design weight ({total_design_weight:.2f} kg).")
        
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Confirm Submit", type="primary", use_container_width=True, disabled=is_weight_mismatched):
            st.session_state.so_submit_confirmed = True
            st.rerun()
    with c2:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.so_submit_confirmed = False
            st.session_state.so_save_lock = 0
            st.rerun()

@st.dialog("Confirm Full Coil Sale", width="large")
def _show_fcs_confirmation_dialog(service: SalesOrderService, request_data: dict):
    """Shows a modal to confirm full coil sale details before saving."""
    st.markdown("Please review the Full Coil Sale details before submitting.")
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Job Card:** {request_data.get('job_card')}")
        st.markdown(f"**Party:** {request_data.get('party_name')}")
        st.markdown(f"**Material Type:** {request_data.get('material_type')}")
    with col2:
        st.metric("Quantity", f"{request_data.get('qty'):.2f} kg")
        st.markdown(f"**Width:** {request_data.get('width')} mm")
        st.markdown(f"**Thickness:** {request_data.get('thk')} mm")
        
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Confirm Submit", type="primary", use_container_width=True):
            st.session_state.fcs_submit_confirmed = True
            st.rerun()
    with c2:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.fcs_submit_confirmed = False
            st.session_state.fcs_save_lock = 0
            st.rerun()

@st.dialog("Confirm Sales Order Update", width="large")
def _show_upd_confirmation_dialog(job_card: str, validated_designs: list):
    """Shows a modal to confirm sales order updates before saving."""
    st.markdown(f"**Update Job Card:** {job_card}")
    st.markdown("Please review the updated designs below before submitting.")
    st.markdown("---")
    
    # Show preview table
    df = pd.DataFrame([d.model_dump() for d in validated_designs])
    display_cols = ['width', 'length', 'weight', 'sets', 'hole', 'thk', 'remark']
    display_df = df[[c for c in display_cols if c in df.columns]].copy()
    display_df.columns = ['Width (mm)', 'Length (mm)', 'Weight (kg)', 'Sets', 'Hole', 'Thk (mm)', 'Remark']
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Confirm Update", type="primary", use_container_width=True):
            st.session_state.upd_submit_confirmed = True
            st.rerun()
    with c2:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.upd_submit_confirmed = False
            st.session_state.upd_save_lock = 0
            st.rerun()



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
    if 'so_job_card_material_type' not in st.session_state:
        st.session_state.so_job_card_material_type = None

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
        st.selectbox("Party Name", options=dropdown_data.all_party_names, index=None, placeholder="Select a Party", key="so_party_name", accept_new_options=True)
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
        st.text_input("Job Card Number", value=st.session_state.so_job_card_number, disabled=True)
        st.number_input("Number of Cores", min_value=0, step=1, key="so_num_cores")
        st.number_input("Header Core Stack (mm)", min_value=0.0, step=1.0, format="%.1f", key="so_header_core_stack")
        st.text_input("Grade (Optional)", key="so_grade")
        st.selectbox("Coating (Optional)", options=dropdown_data.coatings, index=None, placeholder="Select a Coating", key="so_coating")
        
        # Display order type badge
        order_type = "EI Ready" if st.session_state.get("so_is_ready_entry") else ("Loose Strips" if st.session_state.get("so_num_cores", 1) == 0 else "Core Building")
        badge_color = "🟢" if order_type == "Core Building" else ("🟡" if order_type == "Loose Strips" else "🔵")
        st.markdown(f"**Order Type:** {badge_color} {order_type}")

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
        is_loose = st.checkbox("Calculate from Weight", key="design_is_loose")
    with col3:
        _render_hole_selector("design_hole")
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
            mm_stack = round((stack_per_set_m * 1000) * num_sets, 2)
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
            grade=st.session_state.so_grade or None, hole=_resolve_hole("design_hole"),
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
            party_job_no=st.session_state.so_job_card_number,
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

    col1, col2, col3 = st.columns(3)

    with col1:
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



def _clear_so_form_state():
    """Clears all sales order form state keys, preserving the save lock to block rapid clicks."""
    lock_keys = {'so_save_lock', 'fcs_save_lock', 'so_save_in_flight', 'so_save_completed'}
    keys_to_clear = [key for key in list(st.session_state.keys())
                     if (key.startswith('so_') or key.startswith('design_') or key.startswith('assign_') or key.startswith('ready_'))
                     and key not in lock_keys]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]


def handle_final_submission(service: SalesOrderService):
    """Handles the final submission of the entire sales order."""
    run_id = f"{time.time():.3f}"
    logger.info(f"[SO-SAVE][{run_id}] handle_final_submission ENTERED")

    # If the user has explicitly confirmed in the dialog
    if st.session_state.pop("so_submit_confirmed", False) and "pending_so_request" in st.session_state:
        request_data = st.session_state.pop("pending_so_request")
        try:
            request = SalesOrderRequest(**request_data)

            # Mark save as in-flight BEFORE the API call.
            st.session_state.so_save_in_flight = request.model_dump(mode='json')
            logger.info(f"[SO-SAVE][{run_id}] Calling save_sales_order for {request.job_card_number}...")

            with st.spinner("Saving full order..."):
                success = service.save_sales_order(request)
            logger.info(f"[SO-SAVE][{run_id}] save_sales_order returned success={success}")

            if success:
                st.session_state.so_save_completed = st.session_state.pop('so_save_in_flight', None)
                st.success(f"Sales Order {request.job_card_number} saved successfully!")
                logger.info(f"[SO-SAVE][{run_id}] Calling invoke_power_automate_flow for {request.job_card_number}...")
                service.invoke_power_automate_flow(request)
                logger.info(f"[SO-SAVE][{run_id}] PA completed for {request.job_card_number}")

                st.session_state.pop('so_save_completed', None)
                logger.info(f"[SO-SAVE][{run_id}] Clearing state and rerunning...")
                load_dropdowns.clear()
                _clear_so_form_state()
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.pop('so_save_in_flight', None)
                st.session_state.so_save_lock = 0
                logger.warning(f"[SO-SAVE][{run_id}] save_sales_order returned False")
                st.error("Failed to save the sales order.")
        except ValidationError as e:
            st.session_state.pop('so_save_in_flight', None)
            st.session_state.so_save_lock = 0
            logger.error(f"[SO-SAVE][{run_id}] ValidationError: {e}")
            st.error(f"Final validation failed: {e}")
        except Exception as e:
            st.session_state.pop('so_save_in_flight', None)
            st.session_state.so_save_lock = 0
            logger.error(f"[SO-SAVE][{run_id}] Exception: {e}")
            st.error("A temporary error occurred (possibly rate limit). Please try saving again.")
        return

    # Initial click on 'Save Full Sales Order'
    current_time = time.time()
    lock_age = current_time - st.session_state.get('so_save_lock', 0)
    logger.info(f"[SO-SAVE][{run_id}] Lock check: age={lock_age:.1f}s, locked={'YES' if lock_age < 30 else 'NO'}")
    if lock_age < 30:
        st.warning("Save already in progress. Please wait...")
        st.stop()
    st.session_state.so_save_lock = current_time

    if not st.session_state.so_designs:
        logger.info(f"[SO-SAVE][{run_id}] Early return: no designs")
        st.session_state.so_save_lock = 0
        if not st.session_state.get('so_save_success_msg'):
            st.error("Please add at least one design.")
        return

    # Calculate weights for dialog
    total_design_weight = sum(d.get('weight', 0) for d in st.session_state.so_designs)
    total_coil_weight = sum(c.get('weight_used', 0) for c in st.session_state.so_assigned_coils)
    is_weight_mismatched = False

    if st.session_state.so_assigned_coils:
        lower_bound = total_design_weight * 0.99
        upper_bound = total_design_weight * 1.01
        if not (lower_bound <= total_coil_weight <= upper_bound):
            is_weight_mismatched = True

    try:
        request_data = {
            "order_date": st.session_state.so_order_date,
            "po_no": st.session_state.so_po_no,
            "party_name": st.session_state.so_party_name,
            "delivery_date": st.session_state.so_delivery_date,
            "job_card_number": st.session_state.so_job_card_number,
            "hole_size": st.session_state.so_hole_size,
            "number_of_cores": st.session_state.so_num_cores,
            "rate_per_kg": st.session_state.so_rate_per_kg,
            "header_core_stack": st.session_state.so_header_core_stack,
            "coating": st.session_state.so_coating or None,
            "designs": st.session_state.so_designs,
            "assigned_coils": st.session_state.so_assigned_coils,
        }
        
        # Store for dialog and open it
        st.session_state.pending_so_request = request_data
        _show_sales_order_confirmation_dialog(service, request_data, total_design_weight, total_coil_weight, is_weight_mismatched)
        
    except Exception as e:
        st.session_state.so_save_lock = 0
        logger.error(f"[SO-SAVE][{run_id}] Exception preparing dialog: {e}")
        st.error(f"Error preparing save: {e}")

def render_full_coil_sale_form(service: SalesOrderService, dropdown_data):
    """Renders the form for Full Coil Sale."""
    st.markdown("<h5>Full Coil Sale Details</h5>", unsafe_allow_html=True)
    
    # Initialize a tracker for the material type used in this form
    if 'fcs_material_type_for_jc' not in st.session_state:
        st.session_state.fcs_material_type_for_jc = None
    
    # Load dropdowns from RM Inward service
    @st.cache_resource(ttl=600)
    def load_rm_inward_dropdowns(_service: SalesOrderService):
        app_services = get_services()
        return app_services.rm_inward.get_dropdown_data()

    rm_inward_dropdowns = load_rm_inward_dropdowns(service)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.date_input("Order Entry Date", key="fcs_order_date")
        st.selectbox("Party Name", options=dropdown_data.all_party_names, index=None, placeholder="Select a Party", key="fcs_party_name", accept_new_options=True)
        
        material_type_options = ["CR COIL", "CRGO EI", "CRNO", "CRNO COIL", "CRNO EI", "CRNO EI TRD", "CRNO TL"]
        st.selectbox("Material Type", options=material_type_options, index=0, key="fcs_material_type", accept_new_options=True)
        
        st.checkbox("Enter Job Card Manually", key="fcs_manual_job_card")

        # --- Unified Job Card Generation ---
        if not st.session_state.fcs_manual_job_card:
            current_fcs_type = st.session_state.get('fcs_material_type')
            previous_fcs_type = st.session_state.fcs_material_type_for_jc
            
            # Regenerate if type changes or if it was never generated
            if (current_fcs_type and previous_fcs_type != current_fcs_type) or 'fcs_job_card_generated' not in st.session_state:
                if current_fcs_type: # Ensure a type is selected
                    st.session_state.fcs_job_card_generated = service.generate_sequential_job_card_number(current_fcs_type)
                    st.session_state.fcs_material_type_for_jc = current_fcs_type
            
            st.text_input("Job Card", value=st.session_state.get('fcs_job_card_generated', ""), key="fcs_job_card", disabled=True)
        else:
            st.text_input("Job Card", key="fcs_job_card")
        
        st.text_input("PO No. (Optional)", key="fcs_po_no")

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
    
    # If the user has explicitly confirmed in the dialog
    if st.session_state.pop("fcs_submit_confirmed", False) and "pending_fcs_request" in st.session_state:
        request_data = st.session_state.pop("pending_fcs_request")
        try:
            from src.data_entry.models.sales_order_models import FullCoilSaleRequest
            request = FullCoilSaleRequest(**request_data)
            
            with st.spinner("Saving Full Coil Sale order..."):
                success = service.save_full_coil_sale(request)
            if success:
                st.success(f"Full Coil Sale {request.job_card} saved successfully!")
                st.session_state.fcs_save_lock = 0
                time.sleep(2)
                # Clear relevant session state keys for FCS
                keys_to_clear = [key for key in st.session_state.keys() if key.startswith('fcs_')]
                for key in keys_to_clear:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()
            else:
                st.session_state.fcs_save_lock = 0
                st.error("Failed to save the Full Coil Sale order.")
        except ValidationError as e:
            st.session_state.fcs_save_lock = 0
            st.error(f"Validation failed: {e}")
        except Exception as e:
            st.session_state.fcs_save_lock = 0
            st.error(f"An error occurred: {e}")

    # Initial click on Save
    elif st.button("Save Full Coil Sale"):
        current_time = time.time()
        if current_time - st.session_state.get('fcs_save_lock', 0) < 30:
            st.warning("Save already in progress. Please wait...")
            st.stop()
        st.session_state.fcs_save_lock = current_time

        job_card = st.session_state.fcs_job_card_generated if not st.session_state.fcs_manual_job_card else st.session_state.fcs_job_card
        
        if not st.session_state.fcs_width or not st.session_state.fcs_thk:
            st.session_state.fcs_save_lock = 0
            st.error("Please provide both Width and Thickness.")
            return

        request_data = {
            "job_card": job_card,
            "order_date": st.session_state.fcs_order_date,
            "po_no": st.session_state.fcs_po_no,
            "party_name": st.session_state.fcs_party_name,
            "width": float(st.session_state.fcs_width),
            "qty": st.session_state.fcs_qty,
            "material_type": st.session_state.fcs_material_type,
            "thk": float(st.session_state.fcs_thk),
            "rate": st.session_state.fcs_rate,
            "delivery_date": st.session_state.fcs_delivery_date,
            "remark": st.session_state.fcs_remark,
            "grade": st.session_state.fcs_grade,
            "coating": st.session_state.fcs_coating
        }
        
        st.session_state.pending_fcs_request = request_data
        _show_fcs_confirmation_dialog(service, request_data)


def render_update_sales_order(service: SalesOrderService, dropdown_data):
    """Renders the Update Sales Order section for editing existing designs."""
    # --- Session State Initialization ---
    if 'upd_designs' not in st.session_state:
        st.session_state.upd_designs = []
    if 'upd_jc_data' not in st.session_state:
        st.session_state.upd_jc_data = None
    if 'upd_loaded_jc' not in st.session_state:
        st.session_state.upd_loaded_jc = None
    if 'upd_save_lock' not in st.session_state:
        st.session_state.upd_save_lock = 0

    # --- Recovery: handle a save that completed but was interrupted before rerun ---
    # If upd_save_completed is set, the API call succeeded. We clear all form state
    # here (on the next render cycle) to guarantee a clean slate.
    if st.session_state.pop('upd_save_completed', None):
        st.session_state.upd_save_lock = 0
        st.session_state.upd_loaded_jc = None
        st.session_state.upd_designs = []
        st.session_state.upd_jc_data = None
        load_dropdowns.clear()
        st.toast("Sales Order updated successfully!", icon="✅")
        st.rerun()

    # --- Step 1: Select Party Name ---
    upd_party = st.selectbox(
        "Party Name",
        options=dropdown_data.active_party_names,
        index=None,
        placeholder="Select a Party to update",
        key="upd_party_name"
    )

    if not upd_party:
        st.info("Select a Party Name to load their Sales Orders.")
        return

    # --- Step 2: Fetch and Select Job Card ---
    with st.spinner("Loading job cards..."):
        job_cards = service.get_sales_orders_by_party(upd_party)

    if not job_cards:
        st.warning("No Sales Orders found for this party.")
        return

    jc_options = {jc.get('job_card_number', 'N/A'): jc for jc in job_cards}
    selected_jc_key = st.selectbox(
        "Select Job Card to Update",
        options=[""] + list(jc_options.keys()),
        key="upd_selected_jc"
    )

    if not selected_jc_key:
        return

    selected_jc = jc_options[selected_jc_key]

    # Load designs when a new JC is selected
    if st.session_state.upd_loaded_jc != selected_jc_key:
        try:
            designs_raw = json.loads(selected_jc.get('designs_json', '[]'))
        except (json.JSONDecodeError, TypeError):
            designs_raw = []
        st.session_state.upd_designs = designs_raw
        st.session_state.upd_jc_data = selected_jc
        st.session_state.upd_loaded_jc = selected_jc_key

    # --- Step 3: Display Order Header (Read-Only) ---
    st.markdown("---")
    st.markdown("<h6>Order Details (Read-Only)</h6>", unsafe_allow_html=True)
    hcol1, hcol2, hcol3, hcol4 = st.columns(4)
    hcol1.text_input("Job Card", value=selected_jc_key, disabled=True, key="upd_disp_jc")
    hcol2.text_input("Order Date", value=str(selected_jc.get('order_date', '')), disabled=True, key="upd_disp_date")
    hcol3.text_input("PO No.", value=str(selected_jc.get('po_no', '')), disabled=True, key="upd_disp_po")
    hcol4.text_input("Rate/Kg", value=str(selected_jc.get('rate_per_kg', '')), disabled=True, key="upd_disp_rate")

    # --- Step 4: Editable Designs Table ---
    st.markdown("---")
    st.markdown("<h6>Edit Existing Designs</h6>", unsafe_allow_html=True)

    if not st.session_state.upd_designs:
        st.info("No designs found for this Job Card.")
    else:
        df = pd.DataFrame(st.session_state.upd_designs)

        # Define which columns are editable and their display config
        editable_columns = ['width', 'length', 'weight', 'mm_stack', 'sets', 'hole', 'thk', 'remark']
        column_config = {
            "width": st.column_config.NumberColumn("Width (mm)", format="%.2f"),
            "length": st.column_config.NumberColumn("Length (mm)", format="%.2f"),
            "weight": st.column_config.NumberColumn("Weight (kg)", format="%.2f"),
            "mm_stack": st.column_config.NumberColumn("Stack (mm)", format="%.1f"),
            "sets": st.column_config.NumberColumn("Sets", format="%d"),
            "hole": st.column_config.TextColumn("Hole"),
            "thk": st.column_config.NumberColumn("Thickness (mm)", format="%.2f"),
            "remark": st.column_config.TextColumn("Remark"),
            "pcs": st.column_config.NumberColumn("Pieces", disabled=True),
            "type": st.column_config.TextColumn("Type", disabled=True),
            "party_job_no": st.column_config.TextColumn("Party Job No", disabled=True),
            "grade": st.column_config.TextColumn("Grade", disabled=True),
            "coating": st.column_config.TextColumn("Coating", disabled=True),
            "fm_name": st.column_config.TextColumn("FM Name", disabled=True),
        }

        # Only show columns that exist in the data
        visible_columns = [c for c in ['width', 'length', 'weight', 'mm_stack', 'sets', 'hole', 'thk', 'remark', 'pcs', 'type'] if c in df.columns]

        # Cast string columns to str so pandas doesn't infer None as float64,
        # which would make TextColumn incompatible with the underlying dtype.
        for str_col in ['remark', 'hole', 'type']:
            if str_col in df.columns:
                df[str_col] = df[str_col].fillna('').astype(str)

        edited_df = st.data_editor(
            df[visible_columns] if visible_columns else df,
            num_rows="dynamic",
            key="upd_designs_editor",
            use_container_width=True,
            column_config=column_config
        )

        # Sync edits back — merge edited columns into the full design dicts
        if len(edited_df) != len(st.session_state.upd_designs):
            # Rows were added or deleted via data_editor
            st.session_state.upd_designs = edited_df.to_dict('records')
            st.rerun()
        else:
            # Update existing rows with edits
            for i, row in edited_df.iterrows():
                if i < len(st.session_state.upd_designs):
                    for col in editable_columns:
                        if col in row:
                            st.session_state.upd_designs[i][col] = row[col]

    # --- Step 5: Add New Design Sub-Form ---
    st.markdown("---")
    with st.expander("➕ Add New Design"):
        nc1, nc2, nc3, nc4 = st.columns(4)
        with nc1:
            new_width = st.number_input("Width (mm)", min_value=0.0, step=1.0, format="%.2f", key="upd_new_width")
            new_sets = st.number_input("Sets", min_value=1, step=1, key="upd_new_sets")
        with nc2:
            new_length = st.number_input("Length (mm)", min_value=0.0, step=1.0, format="%.2f", key="upd_new_length")
            new_thk = st.number_input("Thickness (mm)", min_value=0.0, step=0.01, format="%.2f", key="upd_new_thk")
        with nc3:
            new_hole = _render_hole_selector("upd_new_hole")
            new_weight = st.number_input("Weight (kg)", min_value=0.0, step=1.0, format="%.2f", key="upd_new_weight")
        with nc4:
            new_mm_stack = st.number_input("Stack (mm)", min_value=0.0, step=1.0, format="%.1f", key="upd_new_mm_stack")
            new_remark = st.text_input("Remark (Optional)", key="upd_new_remark")

        if st.button("Add Design", key="upd_add_design_btn"):
            if new_width <= 0 or new_length <= 0:
                st.error("Width and Length must be greater than zero.")
            elif new_thk <= 0:
                st.error("Thickness must be greater than zero.")
            else:
                # Calculate pcs from mm_stack and thk
                pcs = int(new_mm_stack / new_thk) if new_thk > 0 and new_mm_stack > 0 else 0

                # Infer type from the first existing design, or default
                design_type = "CRNO"
                if st.session_state.upd_designs:
                    design_type = st.session_state.upd_designs[0].get('type', 'CRNO')

                new_design = {
                    'width': new_width,
                    'length': new_length,
                    'weight': new_weight,
                    'mm_stack': new_mm_stack,
                    'sets': new_sets,
                    'hole': new_hole,
                    'thk': new_thk,
                    'pcs': pcs,
                    'type': design_type,
                    'remark': new_remark or None,
                    'party_job_no': None,
                    'fm_name': None,
                    'grade': None,
                    'coating': None,
                }
                st.session_state.upd_designs.append(new_design)
                st.success("New design added. Review the table above and click 'Save Changes' when ready.")
                st.rerun()

    # --- Step 6: Save Changes ---
    st.markdown("---")
    
    if st.session_state.pop("upd_submit_confirmed", False) and "pending_upd_request" in st.session_state:
        request_data = st.session_state.pop("pending_upd_request")
        validated_designs = request_data['validated_designs']
        selected_jc_key = request_data['selected_jc_key']
        
        try:
            # Set the recovery flag BEFORE the API call.
            st.session_state.upd_save_completed = True

            with st.spinner("Saving changes to Sales Order..."):
                success = service.update_sales_order_designs(
                    job_card_number=selected_jc_key,
                    updated_designs=validated_designs,
                    jc_data=st.session_state.upd_jc_data
                )

            if success:
                st.session_state.pop('upd_save_completed', None)
                st.session_state.upd_save_lock = 0
                load_dropdowns.clear()
                st.cache_data.clear()
                st.session_state.upd_loaded_jc = None
                st.session_state.upd_designs = []
                st.session_state.upd_jc_data = None
                st.success(f"✅ Sales Order {selected_jc_key} updated successfully! Go to Weight Receipt to weigh new/updated designs.")
                time.sleep(2)
                st.rerun()
            else:
                st.session_state.pop('upd_save_completed', None)
                st.session_state.upd_save_lock = 0
                st.error("Failed to save changes. Please check the logs and try again.")
        except Exception:
            st.session_state.pop('upd_save_completed', None)
            st.session_state.upd_save_lock = 0
            st.error("A temporary error occurred (possibly rate limit). Please try saving again.")

    elif st.button("💾 Save Changes", key="upd_save_btn", type="primary"):
        if not st.session_state.upd_designs:
            st.error("Cannot save with no designs. Please add at least one design.")
            return

        # Guard: prevent double-click from triggering a second delete+re-insert
        current_time = time.time()
        if current_time - st.session_state.upd_save_lock < 30:
            st.warning("Save already in progress. Please wait...", icon="⏳")
            st.stop()
        st.session_state.upd_save_lock = current_time

        # Validate designs before touching the sheets
        try:
            validated_designs = []
            for d in st.session_state.upd_designs:
                validated_designs.append(DesignDetail(
                    width=float(d.get('width', 0)),
                    length=float(d.get('length', 0)),
                    weight=float(d.get('weight', 0)) if d.get('weight') else None,
                    mm_stack=float(d.get('mm_stack', 0)) if d.get('mm_stack') else None,
                    sets=int(d.get('sets', 1)),
                    hole=str(d.get('hole', 'Plain')),
                    thk=float(d.get('thk', 0)),
                    pcs=int(d.get('pcs', 0)),
                    type=str(d.get('type', 'CRNO')),
                    remark=d.get('remark') or None,
                    party_job_no=d.get('party_job_no') or None,
                    fm_name=d.get('fm_name') or None,
                    grade=d.get('grade') or None,
                    coating=d.get('coating') or None,
                ))
        except (ValidationError, ValueError) as e:
            st.session_state.upd_save_lock = 0
            st.error(f"Design validation failed: {e}")
            return

        st.session_state.pending_upd_request = {
            'selected_jc_key': selected_jc_key,
            'validated_designs': validated_designs
        }
        _show_upd_confirmation_dialog(selected_jc_key, validated_designs)


@st.cache_resource(ttl=600)
def load_dropdowns(_service: SalesOrderService):
    return _service.get_dropdown_data()

def render_sales_order_form() -> None:
    """Renders the main Sales Order entry form."""
    services = get_services()

    # --- Recovery: handle interrupted save operations ---
    # Both cases: clear form state FIRST (instant), THEN call PA (slow HTTP call).
    # This order is critical because Streamlit can interrupt the script at any time
    # when more clicks arrive. The form must be clean before we attempt the slow PA call.
    # Even if the PA call is interrupted, the HTTP request is already dispatched and
    # will complete server-side — same pattern as the save itself.
    save_data = st.session_state.pop('so_save_completed', None) or st.session_state.pop('so_save_in_flight', None)
    if save_data:
        job_card = save_data.get('job_card_number', 'unknown')
        logger.info(f"[SO-RECOVERY] Recovering interrupted save for {job_card}. Clearing form first, then calling PA.")
        load_dropdowns.clear()
        _clear_so_form_state()
        # Reset the lock so queued clicks don't hit st.stop() and freeze the screen
        st.session_state.so_save_lock = 0
        try:
            pa_request = SalesOrderRequest(**save_data)
            services.sales_order.invoke_power_automate_flow(pa_request)
            logger.info(f"[SO-RECOVERY] PA call completed for {job_card}")
        except Exception as e:
            logger.error(f"[SO-RECOVERY] PA call failed for {job_card}: {e}")
        st.session_state.so_save_success_msg = f"Sales Order {job_card} saved successfully!"
        st.rerun()

    # Show success message from a recovered save (survives queued reruns)
    success_msg = st.session_state.pop('so_save_success_msg', None)
    if success_msg:
        st.success(success_msg)

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
        if st.session_state.get("so_party_name"):
            current_material_type = st.session_state.so_type
            previous_material_type = st.session_state.so_job_card_material_type
            
            if previous_material_type != current_material_type:
                try:
                    new_job_card = services.sales_order.generate_sequential_job_card_number(current_material_type)
                    st.session_state.so_job_card_number = new_job_card
                    st.session_state.so_job_card_material_type = current_material_type
                except Exception as e:
                    st.error(f"Error generating job card number: {e}")

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
            if st.session_state.get("so_submit_confirmed", False) or st.button("Save Full Sales Order"):
                handle_final_submission(services.sales_order)
    elif order_type == "Full Coil Sale":
        render_full_coil_sale_form(services.sales_order, dropdown_data)

    # --- Update Sales Order Section ---
    st.markdown("---")
    with st.expander("📝 Update Sales Order"):
        render_update_sales_order(services.sales_order, dropdown_data)