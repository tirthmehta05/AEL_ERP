from pydantic import BaseModel, Field
from datetime import date
from typing import List

class RMUsedRequest(BaseModel):
    rm_used_date: date
    card_no: str
    coil_no: str
    weight: float
    machine: str
    remarks: str

class RMUsedRecord(BaseModel):
    rm_used_date: date
    card_no: str
    coil_no: str
    weight: float
    machine: str
    remarks: str

    def to_list(self) -> list:
        """Convert to list format for Google Sheets"""
        return [
            self.rm_used_date.strftime("%m/%d/%Y"),
            self.card_no,
            self.coil_no,
            self.weight,
            self.machine,
            self.remarks,
            self.rm_used_date.strftime("%m/%d/%Y"),
            self.coil_no,
        ]

class DropdownData(BaseModel):
    job_cards: List[str] = Field(default_factory=list)
    coil_nos: List[str] = Field(default_factory=list)
    machines: List[str] = Field(default_factory=list)
    remarks: List[str] = Field(default_factory=list)