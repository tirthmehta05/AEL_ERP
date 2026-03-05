import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import time
from pages.shared.utils import get_services
from src.services import SalesOrderService
from src.data_entry.models.weight_receipt_models import WeightReceiptRequest, WeighedDesignDetail
from src.shared.utils.logger_config import setup_logger
from config import settings

logger = setup_logger(__name__)


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
    if 'wr_design_deductions' not in st.session_state:
        st.session_state.wr_design_deductions = {}
    if 'wr_selected_designs' not in st.session_state:
        st.session_state.wr_selected_designs = set()
    if 'wr_total_weight' not in st.session_state:
        st.session_state.wr_total_weight = 0.0
    if 'current_jc_for_wr' not in st.session_state:
        st.session_state.current_jc_for_wr = None
    if 'wr_core_remark' not in st.session_state:
        st.session_state.wr_core_remark = ""
    if 'wr_save_locks' not in st.session_state:
        st.session_state.wr_save_locks = {}
    if 'wr_design_sets' not in st.session_state:
        st.session_state.wr_design_sets = {}
    if 'wr_is_manual_entry' not in st.session_state:
        st.session_state.wr_is_manual_entry = False
    if 'wr_pending_save' not in st.session_state:
        st.session_state.wr_pending_save = None

def _is_manual_entry_authorized():
    """Check if the current user is authorized for manual weight entry."""
    user_email = st.session_state.get('user_info', {}).get('username', '')
    authorized = [e.lower() for e in settings.weight_receipt.manual_entry_authorized_emails]
    return user_email.lower() in authorized


@st.dialog("Confirm Weight Receipt Save", width="large")
def _show_save_confirmation_dialog(candidate_designs, job_card_number, party_name):
    """
    Shows a modal dialog with all weighed designs for the user to review
    and optionally deselect before saving. This is the final selection
    step — the grid checkboxes are only used for weighing.
    """
    st.markdown(f"**Job Card:** {job_card_number} &nbsp; | &nbsp; **Party:** {party_name}")
    st.markdown("Review the designs below. **Uncheck** any you don't want to save.")
    st.markdown("---")

    # Header row
    cols = st.columns([0.8, 1, 1, 1, 1.5, 1.5, 2])
    for col, header in zip(cols, ["Save", "Sets", "Width", "Length", "Actual Wt.", "Deduction", "Remark"]):
        col.markdown(f"**{header}**")

    confirmed_indices = []
    total_weight = 0.0
    total_deduction = 0.0

    for item in candidate_designs:
        c1, c2, c3, c4, c5, c6, c7 = st.columns([0.8, 1, 1, 1, 1.5, 1.5, 2])
        with c1:
            include = st.checkbox(
                "Include",
                value=True,
                key=f"confirm_sel_{item['original_index']}",
                label_visibility="collapsed"
            )
        with c2:
            st.text(f"{item['sets']}")
        with c3:
            st.text(f"{item['width']}")
        with c4:
            st.text(f"{item['length']}")
        with c5:
            st.text(f"{item['actual_weight']:.2f}")
        with c6:
            st.text(f"{item['design_deduction']:.2f}")
        with c7:
            st.text(item['remark'] or "")

        if include:
            confirmed_indices.append(item['original_index'])
            total_weight += item['actual_weight']
            total_deduction += item['design_deduction']

    st.markdown("---")
    net_weight = total_weight - total_deduction
    summary_cols = st.columns(3)
    summary_cols[0].metric("Total Weight", f"{total_weight:.2f} kg")
    summary_cols[1].metric("Total Deduction", f"{total_deduction:.2f} kg")
    summary_cols[2].metric("Net Weight", f"{net_weight:.2f} kg")

    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        if st.button("✅ Confirm Save", type="primary", use_container_width=True, disabled=len(confirmed_indices) == 0):
            # Store confirmed indices in session state so the main page can proceed
            st.session_state.wr_pending_save = confirmed_indices
            st.rerun()
    with cancel_col:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.wr_pending_save = None
            st.rerun()


def _render_designs_grid(designs, drafts, is_itemized_mode=False, total_sets_in_jc=1, editable=True):
    """
    Renders the designs list using native Streamlit widgets.
    In Itemized Mode, allows editing 'Sets' per row and calculates Expected Weight dynamically.
    In Total Mode, 'Sets' is read-only (already scaled in the input 'designs').
    """
    # Header row: Select, Sets, Width, Length, Expected, Actual, Design Deduction, Remark
    cols = st.columns([1, 1.5, 2, 2, 2, 2, 2, 3.5])
    headers = ["Select", "Sets", "Width", "Length", "Expected", "Actual", "Design Deduction", "Remark"]
    for col, header in zip(cols, headers):
        col.markdown(f"**{header}**")
    
    st.markdown("---")
    
    # Rows
    updated_data = []
    
    for i, design_item in enumerate(designs):
        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([1, 1.5, 2, 2, 2, 2, 2, 3.5])
        
        # Determine current values
        is_selected_state = i in st.session_state.get('wr_selected_designs', set())
        current_weight = st.session_state.wr_weights.get(i, drafts.get(i, {}).get('weight', 0.0))
        current_deduction = st.session_state.wr_design_deductions.get(i, drafts.get(i, {}).get('design_deduction', 0.0))
        current_remark = st.session_state.wr_remarks.get(i, drafts.get(i, {}).get('remark', ''))
        
        # Sets Logic
        current_sets_val = 1
        widget_key = f"sets_{i}"
        
        if is_itemized_mode:
            # Priority: Widget Key (Immediate Input) -> Session Dict -> Draft -> Design Item -> 1
            if widget_key in st.session_state:
                current_sets_val = st.session_state[widget_key]
                # Sync back to persistence dict immediately
                if 'wr_design_sets' not in st.session_state: st.session_state.wr_design_sets = {}
                st.session_state.wr_design_sets[i] = current_sets_val
            elif i in st.session_state.get('wr_design_sets', {}):
                 current_sets_val = st.session_state.wr_design_sets[i]
            else:
                 # Default to draft or original design value
                 draft_sets = drafts.get(i, {}).get('sets')
                 if draft_sets is not None:
                     current_sets_val = int(draft_sets)
                 else:
                     # Check if design has a default 'sets' value (e.g. from SO)
                     current_sets_val = int(design_item.get('sets', 1))
        else:
             # In Total mode, the design item already has the scaled sets
            current_sets_val = int(design_item.get('sets', 0))

        # Expected Weight Calculation
        if is_itemized_mode and total_sets_in_jc > 0:
            # Calculate dynamic portion based on row specific sets
            base_weight = design_item.get('weight', 0.0) # Assuming design_item is the ORIGINAL (full sets) item
            expected_display_weight = (base_weight / total_sets_in_jc) * current_sets_val
        else:
            # Already scaled
            expected_display_weight = design_item.get('weight', 0.0)
        
        # 1. Select Checkbox
        with c1:
            is_selected = st.checkbox(
                "Select", 
                value=is_selected_state, 
                key=f"sel_{i}", 
                label_visibility="collapsed",
                disabled=not editable
            )
        
        # 2. Sets (Editable in Itemized, Read-only in Total)
        with c2:
            if is_itemized_mode and editable:
                sets_val = st.number_input(
                    "Sets",
                    min_value=1,
                    max_value=int(design_item.get('sets', total_sets_in_jc)), # Enforce upper limit per design
                    value=int(current_sets_val),
                    key=f"sets_{i}",
                    label_visibility="collapsed",
                    step=1
                )
            else:
                st.text(f"{current_sets_val}")
                sets_val = current_sets_val

        # 3. Width (Read-only)
        with c3:
            st.text(f"{design_item.get('width', 0)}")
            
        # 4. Length (Read-only)
        with c4:
            st.text(f"{design_item.get('length', 0)}")
            
        # 5. Expected Weight (Read-only, Dynamic)
        with c5:
            st.text(f"{expected_display_weight:.2f}")
            
        # 6. Actual Weight (Read-only / Disabled)
        with c6:
            # User wants this populated by buttons only
            st.number_input(
                "Weight", 
                value=float(current_weight) if current_weight else 0.0,
                key=f"wt_{i}",
                label_visibility="collapsed",
                disabled=True 
            )
            actual_wt = float(current_weight) if current_weight else 0.0

        # 7. Design Deduction (Editable)
        with c7:
            if editable:
                deduction_val = st.number_input(
                    "Design Deduction",
                    value=float(current_deduction),
                    key=f"ded_{i}",
                    label_visibility="collapsed",
                    step=0.1,
                    min_value=0.0
                )
            else:
                st.text(f"{current_deduction:.2f}" if current_deduction else "")
                deduction_val = current_deduction
        
        # 8. Remark (Editable)
        with c8:
            if editable:
                remark = st.text_input(
                    "Remark",
                    value=current_remark,
                    key=f"rem_{i}",
                    label_visibility="collapsed"
                )
            else:
                st.text(current_remark)
                remark = current_remark
        
        # Update session state immediately
        if editable:
            if is_selected:
                st.session_state.wr_selected_designs.add(i)
            elif i in st.session_state.get('wr_selected_designs', set()):
                st.session_state.wr_selected_designs.discard(i)
            
            st.session_state.wr_design_deductions[i] = deduction_val
            st.session_state.wr_remarks[i] = remark
            if is_itemized_mode:
                st.session_state.wr_design_sets[i] = sets_val

        # Build data dict
        updated_data.append({
            "Select": is_selected,
            "Sets": sets_val,
            "Width": design_item.get('width', 0),
            "Length": design_item.get('length', 0),
            "Expected Wt.": expected_display_weight,
            "Actual Wt.": actual_wt,
            "Design Deduction": deduction_val,
            "Remark": remark,
            "original_index": i
        })
        
    return pd.DataFrame(updated_data)



def render_weight_receipt_form():
    st.markdown("<h3>Create Weight Receipt</h3>", unsafe_allow_html=True)

    services = get_services()
    initialize_wr_session_state() # Call the new initialization function

    dropdown_data = load_so_dropdowns(services.sales_order)
    party_names = dropdown_data.party_names

    # --- Filters ---
    col1, col2, col3, col_refresh = st.columns([2, 2, 2, 1])
    with col1:
        selected_party = st.selectbox("Select Party", options=[""] + party_names)
    with col2:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
    with col3:
        end_date = st.date_input("End Date", datetime.now())
    with col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)  # Vertical alignment
        if st.button("🔄 Refresh", help="Clear cached job cards — use this after updating a Sales Order to see the latest designs"):
            get_cached_job_cards.clear()
            st.toast("Job card cache cleared.", icon="🔄")
            st.rerun()


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
                
                # When JC changes, reset the session state for weights, remarks, deductions, and selection
                st.session_state.wr_weights = {}
                st.session_state.wr_remarks = {}
                st.session_state.wr_design_sets = {}
                st.session_state.wr_design_deductions = {}
                st.session_state.wr_selected_designs = set()
                st.session_state.wr_is_manual_entry = False

                # Crucial: Clear specific widget keys from session state to prevent StreamlitValueAboveMaxError
                # and stale values in inputs. We clear up to a reasonable number of designs.
                for i in range(50): # Assuming max 50 designs per JC
                    for prefix in ['sets_', 'sel_', 'wt_', 'ded_', 'rem_']:
                        key = f"{prefix}{i}"
                        if key in st.session_state:
                            del st.session_state[key]
                
                # Also clear global deduction input
                if 'deduction_input' in st.session_state:
                    del st.session_state['deduction_input']

                if draft_total_weight is not None:
                    st.session_state.wr_total_weight = draft_total_weight
                else:
                    st.session_state.wr_total_weight = 0.0
                
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
            
            # --- Weighing Mode Selection ---
            st.markdown("---")
            # Default to "Total Weight" for Core Building, "Individual Items" for others
            mode_options = ["Total Weight", "Individual Items"]
            default_mode_index = 0 if order_type == "CORE_BUILDING" else 1
            
            selected_mode = st.radio(
                "Weighing Mode", 
                mode_options, 
                index=default_mode_index, 
                horizontal=True,
                help="Choose 'Total Weight' to weigh the entire set at once, or 'Individual Items' to weigh specific designs."
            )

            is_itemized_mode = (selected_mode == "Individual Items")
            
            # Map mode to backend 'weight_entry_type'
            # "Loose Strips" implies itemized tracking in the backend logic
            # "Building Core" implies total weight tracking
            weight_entry_type = "Loose Strips" if is_itemized_mode else "Building Core"
            
            st.markdown("---")

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
                    "Number of Cores for this Receipt",
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
                total_sets_in_jc = max(1, int(selected_jc.get('number_of_cores') or 1))  # Default to 1 if 0 or None
                completed_sets = services.weight_receipt.get_receipted_sets_for_job_card(selected_jc_str)
                
                sets_for_this_receipt_val = st.session_state.get('wr_sets_for_receipt', 1)
                sets_for_this_receipt = 1
                sets_for_this_receipt = 1
                if not is_itemized_mode and order_type == "CORE_BUILDING": # Only show global sets input if Core Building
                    sets_for_this_receipt = st.number_input(
                        "Number of Sets for this Receipt (for tracking only)",
                        min_value=1,
                        max_value=total_sets_in_jc,
                        value=sets_for_this_receipt_val,
                        step=1,
                        key='wr_sets_for_receipt_input',
                        help="Sets are tracked but not enforced for partial dispatch orders"
                    )
                st.session_state.wr_sets_for_receipt = sets_for_this_receipt


            original_designs = json.loads(selected_jc.get('designs_json', '[]'))
            designs = [] 
            total_sets_in_jc = int(selected_jc.get('number_of_cores', 0))

            if original_designs and total_sets_in_jc > 0 and sets_for_this_receipt > 0 and not is_itemized_mode and order_type == "CORE_BUILDING":
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
                # Don't pre-generate the number to avoid race conditions
                # Number will be generated at save time
                wr_number = st.text_input(
                    "Weight Receipt Number", 
                    value="Auto-generated on save",
                    disabled=True,
                    help="Weight receipt number will be automatically generated when you save"
                )
            with wr_col2:
                receipt_date = st.date_input("Receipt Date", datetime.now())

            st.markdown("---")

            # --- Weighing Mode logic moved up ---
            st.markdown("<h6>Design Details (Scaled for this Receipt)</h6>", unsafe_allow_html=True)
            
            deduction = 0.0
            if not is_itemized_mode:
                 deduction = st.number_input("Deduction (kg)", value=0.0, step=0.1, key="deduction_input")
            else:
                # In itemized mode, global deduction is 0. Deductions are entered per-design.
                st.write("") # Spacer

            
            drafts = st.session_state.get('wr_draft_data', {})

            if weight_entry_type == "Loose Strips":
                edited_df = _render_designs_grid(
                    designs, 
                    drafts, 
                    is_itemized_mode=is_itemized_mode,
                    total_sets_in_jc=total_sets_in_jc,
                    editable=True
                )
                # Legacy Deduction Section Removed
                # Deductions are now handled directly in the grid above.
                selected_indices = st.session_state.get('wr_selected_designs', set())

                st.markdown("---")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    get_weight_clicked = st.button("Get Weight", key="get_weight_for_selected_design")
                with col2:
                    add_weight_clicked = st.button("Add Weight", key="add_weight_for_selected_design")
                with col3:
                    save_draft_clicked = st.button("Save Draft", key="save_draft_for_selected_design")
                # Clear Selection Logic
                with col4:
                    if len(selected_indices) > 0:
                        if st.button("Clear Selection", key="clear_selection"):
                            st.session_state.wr_selected_designs = set()
                            st.rerun()

                # Action Handlers
                if get_weight_clicked or add_weight_clicked:
                    selected_indices = st.session_state.get('wr_selected_designs', set())
                    if len(selected_indices) > 0:
                        with st.spinner("Fetching weight..."):
                            response_data = services.weight_receipt.get_current_weight_from_scale()
                            if response_data.get("success") and response_data.get("status") == "stable":
                                total_scale_weight = response_data.get("weight", 0.0)
                                st.session_state.wr_is_manual_entry = False

                                # Helper to get effective weight
                                def get_effective_weight(idx):
                                    if is_itemized_mode:
                                        orig_weight = designs[idx].get('weight', 0.0)
                                        # Use session state, fallback to draft, fallback to 1
                                        draft_sets = drafts.get(idx, {}).get('sets', 1)
                                        current_sets = st.session_state.wr_design_sets.get(idx, int(draft_sets) if draft_sets is not None else 1)

                                        if total_sets_in_jc > 0:
                                            return (orig_weight / total_sets_in_jc) * current_sets
                                        return 0.0
                                    else:
                                        return designs[idx].get('weight', 0.0)

                                # Calculate total expected weight of selected designs
                                selected_total_expected = sum(get_effective_weight(i) for i in selected_indices)

                                # Apply proportionally to selected designs
                                num_selected = len(selected_indices)

                                for idx in selected_indices:
                                    design = designs[idx]
                                    expected_wt = get_effective_weight(idx)

                                    # Calculate allocated weight portion
                                    if selected_total_expected > 0:
                                        # Proportional distribution: (Item Expected / Total Expected) * Total Scale Weight
                                        allocated_portion = (expected_wt / selected_total_expected) * total_scale_weight
                                    else:
                                        # Fallback to equal distribution if no expected weights
                                        allocated_portion = total_scale_weight / num_selected

                                    if add_weight_clicked:
                                        # Fix: Use draft weight as base if session state weight is not yet set
                                        current_base_weight = st.session_state.wr_weights.get(idx)
                                        if current_base_weight is None:
                                            current_base_weight = drafts.get(idx, {}).get('weight', 0.0)

                                        st.session_state.wr_weights[idx] = current_base_weight + allocated_portion
                                    else: # Get Weight
                                        st.session_state.wr_weights[idx] = allocated_portion

                                if add_weight_clicked:
                                    st.toast(f"Added {total_scale_weight:.2f} kg to {num_selected} designs (Proportional).", icon="⚖️")
                                else:
                                    st.toast(f"Fetched {total_scale_weight:.2f} kg for {num_selected} designs (Proportional).", icon="⚖️")

                                st.rerun()
                            else:
                                st.warning(f"Unstable: {response_data.get('status')}", icon="⚠️")
                    else:
                        st.warning("Please select at least one design to weigh.")

                # --- Manual Weight Entry (Loose Strips) ---
                if _is_manual_entry_authorized():
                    with st.expander("Manual Weight Entry", expanded=False):
                        manual_wt_loose = st.number_input(
                            "Weight (kg)", min_value=0.0, step=0.1, key="manual_weight_loose", format="%.2f"
                        )
                        m_col1, m_col2 = st.columns(2)
                        with m_col1:
                            manual_set_clicked = st.button("Set Weight (Manual)", key="manual_set_loose")
                        with m_col2:
                            manual_add_clicked = st.button("Add Weight (Manual)", key="manual_add_loose")

                        if manual_set_clicked or manual_add_clicked:
                            selected_indices_m = st.session_state.get('wr_selected_designs', set())
                            if len(selected_indices_m) == 0:
                                st.warning("Please select at least one design to weigh.")
                            elif manual_wt_loose <= 0:
                                st.warning("Weight must be greater than 0.")
                            else:
                                st.session_state.wr_is_manual_entry = True
                                total_manual_weight = manual_wt_loose
                                action = "SET" if manual_set_clicked else "ADD"

                                # Reuse same proportional distribution logic
                                def get_effective_weight_manual(idx):
                                    if is_itemized_mode:
                                        orig_weight = designs[idx].get('weight', 0.0)
                                        draft_sets = drafts.get(idx, {}).get('sets', 1)
                                        current_sets = st.session_state.wr_design_sets.get(idx, int(draft_sets) if draft_sets is not None else 1)
                                        if total_sets_in_jc > 0:
                                            return (orig_weight / total_sets_in_jc) * current_sets
                                        return 0.0
                                    else:
                                        return designs[idx].get('weight', 0.0)

                                selected_total_expected_m = sum(get_effective_weight_manual(i) for i in selected_indices_m)
                                num_selected_m = len(selected_indices_m)

                                for idx in selected_indices_m:
                                    expected_wt = get_effective_weight_manual(idx)
                                    if selected_total_expected_m > 0:
                                        allocated_portion = (expected_wt / selected_total_expected_m) * total_manual_weight
                                    else:
                                        allocated_portion = total_manual_weight / num_selected_m

                                    if manual_add_clicked:
                                        current_base_weight = st.session_state.wr_weights.get(idx)
                                        if current_base_weight is None:
                                            current_base_weight = drafts.get(idx, {}).get('weight', 0.0)
                                        st.session_state.wr_weights[idx] = current_base_weight + allocated_portion
                                    else:
                                        st.session_state.wr_weights[idx] = allocated_portion

                                user_email = st.session_state.get('user_info', {}).get('username', 'UNKNOWN')
                                logger.warning(
                                    "MANUAL WEIGHT ENTRY | user=%s | JC=%s | weight=%.2f kg | designs=%s | action=%s | mode=Loose Strips",
                                    user_email, selected_jc_str, total_manual_weight, list(selected_indices_m), action
                                )

                                if manual_add_clicked:
                                    st.toast(f"Manual: Added {total_manual_weight:.2f} kg to {num_selected_m} designs.", icon="⚖️")
                                else:
                                    st.toast(f"Manual: Set {total_manual_weight:.2f} kg for {num_selected_m} designs.", icon="⚖️")
                                st.rerun()

                if save_draft_clicked:
                    selected_indices = st.session_state.get('wr_selected_designs', set())
                    if len(selected_indices) > 0:
                        with st.spinner("Saving drafts..."):
                            sets_for_this_receipt = st.session_state.get('wr_sets_for_receipt', 0)
                            
                            for idx in selected_indices:
                                weight_to_save = st.session_state.wr_weights.get(idx, 0.0)
                                remark_to_save = st.session_state.wr_remarks.get(idx, "")
                                deduction_to_save = st.session_state.wr_design_deductions.get(idx, 0.0)
                                
                                # Determine sets to save: Row-specific for itemized, global for total
                                item_sets_to_save = st.session_state.wr_design_sets.get(idx, sets_for_this_receipt) if is_itemized_mode else sets_for_this_receipt

                                services.weight_receipt.save_weight_receipt_draft(
                                    job_card=selected_jc_str,
                                    design_index=idx,
                                    weight=weight_to_save,
                                    remark=remark_to_save,
                                    sets_for_this_receipt=item_sets_to_save,
                                    design_deduction=deduction_to_save
                                )
                            
                            st.success(f"Draft saved for {len(selected_indices)} designs!")
                    else:
                        st.warning("Please select designs to save.")


                st.markdown("---")

                # --- Step 1: "Save Weight Receipt" button opens confirmation dialog ---
                if st.button("Save Weight Receipt", key="save_wr_button_loose"):
                    # Collect all designs with Actual Wt. > 0 as candidates
                    candidate_designs = []
                    for i, row in edited_df.iterrows():
                        actual_weight = row["Actual Wt."]
                        if actual_weight > 0:
                            original_design_data = designs[row['original_index']]
                            candidate_designs.append({
                                'original_index': row['original_index'],
                                'sets': row['Sets'],
                                'width': original_design_data.get('width', 0),
                                'length': original_design_data.get('length', 0),
                                'actual_weight': actual_weight,
                                'design_deduction': row['Design Deduction'],
                                'remark': row['Remark'],
                            })

                    if not candidate_designs:
                        st.error("Please weigh at least one item before saving.", icon="⚠️")
                    else:
                        _show_save_confirmation_dialog(
                            candidate_designs,
                            job_card_number=selected_jc_str,
                            party_name=selected_party
                        )

                # --- Step 2: Process confirmed save (triggered by dialog rerun) ---
                confirmed_indices = st.session_state.get('wr_pending_save')
                if confirmed_indices is not None:
                    # Clear the pending flag immediately
                    st.session_state.wr_pending_save = None

                    # Check for existing save lock
                    current_time = time.time()
                    last_save_time = st.session_state.wr_save_locks.get(selected_jc_str, 0)
                    if current_time - last_save_time < 30:
                        st.warning("Save already in progress. Please wait...", icon="⏳")
                        st.stop()

                    st.session_state.wr_save_locks[selected_jc_str] = current_time

                    weighed_designs = []
                    actual_total_weight = 0.0
                    sum_design_deductions = 0.0

                    for i, row in edited_df.iterrows():
                        actual_weight = row["Actual Wt."]
                        if row['original_index'] in confirmed_indices and actual_weight > 0:
                            actual_total_weight += actual_weight
                            sum_design_deductions += row["Design Deduction"]
                            original_design_data = designs[row['original_index']]
                            weighed_design_data = original_design_data.copy()
                            weighed_design_data['actual_weight'] = actual_weight
                            weighed_design_data['remark'] = row["Remark"]
                            weighed_design_data['design_deduction'] = row["Design Deduction"]
                            weighed_design_data['sets'] = row["Sets"]
                            weighed_designs.append(WeighedDesignDetail(**weighed_design_data))

                    if not weighed_designs:
                        if selected_jc_str in st.session_state.wr_save_locks:
                            del st.session_state.wr_save_locks[selected_jc_str]
                        st.error("No valid designs to save.", icon="⚠️")
                        st.stop()

                    # In itemized mode, use the sum of per-design deductions
                    if is_itemized_mode:
                        deduction = sum_design_deductions

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

                    generated_wr_number = services.weight_receipt.generate_weight_receipt_number()

                    request = WeightReceiptRequest(
                        weight_receipt_number=generated_wr_number,
                        receipt_date=receipt_date,
                        job_card_number=selected_jc_str,
                        party_name=selected_party,
                        po_no=selected_jc.get('po_no', 'N/A'),
                        material=selected_jc.get('material', 'N/A'),
                        sets=st.session_state.get('wr_sets_for_receipt', 0),
                        designs=weighed_designs,
                        weight_entry_type="Loose Strips (Manual)" if st.session_state.get('wr_is_manual_entry') else "Loose Strips",
                        total_weight=actual_total_weight,
                        deduction=deduction,
                        order_type=order_type
                    )

                    with st.spinner("Saving Weight Receipt..."):
                        success = services.weight_receipt.save_weight_receipt(request)
                        if success:
                            st.success(f"Weight Receipt {generated_wr_number} saved successfully!")
                            user_id = st.session_state.get('user_info', {}).get('username', 'SYSTEM')
                            services.weight_receipt.save_to_finished_goods(
                                user_id=user_id,
                                job_card=selected_jc['job_card_number'],
                                fg_qty=actual_total_weight - deduction,
                                weight_receipt_number=generated_wr_number
                            )

                            # Selective draft clearing: only clear drafts for designs that were saved
                            services.weight_receipt.clear_drafts_for_design_indices(
                                selected_jc['job_card_number'],
                                confirmed_indices
                            )

                            # Clear session state only for saved design indices
                            for idx in confirmed_indices:
                                st.session_state.wr_weights.pop(idx, None)
                                st.session_state.wr_remarks.pop(idx, None)
                                st.session_state.wr_design_deductions.pop(idx, None)
                                st.session_state.wr_design_sets.pop(idx, None)

                            st.session_state.last_selected_index = None
                            st.session_state.wr_is_manual_entry = False

                            # Clear lock on success
                            if selected_jc_str in st.session_state.wr_save_locks:
                                del st.session_state.wr_save_locks[selected_jc_str]

                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Failed to save Weight Receipt.")
                            # Clear lock on failure
                            if selected_jc_str in st.session_state.wr_save_locks:
                                del st.session_state.wr_save_locks[selected_jc_str]

            elif weight_entry_type == "Building Core":
                _render_designs_grid(designs, drafts, is_itemized_mode=False, editable=False)
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
                            st.session_state.wr_is_manual_entry = False

                            if add_weight_clicked_core:
                                st.session_state.wr_total_weight += weight
                                st.toast(f"Added {weight:.2f} kg. New total: {st.session_state.wr_total_weight:.2f} kg. Click 'Save Draft' to persist.", icon="⚖️")
                            else: # Get Weight
                                st.session_state.wr_total_weight = weight
                                st.toast(f"Weight received: {weight:.2f} kg. Click 'Save Draft' to persist.", icon="⚖️")

                            st.rerun()
                        else:
                            st.warning(f"Weight is unstable: {response_data.get('status')}", icon="⚠️")

                # --- Manual Weight Entry (Building Core) ---
                if _is_manual_entry_authorized():
                    with st.expander("Manual Weight Entry", expanded=False):
                        manual_wt_core = st.number_input(
                            "Weight (kg)", min_value=0.0, step=0.1, key="manual_weight_core", format="%.2f"
                        )
                        mc_col1, mc_col2 = st.columns(2)
                        with mc_col1:
                            manual_set_core = st.button("Set Weight (Manual)", key="manual_set_core")
                        with mc_col2:
                            manual_add_core = st.button("Add Weight (Manual)", key="manual_add_core")

                        if manual_set_core or manual_add_core:
                            if manual_wt_core <= 0:
                                st.warning("Weight must be greater than 0.")
                            else:
                                st.session_state.wr_is_manual_entry = True
                                action = "SET" if manual_set_core else "ADD"

                                if manual_add_core:
                                    st.session_state.wr_total_weight += manual_wt_core
                                    st.toast(f"Manual: Added {manual_wt_core:.2f} kg. New total: {st.session_state.wr_total_weight:.2f} kg.", icon="⚖️")
                                else:
                                    st.session_state.wr_total_weight = manual_wt_core
                                    st.toast(f"Manual: Weight set to {manual_wt_core:.2f} kg.", icon="⚖️")

                                user_email = st.session_state.get('user_info', {}).get('username', 'UNKNOWN')
                                logger.warning(
                                    "MANUAL WEIGHT ENTRY | user=%s | JC=%s | weight=%.2f kg | action=%s | mode=Building Core",
                                    user_email, selected_jc_str, manual_wt_core, action
                                )
                                st.rerun()

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
                    # Check for existing save lock
                    current_time = time.time()
                    last_save_time = st.session_state.wr_save_locks.get(selected_jc_str, 0)
                    if current_time - last_save_time < 30: # 30 seconds lock
                        st.warning("Save already in progress. Please wait...", icon="⏳")
                        st.stop()
                    
                    st.session_state.wr_save_locks[selected_jc_str] = current_time

                    actual_total_weight = st.session_state.get('wr_total_weight', 0.0)

                    if actual_total_weight <= 0:
                        if selected_jc_str in st.session_state.wr_save_locks:
                            del st.session_state.wr_save_locks[selected_jc_str]
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

                    # Generate weight receipt number at save time to prevent race conditions
                    generated_wr_number = services.weight_receipt.generate_weight_receipt_number()

                    request = WeightReceiptRequest(
                        weight_receipt_number=generated_wr_number,
                        receipt_date=receipt_date,
                        job_card_number=selected_jc_str,
                        party_name=selected_party,
                        po_no=selected_jc.get('po_no', 'N/A'),
                        material=selected_jc.get('material', 'N/A'),
                        sets=st.session_state.get('wr_sets_for_receipt', 0),
                        designs=weighed_designs,
                        weight_entry_type="Building Core (Manual)" if st.session_state.get('wr_is_manual_entry') else "Building Core",
                        total_weight=actual_total_weight,
                        deduction=deduction,
                        order_type=order_type
                    )
                    
                    with st.spinner("Saving Weight Receipt..."):
                        success = services.weight_receipt.save_weight_receipt(request)
                        if success:
                            st.success(f"Weight Receipt {generated_wr_number} saved successfully!")
                            user_id = st.session_state.get('user_info', {}).get('username', 'SYSTEM')
                            services.weight_receipt.save_to_finished_goods(
                                user_id=user_id,
                                job_card=selected_jc['job_card_number'],
                                fg_qty=actual_total_weight - deduction,
                                weight_receipt_number=generated_wr_number
                            )
                            services.weight_receipt.clear_weight_receipt_drafts(selected_jc['job_card_number'])
                            st.session_state.wr_weights = {}
                            st.session_state.wr_remarks = {}
                            st.session_state.wr_total_weight = 0.0
                            st.session_state.wr_draft_data = {}
                            st.session_state.last_selected_index = None
                            st.session_state.wr_is_manual_entry = False

                            # Clear lock on success
                            if selected_jc_str in st.session_state.wr_save_locks:
                                del st.session_state.wr_save_locks[selected_jc_str]

                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("Failed to save Weight Receipt.")
