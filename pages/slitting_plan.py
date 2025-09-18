import streamlit as st
import pandas as pd
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService

def render():
    st.markdown("<h1 class='main-header'>Slitting Plan</h1>", unsafe_allow_html=True)

    service = SlittingPlanService()
    available_coils_df = service.get_available_coils()

    if available_coils_df.empty:
        st.warning("No available coils found.")
        return

    # --- Filters ---
    with st.container():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='card-header'>Filters</div>", unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            grade = st.selectbox("Grade", options=["All"] + list(available_coils_df["grade"].unique()))
        with col2:
            thickness = st.selectbox("Thickness (Thk)", options=["All"] + list(available_coils_df["thickness"].unique()))
        with col3:
            width = st.selectbox("Width", options=["All"] + list(available_coils_df["width"].unique()))
        with col4:
            coating = st.selectbox("Coating", options=["All"] + list(available_coils_df["coating"].unique()))
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Filter Data ---
    filtered_df = available_coils_df.copy()
    if grade != "All":
        filtered_df = filtered_df[filtered_df["grade"] == grade]
    if thickness != "All":
        filtered_df = filtered_df[filtered_df["thickness"] == thickness]
    if width != "All":
        filtered_df = filtered_df[filtered_df["width"] == width]
    if coating != "All":
        filtered_df = filtered_df[filtered_df["coating"] == coating]

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
        
        slitting_plan_df = pd.DataFrame(
            [
                {"Size": 0, "No. of Slits": 0, "MM": 0, "Weight in Kg": 0.0},
            ]
        )
        edited_df = st.data_editor(
            slitting_plan_df,
            num_rows="dynamic",
            key="slitting_plan_editor",
            use_container_width=True
        )

        # --- Calculations ---
        total_weight_selected = sum([float(c.split(" - ")[1].split(" kg")[0]) for c in selected_coils])
        total_width_selected = filtered_df[filtered_df["Coil Number"].isin([c.split(" - ")[0] for c in selected_coils])]["width"].sum()

        if not edited_df.empty:
            edited_df["MM"] = edited_df["Size"] * edited_df["No. of Slits"]
            if total_width_selected > 0:
                edited_df["Weight in Kg"] = (total_weight_selected / total_width_selected) * edited_df["MM"]

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
