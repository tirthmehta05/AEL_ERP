import streamlit as st
import pandas as pd
import base64
from src.job_work.service.job_work_service import JobWorkService

def render():
    st.markdown("<h1 class='main-header'>Create Job Card</h1>", unsafe_allow_html=True)

    job_work_service = JobWorkService()

    with st.form("job_card_form"):
        st.markdown("<h4>Header Information</h4>", unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            core_stack = st.text_input("Core Stack")
            number_of_cores = st.text_input("Number of cores")
        with col2:
            order_dt = st.date_input("Order Dt")
            delivery_dt = st.date_input("Delivery Dt")
        with col3:
            thickness = st.text_input("Thickness")
            po_no = st.text_input("P. O. No.")
        with col4:
            job_card_no = st.text_input("Job Card No")
            job_no = st.text_input("Job No")

        cutter = st.text_input("Cutter", "Amba Enterprise Ltd. (Unit I)")
        machine = st.text_input("Machine", "Canwin - Punch/length")
        party_name = st.text_input("Party Name", "Kraftpowercon India Pvt Ltd")
        watt = st.text_input("Watt")

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("<h4>Line Items</h4>", unsafe_allow_html=True)

        # Using st.data_editor for a dynamic table
        df = pd.DataFrame(
            [
                {"Sr No": 1, "Width X Length": "", "Hole: 16": "", "in MM": 0.0, "Pcs": 0, "Weight": 0.0},
            ]
        )
        line_items = st.data_editor(
            df,
            num_rows="dynamic",
            key="line_items",
            use_container_width=True
        )

        submitted = st.form_submit_button("Generate Job Card")

    if submitted:
        form_data = {
            "core_stack": core_stack,
            "number_of_cores": number_of_cores,
            "order_dt": order_dt,
            "delivery_dt": delivery_dt,
            "thickness": thickness,
            "po_no": po_no,
            "job_card_no": job_card_no,
            "job_no": job_no,
            "cutter": cutter,
            "machine": machine,
            "party_name": party_name,
            "watt": watt,
            "line_items": line_items.to_dict("records"),
        }
        
        pdf_bytes = job_work_service.generate_pdf(form_data)

        # PDF Preview
        st.markdown("<h4>PDF Preview</h4>", unsafe_allow_html=True)
        base64_pdf = base64.b64encode(pdf_bytes.read()).decode('utf-8')
        pdf_display = f'<embed src="data:application/pdf;base64,{base64_pdf}" width="700" height="800" type="application/pdf">'
        st.markdown(pdf_display, unsafe_allow_html=True)

        # Download Button
        st.download_button(
            label="Download Job Card PDF",
            data=pdf_bytes,
            file_name="job_card.pdf",
            mime="application/pdf",
        )
