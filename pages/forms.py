import streamlit as st

def page():
    st.title("Microsoft Forms")

    st.warning(
        "**Note:** Due to security restrictions, Microsoft Forms cannot be embedded directly into this application. "
        "Please use the buttons below to open the forms in a new tab."
    )

    tab1, tab2, tab3 = st.tabs(["Raw Material Procurement", "Orders", "Production Schedule"])

    with tab1:
        st.header("Raw Material Procurement")
        st.link_button("Open Raw Material Procurement Form", "https://forms.office.com/Pages/ResponsePage.aspx?id=lScIhoE39ECkPXjt8PlYz4HjhTKFB_lLleCT_gbDyxtURU1BUUtMR09CSDdLVVpUWklLQ1FSUzlRNC4u")

    with tab2:
        st.header("Orders")
        st.link_button("Open Orders Form", "https://forms.office.com/Pages/ResponsePage.aspx?id=lScIhoE39ECkPXjt8PlYz4HjhTKFB_lLleCT_gbDyxtUN1JKNlg3N1hOSkdJNUszMFNWNjFFM00wRy4u")

    with tab3:
        st.header("Production Schedule")
        st.link_button("Open Production Schedule Form", "https://forms.office.com/Pages/ResponsePage.aspx?id=lScIhoE39ECkPXjt8PlYz4HjhTKFB_lLleCT_gbDyxtUOVpRQkFEV0VKTkdNNUVDWFEzNVZVWkQ1RS4u")

if __name__ == "__main__":
    page()