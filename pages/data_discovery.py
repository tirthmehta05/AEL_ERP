"""
Data Discovery Page - Run from Streamlit App

This page runs data quality checks on your Google Sheets
and generates reports for migration preparation.
"""

import streamlit as st
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.shared.integrations.google_drive_service import google_drive_service
from config import settings

st.set_page_config(
    page_title="Data Discovery - AEL ERP",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 Data Discovery & Quality Check")
st.markdown("---")

st.info("""
**Purpose**: Analyze your Google Sheets data to identify issues BEFORE migration.

This tool will check for:
- Duplicate records (Job Cards, Coil Numbers, Receipt Numbers)
- Invalid data (dates, weights, JSON)
- Orphaned records (broken references)
- Missing required fields
- Referential integrity issues
""")

# Import the discovery class
from scripts.01_data_discovery import DataDiscoveryReport

if st.button("🚀 Run Data Discovery", type="primary", use_container_width=True):
    
    with st.spinner("Analyzing data... This may take 1-2 minutes..."):
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        spreadsheet_id = settings.api.google_sheets_id
        
        if not spreadsheet_id:
            st.error("❌ Google Sheets ID not configured!")
            st.stop()
        
        try:
            # Create report instance
            report = DataDiscoveryReport(spreadsheet_id)
            
            # Monkey-patch to show progress
            original_check_sales_orders = report.check_sales_orders
            original_check_raw_material = report.check_raw_material
            original_check_weight_receipts = report.check_weight_receipts
            original_check_finished_goods = report.check_finished_goods_transfer
            original_check_slitting_plans = report.check_slitting_plans
            original_check_integrity = report.check_referential_integrity
            
            def tracked_sales_orders():
                status_text.text("📋 Analyzing Sales Orders...")
                progress_bar.progress(15)
                return original_check_sales_orders()
            
            def tracked_raw_material():
                status_text.text("📦 Analyzing Raw Material...")
                progress_bar.progress(30)
                return original_check_raw_material()
            
            def tracked_weight_receipts():
                status_text.text("⚖️ Analyzing Weight Receipts...")
                progress_bar.progress(45)
                return original_check_weight_receipts()
            
            def tracked_finished_goods():
                status_text.text("📦 Analyzing Finished Goods...")
                progress_bar.progress(60)
                return original_check_finished_goods()
            
            def tracked_slitting_plans():
                status_text.text("🔪 Analyzing Slitting Plans...")
                progress_bar.progress(75)
                return original_check_slitting_plans()
            
            def tracked_integrity():
                status_text.text("🔗 Checking Referential Integrity...")
                progress_bar.progress(90)
                return original_check_integrity()
            
            report.check_sales_orders = tracked_sales_orders
            report.check_raw_material = tracked_raw_material
            report.check_weight_receipts = tracked_weight_receipts
            report.check_finished_goods_transfer = tracked_finished_goods
            report.check_slitting_plans = tracked_slitting_plans
            report.check_referential_integrity = tracked_integrity
            
            # Run analysis
            status_text.text("🔍 Starting analysis...")
            progress_bar.progress(5)
            
            report.analyze_all()
            
            progress_bar.progress(100)
            status_text.text("✅ Analysis complete!")
            
            # Display results
            st.success("✅ Data discovery completed successfully!")
            
            # Summary
            st.markdown("---")
            st.subheader("📊 Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            
            critical = len([i for i in report.issues if i['severity'] == 'CRITICAL'])
            high = len([i for i in report.issues if i['severity'] == 'HIGH'])
            medium = len([i for i in report.issues if i['severity'] == 'MEDIUM'])
            low = len([i for i in report.issues if i['severity'] == 'LOW'])
            
            with col1:
                st.metric("🔴 Critical", critical)
            with col2:
                st.metric("🟠 High", high)
            with col3:
                st.metric("🟡 Medium", medium)
            with col4:
                st.metric("🟢 Low", low)
            
            # Display issues by severity
            if report.issues:
                st.markdown("---")
                st.subheader("⚠️ Issues Found")
                
                # Filter controls
                severity_filter = st.multiselect(
                    "Filter by Severity",
                    options=['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
                    default=['CRITICAL', 'HIGH']
                )
                
                filtered_issues = [i for i in report.issues if i['severity'] in severity_filter]
                
                if filtered_issues:
                    for issue in filtered_issues:
                        severity = issue['severity']
                        
                        # Color coding
                        if severity == 'CRITICAL':
                            icon = "🔴"
                            color = "red"
                        elif severity == 'HIGH':
                            icon = "🟠"
                            color = "orange"
                        elif severity == 'MEDIUM':
                            icon = "🟡"
                            color = "yellow"
                        else:
                            icon = "🟢"
                            color = "green"
                        
                        with st.expander(f"{icon} {severity} - {issue['table']}: {issue['issue']}", expanded=(severity in ['CRITICAL', 'HIGH'])):
                            st.markdown(f"**Category**: {issue['category']}")
                            st.markdown(f"**Issue**: {issue['issue']}")
                            
                            if issue.get('sample'):
                                st.markdown("**Sample Data**:")
                                st.json(issue['sample'])
                            
                            st.markdown(f"**Action Required**: {issue['action']}")
                else:
                    st.info("No issues match the selected severity filters.")
            else:
                st.success("🎉 No issues found! Your data is clean and ready for migration!")
            
            # Statistics
            if report.stats:
                st.markdown("---")
                st.subheader("📈 Data Statistics")
                
                stats_cols = st.columns(3)
                for idx, (table, stats) in enumerate(report.stats.items()):
                    with stats_cols[idx % 3]:
                        st.metric(table.replace('_', ' ').title(), f"{stats.get('total_rows', stats.get('total_rows_so', 0))} rows")
            
            # Next steps
            st.markdown("---")
            st.subheader("📋 Next Steps")
            
            if critical > 0 or high > 0:
                st.warning("""
                **⚠️ Action Required Before Migration:**
                
                1. **Fix CRITICAL issues first** (duplicate keys, invalid references)
                2. **Fix HIGH issues next** (missing data, invalid formats)
                3. **Re-run this discovery** until no critical/high issues remain
                4. **Then proceed with migration**
                
                Reports have been saved to `/app/` directory for detailed review.
                """)
            else:
                st.success("""
                **✅ Ready for Migration!**
                
                Your data quality looks good. You can proceed with:
                1. Dry-run migration (test without committing)
                2. Live migration (import all data to database)
                
                Navigate to the **Migration** page to continue.
                """)
            
        except Exception as e:
            st.error(f"❌ Error during analysis: {e}")
            st.exception(e)

# File download section
st.markdown("---")
st.subheader("📁 Download Reports")

# List available reports
import glob
csv_reports = sorted(glob.glob("/app/data_quality_report_*.csv"), reverse=True)
html_reports = sorted(glob.glob("/app/data_quality_report_*.html"), reverse=True)

if csv_reports or html_reports:
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**CSV Reports**")
        for report_file in csv_reports[:5]:  # Show last 5
            filename = os.path.basename(report_file)
            with open(report_file, 'r') as f:
                st.download_button(
                    label=f"📥 {filename}",
                    data=f.read(),
                    file_name=filename,
                    mime="text/csv"
                )
    
    with col2:
        st.markdown("**HTML Reports**")
        for report_file in html_reports[:5]:  # Show last 5
            filename = os.path.basename(report_file)
            with open(report_file, 'r') as f:
                st.download_button(
                    label=f"📥 {filename}",
                    data=f.read(),
                    file_name=filename,
                    mime="text/html"
                )
else:
    st.info("No reports available yet. Run the discovery above to generate reports.")
