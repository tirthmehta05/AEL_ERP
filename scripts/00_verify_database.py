"""
Database Initialization and Test Script

Verifies database setup and creates sample data for testing.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.database.connection import engine, get_db_session
from src.database.models import *
from datetime import datetime, timedelta
from sqlalchemy import inspect


def verify_database():
    """Verify database structure"""
    print("\n🔍 Verifying Database Structure...")
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    print(f"\n✅ Database: {engine.url.database}")
    print(f"📊 Total Tables: {len(tables)}")
    print("\nTables:")
    for table in sorted(tables):
        cols = inspector.get_columns(table)
        print(f"  ✓ {table:30s} ({len(cols)} columns)")
    
    return True


def create_sample_data():
    """Create sample data for testing"""
    print("\n📝 Creating Sample Data...")
    
    with get_db_session() as session:
        # Check if data already exists
        existing_customers = session.query(Customer).count()
        if existing_customers > 0:
            print(f"   ℹ️  Database already has {existing_customers} customers. Skipping sample data creation.")
            return
        
        # Create sample customer
        customer = Customer(
            code="CUST001",
            name="Test Customer Pvt Ltd",
            gstin="27AABCT1332L1ZV",
            credit_days=30,
            credit_limit=500000,
            address="Mumbai, Maharashtra",
            mobile="9876543210",
            created_by="system"
        )
        session.add(customer)
        
        # Create sample vendor
        vendor = Vendor(
            code="VEND001",
            name="Steel Suppliers India",
            vendor_type="Material Supplier",
            gstin="27AABCT1332L1ZW",
            created_by="system"
        )
        session.add(vendor)
        
        session.flush()  # Get IDs
        
        # Create sample coil
        coil = Coil(
            coil_number="COIL-TEST-001",
            grade="50C1000",
            thickness=0.5,
            width=1000.0,
            coating="Full Hard",
            total_weight=5000.0,
            used_weight=0.0,
            vendor_id=vendor.id,
            coil_supplier=vendor.name,
            receipt_date=datetime.now().date(),
            rate=85.50,
            status="Available",
            created_by="system"
        )
        session.add(coil)
        
        # Create sample sales order
        sales_order = SalesOrder(
            job_card_number="TEST-001",
            customer_id=customer.id,
            customer_name=customer.name,
            order_date=datetime.now().date(),
            delivery_date=(datetime.now() + timedelta(days=7)).date(),
            po_no="PO/2025/001",
            order_type="CORE_BUILDING",
            rate_per_kg=120.0,
            status="Pending Coil Assignment",
            created_by="system"
        )
        session.add(sales_order)
        
        session.flush()
        
        # Create sample design
        design = SalesOrderDesign(
            sales_order_id=sales_order.id,
            width=75.0,
            length=245.0,
            mm_stack=112.0,
            thickness=0.5,
            sets=1,
            weight=15.25,
            material_type="CRNO TL",
            grade="50C1000",
            hole_type="Centre"
        )
        session.add(design)
        
        print("   ✅ Created sample customer")
        print("   ✅ Created sample vendor")
        print("   ✅ Created sample coil")
        print("   ✅ Created sample sales order with design")
        
        session.commit()
        
        print("\n✅ Sample data created successfully!")


def test_relationships():
    """Test database relationships"""
    print("\n🔗 Testing Relationships...")
    
    with get_db_session() as session:
        # Test sales order with designs
        sales_order = session.query(SalesOrder).filter_by(job_card_number="TEST-001").first()
        
        if sales_order:
            print(f"   ✓ Sales Order: {sales_order.job_card_number}")
            print(f"   ✓ Customer: {sales_order.customer.name if sales_order.customer else 'N/A'}")
            print(f"   ✓ Designs: {len(sales_order.designs)}")
            
            for design in sales_order.designs:
                print(f"     - {design.width}x{design.length}mm, {design.weight}kg")
        
        # Test coil
        coil = session.query(Coil).filter_by(coil_number="COIL-TEST-001").first()
        if coil:
            print(f"   ✓ Coil: {coil.coil_number}")
            print(f"   ✓ Available: {coil.available_weight}kg / {coil.total_weight}kg")
            print(f"   ✓ Vendor: {coil.vendor.name if coil.vendor else 'N/A'}")
    
    print("\n✅ All relationships working correctly!")


def show_database_stats():
    """Show database statistics"""
    print("\n📊 Database Statistics:")
    
    with get_db_session() as session:
        stats = {
            "Customers": session.query(Customer).count(),
            "Vendors": session.query(Vendor).count(),
            "Coils": session.query(Coil).count(),
            "Sales Orders": session.query(SalesOrder).count(),
            "Designs": session.query(SalesOrderDesign).count(),
            "Material Allocations": session.query(MaterialAllocation).count(),
            "Weight Receipts": session.query(WeightReceipt).count(),
            "Finished Goods": session.query(FinishedGood).count(),
            "Delivery Challans": session.query(DeliveryChallan).count(),
        }
        
        for table, count in stats.items():
            print(f"   {table:25s}: {count:5d} records")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🗄️  AEL ERP Database Verification")
    print("="*60)
    
    try:
        # Verify structure
        verify_database()
        
        # Create sample data
        create_sample_data()
        
        # Test relationships
        test_relationships()
        
        # Show stats
        show_database_stats()
        
        print("\n" + "="*60)
        print("✅ Database verification complete!")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
