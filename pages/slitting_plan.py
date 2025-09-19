import streamlit as st
import pandas as pd
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService
from datetime import datetime, timedelta

def render():
    st.markdown("<h1 class='main-header'>Slitting Plan</h1>", unsafe_allow_html=True)

    service = SlittingPlanService()
    available_coils_df = service.get_available_coils()

    if available_coils_df.empty:
        st.warning("No available coils found.")
        # We still want to show the order summary even if there are no coils
    
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

            # --- Calculations ---
            total_weight_selected = sum([float(c.split(" - ")[1].split(" kg")[0]) for c in selected_coils])
            total_width_selected = filtered_df[filtered_df["Coil Number"].isin([c.split(" - ")[0] for c in selected_coils])]["width"].sum()

            if not edited_df.empty:
                edited_df["Size"] = pd.to_numeric(edited_df["Size"], errors='coerce').fillna(0)
                edited_df["No. of Slits"] = pd.to_numeric(edited_df["No. of Slits"], errors='coerce').fillna(0)

                edited_df["MM"] = edited_df["Size"] * edited_df["No. of Slits"]
                if total_width_selected > 0:
                    edited_df["Weight in Kg"] = (total_weight_selected / total_width_selected) * edited_df["MM"]
                else:
                    edited_df["Weight in Kg"] = 0
                
                st.markdown("<h5>Calculated Plan</h5>", unsafe_allow_html=True)
                st.dataframe(edited_df, use_container_width=True)

                st.markdown("<h4>Summary</h4>", unsafe_allow_html=True)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total No. of Slits", edited_df["No. of Slits"].sum())
                with col2:
                    st.metric("Total MM", edited_df["MM"].sum())
                with col3:
                    st.metric("Total Weight (Kg)", f"{edited_df['Weight in Kg'].sum():.2f}")
                with col4:
                    scrap_mm = total_width_selected - edited_df["MM"].sum()
                    scrap_weight = (total_weight_selected / total_width_selected) * scrap_mm if total_width_selected > 0 else 0
                    st.metric("Scrap MM", scrap_mm)
                    st.metric("Scrap Weight (Kg)", f"{scrap_weight:.2f}")
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
        
        material_type_options = service.get_material_type_options()
        material_type = st.selectbox("Material Type", options=material_type_options)

        # Get and display summary
        if start_date and end_date:
            if start_date > end_date:
                st.error("Start date cannot be after end date.")
            else:
                order_summary_df = service.get_sales_order_summary(start_date, end_date, material_type)
                st.markdown("<h5>Filtered Order Summary</h5>", unsafe_allow_html=True)
                if not order_summary_df.empty:
                    st.dataframe(order_summary_df, use_container_width=True)
                else:
                    st.info("No orders found for the selected criteria.")
