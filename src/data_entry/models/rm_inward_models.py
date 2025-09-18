from pydantic import BaseModel, Field, field_validator
from datetime import date
from typing import List

class RMInwardIssueRequest(BaseModel):
    """Request model for creating a new RM Inward Issue"""

    user_id: str = Field(..., min_length=1, description="User ID")
    rm_receipt_date: date = Field(..., description="RM Receipt Date")
    rm_type: str = Field(..., min_length=1, description="RM Type")
    coil_number: str = Field(..., min_length=1, description="Coil Number")
    grade: str = Field(..., min_length=1, description="Grade")
    thk: float = Field(..., gt=0, description="Thk")
    width: int = Field(..., gt=0, description="Width")
    coating: str = Field(..., min_length=1, description="Coating")
    coil_weight: float = Field(..., gt=0, description="Coil Weight")
    po_number: str = Field(..., min_length=1, description="PO Number")
    coil_supplier: str = Field(..., min_length=1, description="Coil Supplier")

    @field_validator("coil_weight", "thk", "width")
    @classmethod
    def validate_positive_numbers(cls, v):
        if v <= 0:
            raise ValueError("Value must be greater than 0")
        return v

    @field_validator(
        "user_id",
        "rm_type",
        "coil_number",
        "grade",
        "coating",
        "po_number",
        "coil_supplier",
    )
    @classmethod
    def validate_string_fields(cls, v):
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class RMInwardIssueRecord(BaseModel):
    """Record model for RM Inward Issue data"""

    user_id: str
    rm_receipt_date: date
    rm_type: str
    coil_number: str
    grade: str
    thk: float
    width: int
    coating: str
    coil_weight: float
    po_number: str
    coil_supplier: str

    def to_list(self) -> list:
        """Convert to list format for Google Sheets"""
        return [
            self.user_id,
            self.rm_receipt_date.strftime("%m/%d/%Y"),
            self.rm_type,
            self.coil_number,
            self.grade,
            self.thk,
            self.width,
            self.coating,
            self.coil_weight,
            self.po_number,
            self.coil_supplier,
        ]

    def to_dict(self) -> dict:
        """Convert to dictionary format"""
        return {
            "User ID": self.user_id,
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

    user_ids: List[str] = []
    rm_types: List[str] = []
    coil_numbers: List[str] = []
    grades: List[str] = []
    thks: List[str] = []
    widths: List[str] = []
    coatings: List[str] = []
    suppliers: List[str] = []