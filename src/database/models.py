"""SQLAlchemy models for AEL ERP database"""

from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Boolean, Text, 
    ForeignKey, CheckConstraint, Index, func
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .connection import Base


# ============================================
# MASTER DATA TABLES
# ============================================

class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    gstin = Column(String(15))
    pan = Column(String(10))
    credit_days = Column(Integer, default=0)
    credit_limit = Column(Float, default=0)
    address = Column(Text)
    contact_person = Column(String(100))
    mobile = Column(String(15))
    email = Column(String(100))
    is_active = Column(Boolean, default=True, index=True)
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    updated_at = Column(DateTime, onupdate=datetime.now)
    updated_by = Column(String(100))
    
    # Relationships
    sales_orders = relationship("SalesOrder", back_populates="customer")
    delivery_challans = relationship("DeliveryChallan", back_populates="customer")


class Vendor(Base):
    __tablename__ = "vendors"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    vendor_type = Column(String(50))  # 'Material Supplier' or 'Job Worker'
    gstin = Column(String(15))
    pan = Column(String(10))
    address = Column(Text)
    contact_person = Column(String(100))
    mobile = Column(String(15))
    email = Column(String(100))
    is_active = Column(Boolean, default=True, index=True)
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    updated_at = Column(DateTime, onupdate=datetime.now)
    updated_by = Column(String(100))
    
    # Relationships
    coils = relationship("Coil", back_populates="vendor")
    
    __table_args__ = (
        Index('idx_vendors_type', 'vendor_type'),
    )


# ============================================
# RAW MATERIAL (INVENTORY)
# ============================================

class Coil(Base):
    __tablename__ = "coils"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    coil_number = Column(String(50), unique=True, nullable=False, index=True)
    
    # Material Properties
    grade = Column(String(50), index=True)
    thickness = Column(Float)  # in mm
    width = Column(Float, index=True)  # in mm
    coating = Column(String(50))
    
    # Weights
    total_weight = Column(Float, nullable=False)
    used_weight = Column(Float, default=0)
    # available_weight is computed: total_weight - used_weight
    
    # Source & Location
    vendor_id = Column(Integer, ForeignKey('vendors.id'))
    coil_supplier = Column(String(200))  # Denormalized
    location = Column(String(50), default='Amba', index=True)
    
    # Tracking
    receipt_date = Column(Date)
    po_number = Column(String(50))
    rate = Column(Float)
    rm_age_days = Column(Integer)
    
    # Status
    status = Column(String(20), default='Available', index=True)
    is_deleted = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    updated_at = Column(DateTime, onupdate=datetime.now)
    updated_by = Column(String(100))
    
    # Relationships
    vendor = relationship("Vendor", back_populates="coils")
    material_allocations = relationship("MaterialAllocation", back_populates="coil")
    
    @property
    def available_weight(self):
        """Computed property for available weight"""
        return self.total_weight - self.used_weight
    
    __table_args__ = (
        CheckConstraint('total_weight >= 0', name='check_coil_total_weight'),
        CheckConstraint('used_weight >= 0', name='check_coil_used_weight'),
        Index('idx_coils_grade', 'grade'),
    )


# ============================================
# SALES ORDERS
# ============================================

class SalesOrder(Base):
    __tablename__ = "sales_orders"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_card_number = Column(String(50), unique=True, nullable=False, index=True)
    
    customer_id = Column(Integer, ForeignKey('customers.id'))
    customer_name = Column(String(200))  # Denormalized
    
    order_date = Column(Date, nullable=False, index=True)
    delivery_date = Column(Date, nullable=False, index=True)
    po_no = Column(String(50))
    
    order_type = Column(String(20))  # 'CORE_BUILDING', 'LOOSE_STRIPS', 'EI_READY'
    hole_size = Column(Integer)
    number_of_cores = Column(Integer, default=0)
    header_core_stack = Column(Float)
    
    rate_per_kg = Column(Float)
    
    status = Column(String(30), default='Pending Coil Assignment', index=True)
    
    total_design_weight = Column(Float, default=0)
    total_allocated_weight = Column(Float, default=0)
    
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime)
    deleted_by = Column(String(100))
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    updated_at = Column(DateTime, onupdate=datetime.now)
    updated_by = Column(String(100))
    
    # Relationships
    customer = relationship("Customer", back_populates="sales_orders")
    designs = relationship("SalesOrderDesign", back_populates="sales_order", cascade="all, delete-orphan")
    material_allocations = relationship("MaterialAllocation", back_populates="sales_order", cascade="all, delete-orphan")
    weight_receipts = relationship("WeightReceipt", back_populates="sales_order")
    finished_goods = relationship("FinishedGood", back_populates="sales_order")
    
    __table_args__ = (
        CheckConstraint('delivery_date >= order_date', name='check_delivery_after_order'),
        CheckConstraint('total_design_weight >= 0', name='check_total_design_weight'),
    )


class SalesOrderDesign(Base):
    __tablename__ = "sales_order_designs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sales_order_id = Column(Integer, ForeignKey('sales_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    
    width = Column(Float, nullable=False)
    length = Column(Float, nullable=False)
    mm_stack = Column(Float)
    thickness = Column(Float, nullable=False)
    
    sets = Column(Integer, default=1)
    pieces = Column(Integer, default=0)
    weight = Column(Float, nullable=False)
    
    material_type = Column(String(50), index=True)
    grade = Column(String(50))
    hole_type = Column(String(50))
    coating = Column(String(50))
    
    party_job_no = Column(String(50))
    fm_name = Column(String(50))  # For EI Ready
    
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    sales_order = relationship("SalesOrder", back_populates="designs")
    
    __table_args__ = (
        CheckConstraint('weight >= 0', name='check_design_weight'),
        CheckConstraint('sets > 0', name='check_design_sets'),
        Index('idx_designs_width', 'width'),
    )


class MaterialAllocation(Base):
    __tablename__ = "material_allocations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    sales_order_id = Column(Integer, ForeignKey('sales_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    coil_id = Column(Integer, ForeignKey('coils.id', ondelete='RESTRICT'), nullable=False, index=True)
    
    weight_allocated = Column(Float, nullable=False)
    allocation_date = Column(Date, nullable=False, index=True)
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    
    # Relationships
    sales_order = relationship("SalesOrder", back_populates="material_allocations")
    coil = relationship("Coil", back_populates="material_allocations")
    
    __table_args__ = (
        CheckConstraint('weight_allocated > 0', name='check_allocation_weight'),
    )


# ============================================
# PRODUCTION TRACKING
# ============================================

class WeightReceiptDraft(Base):
    __tablename__ = "weight_receipt_drafts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    job_card_number = Column(String(50), nullable=False, index=True)
    design_index = Column(Integer, nullable=False)  # -1 for "Building Core", >=0 for individual designs
    
    actual_weight = Column(Float, nullable=False)
    remark = Column(Text)
    design_deduction = Column(Float, default=0)
    
    receipt_sets = Column(Integer)  # Number of sets/cores this draft entry is for
    
    timestamp = Column(DateTime, default=datetime.now, index=True)
    
    __table_args__ = (
        Index('idx_wrd_job_design', 'job_card_number', 'design_index'),
    )


class WeightReceipt(Base):
    __tablename__ = "weight_receipts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_number = Column(String(50), unique=True, nullable=False, index=True)
    
    sales_order_id = Column(Integer, ForeignKey('sales_orders.id'), nullable=False, index=True)
    job_card_number = Column(String(50), index=True)  # Denormalized
    
    receipt_date = Column(Date, nullable=False, index=True)
    party_name = Column(String(200))
    po_number = Column(String(50))
    material = Column(String(100))  # e.g., "CRNO 0.5"
    sets = Column(Integer, default=1)
    
    # Design details stored as JSON (matches current structure)
    design_details_json = Column(Text, nullable=False)
    
    weight_entry_type = Column(String(50))  # 'Building Core' or 'Loose Strips'
    order_type = Column(String(20))  # 'CORE_BUILDING', 'LOOSE_STRIPS', 'EI_READY'
    
    total_weight = Column(Float, nullable=False)
    deduction = Column(Float, default=0)
    # net_weight is computed: total_weight - deduction
    
    production_status = Column(String(30), default='Completed')
    
    is_deleted = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    updated_at = Column(DateTime, onupdate=datetime.now)
    updated_by = Column(String(100))
    
    # Relationships
    sales_order = relationship("SalesOrder", back_populates="weight_receipts")
    finished_goods = relationship("FinishedGood", back_populates="weight_receipt")
    delivery_challan_items = relationship("DeliveryChallanItem", back_populates="weight_receipt")
    
    @property
    def net_weight(self):
        """Computed property for net weight"""
        return self.total_weight - self.deduction
    
    __table_args__ = (
        CheckConstraint('total_weight >= 0', name='check_wr_total_weight'),
        CheckConstraint('deduction >= 0', name='check_wr_deduction'),
    )


# ============================================
# FINISHED GOODS (POST-PRODUCTION INVENTORY)
# ============================================

class FinishedGood(Base):
    __tablename__ = "finished_goods"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    weight_receipt_id = Column(Integer, ForeignKey('weight_receipts.id'), nullable=False, index=True)
    sales_order_id = Column(Integer, ForeignKey('sales_orders.id'), nullable=False, index=True)
    job_card_number = Column(String(50), index=True)  # Denormalized
    weight_receipt_number = Column(String(50))  # Denormalized for traceability
    
    # Product Details
    party_name = Column(String(200))
    material = Column(String(100))
    
    # Quantities
    fg_qty = Column(Float, nullable=False)  # Net weight from weight receipt
    despatched_qty = Column(Float, default=0)
    # available_qty is computed: fg_qty - despatched_qty
    
    # Status
    status = Column(String(30), default='In Stock', index=True)
    location = Column(String(50), default='FG Warehouse')
    
    # Tracking
    fg_date = Column(Date, nullable=False)
    
    is_deleted = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    updated_at = Column(DateTime, onupdate=datetime.now)
    updated_by = Column(String(100))
    
    # Relationships
    weight_receipt = relationship("WeightReceipt", back_populates="finished_goods")
    sales_order = relationship("SalesOrder", back_populates="finished_goods")
    transfers = relationship("FinishedGoodTransfer", back_populates="finished_good")
    delivery_challan_items = relationship("DeliveryChallanItem", back_populates="finished_good")
    
    @property
    def available_qty(self):
        """Computed property for available quantity"""
        return self.fg_qty - self.despatched_qty
    
    __table_args__ = (
        CheckConstraint('fg_qty >= 0', name='check_fg_qty'),
        CheckConstraint('despatched_qty >= 0', name='check_despatched_qty'),
    )


class FinishedGoodTransfer(Base):
    __tablename__ = "finished_goods_transfers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    transfer_number = Column(String(50), unique=True, nullable=False, index=True)
    
    finished_goods_id = Column(Integer, ForeignKey('finished_goods.id'), nullable=False, index=True)
    job_card_number = Column(String(50))
    
    transfer_date = Column(Date, nullable=False, index=True)
    from_location = Column(String(50), nullable=False)
    to_location = Column(String(50), nullable=False)
    transfer_type = Column(String(50))
    
    quantity_transferred = Column(Float, nullable=False)
    
    vehicle_number = Column(String(50))
    remarks = Column(Text)
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    
    # Relationships
    finished_good = relationship("FinishedGood", back_populates="transfers")
    
    __table_args__ = (
        CheckConstraint('quantity_transferred > 0', name='check_transfer_qty'),
        CheckConstraint('from_location != to_location', name='check_different_locations'),
        Index('idx_fgt_from', 'from_location'),
        Index('idx_fgt_to', 'to_location'),
    )


# ============================================
# DELIVERY CHALLAN
# ============================================

class DeliveryChallan(Base):
    __tablename__ = "delivery_challans"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    challan_number = Column(String(50), unique=True, nullable=False, index=True)
    
    # Customer Info
    customer_id = Column(Integer, ForeignKey('customers.id'), index=True)
    customer_name = Column(String(200))
    delivery_address = Column(Text)
    
    challan_date = Column(Date, nullable=False, index=True)
    
    # Transport
    vehicle_number = Column(String(50))
    
    # Summary (calculated from items)
    total_gross_weight = Column(Float, default=0)
    total_deduction = Column(Float, default=0)
    # total_net_weight is computed: total_gross_weight - total_deduction
    
    # Status
    status = Column(String(30), default='Created', index=True)
    delivery_date = Column(Date)
    
    is_deleted = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    updated_at = Column(DateTime, onupdate=datetime.now)
    updated_by = Column(String(100))
    
    # Relationships
    customer = relationship("Customer", back_populates="delivery_challans")
    items = relationship("DeliveryChallanItem", back_populates="challan", cascade="all, delete-orphan")
    
    @property
    def total_net_weight(self):
        """Computed property for total net weight"""
        return self.total_gross_weight - self.total_deduction
    
    __table_args__ = (
        CheckConstraint('total_gross_weight >= 0', name='check_dc_gross_weight'),
    )


class DeliveryChallanItem(Base):
    __tablename__ = "delivery_challan_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    challan_id = Column(Integer, ForeignKey('delivery_challans.id', ondelete='CASCADE'), nullable=False, index=True)
    weight_receipt_id = Column(Integer, ForeignKey('weight_receipts.id'), nullable=False, index=True)
    finished_goods_id = Column(Integer, ForeignKey('finished_goods.id'), nullable=False, index=True)
    
    # From Weight Receipt
    job_card_number = Column(String(50))
    po_number = Column(String(50))
    material = Column(String(100))
    sets = Column(Integer)
    
    gross_weight = Column(Float, nullable=False)
    deduction = Column(Float, default=0)
    # net_weight is computed: gross_weight - deduction
    
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    challan = relationship("DeliveryChallan", back_populates="items")
    weight_receipt = relationship("WeightReceipt", back_populates="delivery_challan_items")
    finished_good = relationship("FinishedGood", back_populates="delivery_challan_items")
    
    @property
    def net_weight(self):
        """Computed property for net weight"""
        return self.gross_weight - self.deduction
    
    __table_args__ = (
        CheckConstraint('gross_weight > 0', name='check_dci_gross_weight'),
    )


# ============================================
# SLITTING PLANS
# ============================================

class SlittingPlan(Base):
    __tablename__ = "slitting_plans"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(String(50), unique=True, nullable=False, index=True)
    
    plan_date = Column(Date, nullable=False)
    coil_width = Column(Float, nullable=False)
    total_coil_weight = Column(Float, nullable=False)
    
    scrap_mm = Column(Float, default=0)
    scrap_weight = Column(Float, default=0)
    
    # JSON fields (matches current structure)
    raw_materials_json = Column(Text, nullable=False)
    slit_details_json = Column(Text, nullable=False)
    
    status = Column(String(20), default='Created', index=True)  # 'Created', 'In Process', 'Completed'
    
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    updated_at = Column(DateTime, onupdate=datetime.now)
    updated_by = Column(String(100))


# ============================================
# AUDIT LOG
# ============================================

class AuditLog(Base):
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    table_name = Column(String(50), nullable=False, index=True)
    record_id = Column(Integer, nullable=False, index=True)
    action = Column(String(10), nullable=False)  # 'INSERT', 'UPDATE', 'DELETE'
    
    old_values = Column(Text)  # JSON
    new_values = Column(Text)  # JSON
    
    user_name = Column(String(100), index=True)
    user_ip = Column(String(45))
    timestamp = Column(DateTime, default=datetime.now, index=True)
    
    __table_args__ = (
        Index('idx_audit_table_record', 'table_name', 'record_id'),
    )
