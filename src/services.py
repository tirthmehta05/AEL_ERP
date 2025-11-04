from config import settings

# Located in src/services.py - NO STREAMLIT IMPORT
# Re-export the classes for convenient type hinting
from src.data_entry.service.sales_order_service import SalesOrderService
from src.pdf_generator.service.pdf_service import PDFService
from src.data_entry.service.weight_receipt_service import WeightReceiptService
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService

class AppServices:
    """A container for all application services."""
    def __init__(
        self,
        sales_order: SalesOrderService,
        pdf: PDFService,
        weight_receipt: WeightReceiptService,
        slitting_plan: SlittingPlanService,
    ):
        self.sales_order = sales_order
        self.pdf = pdf
        self.weight_receipt = weight_receipt
        self.slitting_plan = slitting_plan

def create_services() -> AppServices:
    """
    Factory function to create and wire all application services.
    This is the single point of instantiation for backend services.
    """
    # Instantiate services, injecting dependencies as needed
    sales_order_service = SalesOrderService(
        pa_client_id=settings.power_automate.pa_client_id,
        pa_client_secret=settings.power_automate.pa_client_secret,
        pa_tenant_id=settings.power_automate.pa_tenant_id
    )
    pdf_service = PDFService(sales_order_service=sales_order_service)
    weight_receipt_service = WeightReceiptService()
    slitting_plan_service = SlittingPlanService()

    # Return the container with all services
    return AppServices(
        sales_order=sales_order_service,
        pdf=pdf_service,
        weight_receipt=weight_receipt_service,
        slitting_plan=slitting_plan_service,
    )
