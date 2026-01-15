from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import date

class DesignDetail(BaseModel):
    """Model for a single design detail line item in a Sales Order."""
    party_job_no: Optional[str] = None
    fm_name: Optional[str] = None
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
    run_child_flow: Optional[bool] = None
    order_type: Optional[Literal["CORE_BUILDING", "LOOSE_STRIPS", "EI_READY"]] = None
    
    def determine_order_type(self) -> str:
        """Determines the order type based on design details and number of cores.
        
        Returns:
            str: One of "EI_READY", "LOOSE_STRIPS", or "CORE_BUILDING"
        """
        # Check if any design is an EI Ready entry (takes precedence)
        if self.designs:
            for design in self.designs:
                if design.hole == "Ready Entry":
                    return "EI_READY"
        
        # Check if it's a loose strips order (number_of_cores = 0)
        if self.number_of_cores == 0:
            return "LOOSE_STRIPS"
        
        # Default to core building
        return "CORE_BUILDING"

class SalesOrderDropdownData(BaseModel):
    """Model for dropdown data for the Sales Order form."""
    party_names: List[str] = []
    hole_sizes: List[int] = []
    coatings: List[str] = []

class PowerAutomatePlannerRequest(BaseModel):
    """Model for the payload sent to the Power Automate Planner flow."""
    companyName: str
    jobNumber: str
    poNumber: Optional[str] = None
    jobDate: str # Assuming YYYY-MM-DD format string
    orderType: str = Field(default="MFG")
    runChildFlow: bool = Field(default=False)

class FullCoilSaleRequest(BaseModel):
    """Request model for creating a new Full Coil Sale."""
    job_card: str
    order_date: date
    po_no: Optional[str] = None
    party_name: str
    width: float
    qty: float
    material_type: str
    thk: float
    rate: float
    delivery_date: date
    remark: Optional[str] = None
    grade: Optional[str] = None
    coating: Optional[str] = None