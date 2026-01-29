"""
Data Discovery Script for AEL ERP Migration

Analyzes Google Sheets data to identify:
- Duplicates
- Missing required fields
- Invalid data types
- Orphaned records (broken references)
- Data quality issues

Run this BEFORE attempting migration!
"""

import pandas as pd
from datetime import datetime
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.shared.integrations.google_drive_service import google_drive_service
from config import settings


class DataDiscoveryReport:
    """Analyzes Google Sheets and generates comprehensive data quality report"""
    
    def __init__(self, spreadsheet_id):
        self.spreadsheet_id = spreadsheet_id
        self.issues = []
        self.stats = {}
        
    def analyze_all(self):
        """Run all data quality checks"""
        print("\n" + "="*60)
        print("🔍 AEL ERP DATA DISCOVERY REPORT")
        print("="*60)
        print(f"Spreadsheet ID: {self.spreadsheet_id}")
        print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60 + "\n")
        
        # Run all checks
        self.check_sales_orders()
        self.check_raw_material()
        self.check_weight_receipts()
        self.check_weight_receipt_drafts()
        self.check_finished_goods_transfer()
        self.check_slitting_plans()
        self.check_referential_integrity()
        
        # Generate reports
        self.generate_report()
        self.generate_html_report()
        
    def check_sales_orders(self):
        """Validate Sales Order data"""
        print("\n📋 Analyzing Sales Orders...")
        
        try:
            # Get both sheets
            df_so = self.get_sheet_data("Sales Order")
            df_jc = self.get_sheet_data("Sales Order-JC", header_row=1)
            
            # Statistics
            self.stats['sales_orders'] = {
                'total_rows_so': len(df_so),
                'total_rows_jc': len(df_jc)
            }
            
            # Issue 1: Duplicate Job Card numbers in main sheet
            if 'Job Card' in df_so.columns:
                duplicates = df_so[df_so.duplicated(['Job Card'], keep=False)]
                if not duplicates.empty:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Duplicates',
                        'table': 'Sales Order',
                        'issue': f'Found {len(duplicates)} duplicate Job Card numbers',
                        'sample': duplicates['Job Card'].unique().tolist()[:5],
                        'action': 'MANUAL: Decide which to keep, update others with -REV suffix',
                        'count': len(duplicates)
                    })
            
            # Issue 2: Duplicate Job Card numbers in JC sheet
            if 'job_card_number' in df_jc.columns:
                duplicates_jc = df_jc[df_jc.duplicated(['job_card_number'], keep=False)]
                if not duplicates_jc.empty:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Duplicates',
                        'table': 'Sales Order-JC',
                        'issue': f'Found {len(duplicates_jc)} duplicate Job Card numbers',
                        'sample': duplicates_jc['job_card_number'].unique().tolist()[:5],
                        'action': 'MANUAL: Resolve duplicates before migration',
                        'count': len(duplicates_jc)
                    })
            
            # Issue 3: Invalid dates
            if 'Order Entry Date' in df_so.columns and 'Delivery Date' in df_so.columns:
                df_so['Order Entry Date'] = pd.to_datetime(df_so['Order Entry Date'], errors='coerce', dayfirst=True)
                df_so['Delivery Date'] = pd.to_datetime(df_so['Delivery Date'], errors='coerce', dayfirst=True)
                
                invalid_dates = df_so[df_so['Order Entry Date'].isna() | df_so['Delivery Date'].isna()]
                if not invalid_dates.empty:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Invalid Data',
                        'table': 'Sales Order',
                        'issue': f'{len(invalid_dates)} rows with invalid dates',
                        'sample': invalid_dates[['Job Card', 'Order Entry Date', 'Delivery Date']].head(3).to_dict('records'),
                        'action': 'MANUAL: Fix date formats or remove invalid rows',
                        'count': len(invalid_dates)
                    })
                
                # Illogical dates (delivery before order)
                illogical_dates = df_so[df_so['Delivery Date'] < df_so['Order Entry Date']]
                if not illogical_dates.empty:
                    self.issues.append({
                        'severity': 'MEDIUM',
                        'category': 'Business Logic',
                        'table': 'Sales Order',
                        'issue': f'{len(illogical_dates)} orders with delivery before order date',
                        'sample': illogical_dates[['Job Card', 'Order Entry Date', 'Delivery Date']].head(3).to_dict('records'),
                        'action': 'MANUAL: Verify which date is correct',
                        'count': len(illogical_dates)
                    })
            
            # Issue 4: Missing Party Names
            if 'Party Name' in df_so.columns:
                missing_party = df_so[df_so['Party Name'].isna() | (df_so['Party Name'] == '')]
                if not missing_party.empty:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Missing Data',
                        'table': 'Sales Order',
                        'issue': f'{len(missing_party)} orders without Party Name',
                        'sample': missing_party['Job Card'].tolist()[:5] if 'Job Card' in missing_party else [],
                        'action': 'MANUAL: Fill in customer names or mark as internal',
                        'count': len(missing_party)
                    })
            
            # Issue 5: Invalid weights
            if 'Qty' in df_so.columns:
                df_so['Qty'] = pd.to_numeric(df_so['Qty'], errors='coerce')
                invalid_weights = df_so[(df_so['Qty'] <= 0) | (df_so['Qty'].isna())]
                if not invalid_weights.empty:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Invalid Data',
                        'table': 'Sales Order',
                        'issue': f'{len(invalid_weights)} designs with invalid weights',
                        'sample': invalid_weights[['Job Card', 'Qty']].head(3).to_dict('records') if 'Job Card' in invalid_weights else [],
                        'action': 'MANUAL: Correct weights or remove invalid designs',
                        'count': len(invalid_weights)
                    })
            
            # Issue 6: Invalid JSON in designs_json (Sales Order-JC)
            if 'designs_json' in df_jc.columns:
                invalid_json_count = 0
                for idx, row in df_jc.iterrows():
                    designs_json = row.get('designs_json')
                    if pd.notna(designs_json):
                        try:
                            json.loads(designs_json)
                        except:
                            invalid_json_count += 1
                
                if invalid_json_count > 0:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Invalid Data',
                        'table': 'Sales Order-JC',
                        'issue': f'{invalid_json_count} rows with invalid designs_json',
                        'action': 'MANUAL: Fix JSON format or regenerate from Sales Order sheet',
                        'count': invalid_json_count
                    })
            
            print(f"   ✅ Found {len([i for i in self.issues if i['table'] in ['Sales Order', 'Sales Order-JC']])} issues")
            
        except Exception as e:
            print(f"   ❌ Error analyzing Sales Orders: {e}")
            self.issues.append({
                'severity': 'CRITICAL',
                'category': 'System Error',
                'table': 'Sales Order',
                'issue': f'Failed to analyze: {str(e)}',
                'action': 'CHECK: Verify sheet exists and has correct structure'
            })
    
    def check_raw_material(self):
        """Validate Raw Material data"""
        print("\n📦 Analyzing Raw Material...")
        
        try:
            df_rm = self.get_sheet_data("RM inward_Issue format", header_row=2)
            
            self.stats['raw_material'] = {'total_rows': len(df_rm)}
            
            # Issue 1: Duplicate coil numbers
            if 'Coil Number' in df_rm.columns:
                duplicates = df_rm[df_rm.duplicated(['Coil Number'], keep=False)]
                if not duplicates.empty:
                    self.issues.append({
                        'severity': 'CRITICAL',
                        'category': 'Duplicates',
                        'table': 'RM Inward',
                        'issue': f'Found {len(duplicates)} duplicate Coil Numbers',
                        'sample': duplicates['Coil Number'].unique().tolist()[:5],
                        'action': 'MANUAL: Each coil MUST have unique number. Rename with suffix',
                        'count': len(duplicates)
                    })
            
            # Issue 2: Negative available weight
            if 'Material in stock' in df_rm.columns:
                df_rm['Material in stock'] = pd.to_numeric(df_rm['Material in stock'], errors='coerce')
                negative_stock = df_rm[df_rm['Material in stock'] < 0]
                if not negative_stock.empty:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Invalid Data',
                        'table': 'RM Inward',
                        'issue': f'{len(negative_stock)} coils with negative available weight',
                        'sample': negative_stock[['Coil Number', 'Coil Weight', 'Material in stock']].head(3).to_dict('records') if 'Coil Number' in negative_stock else [],
                        'action': 'MANUAL: Check if over-allocated. Adjust allocations or fix weight',
                        'count': len(negative_stock)
                    })
            
            # Issue 3: Missing critical fields
            critical_fields = ['Coil Number', 'Grade', 'Thk', 'Width', 'Coil Weight']
            for field in critical_fields:
                if field in df_rm.columns:
                    missing = df_rm[df_rm[field].isna() | (df_rm[field] == '')]
                    if not missing.empty:
                        self.issues.append({
                            'severity': 'HIGH',
                            'category': 'Missing Data',
                            'table': 'RM Inward',
                            'issue': f'{len(missing)} coils missing {field}',
                            'sample': missing['Coil Number'].tolist()[:5] if 'Coil Number' in missing else [],
                            'action': f'MANUAL: Fill in {field} or remove incomplete records',
                            'count': len(missing)
                        })
            
            print(f"   ✅ Found {len([i for i in self.issues if i['table'] == 'RM Inward'])} issues")
            
        except Exception as e:
            print(f"   ❌ Error analyzing Raw Material: {e}")
            self.issues.append({
                'severity': 'CRITICAL',
                'category': 'System Error',
                'table': 'RM Inward',
                'issue': f'Failed to analyze: {str(e)}',
                'action': 'CHECK: Verify sheet exists and header is on row 2'
            })
    
    def check_weight_receipts(self):
        """Validate Weight Receipt data"""
        print("\n⚖️  Analyzing Weight Receipts...")
        
        try:
            df_wr = self.get_sheet_data("WeightReceipts")
            
            self.stats['weight_receipts'] = {'total_rows': len(df_wr)}
            
            # Issue 1: Duplicate receipt numbers
            if 'WeightReceiptNumber' in df_wr.columns:
                duplicates = df_wr[df_wr.duplicated(['WeightReceiptNumber'], keep=False)]
                if not duplicates.empty:
                    self.issues.append({
                        'severity': 'CRITICAL',
                        'category': 'Duplicates',
                        'table': 'WeightReceipts',
                        'issue': f'Found {len(duplicates)} duplicate Weight Receipt Numbers',
                        'sample': duplicates['WeightReceiptNumber'].unique().tolist()[:5],
                        'action': 'MANUAL: Receipt numbers must be unique. Regenerate duplicates',
                        'count': len(duplicates)
                    })
            
            # Issue 2: Invalid JSON in designs
            if 'DesignDetailsWithWeightsJSON' in df_wr.columns:
                invalid_json_count = 0
                for idx, row in df_wr.iterrows():
                    designs_json = row.get('DesignDetailsWithWeightsJSON')
                    if pd.notna(designs_json):
                        try:
                            json.loads(designs_json)
                        except:
                            invalid_json_count += 1
                
                if invalid_json_count > 0:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Invalid Data',
                        'table': 'WeightReceipts',
                        'issue': f'{invalid_json_count} receipts with invalid JSON',
                        'action': 'MANUAL: Fix JSON format',
                        'count': invalid_json_count
                    })
            
            # Issue 3: Negative weights
            if 'TotalWeight' in df_wr.columns:
                df_wr['TotalWeight'] = pd.to_numeric(df_wr['TotalWeight'], errors='coerce')
                negative_weight = df_wr[df_wr['TotalWeight'] <= 0]
                if not negative_weight.empty:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Invalid Data',
                        'table': 'WeightReceipts',
                        'issue': f'{len(negative_weight)} receipts with zero or negative weight',
                        'sample': negative_weight[['WeightReceiptNumber', 'TotalWeight']].head(3).to_dict('records') if 'WeightReceiptNumber' in negative_weight else [],
                        'action': 'MANUAL: Fix weights or remove invalid receipts',
                        'count': len(negative_weight)
                    })
            
            print(f"   ✅ Found {len([i for i in self.issues if i['table'] == 'WeightReceipts'])} issues")
            
        except Exception as e:
            print(f"   ❌ Error analyzing Weight Receipts: {e}")
    
    def check_weight_receipt_drafts(self):
        """Validate Weight Receipt Draft sheet"""
        print("\n📝 Analyzing Weight Receipt Drafts...")
        
        try:
            df = self.get_sheet_data("Weight Receipt Draft")
            
            if df.empty:
                print("   ℹ️  No draft data found (this is OK)")
                return
            
            self.stats['weight_receipt_drafts'] = {'total_rows': len(df)}
            
            # Check for orphaned drafts (job cards that don't exist)
            df_jc = self.get_sheet_data("Sales Order-JC", header_row=1)
            
            if 'job_card_number' in df_jc.columns and 'JobCardNumber' in df.columns:
                valid_job_cards = set(df_jc['job_card_number'].dropna().unique())
                draft_job_cards = set(df['JobCardNumber'].dropna().unique())
                orphaned_drafts = draft_job_cards - valid_job_cards
                
                if orphaned_drafts:
                    self.issues.append({
                        'severity': 'MEDIUM',
                        'category': 'Orphaned Drafts',
                        'table': 'Weight Receipt Draft',
                        'issue': f'{len(orphaned_drafts)} drafts reference non-existent job cards',
                        'sample': list(orphaned_drafts)[:5],
                        'action': 'SAFE TO DELETE: These are abandoned drafts from deleted/renamed job cards',
                        'count': len(orphaned_drafts)
                    })
            
            print(f"   ✅ Found {len([i for i in self.issues if i['table'] == 'Weight Receipt Draft'])} issues")
            
        except Exception as e:
            print(f"   ⚠️  Weight Receipt Draft sheet not found or empty (this is OK)")
    
    def check_finished_goods_transfer(self):
        """Validate Finished Goods Transfer sheet (headers on row 2!)"""
        print("\n📦 Analyzing Finished Goods Transfer...")
        
        try:
            df = self.get_sheet_data("Finished Goods Transfer", header_row=2)
            
            if df.empty:
                print("   ℹ️  No finished goods data found")
                return
            
            self.stats['finished_goods'] = {'total_rows': len(df)}
            
            # Issue 1: Negative FG Qty
            if 'FG Qty' in df.columns:
                df['FG Qty'] = pd.to_numeric(df['FG Qty'], errors='coerce')
                negative_qty = df[df['FG Qty'] < 0]
                
                if not negative_qty.empty:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Invalid Data',
                        'table': 'Finished Goods Transfer',
                        'issue': f'{len(negative_qty)} entries with negative FG Qty',
                        'sample': negative_qty[['Job Card', 'FG Qty']].head(3).to_dict('records') if 'Job Card' in negative_qty else [],
                        'action': 'MANUAL: Check if these are correction entries or errors',
                        'count': len(negative_qty)
                    })
            
            # Issue 2: Orphaned Job Cards
            df_so = self.get_sheet_data("Sales Order")
            
            if 'Job Card' in df_so.columns and 'Job Card' in df.columns:
                valid_job_cards = set(df_so['Job Card'].dropna().unique())
                fg_job_cards = set(df['Job Card'].dropna().unique())
                orphaned_fg = fg_job_cards - valid_job_cards
                
                if orphaned_fg:
                    self.issues.append({
                        'severity': 'MEDIUM',
                        'category': 'Orphaned Records',
                        'table': 'Finished Goods Transfer',
                        'issue': f'{len(orphaned_fg)} FG entries for non-existent job cards',
                        'sample': list(orphaned_fg)[:5],
                        'action': 'REVIEW: May be legacy data or renamed job cards',
                        'count': len(orphaned_fg)
                    })
            
            print(f"   ✅ Found {len([i for i in self.issues if i['table'] == 'Finished Goods Transfer'])} issues")
            
        except Exception as e:
            print(f"   ⚠️  Error analyzing Finished Goods: {e}")
    
    def check_slitting_plans(self):
        """Validate Slitting Plans"""
        print("\n🔪 Analyzing Slitting Plans...")
        
        try:
            df = self.get_sheet_data("SlittingPlans")
            
            if df.empty:
                print("   ℹ️  No slitting plans found")
                return
            
            self.stats['slitting_plans'] = {'total_rows': len(df)}
            
            # Issue 1: Duplicate Plan IDs
            if 'PlanID' in df.columns:
                duplicates = df[df.duplicated(['PlanID'], keep=False)]
                if not duplicates.empty:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Duplicates',
                        'table': 'SlittingPlans',
                        'issue': f'Found {len(duplicates)} duplicate Plan IDs',
                        'sample': duplicates['PlanID'].unique().tolist()[:5],
                        'action': 'MANUAL: Plan IDs must be unique. Rename duplicates',
                        'count': len(duplicates)
                    })
            
            # Issue 2: Invalid JSON
            for json_col in ['RawMaterialsJSON', 'SlitDetailsJSON']:
                if json_col in df.columns:
                    invalid_json_count = 0
                    for idx, row in df.iterrows():
                        json_data = row.get(json_col)
                        if pd.notna(json_data):
                            try:
                                json.loads(json_data)
                            except:
                                invalid_json_count += 1
                    
                    if invalid_json_count > 0:
                        self.issues.append({
                            'severity': 'HIGH',
                            'category': 'Invalid Data',
                            'table': 'SlittingPlans',
                            'issue': f'{invalid_json_count} plans with invalid {json_col}',
                            'action': 'MANUAL: Fix JSON format',
                            'count': invalid_json_count
                        })
            
            print(f"   ✅ Found {len([i for i in self.issues if i['table'] == 'SlittingPlans'])} issues")
            
        except Exception as e:
            print(f"   ⚠️  Error analyzing Slitting Plans: {e}")
    
    def check_referential_integrity(self):
        """Check for orphaned records across sheets"""
        print("\n🔗 Checking Referential Integrity...")
        
        try:
            df_so = self.get_sheet_data("Sales Order")
            df_wr = self.get_sheet_data("WeightReceipts")
            df_rm_used = self.get_sheet_data("Raw Material Used", header_row=2)
            
            # Issue 1: Weight Receipts for non-existent Job Cards
            if 'Job Card' in df_so.columns and 'JobCardNumber' in df_wr.columns:
                valid_job_cards = set(df_so['Job Card'].dropna().unique())
                wr_job_cards = set(df_wr['JobCardNumber'].dropna().unique())
                orphaned_wr = wr_job_cards - valid_job_cards
                
                if orphaned_wr:
                    self.issues.append({
                        'severity': 'HIGH',
                        'category': 'Orphaned Records',
                        'table': 'WeightReceipts',
                        'issue': f'{len(orphaned_wr)} weight receipts reference non-existent job cards',
                        'sample': list(orphaned_wr)[:5],
                        'action': 'MANUAL: Either create missing sales orders or delete orphaned receipts',
                        'count': len(orphaned_wr)
                    })
            
            # Issue 2: Raw Material Used for non-existent Coils
            df_rm = self.get_sheet_data("RM inward_Issue format", header_row=2)
            
            if 'Coil Number' in df_rm.columns and 'Coil No' in df_rm_used.columns:
                valid_coils = set(df_rm['Coil Number'].dropna().unique())
                used_coils = set(df_rm_used['Coil No'].dropna().unique())
                orphaned_used = used_coils - valid_coils
                
                if orphaned_used:
                    self.issues.append({
                        'severity': 'MEDIUM',
                        'category': 'Orphaned Records',
                        'table': 'Raw Material Used',
                        'issue': f'{len(orphaned_used)} allocations reference non-existent coils',
                        'sample': list(orphaned_used)[:5],
                        'action': 'MANUAL: Either create coil records or remove invalid allocations',
                        'count': len(orphaned_used)
                    })
            
            print(f"   ✅ Found {len([i for i in self.issues if i['category'] == 'Orphaned Records'])} integrity issues")
            
        except Exception as e:
            print(f"   ⚠️  Error checking referential integrity: {e}")
    
    def generate_report(self):
        """Generate console report"""
        print("\n" + "="*60)
        print("📊 DATA QUALITY SUMMARY")
        print("="*60)
        
        # Statistics
        print("\n📈 Statistics:")
        for table, stats in self.stats.items():
            print(f"  - {table}: {stats}")
        
        # Issues by severity
        print(f"\n⚠️  Total Issues Found: {len(self.issues)}")
        print(f"\nBy Severity:")
        
        severity_counts = {}
        for issue in self.issues:
            severity = issue.get('severity', 'UNKNOWN')
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        severity_icons = {
            'CRITICAL': '🔴',
            'HIGH': '🟠',
            'MEDIUM': '🟡',
            'LOW': '🟢'
        }
        
        for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            count = severity_counts.get(severity, 0)
            icon = severity_icons.get(severity, '⚪')
            print(f"  {icon} {severity:8s}: {count}")
        
        # Save to CSV
        if self.issues:
            df_issues = pd.DataFrame(self.issues)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_file = f'/app/data_quality_report_{timestamp}.csv'
            df_issues.to_csv(csv_file, index=False)
            print(f"\n📁 CSV Report saved: {csv_file}")
        
        print("\n" + "="*60)
        print("⚠️  IMPORTANT: Fix CRITICAL and HIGH issues before migration!")
        print("="*60 + "\n")
    
    def generate_html_report(self):
        """Generate HTML report"""
        if not self.issues:
            return
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        html_file = f'/app/data_quality_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
        
        df = pd.DataFrame(self.issues)
        
        html = f"""
        <html>
        <head>
            <title>AEL ERP Data Quality Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
                h1 {{ color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
                .stats {{ background: #e8f5e9; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .critical {{ background-color: #ff4444; color: white; padding: 2px 8px; border-radius: 3px; }}
                .high {{ background-color: #ff9944; color: white; padding: 2px 8px; border-radius: 3px; }}
                .medium {{ background-color: #ffdd44; padding: 2px 8px; border-radius: 3px; }}
                .low {{ background-color: #44ff44; padding: 2px 8px; border-radius: 3px; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .action {{ font-style: italic; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔍 AEL ERP Data Quality Report</h1>
                <div class="stats">
                    <p><strong>Generated:</strong> {timestamp}</p>
                    <p><strong>Total Issues:</strong> {len(self.issues)}</p>
                    <p><strong>Critical:</strong> {len([i for i in self.issues if i['severity'] == 'CRITICAL'])}</p>
                    <p><strong>High:</strong> {len([i for i in self.issues if i['severity'] == 'HIGH'])}</p>
                    <p><strong>Medium:</strong> {len([i for i in self.issues if i['severity'] == 'MEDIUM'])}</p>
                    <p><strong>Low:</strong> {len([i for i in self.issues if i['severity'] == 'LOW'])}</p>
                </div>
                {df.to_html(classes='dataframe', escape=False, index=False)}
            </div>
        </body>
        </html>
        """
        
        with open(html_file, 'w') as f:
            f.write(html)
        
        print(f"📁 HTML Report saved: {html_file}")
    
    def get_sheet_data(self, sheet_name, header_row=1):
        """Fetch data from Google Sheet"""
        try:
            return google_drive_service.get_worksheet_data(
                self.spreadsheet_id, 
                sheet_name, 
                header_row=header_row
            )
        except Exception as e:
            print(f"   ⚠️  Could not read sheet '{sheet_name}': {e}")
            return pd.DataFrame()


# Main execution
if __name__ == "__main__":
    print("\n🚀 Starting AEL ERP Data Discovery...")
    print("This will analyze your Google Sheets for data quality issues.\n")
    
    spreadsheet_id = settings.api.google_sheets_id
    
    if not spreadsheet_id:
        print("❌ ERROR: Google Sheets ID not configured!")
        print("Please set GOOGLE_SHEETS_ID in your .env file or config.py")
        sys.exit(1)
    
    report = DataDiscoveryReport(spreadsheet_id)
    report.analyze_all()
    
    print("\n✅ Data discovery complete!")
    print("\n📋 Next Steps:")
    print("1. Review the generated reports (CSV and HTML)")
    print("2. Fix CRITICAL and HIGH severity issues in your Google Sheets")
    print("3. Re-run this script until no critical issues remain")
    print("4. Then proceed with migration script\n")
