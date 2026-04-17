from src.data_entry.service.delivery_challan_service import DeliveryChallanService
service = DeliveryChallanService()
challan_number = "F/001/25-26"   # change if needed
pdf_bytes = service.generate_challan_pdf(challan_number)
with open("delivery_challan.pdf", "wb") as f:
    f.write(pdf_bytes)

print("PDF Generated Successfully")