import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta

def render_filters(available_coils_df):
    with st.container():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='card-header'>Filters</div>", unsafe_allow_html=True)
        
        filtered_df = available_coils_df.copy()

        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        with col1:
            from config import settings
            slitter = st.selectbox("Slitter", options=settings.slitting_plan.slitters)

        with col2:
            coil_location_options = ["All"] + list(filtered_df["coil_location"].unique())
            coil_location = st.selectbox("Coil Location", options=coil_location_options)
            if coil_location != "All":
                filtered_df = filtered_df[filtered_df["coil_location"] == coil_location]

        with col3:
            grade_options = ["All"] + list(filtered_df["grade"].unique())
            grade = st.selectbox("Grade", options=grade_options)
            if grade != "All":
                filtered_df = filtered_df[filtered_df["grade"] == grade]

        with col4:
            thickness_options = ["All"] + list(filtered_df["thickness"].unique())
            thickness = st.selectbox("Thickness (Thk)", options=thickness_options)
            if thickness != "All":
                filtered_df = filtered_df[filtered_df["thickness"] == thickness]

        with col5:
            width_options = ["All"] + list(filtered_df["width"].unique())
            width = st.selectbox("Width", options=width_options)
            if width != "All":
                filtered_df = filtered_df[filtered_df["width"] == width]

        with col6:
            coating_options = ["All"] + list(filtered_df["coating"].unique())
            coating = st.selectbox("Coating", options=coating_options)
            if coating != "All":
                filtered_df = filtered_df[filtered_df["coating"] == coating]

        st.markdown("</div>", unsafe_allow_html=True)
    return filtered_df, slitter

def render_coil_selection(filtered_df):
    with st.container():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='card-header'>Coil Selection</div>", unsafe_allow_html=True)
        coil_options = [f"{row['Coil Number']} - {row['available_weight']:.2f} kg" for index, row in filtered_df.iterrows()]
        selected_coils = st.multiselect("Select Coils", options=coil_options)
        st.markdown("</div>", unsafe_allow_html=True)
    return selected_coils

def render_slitting_plan_editor_and_summary(service, filtered_df, selected_coils, slitter, get_cached_available_coils):
    with st.container():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='card-header'>Slitting Plan</div>", unsafe_allow_html=True)
        
        slitting_plan_input_df = pd.DataFrame(
            [{"Size": 0.0, "No. of Slits": 0}]
        )

        st.markdown("<h5>Enter Slitting Sizes</h5>", unsafe_allow_html=True)
        edited_df = st.data_editor(
            slitting_plan_input_df,
            num_rows="dynamic",
            key="slitting_plan_editor",
            use_container_width=True,
            column_config={
                "Size": st.column_config.NumberColumn(
                    "Slit Size (mm)",
                    help="The width of the slit.",
                    format="%.2f",
                ),
                "No. of Slits": st.column_config.NumberColumn(
                    "Number of Slits",
                    help="How many slits of this size.",
                    format="%d",
                )
            }
        )

        if not selected_coils:
            st.warning("Please select at least one coil to proceed.")
        elif not edited_df.empty:
            selected_coil_numbers = [c.split(" - ")[0] for c in selected_coils]
            selected_coils_df = filtered_df[filtered_df["Coil Number"].isin(selected_coil_numbers)]
            
            # Call the backend service for calculation and validation
            result = service.calculate_slitting_plan(selected_coils_df, edited_df)
            
            errors = result["errors"]
            calculated_plan_df = result["calculated_plan"]
            summary = result["summary"]

            for error in errors:
                st.error(error)

            if not errors:
                st.markdown("<h5>Calculated Plan</h5>", unsafe_allow_html=True)
                st.dataframe(calculated_plan_df, use_container_width=True)

                st.markdown("<h4>Summary</h4>", unsafe_allow_html=True)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total No. of Slits", summary["total_slits"])
                with col2:
                    st.metric("Total MM Used", summary["total_mm_used"])
                with col3:
                    st.metric("Total Weight (Kg)", f"{summary['total_weight_kg']:.2f}")
                with col4:
                    st.metric("Scrap per Coil (MM)", summary["scrap_per_coil_mm"])
                    st.metric("Scrap Weight (Kg)", f"{summary['scrap_weight_kg']:.2f}")

                st.markdown("---")
                if st.button("Save Slitting Plan"):
                    plan_data = {
                        'slitter': slitter,
                        'coil_width': summary["single_coil_width"],
                        'total_coil_weight': summary["total_weight_selected"],
                        'scrap_mm': summary["scrap_per_coil_mm"],
                        'scrap_weight': summary["scrap_weight_kg"],
                        'selected_coils': selected_coils_df.to_dict('records'),
                        'slit_details': calculated_plan_df[calculated_plan_df['Size'] > 0].to_dict('records')
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

def render_summary_expanders(service, available_coils_df, get_cached_material_type_options, get_cached_sales_order_summary):
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
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=30))
        with col2:
            end_date = st.date_input("End Date", value=datetime.now())
        
        material_type_options = get_cached_material_type_options(service)
        material_type = st.selectbox("Material Type", options=material_type_options)

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
