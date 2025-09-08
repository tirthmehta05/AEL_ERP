"""
Raw Material Inward Issue Models
Pydantic models for data validation and serialization
"""

from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import Optional, List


class RMInwardIssueRequest(BaseModel):
    """Request model for creating a new RM Inward Issue"""

    user_id: str = Field(..., min_length=1, description="User ID")
    rm_receipt_date: date = Field(..., description="RM Receipt Date")
    rm_type: str = Field(..., min_length=1, description="RM Type")
    coil_number: str = Field(..., min_length=1, description="Coil Number")
    grade: str = Field(..., min_length=1, description="Grade")
    thickness: str = Field(..., min_length=1, description="Thickness")
    width: str = Field(..., min_length=1, description="Width")
    coating: str = Field(..., min_length=1, description="Coating")
    coil_weight: float = Field(..., gt=0, description="Coil Weight")
    coil_supplier: str = Field(..., min_length=1, description="Coil Supplier")

    @field_validator("coil_weight")
    @classmethod
    def validate_coil_weight(cls, v):
        if v <= 0:
            raise ValueError("Coil weight must be greater than 0")
        return v

    @field_validator(
        "user_id",
        "rm_type",
        "coil_number",
        "grade",
        "thickness",
        "width",
        "coating",
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
    thickness: str
    width: str
    coating: str
    coil_weight: float
    coil_supplier: str
    created_at: Optional[str] = None

    def to_list(self) -> list:
        """Convert to list format for Google Sheets"""
        return [
            self.user_id,
            self.rm_receipt_date.strftime("%Y-%m-%d"),
            self.rm_type,
            self.coil_number,
            self.grade,
            self.thickness,
            self.width,
            self.coating,
            self.coil_weight,
            self.coil_supplier,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # created_at
        ]

    def to_dict(self) -> dict:
        """Convert to dictionary format"""
        return {
            "User ID": self.user_id,
            "RM Receipt Date": self.rm_receipt_date.strftime("%Y-%m-%d"),
            "RM Type": self.rm_type,
            "Coil Number": self.coil_number,
            "Grade": self.grade,
            "Thickness": self.thickness,
            "Width": self.width,
            "Coating": self.coating,
            "Coil Weight": self.coil_weight,
            "Coil Supplier": self.coil_supplier,
            "Created At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


class DropdownData(BaseModel):
    """Model for dropdown data"""

    user_ids: List[str] = []
    rm_types: List[str] = []
    coil_numbers: List[str] = []
    grades: List[str] = []
    thicknesses: List[str] = []
    widths: List[str] = []
    coatings: List[str] = []
    suppliers: List[str] = []
