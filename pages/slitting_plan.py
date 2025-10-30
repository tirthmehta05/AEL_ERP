import streamlit as st
import pandas as pd
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService
from datetime import datetime, timedelta
import time

# --- Data Caching ---
@st.cache_data
def get_cached_available_coils(_service):
    return _service.get_available_coils()

@st.cache_data
def get_cached_material_type_options(_service):
    return _service.get_material_type_options()

@st.cache_data
def get_cached_sales_order_summary(_service, start_date, end_date, material_type):
    return _service.get_sales_order_summary(start_date, end_date, material_type)

def render():
    st.markdown("<h1 class='main-header'>Slitting Plan</h1>", unsafe_allow_html=True)

    service = SlittingPlanService()
    available_coils_df = get_cached_available_coils(service)

    if available_coils_df.empty:
        st.warning("No available coils found.")
    
    # --- Main Page Content ---
    if not available_coils_df.empty:
        # --- Dependent Filters ---
        with st.container():
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-header'>Filters</div>", unsafe_allow_html=True)
            
            filtered_df = available_coils_df.copy()

            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                coil_location_options = ["All"] + list(filtered_df["coil_location"].unique())
                coil_location = st.selectbox("Coil Location", options=coil_location_options)
                if coil_location != "All":
                    filtered_df = filtered_df[filtered_df["coil_location"] == coil_location]

            with col2:
                grade_options = ["All"] + list(filtered_df["grade"].unique())
                grade = st.selectbox("Grade", options=grade_options)
                if grade != "All":
                    filtered_df = filtered_df[filtered_df["grade"] == grade]

            with col3:
                thickness_options = ["All"] + list(filtered_df["thickness"].unique())
                thickness = st.selectbox("Thickness (Thk)", options=thickness_options)
                if thickness != "All":
                    filtered_df = filtered_df[filtered_df["thickness"] == thickness]

            with col4:
                width_options = ["All"] + list(filtered_df["width"].unique())
                width = st.selectbox("Width", options=width_options)
                if width != "All":
                    filtered_df = filtered_df[filtered_df["width"] == width]

            with col5:
                coating_options = ["All"] + list(filtered_df["coating"].unique())
                coating = st.selectbox("Coating", options=coating_options)
                if coating != "All":
                    filtered_df = filtered_df[filtered_df["coating"] == coating]

            st.markdown("</div>", unsafe_allow_html=True)

        # --- Coil Selection ---
        with st.container():
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-header'>Coil Selection</div>", unsafe_allow_html=True)
            coil_options = [f"{row['Coil Number']} - {row['available_weight']:.2f} kg" for index, row in filtered_df.iterrows()]
            selected_coils = st.multiselect("Select Coils", options=coil_options)
            st.markdown("</div>", unsafe_allow_html=True)

        # --- Slitting Plan Table ---
        with st.container():
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-header'>Slitting Plan</div>", unsafe_allow_html=True)
            
            slitting_plan_input_df = pd.DataFrame(
                [{"Size": 0, "No. of Slits": 0}]
            )

            st.markdown("<h5>Enter Slitting Sizes</h5>", unsafe_allow_html=True)
            edited_df = st.data_editor(
                slitting_plan_input_df,
                num_rows="dynamic",
                key="slitting_plan_editor",
                use_container_width=True
            )

            # --- Calculations and Validation ---
            if not selected_coils:
                st.warning("Please select at least one coil to proceed.")
            elif not edited_df.empty:
                # Get the width of a single coil (assuming all selected coils have the same width)
                selected_coil_numbers = [c.split(" - ")[0] for c in selected_coils]
                selected_coils_df = filtered_df[filtered_df["Coil Number"].isin(selected_coil_numbers)]
                single_coil_width = selected_coils_df["width"].iloc[0] if not selected_coils_df.empty else 0

                # Ensure input columns are numeric
                edited_df["Size"] = pd.to_numeric(edited_df["Size"], errors='coerce').fillna(0)
                edited_df["No. of Slits"] = pd.to_numeric(edited_df["No. of Slits"], errors='coerce').fillna(0)

                # Validation Check 1: No slit size can be wider than the coil width
                max_slit_size = edited_df["Size"].max()
                if max_slit_size > single_coil_width:
                    st.error(f"Error: Requested slit size of {max_slit_size}mm is wider than the selected coil width ({single_coil_width}mm).")
                else:
                    # Calculate the new columns
                    edited_df["MM"] = edited_df["Size"] * edited_df["No. of Slits"]
                    
                    total_mm_used = edited_df["MM"].sum()

                    # Validation Check 2: Total planned width cannot exceed the width of a single coil
                    if total_mm_used > single_coil_width:
                        st.error(f"Error: Total planned width ({total_mm_used}mm) exceeds the width of a single coil ({single_coil_width}mm).")
                    else:
                        # Calculate weight based on the new logic
                        total_weight_selected = sum([float(c.split(" - ")[1].split(" kg")[0]) for c in selected_coils])
                        if single_coil_width > 0:
                            weight_per_mm = total_weight_selected / single_coil_width
                            edited_df["Weight in Kg"] = weight_per_mm * edited_df["MM"]
                        else:
                            edited_df["Weight in Kg"] = 0
                        
                        # Display the full table with calculated values
                        st.markdown("<h5>Calculated Plan</h5>", unsafe_allow_html=True)
                        st.dataframe(edited_df, use_container_width=True)

                        # --- Summary ---
                        st.markdown("<h4>Summary</h4>", unsafe_allow_html=True)
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Total No. of Slits", edited_df["No. of Slits"].sum())
                        with col2:
                            st.metric("Total MM Used", total_mm_used)
                        with col3:
                            st.metric("Total Weight (Kg)", f"{edited_df['Weight in Kg'].sum():.2f}")
                        with col4:
                            scrap_per_coil = single_coil_width - total_mm_used
                            scrap_weight = weight_per_mm * scrap_per_coil if single_coil_width > 0 else 0
                            st.metric("Scrap per Coil (MM)", scrap_per_coil)
                            st.metric("Scrap Weight (Kg)", f"{scrap_weight:.2f}")

                        st.markdown("---")
                        if st.button("Save Slitting Plan"):
                            plan_data = {
                                'coil_width': single_coil_width,
                                'total_coil_weight': total_weight_selected,
                                'scrap_mm': scrap_per_coil,
                                'scrap_weight': scrap_weight,
                                'selected_coils': selected_coils_df.to_dict('records'),
                                'slit_details': edited_df[edited_df['Size'] > 0].to_dict('records')
                            }
                            with st.spinner("Saving plan..."):
                                plan_id = service.save_plan(plan_data)
                                if plan_id:
                                    st.success(f"Successfully saved Slitting Plan with ID: **{plan_id}**")
                                    get_cached_available_coils.clear()
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("Failed to save the slitting plan.")

            st.markdown("</div>", unsafe_allow_html=True)

    # --- Summary Expanders at the bottom ---
    with st.expander("View Current Material Availability"):
        if not available_coils_df.empty:
            st.markdown("<h5>Available Stock Summary</h5>", unsafe_allow_html=True)
            stock_summary_df = available_coils_df.groupby(["width", "thickness", "grade"]).agg(
                Total_Available_Weight=("available_weight", "sum")
            ).reset_index()
            st.dataframe(stock_summary_df, use_container_width=True)
        else:
            st.info("No available stock to summarize.")

    with st.expander("View Order Summary"):
        st.markdown("<h5>Order Summary Filters</h5>", unsafe_allow_html=True)
        
        # Filters inside the expander
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=30))
        with col2:
            end_date = st.date_input("End Date", value=datetime.now())
        
        material_type_options = get_cached_material_type_options(service)
        material_type = st.selectbox("Material Type", options=material_type_options)

        # Get and display summary
        if start_date and end_date:
            if start_date > end_date:
                st.error("Start date cannot be after end date.")
            else:
                order_summary_df = get_cached_sales_order_summary(service, start_date, end_date, material_type)
                st.markdown("<h5>Filtered Order Summary</h5>", unsafe_allow_html=True)
                if not order_summary_df.empty:
                    st.dataframe(order_summary_df, use_container_width=True)
                else:
                    st.info("No orders found for the selected criteria.")