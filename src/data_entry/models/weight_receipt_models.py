from pydantic import BaseModel, Field
from datetime import date
from typing import List, Dict, Optional, Literal

class WeighedDesignDetail(BaseModel):
    """Model for a single design detail with its actual weight."""
    party_job_no: Optional[str] = None
    width: float
    length: float
    mm_stack: Optional[float] = None
    actual_weight: Optional[float] = None
    remark: Optional[str] = None

class WeightReceiptRequest(BaseModel):
    """Request model for creating a new Weight Receipt."""
    weight_receipt_number: str
    receipt_date: date
    job_card_number: str
    party_name: str
    po_no: Optional[str] = None
    material: str
    sets: int
    designs: List[WeighedDesignDetail]
    weight_entry_type: str = "Loose Strips"
    total_weight: Optional[float] = None
    deduction: float = 0.0
    order_type: Optional[Literal["CORE_BUILDING", "LOOSE_STRIPS", "EI_READY"]] = None

class WeightReceiptRecord(BaseModel):
    """Record model for Weight Receipt data."""
    weight_receipt_number: str
    receipt_date: date
    job_card_number: str
    party_name: str
    po_no: Optional[str] = None
    material: str
    sets: int
    designs_json: str
    weight_entry_type: str = "Loose Strips"
    total_weight: Optional[float] = None
    deduction: float = 0.0

    def to_list(self) -> list:
        """Convert to list format for Google Sheets."""
        return [
            self.weight_receipt_number,
            self.receipt_date.strftime("%d/%m/%Y"),
            self.job_card_number,
            self.party_name,
            self.po_no or "",
            self.material,
            self.sets,
            self.designs_json,
            self.weight_entry_type,
            self.total_weight,
            self.deduction,
        ]
