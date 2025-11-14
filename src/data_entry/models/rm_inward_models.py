from pydantic import BaseModel, Field, field_validator, BeforeValidator
from datetime import date
from typing import List, Optional, Annotated

def force_str(v: any) -> str:
    """Coerces a value to a stripped string."""
    return str(v).strip()

class RMInwardIssueRequest(BaseModel):
    """Request model for creating a new RM Inward Issue"""

    rm_receipt_date: date = Field(..., description="RM Receipt Date")
    rm_type: str = Field(..., min_length=1, description="RM Type")
    coil_number: Annotated[str, BeforeValidator(force_str)] = Field(..., min_length=1, description="Coil Number")
    grade: str = Field(..., min_length=1, description="Grade")
    thk: float = Field(..., gt=0, description="Thk")
    width: int = Field(..., gt=0, description="Width")
    coating: str = Field(..., min_length=1, description="Coating")
    coil_weight: float = Field(..., gt=0, description="Coil Weight")
    po_number: Optional[str] = Field(default=None, description="PO Number")
    coil_supplier: str = Field(..., min_length=1, description="Coil Supplier")
    coil_location: str = Field(..., description="Coil Location")

    @field_validator("coil_weight", "thk", "width")
    @classmethod
    def validate_positive_numbers(cls, v):
        if v <= 0:
            raise ValueError("Value must be greater than 0")
        return v

    @field_validator(
        "rm_type",
        "grade",
        "coating",
        "coil_supplier",
        "coil_location",
    )
    @classmethod
    def validate_string_fields(cls, v):
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class RMInwardIssueRecord(BaseModel):
    """Record model for RM Inward Issue data"""

    rm_receipt_date: date
    rm_type: str
    coil_number: str
    grade: str
    thk: float
    width: int
    coating: str
    coil_weight: float
    po_number: Optional[str] = None
    coil_supplier: str
    coil_location: str

    def to_list(self) -> list:
        """Convert to list format for Google Sheets"""
        return [
            self.coil_location,
            self.rm_receipt_date.strftime("%m/%d/%Y"),
            self.rm_type,
            self.coil_number,
            self.grade,
            self.thk,
            self.width,
            self.coating,
            self.coil_weight,
            None,  # No of Box / Coil
            self.po_number or "",
            self.coil_supplier,
            None,  # RM Issue Date
            None,  # RM Issue Qty
            None,  # Material Issue Line
            None,  # Material in stock
            None,  # RM Age
            None,  # Card No
            None,  # RM Allocated Qty
            None,  # Balance RM pending
            None,  # Boxes Used
        ]

    def to_dict(self) -> dict:
        """Convert to dictionary format"""
        return {
            "Location": self.coil_location,
            "RM Receipt Date": self.rm_receipt_date.strftime("%m/%d/%Y"),
            "RM Type": self.rm_type,
            "Coil Number": self.coil_number,
            "Grade": self.grade,
            "Thk": self.thk,
            "Width": self.width,
            "Coating": self.coating,
            "Coil Weight": self.coil_weight,
            "PO Number": self.po_number,
            "Coil Supplier": self.coil_supplier,
        }

class DropdownData(BaseModel):
    """Model for dropdown data"""

    rm_types: List[str] = []
    coil_numbers: List[str] = []
    grades: List[str] = []
    thks: List[str] = []
    widths: List[str] = []
    coatings: List[str] = []
    suppliers: List[str] = []
