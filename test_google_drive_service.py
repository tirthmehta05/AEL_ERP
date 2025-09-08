"""
Test file for GoogleDriveService class
Run this file to test all methods of the GoogleDriveService

Usage:
    streamlit run test_google_drive_service.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import os
from src.shared.integrations.google_drive_service import GoogleDriveService

# Page configuration
st.set_page_config(
    page_title="Google Drive Service Test",
    page_icon="🔧",
    layout="wide"
)

st.title("🔧 Google Drive Service Test Suite")
st.markdown("Test all methods of the GoogleDriveService class")

# Initialize service
service = GoogleDriveService()

# Sidebar for configuration
st.sidebar.header("📋 Test Configuration")

# Get test parameters
spreadsheet_id = st.sidebar.text_input(
    "Spreadsheet ID", 
    value=os.getenv("GOOGLE_SHEETS_ID", ""),
    help="Enter the Google Sheets ID to test with"
)

worksheet_name = st.sidebar.text_input(
    "Worksheet Name", 
    value="Sheet1",
    help="Enter the worksheet name to test with"
)

column_name = st.sidebar.text_input(
    "Column Name", 
    value="A",
    help="Enter column name for dropdown options test"
)

# Test data
test_data = st.sidebar.text_area(
    "Test Data (JSON format)",
    value='[["Test User", "2024-01-01", "Test Type", "TEST001", "Grade A", "1.5", "1000", "Coating A", 1500.5, "Test Supplier"]]',
    help="Enter test data in JSON format for append test"
)

# Main content
if not spreadsheet_id:
    st.warning("⚠️ Please enter a Spreadsheet ID in the sidebar to run tests")
    st.stop()

# Create tabs for different test categories
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔗 Connection Test", 
    "📊 Data Reading", 
    "📝 Data Writing", 
    "🔽 Dropdown Options", 
    "📋 Headers & Info"
])

with tab1:
    st.header("🔗 Connection Test")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("Test Connection", type="primary"):
            with st.spinner("Testing connection..."):
                is_connected = service.test_connection(spreadsheet_id)
                
                if is_connected:
                    st.success("✅ Connection successful!")
                    st.balloons()
                else:
                    st.error("❌ Connection failed!")
    
    with col2:
        # Display client status
        st.subheader("Client Status")
        if service.client:
            st.success("✅ Google Drive client is initialized")
        else:
            st.error("❌ Google Drive client is not initialized")
        
        # Display credentials status
        st.subheader("Credentials Status")
        if service.credentials:
            st.success("✅ Credentials are loaded")
        else:
            st.error("❌ No credentials found")

with tab2:
    st.header("📊 Data Reading Tests")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("Get Worksheet Data", type="primary"):
            with st.spinner("Reading worksheet data..."):
                try:
                    df = service.get_worksheet_data(spreadsheet_id, worksheet_name)
                    
                    if not df.empty:
                        st.success(f"✅ Successfully read {len(df)} rows from '{worksheet_name}'")
                        st.dataframe(df, use_container_width=True)
                        
                        # Display data info
                        st.subheader("📈 Data Summary")
                        col_info1, col_info2, col_info3 = st.columns(3)
                        with col_info1:
                            st.metric("Total Rows", len(df))
                        with col_info2:
                            st.metric("Total Columns", len(df.columns))
                        with col_info3:
                            st.metric("Memory Usage", f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB")
                    else:
                        st.warning("⚠️ Worksheet is empty or doesn't exist")
                        
                except Exception as e:
                    st.error(f"❌ Error reading data: {str(e)}")
    
    with col2:
        st.subheader("📋 Available Worksheets")
        if st.button("List Worksheets"):
            with st.spinner("Getting worksheet list..."):
                try:
                    if service.client:
                        spreadsheet = service.client.open_by_key(spreadsheet_id)
                        worksheets = spreadsheet.worksheets()
                        
                        st.success(f"✅ Found {len(worksheets)} worksheets")
                        
                        for i, ws in enumerate(worksheets):
                            st.write(f"{i+1}. **{ws.title}** (ID: {ws.id})")
                    else:
                        st.error("❌ Client not initialized")
                        
                except Exception as e:
                    st.error(f"❌ Error listing worksheets: {str(e)}")

with tab3:
    st.header("📝 Data Writing Tests")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Append Test Data")
        if st.button("Append Test Data", type="primary"):
            with st.spinner("Appending test data..."):
                try:
                    import json
                    test_data_list = json.loads(test_data)
                    
                    success = service.append_data(spreadsheet_id, worksheet_name, test_data_list)
                    
                    if success:
                        st.success("✅ Test data appended successfully!")
                        st.balloons()
                        
                        # Show what was appended
                        st.subheader("📤 Appended Data")
                        st.json(test_data_list)
                    else:
                        st.error("❌ Failed to append test data")
                        
                except json.JSONDecodeError:
                    st.error("❌ Invalid JSON format in test data")
                except Exception as e:
                    st.error(f"❌ Error appending data: {str(e)}")
    
    with col2:
        st.subheader("Custom Data Entry")
        st.write("Enter custom data to append:")
        
        # Simple form for custom data
        with st.form("custom_data_form"):
            custom_data = st.text_area(
                "Data (one row per line, comma-separated values)",
                placeholder="Value1,Value2,Value3\nValue4,Value5,Value6"
            )
            
            if st.form_submit_button("Append Custom Data"):
                if custom_data.strip():
                    try:
                        # Parse custom data
                        rows = []
                        for line in custom_data.strip().split('\n'):
                            if line.strip():
                                row = [cell.strip() for cell in line.split(',')]
                                rows.append(row)
                        
                        if rows:
                            success = service.append_data(spreadsheet_id, worksheet_name, rows)
                            
                            if success:
                                st.success(f"✅ Appended {len(rows)} rows successfully!")
                            else:
                                st.error("❌ Failed to append custom data")
                        else:
                            st.warning("⚠️ No valid data to append")
                            
                    except Exception as e:
                        st.error(f"❌ Error processing custom data: {str(e)}")
                else:
                    st.warning("⚠️ Please enter some data")

with tab4:
    st.header("🔽 Dropdown Options Tests")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("Get Dropdown Options", type="primary"):
            with st.spinner("Getting dropdown options..."):
                try:
                    options = service.get_dropdown_options(spreadsheet_id, worksheet_name, column_name)
                    
                    if options:
                        st.success(f"✅ Found {len(options)} unique options in column '{column_name}'")
                        
                        # Display options
                        st.subheader(f"📋 Options from Column '{column_name}'")
                        for i, option in enumerate(options, 1):
                            st.write(f"{i}. {option}")
                        
                        # Show as selectbox
                        st.subheader("🎯 Test Dropdown")
                        selected_option = st.selectbox(
                            f"Select from column '{column_name}':",
                            options=[""] + options
                        )
                        if selected_option:
                            st.write(f"Selected: **{selected_option}**")
                    else:
                        st.warning(f"⚠️ No options found in column '{column_name}'")
                        
                except Exception as e:
                    st.error(f"❌ Error getting dropdown options: {str(e)}")
    
    with col2:
        st.subheader("🔍 Column Analysis")
        if st.button("Analyze All Columns"):
            with st.spinner("Analyzing columns..."):
                try:
                    df = service.get_worksheet_data(spreadsheet_id, worksheet_name)
                    
                    if not df.empty:
                        st.success("✅ Column analysis complete")
                        
                        # Show column info
                        st.subheader("📊 Column Information")
                        for col in df.columns:
                            unique_count = df[col].nunique()
                            null_count = df[col].isnull().sum()
                            
                            col1, col2, col3 = st.columns([2, 1, 1])
                            with col1:
                                st.write(f"**{col}**")
                            with col2:
                                st.write(f"Unique: {unique_count}")
                            with col3:
                                st.write(f"Null: {null_count}")
                    else:
                        st.warning("⚠️ No data to analyze")
                        
                except Exception as e:
                    st.error(f"❌ Error analyzing columns: {str(e)}")

with tab5:
    st.header("📋 Headers & Information")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("Get Worksheet Headers", type="primary"):
            with st.spinner("Getting headers..."):
                try:
                    headers = service.get_worksheet_headers(spreadsheet_id, worksheet_name)
                    
                    if headers:
                        st.success(f"✅ Found {len(headers)} headers in '{worksheet_name}'")
                        
                        st.subheader("📋 Column Headers")
                        for i, header in enumerate(headers, 1):
                            st.write(f"{i}. **{header}**")
                        
                        # Show as JSON
                        st.subheader("📄 Headers as JSON")
                        st.json(headers)
                    else:
                        st.warning("⚠️ No headers found")
                        
                except Exception as e:
                    st.error(f"❌ Error getting headers: {str(e)}")
    
    with col2:
        st.subheader("🔧 Service Information")
        
        # Display service configuration
        st.write("**Service Configuration:**")
        st.write(f"- Scope: {len(service.scope)} permissions")
        st.write(f"- Client Status: {'✅ Initialized' if service.client else '❌ Not Initialized'}")
        st.write(f"- Credentials Status: {'✅ Loaded' if service.credentials else '❌ Not Loaded'}")
        
        # Display environment info
        st.write("**Environment Information:**")
        st.write(f"- GOOGLE_SHEETS_ID: {'✅ Set' if os.getenv('GOOGLE_SHEETS_ID') else '❌ Not Set'}")
        st.write(f"- GOOGLE_SERVICE_ACCOUNT_JSON: {'✅ Set' if os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON') else '❌ Not Set'}")
        st.write(f"- GOOGLE_SERVICE_ACCOUNT_PATH: {'✅ Set' if os.getenv('GOOGLE_SERVICE_ACCOUNT_PATH') else '❌ Not Set'}")

# Footer
st.markdown("---")
st.markdown("**Test completed at:** " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# Instructions
with st.expander("📖 How to Use This Test Suite"):
    st.markdown("""
    ### Setup Instructions:
    
    1. **Set up Google Service Account:**
       - Create a service account in Google Cloud Console
       - Download the JSON key file
       - Add the JSON content to your `.env` file as `GOOGLE_SERVICE_ACCOUNT_JSON`
       - Set `GOOGLE_SHEETS_ID` in your `.env` file
    
    2. **Share your Google Sheet:**
       - Open your Google Sheet
       - Click "Share" and add your service account email
       - Give "Editor" permissions
    
    3. **Run Tests:**
       - Enter your Spreadsheet ID in the sidebar
       - Adjust worksheet name and column name as needed
       - Click the test buttons in each tab
    
    ### Test Categories:
    
    - **Connection Test:** Verify connection to your spreadsheet
    - **Data Reading:** Read and display worksheet data
    - **Data Writing:** Append test data to your worksheet
    - **Dropdown Options:** Extract unique values for dropdowns
    - **Headers & Info:** Get column headers and service information
    
    ### Troubleshooting:
    
    - If connection fails, check your credentials and sheet permissions
    - If data reading fails, verify the worksheet name exists
    - If writing fails, ensure the service account has edit permissions
    """)
