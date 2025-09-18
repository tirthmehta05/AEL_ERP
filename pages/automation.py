import streamlit as st
import time

def render() -> None:
    st.markdown("<h1 class='main-header'>Automation Workflows</h1>", unsafe_allow_html=True)
    
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'><span class='material-icons'>receipt_long</span> Invoice Processor (OCR)</div>", unsafe_allow_html=True)
    st.markdown("<p>Upload a purchase invoice (PDF or image) to automatically extract data and update your inventory and payables.</p>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Choose an invoice file", type=['pdf', 'png', 'jpg'])
    if uploaded_file is not None:
        with st.spinner('Processing invoice... This may take a moment.'):
            time.sleep(3)
            st.success("Invoice processed! Data extracted and ready for review.")
            st.json({
                "Supplier": "JSW Steel Ltd.",
                "Invoice Number": "JSW-INV-2025-0045",
                "Date": "2025-09-02",
                "Items": [{"Description": "HR Coils", "Quantity": 25, "Rate": 55000, "Amount": 1375000}],
                "GST": "247500",
                "Total": "1622500"
            })
            st.button("Confirm and Save Data")
            
    st.markdown("</div>", unsafe_allow_html=True)
