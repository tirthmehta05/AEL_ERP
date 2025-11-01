from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

class DesignDetail(BaseModel):
    """Model for a single design detail line item in a Sales Order."""
    party_job_no: Optional[str] = None
    width: float
    length: float
    mm_stack: Optional[float] = None
    weight: Optional[float] = None
    sets: int
    type: str
    thk: float
    grade: Optional[str] = None
    hole: str
    pcs: int
    coating: Optional[str] = None

class AssignedCoil(BaseModel):
    """Model for a single coil assigned to a Sales Order."""
    coil_no: str
    weight_used: float

class SalesOrderRequest(BaseModel):
    """Request model for creating a new Sales Order for a Job Card."""
    order_date: date
    po_no: Optional[str] = None
    party_name: str
    delivery_date: date
    job_card_number: str
    hole_size: int
    number_of_cores: int
    rate_per_kg: float
    header_core_stack: Optional[float] = None
    coating: Optional[str] = None
    designs: List[DesignDetail]
    assigned_coils: Optional[List[AssignedCoil]] = None

class SalesOrderDropdownData(BaseModel):
    """Model for dropdown data for the Sales Order form."""
    party_names: List[str] = []
    hole_sizes: List[int] = []
    coatings: List[str] = []