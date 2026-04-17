from pydantic import BaseModel, validator
from datetime import date
from typing import List, Optional, Literal
import json


class DeliveryChallanItem(BaseModel):
    coil_number: str
    description: str
    grade: str
    width: float
    thk: float
    coating: str
    weight_kg: float
    weight_mt: float
    nature_of_processing: str
    hsn_code: str
    rate_per_mt: float
    value: float


class DeliveryChallanRequest(BaseModel):
    challan_type: Literal["job_work", "return"]
    challan_date: date
    party_name: str = "TAIIN STEEL FAB & INFRA PVT LTD"
    vehicle_no: Optional[str] = None
    ewaybill_no: Optional[str] = None
    hsn_code: str = ""
    rounded_off: float = 0.0
    remarks: Optional[str] = None
    items: List[DeliveryChallanItem]

    @validator("items")
    def must_have_items(cls, v):
        if len(v) == 0:
            raise ValueError("At least one coil item is required")
        return v


class MissingFieldResult(BaseModel):
    """Result of missing field validation for a challan request."""
    field_name: str
    display_name: str
    source: str  # e.g. "Consignee Master", "RM Inward", "User Input"
    is_missing: bool = True


class DeliveryChallanRecord(BaseModel):
    challan_number: str
    challan_date: date
    challan_type: str
    party_name: str
    vehicle_no: Optional[str]
    ewaybill_no: Optional[str]
    hsn_code: str
    total_weight_mt: float
    total_value: float
    rounded_off: float
    remarks: Optional[str]
    status: str = "Finalized"
    coils_json: str

    def to_list(self) -> list:
        return [
            self.challan_number,
            str(self.challan_date),
            self.challan_type,
            self.party_name,
            self.vehicle_no or "",
            self.ewaybill_no or "",
            self.hsn_code,
            self.total_weight_mt,
            self.total_value,
            self.rounded_off,
            self.remarks or "",
            self.status,
            self.coils_json,
        ]