"""
Test script for Google Drive Integration
Run this to test your Google Drive setup
"""

import streamlit as st
import os
import json
from datetime import date
from src.shared.integrations.google_drive_service import google_drive_service
from src.data_entry.service.rm_inward_service import RMInwardService
from src.data_entry.models.rm_inward_models import RMInwardIssueRequest

def main():
    st.title("🧪 Google Drive Integration Test")
    st.markdown("---")
    
    # Configuration section
    st.subheader("📋 Configuration")
    
    # Show current configuration
    st.write("**Current Configuration:**")
    col1, col2 = st.columns(2)
    
    with col1:
        st.write(f"**GOOGLE_SHEETS_ID:** {os.getenv('GOOGLE_SHEETS_ID', 'Not set')}")
        st.write(f"**GOOGLE_SERVICE_ACCOUNT_JSON:** {'✅ Set' if os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON') else '❌ Not set'}")
    
    with col2:
        st.write(f"**GOOGLE_SERVICE_ACCOUNT_PATH:** {os.getenv('GOOGLE_SERVICE_ACCOUNT_PATH', 'credentials/service-account-key.json')}")
        file_exists = os.path.exists(os.getenv('GOOGLE_SERVICE_ACCOUNT_PATH', 'credentials/service-account-key.json'))
        st.write(f"**Credentials File:** {'✅ Exists' if file_exists else '❌ Not found'}")
    
    # Get spreadsheet ID
    spreadsheet_id = st.text_input(
        "Google Sheets ID", 
        value=os.getenv('GOOGLE_SHEETS_ID', ''),
        help="Enter your Google Sheets ID (found in the URL)"
    )
    
    if spreadsheet_id:
        os.environ['GOOGLE_SHEETS_ID'] = spreadsheet_id
    
    # Credential setup section
    st.subheader("�� Credential Setup")
    
    # Option 1: Environment Variable
    st.write("**Option 1: Environment Variable (Recommended)**")
    credentials_json = st.text_area(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        value=os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', ''),
        help="Paste your entire service account JSON here (single line)",
        height=100
    )
    
    if st.button("Set Environment Variable"):
        if credentials_json:
            try:
                # Validate JSON
                json.loads(credentials_json)
                os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'] = credentials_json
                st.success("✅ Environment variable set successfully!")
                st.rerun()
            except json.JSONDecodeError:
                st.error("❌ Invalid JSON format!")
        else:
            st.error("❌ Please enter the JSON credentials")
    
    # Option 2: File Upload
    st.write("**Option 2: File Upload (Alternative)**")
    uploaded_file = st.file_uploader(
        "Upload Service Account JSON file",
        type=['json'],
        help="Upload your service account JSON file"
    )
    
    if uploaded_file:
        try:
            # Read and validate the uploaded file
            content = uploaded_file.read().decode('utf-8')
            json.loads(content)  # Validate JSON
            
            # Save to credentials directory
            os.makedirs('credentials', exist_ok=True)
            with open('credentials/service-account-key.json', 'w') as f:
                f.write(content)
            
            st.success("✅ File uploaded and saved successfully!")
            st.rerun()
            
        except json.JSONDecodeError:
            st.error("❌ Invalid JSON file!")
        except Exception as e:
            st.error(f"❌ Error saving file: {str(e)}")
    
    # Test connection
    st.subheader("🔗 Connection Test")
    
    if st.button("Test Google Drive Connection"):
        if google_drive_service.client:
            if google_drive_service.test_connection(spreadsheet_id):
                st.success("✅ Connection successful!")
                
                # Show available worksheets
                try:
                    spreadsheet = google_drive_service.client.open_by_key(spreadsheet_id)
                    worksheets = [ws.title for ws in spreadsheet.worksheets()]
                    st.info(f"📊 Available worksheets: {', '.join(worksheets)}")
                except Exception as e:
                    st.error(f"Error getting worksheets: {str(e)}")
            else:
                st.error("❌ Connection failed!")
        else:
            st.error("❌ Google Drive client not initialized!")
    
    # Test dropdown data
    st.subheader("📋 Dropdown Data Test")
    
    if st.button("Test Dropdown Data"):
        service = RMInwardService()
        dropdown_data = service.get_dropdown_data()
        
        st.write("**Dropdown Data:**")
        st.json(dropdown_data.dict())
    
    # Test form submission
    st.subheader("📝 Form Submission Test")
    
    with st.form("test_form"):
        st.write("**Test RM Inward Issue Form**")
        
        user_id = st.text_input("User ID", value="TEST_USER")
        rm_receipt_date = st.date_input("RM Receipt Date", value=date.today())
        rm_type = st.text_input("RM Type", value="TEST_TYPE")
        coil_number = st.text_input("Coil Number", value="TEST_COIL_001")
        grade = st.text_input("Grade", value="TEST_GRADE")
        thickness = st.text_input("Thickness", value="2.5")
        width = st.text_input("Width", value="1000")
        coating = st.text_input("Coating", value="TEST_COATING")
        coil_weight = st.number_input("Coil Weight", value=1000.0, min_value=0.01)
        coil_supplier = st.text_input("Coil Supplier", value="TEST_SUPPLIER")
        
        submitted = st.form_submit_button("Submit Test Data")
        
        if submitted:
            try:
                request = RMInwardIssueRequest(
                    user_id=user_id,
                    rm_receipt_date=rm_receipt_date,
                    rm_type=rm_type,
                    coil_number=coil_number,
                    grade=grade,
                    thickness=thickness,
                    width=width,
                    coating=coating,
                    coil_weight=coil_weight,
                    coil_supplier=coil_supplier
                )
                
                service = RMInwardService()
                success = service.create_rm_inward_issue(request)
                
                if success:
                    st.success("✅ Test data submitted successfully!")
                else:
                    st.error("❌ Failed to submit test data")
                    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # Show existing records
    st.subheader("📊 Existing Records")
    
    if st.button("Load Existing Records"):
        service = RMInwardService()
        records = service.get_existing_records(limit=5)
        
        if records:
            st.write(f"**Last {len(records)} records:**")
            for i, record in enumerate(records, 1):
                with st.expander(f"Record {i}"):
                    st.json(record)
        else:
            st.info("No records found or error loading records")
    
    # Setup instructions
    st.subheader("📖 Setup Instructions")
    
    with st.expander("How to get your Service Account JSON"):
        st.markdown("""
        ### Step 1: Create Service Account
        1. Go to [Google Cloud Console](https://console.cloud.google.com/)
        2. Create a new project or select existing one
        3. Enable Google Sheets API and Google Drive API
        4. Go to "Credentials" → "Create Credentials" → "Service Account"
        5. Fill in the service account details
        6. Create and download the JSON key file
        
        ### Step 2: Convert JSON to Single Line
        **Option A: Using Python**
        ```python
        import json
        with open('your-service-account-key.json', 'r') as f:
            data = json.load(f)
        print(json.dumps(data))
        ```
        
        **Option B: Using jq (if installed)**
        ```bash
        cat your-service-account-key.json | jq -c .
        ```
        
        **Option C: Manual**
        Copy the entire JSON content and remove all line breaks
        
        ### Step 3: Share Your Google Sheet
        1. Open your Google Sheet
        2. Click "Share" button
        3. Add the service account email (found in the JSON file)
        4. Give "Editor" permissions
        5. Copy the Sheet ID from the URL
        """)

if __name__ == "__main__":
    main()
