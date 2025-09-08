import streamlit as st
import time
try:
    from theme.components import render_main_header, begin_card, end_card
except ModuleNotFoundError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from theme.components import render_main_header, begin_card, end_card


def render() -> None:
    render_main_header("Automation Workflows")
    # begin_card()
    
    st.markdown("<div class='card-header'><span class='card-icon'>📄</span>Invoice Processor (OCR)</div>", unsafe_allow_html=True)
    st.markdown("<div class='card-subheader'>Upload a purchase invoice (PDF or image) to automatically extract data and update your inventory and payables.</div>", unsafe_allow_html=True)
    
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
            
    end_card()
