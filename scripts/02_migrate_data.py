"""
Data Migration Script: Google Sheets → SQLite Database

This script migrates data from Google Sheets to the new SQLite database.

IMPORTANT: Run 01_data_discovery.py FIRST and fix all CRITICAL/HIGH issues!

Usage:
    python scripts/02_migrate_data.py [--dry-run] [--table TABLE_NAME]
    
Options:
    --dry-run        Test migration without committing (shows what would happen)
    --table NAME     Migrate only specific table (customers, vendors, coils, sales_orders, etc.)
"""

import sys
import os
import argparse
import json
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.database.connection import get_db_session
from src.database.models import *
from src.shared.utils.logger_config import setup_logger

logger = setup_logger(__name__)


class DataMigrator:
    """Migrates data from Google Sheets to SQLite database"""
    
    def __init__(self, google_service, spreadsheet_id, dry_run=False):
        self.google_service = google_service
        self.spreadsheet_id = spreadsheet_id
        self.dry_run = dry_run
        self.migration_stats = {}
        self.errors = []
        
    def migrate_all(self):
        """Migrate all tables in correct order (respects foreign keys)"""
        print("\n" + "="*60)
        print("🚀 AEL ERP DATA MIGRATION")
        print("="*60)
        print(f"Mode: {'DRY RUN (no changes)' if self.dry_run else 'LIVE MIGRATION'}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60 + "\n")
        
        # Migration order (respects foreign key dependencies)
        migration_steps = [
            ("customers", self.migrate_customers),
            ("vendors", self.migrate_vendors),
            ("coils", self.migrate_coils),
            ("sales_orders", self.migrate_sales_orders),
            ("sales_order_designs", self.migrate_sales_order_designs),
            ("material_allocations", self.migrate_material_allocations),
            ("weight_receipt_drafts", self.migrate_weight_receipt_drafts),
            ("weight_receipts", self.migrate_weight_receipts),
            ("finished_goods", self.migrate_finished_goods),
            ("slitting_plans", self.migrate_slitting_plans),
        ]
        
        for table_name, migrate_func in migration_steps:
            try:
                print(f"\n{'─'*60}")
                print(f"📦 Migrating: {table_name}")
                print(f"{'─'*60}")
                
                success_count, error_count = migrate_func()
                
                self.migration_stats[table_name] = {
                    'success': success_count,
                    'errors': error_count
                }
                
                if success_count > 0:
                    print(f"   ✅ Migrated: {success_count} records")
                if error_count > 0:
                    print(f"   ⚠️  Errors: {error_count} records")
                
            except Exception as e:
                logger.error(f"Fatal error migrating {table_name}: {e}")
                self.errors.append({
                    'table': table_name,
                    'error': str(e),
                    'fatal': True
                })
                print(f"   ❌ FATAL ERROR: {e}")
                print(f"   Migration stopped at {table_name}")
                break
        
        self.print_summary()
        self.save_migration_log()
    
    def migrate_customers(self):
        """Migrate customer master data"""
        df = self._get_sheet_data("Sales Order")
        
        if df.empty or 'Party Name' not in df.columns:
            print("   ℹ️  No customer data found")
            return 0, 0
        
        # Extract unique customers
        customers_data = df[['Party Name']].drop_duplicates()
        customers_data = customers_data[customers_data['Party Name'].notna()]
        
        success = 0
        errors = 0
        
        with get_db_session() as session:
            for idx, row in customers_data.iterrows():
                try:
                    party_name = str(row['Party Name']).strip()
                    
                    # Check if already exists
                    existing = session.query(Customer).filter_by(name=party_name).first()
                    if existing:
                        continue
                    
                    # Create customer
                    customer = Customer(
                        code=f"C{str(idx).zfill(4)}",  # Auto-generate code
                        name=party_name,
                        is_active=True,
                        created_at=datetime.now(),
                        created_by="migration"
                    )
                    
                    if not self.dry_run:
                        session.add(customer)
                    
                    success += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating customer '{party_name}': {e}")
                    errors += 1
                    self.errors.append({
                        'table': 'customers',
                        'record': party_name,
                        'error': str(e)
                    })
            
            if not self.dry_run:
                session.commit()
        
        return success, errors
    
    def migrate_vendors(self):
        """Migrate vendor master data"""
        df = self._get_sheet_data("RM inward_Issue format", header_row=2)
        
        if df.empty or 'Coil Supplier' not in df.columns:
            print("   ℹ️  No vendor data found")
            return 0, 0
        
        # Extract unique vendors
        vendors_data = df[['Coil Supplier']].drop_duplicates()
        vendors_data = vendors_data[vendors_data['Coil Supplier'].notna()]
        
        success = 0
        errors = 0
        
        with get_db_session() as session:
            for idx, row in vendors_data.iterrows():
                try:
                    supplier_name = str(row['Coil Supplier']).strip()
                    
                    # Check if already exists
                    existing = session.query(Vendor).filter_by(name=supplier_name).first()
                    if existing:
                        continue
                    
                    # Create vendor
                    vendor = Vendor(
                        code=f"V{str(idx).zfill(4)}",
                        name=supplier_name,
                        vendor_type="Material Supplier",
                        is_active=True,
                        created_at=datetime.now(),
                        created_by="migration"
                    )
                    
                    if not self.dry_run:
                        session.add(vendor)
                    
                    success += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating vendor '{supplier_name}': {e}")
                    errors += 1
        
            if not self.dry_run:
                session.commit()
        
        return success, errors
    
    def migrate_coils(self):
        """Migrate coil inventory"""
        df = self._get_sheet_data("RM inward_Issue format", header_row=2)
        
        if df.empty:
            print("   ℹ️  No coil data found")
            return 0, 0
        
        success = 0
        errors = 0
        
        with get_db_session() as session:
            for idx, row in df.iterrows():
                try:
                    coil_number = str(row.get('Coil Number', '')).strip()
                    
                    if not coil_number or coil_number == 'nan':
                        continue
                    
                    # Check if already exists
                    existing = session.query(Coil).filter_by(coil_number=coil_number).first()
                    if existing:
                        continue
                    
                    # Find vendor
                    vendor = None
                    supplier_name = row.get('Coil Supplier')
                    if pd.notna(supplier_name):
                        vendor = session.query(Vendor).filter_by(name=str(supplier_name).strip()).first()
                    
                    # Parse dates
                    receipt_date = None
                    if pd.notna(row.get('Date')):
                        try:
                            receipt_date = pd.to_datetime(row.get('Date'), dayfirst=True).date()
                        except:
                            pass
                    
                    # Parse numeric fields
                    def safe_float(val, default=0.0):
                        try:
                            return float(val) if pd.notna(val) else default
                        except:
                            return default
                    
                    total_weight = safe_float(row.get('Coil Weight'))
                    used_weight = total_weight - safe_float(row.get('Material in stock'))
                    
                    # Determine status
                    available = safe_float(row.get('Material in stock'))
                    if available <= 0:
                        status = 'Fully Used'
                    elif used_weight > 0:
                        status = 'Allocated'
                    else:
                        status = 'Available'
                    
                    # Create coil
                    coil = Coil(
                        coil_number=coil_number,
                        grade=str(row.get('Grade', '')).strip() or None,
                        thickness=safe_float(row.get('Thk')),
                        width=safe_float(row.get('Width')),
                        coating=str(row.get('Coating', '')).strip() or None,
                        total_weight=total_weight,
                        used_weight=used_weight,
                        vendor_id=vendor.id if vendor else None,
                        coil_supplier=str(supplier_name).strip() if pd.notna(supplier_name) else None,
                        location=str(row.get('Location', 'Amba')).strip(),
                        receipt_date=receipt_date,
                        po_number=str(row.get('PO', '')).strip() or None,
                        rate=safe_float(row.get('Rate')),
                        status=status,
                        is_deleted=False,
                        created_at=datetime.now(),
                        created_by="migration"
                    )
                    
                    if not self.dry_run:
                        session.add(coil)
                    
                    success += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating coil '{coil_number}': {e}")
                    errors += 1
                    self.errors.append({
                        'table': 'coils',
                        'record': coil_number,
                        'error': str(e)
                    })
            
            if not self.dry_run:
                session.commit()
        
        return success, errors
    
    def migrate_sales_orders(self):
        """Migrate sales orders (job cards)"""
        df = self._get_sheet_data("Sales Order-JC", header_row=1)
        
        if df.empty:
            print("   ℹ️  No sales order data found")
            return 0, 0
        
        success = 0
        errors = 0
        
        with get_db_session() as session:
            for idx, row in df.iterrows():
                try:
                    job_card = str(row.get('job_card_number', '')).strip()
                    
                    if not job_card or job_card == 'nan':
                        continue
                    
                    # Check if already exists
                    existing = session.query(SalesOrder).filter_by(job_card_number=job_card).first()
                    if existing:
                        continue
                    
                    # Find customer
                    customer = None
                    party_name = row.get('party_name')
                    if pd.notna(party_name):
                        customer = session.query(Customer).filter_by(name=str(party_name).strip()).first()
                    
                    # Parse dates
                    order_date = None
                    delivery_date = None
                    
                    try:
                        if pd.notna(row.get('order_date')):
                            order_date = pd.to_datetime(row.get('order_date'), dayfirst=True).date()
                    except:
                        order_date = datetime.now().date()
                    
                    try:
                        if pd.notna(row.get('delivery_date')):
                            delivery_date = pd.to_datetime(row.get('delivery_date'), dayfirst=True).date()
                    except:
                        delivery_date = order_date
                    
                    # Ensure delivery >= order date
                    if delivery_date < order_date:
                        delivery_date = order_date
                    
                    def safe_float(val, default=0.0):
                        try:
                            return float(val) if pd.notna(val) else default
                        except:
                            return default
                    
                    def safe_int(val, default=0):
                        try:
                            return int(val) if pd.notna(val) else default
                        except:
                            return default
                    
                    # Create sales order
                    sales_order = SalesOrder(
                        job_card_number=job_card,
                        customer_id=customer.id if customer else None,
                        customer_name=str(party_name).strip() if pd.notna(party_name) else None,
                        order_date=order_date,
                        delivery_date=delivery_date,
                        po_no=str(row.get('po_no', '')).strip() or None,
                        order_type=str(row.get('order_type', 'CORE_BUILDING')).strip(),
                        hole_size=safe_int(row.get('hole_size')),
                        number_of_cores=safe_int(row.get('number_of_cores')),
                        header_core_stack=safe_float(row.get('header_core_stack')),
                        rate_per_kg=safe_float(row.get('rate_per_kg')),
                        status='Pending Coil Assignment',
                        total_design_weight=0,  # Will be updated when designs are added
                        total_allocated_weight=0,
                        is_deleted=False,
                        created_at=datetime.now(),
                        created_by="migration"
                    )
                    
                    if not self.dry_run:
                        session.add(sales_order)
                    
                    success += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating sales order '{job_card}': {e}")
                    errors += 1
                    self.errors.append({
                        'table': 'sales_orders',
                        'record': job_card,
                        'error': str(e)
                    })
            
            if not self.dry_run:
                session.commit()
        
        return success, errors
    
    def migrate_sales_order_designs(self):
        """Migrate design details"""
        df_jc = self._get_sheet_data("Sales Order-JC", header_row=1)
        
        if df_jc.empty or 'designs_json' not in df_jc.columns:
            print("   ℹ️  No design data found")
            return 0, 0
        
        success = 0
        errors = 0
        
        with get_db_session() as session:
            for idx, row in df_jc.iterrows():
                try:
                    job_card = str(row.get('job_card_number', '')).strip()
                    designs_json_str = row.get('designs_json')
                    
                    if not job_card or pd.isna(designs_json_str):
                        continue
                    
                    # Find sales order
                    sales_order = session.query(SalesOrder).filter_by(job_card_number=job_card).first()
                    if not sales_order:
                        continue
                    
                    # Parse designs JSON
                    try:
                        designs = json.loads(designs_json_str)
                    except:
                        logger.warning(f"Invalid JSON for job card {job_card}")
                        errors += 1
                        continue
                    
                    if not isinstance(designs, list):
                        continue
                    
                    # Create each design
                    for design_data in designs:
                        try:
                            def safe_float(val, default=0.0):
                                try:
                                    return float(val) if val not in [None, '', 'nan'] else default
                                except:
                                    return default
                            
                            def safe_int(val, default=1):
                                try:
                                    return int(val) if val not in [None, '', 'nan'] else default
                                except:
                                    return default
                            
                            design = SalesOrderDesign(
                                sales_order_id=sales_order.id,
                                width=safe_float(design_data.get('Width')),
                                length=safe_float(design_data.get('Length')),
                                mm_stack=safe_float(design_data.get('MM_Stack')),
                                thickness=safe_float(design_data.get('Thk'), 0.5),
                                sets=safe_int(design_data.get('Sets'), 1),
                                pieces=safe_int(design_data.get('Pieces'), 0),
                                weight=safe_float(design_data.get('Qty')),
                                material_type=str(design_data.get('Material Type', '')).strip() or None,
                                grade=str(design_data.get('Grade', '')).strip() or None,
                                hole_type=str(design_data.get('Hole Type', '')).strip() or None,
                                coating=str(design_data.get('Coating', '')).strip() or None,
                                party_job_no=str(design_data.get('Party Job No', '')).strip() or None,
                                fm_name=str(design_data.get('FM Name', '')).strip() or None,
                                created_at=datetime.now()
                            )
                            
                            if not self.dry_run:
                                session.add(design)
                            
                            success += 1
                            
                        except Exception as e:
                            logger.error(f"Error creating design for {job_card}: {e}")
                            errors += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating designs for '{job_card}': {e}")
                    errors += 1
            
            if not self.dry_run:
                session.commit()
                
                # Update total_design_weight for all sales orders
                all_orders = session.query(SalesOrder).all()
                for order in all_orders:
                    total_weight = sum(d.weight for d in order.designs)
                    order.total_design_weight = total_weight
                
                session.commit()
        
        return success, errors
    
    def migrate_material_allocations(self):
        """Migrate material allocations (coil assignments)"""
        df = self._get_sheet_data("Raw Material Used", header_row=2)
        
        if df.empty:
            print("   ℹ️  No allocation data found")
            return 0, 0
        
        success = 0
        errors = 0
        
        with get_db_session() as session:
            for idx, row in df.iterrows():
                try:
                    job_card = str(row.get('Card No', '')).strip()
                    coil_number = str(row.get('Coil No', '')).strip()
                    
                    if not job_card or not coil_number or job_card == 'nan' or coil_number == 'nan':
                        continue
                    
                    # Find sales order and coil
                    sales_order = session.query(SalesOrder).filter_by(job_card_number=job_card).first()
                    coil = session.query(Coil).filter_by(coil_number=coil_number).first()
                    
                    if not sales_order or not coil:
                        continue
                    
                    # Check if allocation already exists
                    existing = session.query(MaterialAllocation).filter_by(
                        sales_order_id=sales_order.id,
                        coil_id=coil.id
                    ).first()
                    
                    if existing:
                        continue
                    
                    # Parse weight
                    def safe_float(val, default=0.0):
                        try:
                            return float(val) if pd.notna(val) else default
                        except:
                            return default
                    
                    weight = safe_float(row.get('Material used'))
                    
                    if weight <= 0:
                        continue
                    
                    # Parse date
                    allocation_date = datetime.now().date()
                    if pd.notna(row.get('Date')):
                        try:
                            allocation_date = pd.to_datetime(row.get('Date'), dayfirst=True).date()
                        except:
                            pass
                    
                    # Create allocation
                    allocation = MaterialAllocation(
                        sales_order_id=sales_order.id,
                        coil_id=coil.id,
                        weight_allocated=weight,
                        allocation_date=allocation_date,
                        created_at=datetime.now(),
                        created_by="migration"
                    )
                    
                    if not self.dry_run:
                        session.add(allocation)
                    
                    success += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating allocation: {e}")
                    errors += 1
            
            if not self.dry_run:
                session.commit()
                
                # Update coil used_weight and sales_order total_allocated_weight
                # This would normally be done by triggers, but we're doing it manually
                all_coils = session.query(Coil).all()
                for coil in all_coils:
                    total_allocated = sum(a.weight_allocated for a in coil.material_allocations)
                    coil.used_weight = total_allocated
                    
                    if coil.available_weight <= 0:
                        coil.status = 'Fully Used'
                    elif coil.used_weight > 0:
                        coil.status = 'Allocated'
                
                all_orders = session.query(SalesOrder).all()
                for order in all_orders:
                    total_allocated = sum(a.weight_allocated for a in order.material_allocations)
                    order.total_allocated_weight = total_allocated
                    if total_allocated > 0:
                        order.status = 'Coils Assigned'
                
                session.commit()
        
        return success, errors
    
    def migrate_weight_receipt_drafts(self):
        """Migrate weight receipt drafts"""
        # This is typically empty or can be skipped for migration
        # Drafts are temporary and not critical for historical data
        print("   ℹ️  Skipping drafts (temporary data)")
        return 0, 0
    
    def migrate_weight_receipts(self):
        """Migrate weight receipts"""
        df = self._get_sheet_data("WeightReceipts")
        
        if df.empty:
            print("   ℹ️  No weight receipt data found")
            return 0, 0
        
        success = 0
        errors = 0
        
        with get_db_session() as session:
            for idx, row in df.iterrows():
                try:
                    receipt_number = str(row.get('WeightReceiptNumber', '')).strip()
                    job_card = str(row.get('JobCardNumber', '')).strip()
                    
                    if not receipt_number or not job_card:
                        continue
                    
                    # Check if already exists
                    existing = session.query(WeightReceipt).filter_by(receipt_number=receipt_number).first()
                    if existing:
                        continue
                    
                    # Find sales order
                    sales_order = session.query(SalesOrder).filter_by(job_card_number=job_card).first()
                    if not sales_order:
                        logger.warning(f"Sales order not found for receipt {receipt_number}")
                        errors += 1
                        continue
                    
                    # Parse date
                    receipt_date = datetime.now().date()
                    if pd.notna(row.get('Date')):
                        try:
                            receipt_date = pd.to_datetime(row.get('Date'), dayfirst=True).date()
                        except:
                            pass
                    
                    def safe_float(val, default=0.0):
                        try:
                            return float(val) if pd.notna(val) else default
                        except:
                            return default
                    
                    def safe_int(val, default=1):
                        try:
                            return int(val) if pd.notna(val) else default
                        except:
                            return default
                    
                    # Get design details JSON
                    designs_json = row.get('DesignDetailsWithWeightsJSON', '[]')
                    if pd.isna(designs_json):
                        designs_json = '[]'
                    
                    # Create weight receipt
                    weight_receipt = WeightReceipt(
                        receipt_number=receipt_number,
                        sales_order_id=sales_order.id,
                        job_card_number=job_card,
                        receipt_date=receipt_date,
                        party_name=str(row.get('PartyName', '')).strip() or None,
                        po_number=str(row.get('PONo', '')).strip() or None,
                        material=str(row.get('Material', '')).strip() or None,
                        sets=safe_int(row.get('Sets'), 1),
                        design_details_json=designs_json,
                        weight_entry_type=str(row.get('WeightEntryType', '')).strip() or None,
                        order_type=str(row.get('OrderType', '')).strip() or None,
                        total_weight=safe_float(row.get('TotalWeight')),
                        deduction=safe_float(row.get('Deduction')),
                        production_status='Completed',
                        is_deleted=False,
                        created_at=datetime.now(),
                        created_by="migration"
                    )
                    
                    if not self.dry_run:
                        session.add(weight_receipt)
                    
                    success += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating weight receipt '{receipt_number}': {e}")
                    errors += 1
                    self.errors.append({
                        'table': 'weight_receipts',
                        'record': receipt_number,
                        'error': str(e)
                    })
            
            if not self.dry_run:
                session.commit()
        
        return success, errors
    
    def migrate_finished_goods(self):
        """Migrate finished goods inventory"""
        df = self._get_sheet_data("Finished Goods Transfer", header_row=2)
        
        if df.empty:
            print("   ℹ️  No finished goods data found")
            return 0, 0
        
        success = 0
        errors = 0
        
        with get_db_session() as session:
            for idx, row in df.iterrows():
                try:
                    job_card = str(row.get('Job Card', '')).strip()
                    wr_number = str(row.get('Weight Receipt No', '')).strip()
                    
                    if not job_card or job_card == 'nan':
                        continue
                    
                    # Find weight receipt and sales order
                    weight_receipt = None
                    if wr_number and wr_number != 'nan':
                        weight_receipt = session.query(WeightReceipt).filter_by(receipt_number=wr_number).first()
                    
                    sales_order = session.query(SalesOrder).filter_by(job_card_number=job_card).first()
                    
                    if not sales_order:
                        continue
                    
                    # Parse date
                    fg_date = datetime.now().date()
                    if pd.notna(row.get('FG DATE')):
                        try:
                            fg_date = pd.to_datetime(row.get('FG DATE'), dayfirst=True).date()
                        except:
                            pass
                    
                    def safe_float(val, default=0.0):
                        try:
                            return float(val) if pd.notna(val) else default
                        except:
                            return default
                    
                    fg_qty = safe_float(row.get('FG Qty'))
                    
                    if fg_qty <= 0:
                        continue
                    
                    # Create finished good
                    finished_good = FinishedGood(
                        weight_receipt_id=weight_receipt.id if weight_receipt else None,
                        sales_order_id=sales_order.id,
                        job_card_number=job_card,
                        weight_receipt_number=wr_number if wr_number != 'nan' else None,
                        party_name=sales_order.customer_name,
                        material=str(row.get('Material', '')).strip() or None,
                        fg_qty=fg_qty,
                        despatched_qty=0,  # Will be updated if delivery challans are migrated
                        status='In Stock',
                        location='FG Warehouse',
                        fg_date=fg_date,
                        is_deleted=False,
                        created_at=datetime.now(),
                        created_by="migration"
                    )
                    
                    if not self.dry_run:
                        session.add(finished_good)
                    
                    success += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating finished good: {e}")
                    errors += 1
            
            if not self.dry_run:
                session.commit()
        
        return success, errors
    
    def migrate_slitting_plans(self):
        """Migrate slitting plans"""
        df = self._get_sheet_data("SlittingPlans")
        
        if df.empty:
            print("   ℹ️  No slitting plan data found")
            return 0, 0
        
        success = 0
        errors = 0
        
        with get_db_session() as session:
            for idx, row in df.iterrows():
                try:
                    plan_id = str(row.get('PlanID', '')).strip()
                    
                    if not plan_id or plan_id == 'nan':
                        continue
                    
                    # Check if already exists
                    existing = session.query(SlittingPlan).filter_by(plan_id=plan_id).first()
                    if existing:
                        continue
                    
                    # Parse date
                    plan_date = datetime.now().date()
                    if pd.notna(row.get('Date')):
                        try:
                            plan_date = pd.to_datetime(row.get('Date'), dayfirst=True).date()
                        except:
                            pass
                    
                    def safe_float(val, default=0.0):
                        try:
                            return float(val) if pd.notna(val) else default
                        except:
                            return default
                    
                    # Get JSON fields
                    raw_materials_json = row.get('RawMaterialsJSON', '[]')
                    slit_details_json = row.get('SlitDetailsJSON', '[]')
                    
                    if pd.isna(raw_materials_json):
                        raw_materials_json = '[]'
                    if pd.isna(slit_details_json):
                        slit_details_json = '[]'
                    
                    # Create slitting plan
                    slitting_plan = SlittingPlan(
                        plan_id=plan_id,
                        plan_date=plan_date,
                        coil_width=safe_float(row.get('CoilWidth')),
                        total_coil_weight=safe_float(row.get('TotalCoilWeight')),
                        scrap_mm=safe_float(row.get('ScrapMM')),
                        scrap_weight=safe_float(row.get('ScrapWeight')),
                        raw_materials_json=raw_materials_json,
                        slit_details_json=slit_details_json,
                        status='Completed',  # Historical plans are completed
                        created_at=datetime.now(),
                        created_by="migration"
                    )
                    
                    if not self.dry_run:
                        session.add(slitting_plan)
                    
                    success += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating slitting plan '{plan_id}': {e}")
                    errors += 1
            
            if not self.dry_run:
                session.commit()
        
        return success, errors
    
    def print_summary(self):
        """Print migration summary"""
        print("\n" + "="*60)
        print("📊 MIGRATION SUMMARY")
        print("="*60)
        
        total_success = sum(stats['success'] for stats in self.migration_stats.values())
        total_errors = sum(stats['errors'] for stats in self.migration_stats.values())
        
        print(f"\n✅ Total Successful: {total_success}")
        print(f"⚠️  Total Errors: {total_errors}")
        
        print("\nBy Table:")
        for table, stats in self.migration_stats.items():
            print(f"  {table:30s}: {stats['success']:5d} success, {stats['errors']:5d} errors")
        
        if self.dry_run:
            print("\n⚠️  DRY RUN MODE - No changes were committed to database!")
        else:
            print("\n✅ Migration completed and committed to database!")
        
        print("="*60 + "\n")
    
    def save_migration_log(self):
        """Save detailed migration log"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = f'/app/migration_log_{timestamp}.json'
        
        log_data = {
            'timestamp': timestamp,
            'dry_run': self.dry_run,
            'stats': self.migration_stats,
            'errors': self.errors
        }
        
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2, default=str)
        
        print(f"📁 Migration log saved: {log_file}")
    
    def _get_sheet_data(self, sheet_name, header_row=1):
        """Fetch data from Google Sheet"""
        try:
            return self.google_service.get_worksheet_data(
                self.spreadsheet_id, 
                sheet_name, 
                header_row=header_row
            )
        except Exception as e:
            logger.warning(f"Could not read sheet '{sheet_name}': {e}")
            return pd.DataFrame()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Migrate AEL ERP data from Google Sheets to SQLite')
    parser.add_argument('--dry-run', action='store_true', help='Test migration without committing')
    parser.add_argument('--table', type=str, help='Migrate only specific table')
    
    args = parser.parse_args()
    
    # Import here to avoid Streamlit context issues
    try:
        from src.shared.integrations.google_drive_service import google_drive_service
        from config import settings
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        print("\nThis script requires:")
        print("1. Google Sheets API credentials")
        print("2. .streamlit/secrets.toml file configured")
        sys.exit(1)
    
    spreadsheet_id = settings.api.google_sheets_id
    
    if not spreadsheet_id:
        print("❌ ERROR: Google Sheets ID not configured!")
        sys.exit(1)
    
    # Create migrator
    migrator = DataMigrator(
        google_service=google_drive_service,
        spreadsheet_id=spreadsheet_id,
        dry_run=args.dry_run
    )
    
    # Run migration
    if args.table:
        # Migrate specific table only
        print(f"Migrating single table: {args.table}")
        # TODO: Add logic for single table migration
    else:
        # Migrate everything
        migrator.migrate_all()


if __name__ == "__main__":
    main()
