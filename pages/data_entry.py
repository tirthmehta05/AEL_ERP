import streamlit as st
try:
    from theme.components import render_main_header, end_card
except ModuleNotFoundError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from theme.components import render_main_header, end_card


def render() -> None:
    render_main_header("Data Entry")

    entry_type = st.selectbox(
        "Select the type of data you want to enter:",
        ("--- Select ---", "New Purchase Order", "New Sales Order", "Log Expense", "Add Stock Item")
    )
    
    if entry_type != "--- Select ---":
        # begin_card()
        st.markdown(f"<div class='card-header'>{entry_type}</div><div class='card-subheader'>Fill in the details below and click submit.</div>", unsafe_allow_html=True)
        
        if entry_type == "New Purchase Order":
            with st.form("po_form"):
                st.selectbox("Supplier", ["JSW", "SAIL", "Tata Steel"])
                st.text_input("Material Grade")
                st.number_input("Quantity (Tons)", min_value=1)
                st.number_input("Rate (per Ton)", min_value=1000)
                st.date_input("Expected Delivery Date")
                submitted = st.form_submit_button("Submit Purchase Order")
                if submitted:
                    st.success("Purchase Order submitted successfully!")
        
        end_card()
