"""
Home page for AEL ERP System
This is the main dashboard/landing page of the application.
"""

import streamlit as st
from datetime import datetime
import pandas as pd


def render():
    """Render the home page."""

    # Page header with logo
    col1, col2 = st.columns([1, 3])

    with col1:
        st.image("assets/logofinal.png", width=100)

    with col2:
        st.title("AEL ERP System")
        st.markdown("*Your comprehensive Enterprise Resource Planning solution*")

    st.markdown("---")

    # Welcome section
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("""
        ### Welcome to AEL ERP
        
        Your comprehensive Enterprise Resource Planning solution for managing:
        - **Data Entry & Management**
        - **Automation Workflows** 
        - **Business Intelligence**
        - **Process Optimization**
        """)

    with col2:
        # Current date and time
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.info(f"🕒 **Current Time**\n{current_time}")

    st.markdown("---")

    # Quick stats section
    st.subheader("📊 Quick Overview")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(label="Total Records", value="1,234", delta="12")

    with col2:
        st.metric(label="Active Users", value="45", delta="3")

    with col3:
        st.metric(label="Processed Today", value="89", delta="7")

    with col4:
        st.metric(label="System Status", value="🟢 Online", delta=None)

    st.markdown("---")

    # Recent activity section
    st.subheader("📈 Recent Activity")

    # Sample data for recent activity
    recent_data = pd.DataFrame(
        {
            "Time": ["09:30", "09:15", "09:00", "08:45", "08:30"],
            "Action": [
                "Data Entry Completed",
                "Report Generated",
                "User Login",
                "Backup Created",
                "System Update",
            ],
            "User": ["John Doe", "Jane Smith", "Admin", "System", "System"],
            "Status": ["✅", "✅", "✅", "✅", "✅"],
        }
    )

    st.dataframe(recent_data, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Quick actions section
    st.subheader("🚀 Quick Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📝 New Data Entry", use_container_width=True):
            st.switch_page("pages/data_entry.py")

    with col2:
        if st.button("⚙️ Automation Setup", use_container_width=True):
            st.switch_page("pages/automation.py")

    with col3:
        if st.button("📊 View Reports", use_container_width=True):
            st.info("Reports feature coming soon!")

    st.markdown("---")

    # Footer
    st.markdown(
        """
    <div style='text-align: center; color: #666; padding: 20px;'>
        <p>© 2024 AEL ERP System | Version 1.0.0</p>
    </div>
    """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    render()
