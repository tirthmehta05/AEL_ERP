"""
Wrapper to run data discovery using existing app configuration

This script runs the data discovery by importing from the running app context.
"""

import sys
import os

# Set environment to bypass Streamlit warnings
os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Try to import and run
try:
    # Import the discovery class
    from scripts.01_data_discovery import DataDiscoveryReport
    
    # Get Google Sheets ID from environment or config
    from config import settings
    
    spreadsheet_id = settings.api.google_sheets_id
    
    if not spreadsheet_id:
        print("❌ ERROR: Google Sheets ID not configured!")
        print("Please ensure your config.py has the correct Google Sheets ID")
        sys.exit(1)
    
    # Import google drive service
    from src.shared.integrations.google_drive_service import google_drive_service
    
    print("\n🚀 Starting Data Discovery with your existing configuration...")
    
    # Create report instance
    report = DataDiscoveryReport(spreadsheet_id)
    
    # Run analysis
    report.analyze_all()
    
    print("\n✅ Data discovery complete!")
    print("\n📋 Next Steps:")
    print("1. Review the generated reports (CSV and HTML)")
    print("2. Fix CRITICAL and HIGH severity issues in your Google Sheets")
    print("3. Re-run this script until no critical issues remain")
    print("4. Then proceed with migration\n")
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("\nThis likely means the app needs to be running for configuration to load.")
    print("\nAlternative: Run the data discovery from within your Streamlit app")
    print("by adding a button that calls the DataDiscoveryReport class.")
    sys.exit(1)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
