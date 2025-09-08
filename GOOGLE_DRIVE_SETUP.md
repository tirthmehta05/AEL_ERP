# Google Drive Integration Setup Guide

## Prerequisites
1. Google Cloud Console account
2. Google Sheets with your data
3. Python environment with required packages

## Step 1: Install Required Packages

```bash
conda activate ael_erp_dev
conda install -c conda-forge google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client gspread gspread-dataframe
```

## Step 2: Create Google Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google Sheets API and Google Drive API
4. Go to "Credentials" → "Create Credentials" → "Service Account"
5. Fill in the service account details
6. Create and download the JSON key file

## Step 3: Set Up Your Google Sheet

### Required Worksheets:
Your Google Sheet should have these worksheets:

1. **RM inward_Issue_format** - Main data sheet
2. **Users** - User ID dropdown data
3. **RM Types** - RM Type dropdown data  
4. **Coil Numbers** - Coil Number dropdown data
5. **Grades** - Grade dropdown data
6. **Thicknesses** - Thickness dropdown data
7. **Widths** - Width dropdown data
8. **Coatings** - Coating dropdown data
9. **Suppliers** - Supplier dropdown data

### Sheet Structure:
Each dropdown sheet should have a header row with the column name:
- Users sheet: Column A = "User ID"
- RM Types sheet: Column A = "RM Type"
- etc.

## Step 4: Share Your Google Sheet

1. Open your Google Sheet
2. Click "Share" button
3. Add the service account email (found in your JSON key file)
4. Give "Editor" permissions
5. Copy the Sheet ID from the URL

## Step 5: Configure Environment Variables

### Option 1: Environment Variable (Recommended)

Add to your `.env` file:
```bash
# Google Sheets Configuration
GOOGLE_SHEETS_ID=your_sheet_id_here

# Google Service Account JSON (Single line)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"your-project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"your-service-account@your-project.iam.gserviceaccount.com","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"}
```

### Option 2: File-based (Alternative)

Add to your `.env` file:
```bash
# Google Sheets Configuration
GOOGLE_SHEETS_ID=your_sheet_id_here

# Google Service Account File Path
GOOGLE_SERVICE_ACCOUNT_PATH=credentials/service-account-key.json
```

## Step 6: Convert JSON to Single Line (for Environment Variable)

### Method 1: Using Python
```python
import json
with open('your-service-account-key.json', 'r') as f:
    data = json.load(f)
print(json.dumps(data))
```

### Method 2: Using jq (if installed)
```bash
cat your-service-account-key.json | jq -c .
```

### Method 3: Manual
Copy the entire JSON content and remove all line breaks

## Step 7: Test the Integration

Run the test script:
```bash
streamlit run test_google_drive_integration.py
```

## Usage Example

```python
from src.data_entry.service.rm_inward_service import RMInwardService
from src.data_entry.models.rm_inward_models import RMInwardIssueRequest
from datetime import date

# Initialize service
service = RMInwardService()

# Get dropdown data
dropdown_data = service.get_dropdown_data()
print(f"Available users: {dropdown_data.user_ids}")

# Create new record
request = RMInwardIssueRequest(
    user_id="USER001",
    rm_receipt_date=date.today(),
    rm_type="Steel Coil",
    coil_number="COIL001",
    grade="SS304",
    thickness="2.5",
    width="1000",
    coating="Galvanized",
    coil_weight=1500.0,
    coil_supplier="Supplier A"
)

# Submit to Google Sheets
success = service.create_rm_inward_issue(request)
if success:
    print("Record created successfully!")
```

## Benefits of Environment Variable Approach

1. **✅ More Secure** - No files to accidentally commit
2. **✅ Docker Friendly** - Easy to inject in containers
3. **✅ Production Ready** - Standard practice for cloud deployments
4. **✅ No File Dependencies** - Works in serverless environments
5. **✅ Version Control Safe** - No risk of committing credentials

## Troubleshooting

### Common Issues:

1. **"Service account file not found"**
   - Check the path to your JSON key file
   - Ensure the file exists and is readable

2. **"Permission denied"**
   - Make sure you shared the sheet with the service account email
   - Check that the service account has Editor permissions

3. **"Worksheet not found"**
   - Verify all required worksheets exist
   - Check worksheet names match exactly (case-sensitive)

4. **"Column not found"**
   - Ensure each dropdown sheet has the correct column header
   - Check for typos in column names

5. **"Invalid JSON in environment variable"**
   - Ensure the JSON is properly formatted as a single line
   - Use the conversion methods above to format correctly

### Debug Mode:
Set environment variable for detailed logging:
```bash
export GOOGLE_DRIVE_DEBUG=true
```

## Security Best Practices

1. **Never commit credentials to version control**
2. **Use environment variables in production**
3. **Rotate service account keys regularly**
4. **Limit service account permissions to minimum required**
5. **Monitor service account usage**
