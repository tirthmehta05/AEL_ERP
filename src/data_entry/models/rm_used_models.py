from pydantic import BaseModel, Field
from datetime import date
from typing import List, Optional

class RMUsedRequest(BaseModel):
    rm_used_date: date
    card_no: str
    coil_no: str
    weight: float
    machine: str
    remarks: str
    no_of_boxes: Optional[int] = Field(default=0)

class RMUsedRecord(BaseModel):
    rm_used_date: date
    card_no: str
    coil_no: str
    weight: float
    machine: str
    remarks: str
    no_of_boxes: int

    def to_list(self) -> list:
        """Convert to list format for Google Sheets"""
        return [
            self.rm_used_date.strftime("%m/%d/%Y"),
            self.card_no,
            self.coil_no,
            self.weight,
            self.machine,
            self.remarks,
            self.no_of_boxes,
        ]

class DropdownData(BaseModel):
    job_cards: List[str] = Field(default_factory=list)
    coil_nos: List[str] = Field(default_factory=list)
    machines: List[str] = Field(default_factory=list)
    remarks: List[str] = Field(default_factory=list)