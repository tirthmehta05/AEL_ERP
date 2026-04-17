from datetime import date

from src.data_entry.service.delivery_challan_service import DeliveryChallanService
from src.data_entry.models.delivery_challan_models import (
    DeliveryChallanRequest,
    DeliveryChallanItem,
)

service = DeliveryChallanService()

request = DeliveryChallanRequest(
    challan_type="job_work",
    challan_date=date.today(),
    hsn_code="7208",
    items=[
        DeliveryChallanItem(
            coil_number="TEST001",
            description="CRNO COIL",
            grade="CRNO",
            width=1000,
            thk=0.5,
            coating="None",
            weight_kg=1000,
            weight_mt=1.0,
            nature_of_processing="Slitting",
            hsn_code="7208",
            rate_per_mt=50000,
            value=50000,
        )
    ],
)

challan = service.create_delivery_challan(request)

print("Created Challan:", challan)