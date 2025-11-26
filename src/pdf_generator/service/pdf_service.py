from datetime import datetime
import io
from typing import List
import pandas as pd
import qrcode
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService
from src.data_entry.service.sales_order_service import SalesOrderService
from src.data_entry.service.rm_used_service import RMUsedService
from src.data_entry.service.weight_receipt_service import WeightReceiptService
from fpdf import FPDF
import json

class PDFService:
    def __init__(self, sales_order_service: SalesOrderService):
        self.slitting_service = SlittingPlanService()
        self.sales_order_service = sales_order_service
        self.rm_used_service = RMUsedService()
        self.weight_receipt_service = WeightReceiptService()

    def get_sales_orders_for_job_card(self, start_date=None, end_date=None):
        return self.sales_order_service.get_sales_orders_for_job_card(start_date, end_date, include_designs=True)

    def get_available_coils_for_sticker(self) -> pd.DataFrame:
        """Fetches available coils and prepares them for sticker printing display."""
        return self.slitting_service.get_available_coils()

    def _draw_sticker(self, pdf: FPDF, x: float, y: float, coil: pd.Series):
        """Draws a single sticker at the specified (x, y) coordinates."""
        sticker_width = 95
        sticker_height = 55
        margin = 4

        pdf.rect(x, y, sticker_width, sticker_height)
        
        # 1. Company Name
        pdf.set_xy(x + margin, y + 2)
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(sticker_width - 2 * margin, 5, "Amba Enterprise Limited", align='C')

        # 2. Coil Number
        pdf.set_xy(x + margin, y + 8)
        pdf.set_font("Helvetica", 'B', 14)
        pdf.multi_cell(sticker_width - 2 * margin, 5, f"{coil['Coil Number']}", align='C')

        # 3. Other Details (allow for 2 lines of coil number)
        qr_size = 22 # Define QR size before using it for width calculation
        pdf.set_xy(x + margin, y + 20)
        pdf.set_font("Helvetica", '', 9)
        details_text = (
            f"Weight: {coil['available_weight']:.2f} kg\n"
            f"Grade: {coil['grade']}\n"
            f"Thk: {coil['thickness']} mm\n"
            f"Width: {int(coil['width'])} mm\n"
            f"Coating: {coil['coating']}\n"
            f"Supplier: {coil['coil_supplier']}"
        )
        pdf.multi_cell(sticker_width - qr_size - (2 * margin), 4, details_text)

        # 4. QR Code
        qr_x = x + sticker_width - qr_size - margin
        qr_y = y + sticker_height - qr_size - margin
        
        qr_data = (
            f"Coil Number: {coil['Coil Number']}\n"
            f"Weight: {coil['available_weight']:.2f} kg\n"
            f"Grade: {coil['grade']}\n"
            f"Thickness: {coil['thickness']} mm\n"
            f"Width: {int(coil['width'])} mm\n"
            f"Coating: {coil['coating']}\n"
            f"Supplier: {coil['coil_supplier']}"
        )
        qr = qrcode.QRCode(version=1, box_size=3, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        
        qr_bytes = io.BytesIO()
        img.save(qr_bytes, format='PNG')
        qr_bytes.seek(0)
        
        pdf.image(qr_bytes, x=qr_x, y=qr_y, w=qr_size, h=qr_size, type='PNG')

    def generate_sticker_pdf(self, selected_coils: pd.DataFrame) -> bytes:
        """Generates a PDF with a 2x5 grid of stickers."""
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()

        margin_horiz = 10
        margin_vert = 10
        sticker_width = 95
        sticker_height = 55

        sticker_count = 0
        for _, coil in selected_coils.iterrows():
            if sticker_count >= 10:
                pdf.add_page()
                sticker_count = 0

            col = sticker_count % 2
            row = sticker_count // 2

            x = margin_horiz + (col * sticker_width)
            y = margin_vert + (row * sticker_height)

            self._draw_sticker(pdf, x, y, coil)
            sticker_count += 1

        return bytes(pdf.output(dest='S'))

    def generate_slitting_plan_pdf(self, plan_data: dict) -> bytes:
        """Generates a formatted PDF for a given slitting plan."""
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()

        # Header with Logo
        pdf.image("assets/logofinal.png", x=10, y=8, w=50)
        pdf.ln(20) # Move down to create space below the logo

        # Title
        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(0, 10, "Slitting Plan", ln=True, align='C')
        pdf.ln(5)

        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, 8, f"Plan No: {plan_data.get('plan_id', 'N/A')}", ln=True, align='L')
        pdf.cell(0, 8, f"Date: {plan_data.get('date', 'N/A')}", ln=True, align='L')
        pdf.ln(10)

        # Raw Materials Table
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(0, 8, "Raw Materials to be Used:", ln=True)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(60, 8, "R/M No", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Grade", border=1, fill=True, align='C')
        pdf.cell(20, 8, "Thk", border=1, fill=True, align='C')
        pdf.cell(20, 8, "Width", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Net Wt (kg)", border=1, fill=True, align='C', ln=True)

        pdf.set_font("Helvetica", '', 10)
        total_rm_weight = 0
        for coil in plan_data.get('raw_materials', []):
            pdf.cell(60, 8, str(coil.get('Coil Number', '')), border=1)
            pdf.cell(30, 8, str(coil.get('grade', '')), border=1)
            pdf.cell(20, 8, str(coil.get('thickness', '')), border=1)
            pdf.cell(20, 8, str(plan_data.get('coil_width', '')), border=1)
            try:
                weight = float(coil.get('available_weight', 0))
            except (ValueError, TypeError):
                weight = 0
            total_rm_weight += weight
            pdf.cell(30, 8, f"{weight:.2f}", border=1, align='R', ln=True)
        
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(130, 8, "Total", border=1)
        pdf.cell(30, 8, f"{total_rm_weight:.2f}", border=1, align='R', ln=True)
        pdf.ln(10)

        # Slit Details Table
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(0, 8, "Slit Details:", ln=True)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(40, 8, "Size (mm)", border=1, fill=True, align='C')
        pdf.cell(40, 8, "No. of Slits", border=1, fill=True, align='C')
        pdf.cell(40, 8, "Total MM", border=1, fill=True, align='C')
        pdf.cell(40, 8, "Weight (kg)", border=1, fill=True, align='C', ln=True)

        pdf.set_font("Helvetica", '', 10)
        total_slits = 0
        total_mm = 0
        total_slit_weight = 0
        for slit in plan_data.get('slit_details', []):
            try:
                size = float(slit.get('Size', 0))
                num_slits = int(slit.get('No. of Slits', 0))
                weight = float(slit.get('Weight in Kg', 0)) # Correct key is 'Weight in Kg'
            except (ValueError, TypeError):
                size, num_slits, weight = 0, 0, 0

            total_slits += num_slits
            mm = size * num_slits
            total_mm += mm
            total_slit_weight += weight
            pdf.cell(40, 8, str(size), border=1, align='C')
            pdf.cell(40, 8, str(num_slits), border=1, align='C')
            pdf.cell(40, 8, str(mm), border=1, align='C')
            pdf.cell(40, 8, f"{weight:.2f}", border=1, align='R', ln=True)

        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(40, 8, "Total", border=1)
        pdf.cell(40, 8, str(total_slits), border=1, align='C')
        pdf.cell(40, 8, str(total_mm), border=1, align='C')
        pdf.cell(40, 8, f"{total_slit_weight:.2f}", border=1, align='R', ln=True)
        
        # Enhanced Footer for Slit Table
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(120, 6, "Scrap mm:", border='T', align='R')
        pdf.cell(40, 6, f"{float(plan_data.get('scrap_mm', 0)):.2f}", border='T', align='R', ln=True)
        pdf.cell(120, 6, "Scrap Weight:", align='R')
        pdf.cell(40, 6, f"{float(plan_data.get('scrap_weight', 0)):.2f} kg", align='R', ln=True)
        pdf.cell(120, 6, "Total MM:", align='R')
        pdf.cell(40, 6, str(plan_data.get('coil_width', 'N/A')), align='R', ln=True)
        pdf.cell(120, 6, "Total Weight:", align='R')
        pdf.cell(40, 6, f"{float(plan_data.get('total_coil_weight', 0)):.2f} kg", align='R', ln=True)
        pdf.ln(5)

        # General Footer
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(0, 8, "Slit width tolerance: +/- 0.1 mm", ln=True)
        pdf.cell(0, 8, "OD: 510 mm", ln=True)

        return bytes(pdf.output(dest='S'))

    def _draw_hole_representation(self, pdf: FPDF, x: float, y: float, width: float, height: float, hole_type: str):
        padding = 2
        plate_width = width - (2 * padding)
        plate_height = height - (2 * padding)
        plate_x = x + padding
        plate_y = y + padding
        hole_radius = 1.5

        # Set line width for bold lines
        pdf.set_line_width(0.5)
        pdf.set_draw_color(0, 0, 0) # Black

        # Draw the plate outline
        pdf.rect(plate_x, plate_y, plate_width, plate_height, 'D') # 'D' for draw

        # Set fill color to white to draw on top of any existing background
        pdf.set_fill_color(255, 255, 255)

        if str.lower(hole_type) == "side":
            circle_x = plate_x + plate_width * 0.25
            circle_y = plate_y + plate_height / 2
            pdf.ellipse(circle_x - hole_radius, circle_y - hole_radius, hole_radius * 2, hole_radius * 2, 'D')
        elif str.lower(hole_type) == "both side":
            circle_y = plate_y + plate_height / 2
            # Left
            l_circle_x = plate_x + plate_width * 0.25
            pdf.ellipse(l_circle_x - hole_radius, circle_y - hole_radius, hole_radius * 2, hole_radius * 2, 'D')
            # Right
            r_circle_x = plate_x + plate_width * 0.75
            pdf.ellipse(r_circle_x - hole_radius, circle_y - hole_radius, hole_radius * 2, hole_radius * 2, 'D')
        elif str.lower(hole_type) == "centre":
            circle_x = plate_x + plate_width / 2
            circle_y = plate_y + plate_height / 2
            pdf.ellipse(circle_x - hole_radius, circle_y - hole_radius, hole_radius * 2, hole_radius * 2, 'D')
        elif str.lower(hole_type) == "3-hole":
            circle_y = plate_y + plate_height / 2
            positions = [0.25, 0.5, 0.75]
            for pos in positions:
                circle_x = plate_x + plate_width * pos
                pdf.ellipse(circle_x - hole_radius, circle_y - hole_radius, hole_radius * 2, hole_radius * 2, 'D')
        elif str.lower(hole_type) == "5-hole":
            circle_y = plate_y + plate_height / 2
            positions = [0.15, 0.325, 0.5, 0.675, 0.85]
            for pos in positions:
                circle_x = plate_x + plate_width * pos
                pdf.ellipse(circle_x - hole_radius, circle_y - hole_radius, hole_radius * 2, hole_radius * 2, 'D')
        elif str.lower(hole_type) == "ready entry": # Handle "Ready Entry" by drawing no holes
            pass
        
        # Reset line width to default
        pdf.set_line_width(0.2)

    def _draw_items_table_header(self, pdf: FPDF, job_card_data: dict):
        pdf.set_font("Helvetica", 'B', 10)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(15, 8, "Sr No", border=1, fill=True, align='C')
        pdf.cell(50, 8, "Width X Length", border=1, fill=True, align='C')
        hole_size_header = f"Hole: {job_card_data.get('hole_size', 'N/A')}"
        pdf.cell(35, 8, hole_size_header, border=1, fill=True, align='C')
        pdf.cell(30, 8, "in MM", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Pcs", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Weight", border=1, fill=True, align='C', ln=True)

    def _draw_job_card(self, pdf: FPDF, job_card_data: dict):
        """Draws a single job card on the current PDF page."""
        pdf.add_page()

        # Header
        pdf.image("assets/logofinal.png", x=10, y=8, w=50)
        pdf.set_font("Helvetica", 'B', 18)
        pdf.cell(0, 10, "CRNGO JOB CARD", ln=True, align='C')
        pdf.ln(10)

        # Job Details
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(0, 8, f"Party Name: {job_card_data.get('party_name', 'N/A')}", ln=True, align='L')
        pdf.ln(5)

        designs = json.loads(job_card_data.get('designs_json', '[]'))
        thickness = designs[0].get('thk', 'N/A') if designs else 'N/A'
        party_job_no = designs[0].get('party_job_no', 'N/A') if designs else 'N/A'
        
        # Main Parameters Table
        key_font_size = 10
        value_font_size = 12
        cell_width = 95
        key_width = 40
        value_width = cell_width - key_width

        # Row 1
        pdf.set_font("Helvetica", '', key_font_size)
        pdf.cell(key_width, 8, "Core Stack:", border='LTB', align='L')
        pdf.set_font("Helvetica", 'B', value_font_size)
        pdf.cell(value_width, 8, str(job_card_data.get('header_core_stack', 'N/A')), border='RTB', align='L')

        pdf.set_font("Helvetica", '', key_font_size)
        pdf.cell(key_width, 8, "Order Dt:", border='LTB', align='L')
        pdf.set_font("Helvetica", 'B', value_font_size)
        order_date_obj = job_card_data.get('order_date')
        formatted_order_date = pd.to_datetime(order_date_obj).strftime('%d/%m/%Y') if pd.notna(order_date_obj) else 'N/A'
        pdf.cell(value_width, 8, formatted_order_date, border='RTB', align='L', ln=True)

        # Row 2
        pdf.set_font("Helvetica", '', key_font_size)
        pdf.cell(key_width, 8, "Thickness:", border='LTB', align='L')
        pdf.set_font("Helvetica", 'B', value_font_size)
        pdf.cell(value_width, 8, str(thickness), border='RTB', align='L')

        pdf.set_font("Helvetica", '', key_font_size)
        pdf.cell(key_width, 8, "Job Card No:", border='LTB', align='L')
        pdf.set_font("Helvetica", 'B', value_font_size)
        pdf.cell(value_width, 8, str(job_card_data.get('job_card_number', 'N/A')), border='RTB', align='L', ln=True)

        # Row 3
        pdf.set_font("Helvetica", '', key_font_size)
        pdf.cell(key_width, 8, "Number of Cores:", border='LTB', align='L')
        pdf.set_font("Helvetica", 'B', value_font_size)
        pdf.cell(value_width, 8, str(job_card_data.get('number_of_cores', 'N/A')), border='RTB', align='L')

        pdf.set_font("Helvetica", '', key_font_size)
        pdf.cell(key_width, 8, "Delivery Dt:", border='LTB', align='L')
        pdf.set_font("Helvetica", 'B', value_font_size)
        delivery_date_obj = job_card_data.get('delivery_date')
        formatted_delivery_date = pd.to_datetime(delivery_date_obj).strftime('%d/%m/%Y') if pd.notna(delivery_date_obj) else 'N/A'
        pdf.cell(value_width, 8, formatted_delivery_date, border='RTB', align='L', ln=True)

        # Row 4
        pdf.set_font("Helvetica", '', key_font_size)
        pdf.cell(key_width, 8, "PO No:", border='LTB', align='L')
        pdf.set_font("Helvetica", 'B', value_font_size)
        pdf.cell(value_width, 8, str(job_card_data.get('po_no', 'N/A')), border='RTB', align='L')

        pdf.set_font("Helvetica", '', key_font_size)
        pdf.cell(key_width, 8, "Job No:", border='LTB', align='L')
        pdf.set_font("Helvetica", 'B', value_font_size)
        pdf.cell(value_width, 8, str(party_job_no), border='RTB', align='L', ln=True)
        pdf.ln(10)

        # Items Table
        self._draw_items_table_header(pdf, job_card_data)

        pdf.set_font("Helvetica", 'B', 12)
        row_height = 10

        total_weight = 0
        for i, item in enumerate(designs):
            if pdf.get_y() > 260:
                pdf.add_page()
                self._draw_items_table_header(pdf, job_card_data)
                pdf.set_font("Helvetica", 'B', 12)

            pdf.cell(15, row_height, str(i + 1), border=1, align='C')
            pdf.cell(50, row_height, f"{item.get('width', 'N/A')} X {item.get('length', 'N/A')}", border=1, align='C')
            
            hole_cell_width = 35
            hole_cell_x = pdf.get_x()
            hole_cell_y = pdf.get_y()
            hole_type = item.get('hole', 'Plain')
            self._draw_hole_representation(pdf, hole_cell_x, hole_cell_y, hole_cell_width, row_height, hole_type)
            pdf.rect(hole_cell_x, hole_cell_y, hole_cell_width, row_height)
            pdf.set_x(hole_cell_x + hole_cell_width)

            pdf.cell(30, row_height, "" if item.get('mm_stack') is None else str(item.get('mm_stack')), border=1, align='C')
            pdf.cell(30, row_height, "" if item.get('pcs') == 0 else str(item.get('pcs')), border=1, align='C')
            
            weight = 0
            try:
                item_weight = item.get('weight')
                if item_weight is not None:
                    weight = float(item_weight)
            except (ValueError, TypeError):
                weight = 0
            
            total_weight += weight
            pdf.cell(30, row_height, f"{weight:.3f}" if weight > 0 else "", border=1, align='R', ln=True)

        # Footer
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(160, 8, "Total Weight", border=1, align='R')
        pdf.cell(30, 8, f"{total_weight:.3f}", border=1, align='R', ln=True)

        # Assigned Coils Table
        pdf.ln(10)
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(0, 8, "Assigned Coils:", ln=True)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(100, 8, "Coil Number", border=1, fill=True, align='C')
        pdf.cell(90, 8, "Weight Used (kg)", border=1, fill=True, align='C', ln=True)

        pdf.set_font("Helvetica", '', 10)
        assigned_coils = self.rm_used_service.get_coils_for_job_card(job_card_data['job_card_number'])
        if assigned_coils:
            for coil in assigned_coils:
                pdf.cell(100, 8, str(coil.get('Coil No', 'N/A')), border=1, align='C')
                pdf.cell(90, 8, str(coil.get('Weight', 'N/A')), border=1, align='R', ln=True)
        else:
            pdf.cell(190, 8, "Pending Coil Assignment", border=1, align='C', ln=True)

    def generate_job_card_pdf(self, selected_job_cards: List[dict]) -> bytes:
        """Generates a PDF for the selected job cards.""" 
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        for job_card in selected_job_cards:
            self._draw_job_card(pdf, job_card)
        return bytes(pdf.output(dest='S'))

    def generate_delivery_challan_pdf(self, data: dict) -> bytes:
        """Generates a Delivery Challan PDF from a structured dictionary."""
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Header
        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(0, 10, "Delivery Challan Report", ln=True, align='C')
        pdf.ln(5)

        # From/To addresses
        challan_details = data['challan_details']
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(95, 8, "From:", ln=False)
        pdf.cell(95, 8, f"To M/S.: {challan_details['to_customer']}", ln=True)
        
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(95, 8, challan_details['from_company']['name'], ln=True)
        pdf.set_font("Helvetica", '', 10)
        pdf.multi_cell(95, 5, challan_details['from_company']['address'])
        pdf.ln(5)

        # Report Details
        pdf.cell(95, 8, f"Challan No: {challan_details['challan_no']}", ln=False)
        pdf.cell(95, 8, f"Challan Date: {challan_details['challan_date']}", ln=True, align='R')
        pdf.cell(0, 8, f"Vehicle No: {challan_details['vehicle_no']}", ln=True)
        pdf.ln(5)

        # Table Header
        pdf.set_font("Helvetica", 'B', 10)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(40, 8, "Job No", border=1, fill=True, align='C')
        pdf.cell(30, 8, "P O No", border=1, fill=True, align='C')
        pdf.cell(90, 8, "Particulars", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Weight", border=1, fill=True, align='C', ln=True)

        pdf.set_font("Helvetica", '', 10)

        for item in data['items']:
            # --- First line of the item block ---
            pdf.cell(40, 8, str(item['job_no']), border='L', align='C')
            pdf.cell(30, 8, str(item['po_no']), border='L', align='C')
            pdf.cell(90, 8, item['line_items'][0]['description'], border='L', align='C')
            if item['line_items'][0]['weight'] is not None:
                pdf.cell(30, 8, f"{item['line_items'][0]['weight']:.2f}", border='LR', align='R', ln=True)
            else:
                pdf.cell(30, 8, "", border='LR', align='R', ln=True)

            # --- Subsequent line items ---
            for i in range(1, len(item['line_items'])):
                pdf.cell(40, 8, "", border='L', align='C')
                pdf.cell(30, 8, "", border='L', align='C')
                pdf.cell(90, 8, item['line_items'][i]['description'], border='L', align='C')
                if item['line_items'][i]['weight'] is not None:
                    pdf.cell(30, 8, f"{item['line_items'][i]['weight']:.2f}", border='LR', align='R', ln=True)
                else:
                    pdf.cell(30, 8, "", border='LR', align='R', ln=True)

            # --- Summary lines ---
            pdf.cell(40, 8, "", border='L', align='C')
            pdf.cell(30, 8, "", border='L', align='C')
            pdf.cell(90, 8, item['summary']['material'], border='L', align='C')
            pdf.set_font("Helvetica", 'B', 10)
            pdf.cell(30, 8, f"{item['summary']['total_weight']:.2f}", border='LR', align='R', ln=True)
            pdf.set_font("Helvetica", '', 10)

            pdf.cell(40, 8, "", border='LB', align='C')
            pdf.cell(30, 8, "", border='LB', align='C')
            pdf.cell(90, 8, f"Set : {item['summary']['sets']}", border='LB', align='C')
            pdf.cell(30, 8, "", border='LBR', align='R', ln=True)

        return bytes(pdf.output(dest='S'))

    def generate_weight_receipt_pdf(self, receipt_data: dict) -> bytes:
        """Generates a Weight Receipt PDF from a structured dictionary."""
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Title
        pdf.set_font("Helvetica", 'B', 18)
        pdf.cell(0, 10, f"Weight Receipt No: {receipt_data.get('WeightReceiptNumber', 'N/A')}", ln=True, align='C')
        pdf.ln(10)

        # --- Header Box ---
        line_height = 8
        
        # Get data
        party_name = receipt_data.get('PartyName', 'N/A')
        po_no = receipt_data.get('PONumber', 'N/A')
        receipt_date_obj = receipt_data.get('Date')
        receipt_date = pd.to_datetime(receipt_date_obj).strftime('%d/%m/%Y') if pd.notna(receipt_date_obj) else 'N/A'
        card_no = receipt_data.get('JobCardNumber', 'N/A')
        
        designs = json.loads(receipt_data.get('DesignDetailsWithWeightsJSON', '[]'))
        job_no = designs[0].get('party_job_no', 'N/A') if designs else 'N/A'

        # Line 1: Name
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(20, line_height, "Name", border=1)
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, line_height, f": {party_name}", border=1, ln=True)

        # Line 2: PO No and PO Date
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(20, line_height, "PO No", border='L,B')
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(75, line_height, f": {po_no}", border='B,R')
        
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(25, line_height, "PO Date", border='B')
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, line_height, f": {receipt_date}", border='B,R', ln=True)

        # Line 3: Card No and Job No
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(20, line_height, "Card No", border='L,B')
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(75, line_height, f": {card_no}", border='B,R')
        
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(25, line_height, "Job No", border='B')
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, line_height, f": {job_no}", border='B,R', ln=True)
        pdf.ln(10)
        
        # --- Items Table Header ---
        pdf.set_font("Helvetica", 'B', 10)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(20, 8, "Sr No", border=1, fill=True, align='C')
        pdf.cell(140, 8, "Description", border=1, fill=True, align='C')
        pdf.cell(30, 8, "Weight", border=1, fill=True, align='C', ln=True)

        # --- Items Table Rows ---
        pdf.set_font("Helvetica", '', 10)
        total_weight = 0
        row_height = 8 # Use a consistent row height

        is_core_building = receipt_data.get('WeightEntryType') == 'Building Core'
        core_receipt_remark = ""
        if is_core_building and designs:
            core_receipt_remark = designs[0].get('remark', '')

        if is_core_building:
            total_weight = float(receipt_data.get('TotalWeight', 0))
            for i, item in enumerate(designs):
                start_y = pdf.get_y()
                pdf.cell(20, row_height, str(i + 1), border=1, align='C')
                
                desc_x = pdf.get_x()
                description = f"{item.get('width', '')} X {item.get('length', '')}"
                if item.get('mm_stack'):
                    description += f" X {item.get('mm_stack', '')}"
                
                # Use multi_cell for description but manage positioning manually
                pdf.multi_cell(140, row_height, description, border=1, align='C', ln=1)
                
                # Manually set position for the next cell
                pdf.set_xy(desc_x + 140, start_y)
                pdf.cell(30, row_height, "", border=1, align='R', ln=True) # No individual weight
        else: # Loose strips or legacy
            for i, item in enumerate(designs):
                start_y = pdf.get_y()
                pdf.cell(20, row_height, str(i + 1), border=1, align='C')
                
                desc_x = pdf.get_x()
                description = f"{item.get('width', '')} X {item.get('length', '')}"
                if item.get('mm_stack'):
                    description += f" X {item.get('mm_stack', '')}"
                
                item_remark = item.get('remark', '')
                if item_remark:
                    # Use a second line for remark instead of multi_cell to control height
                    pdf.cell(140, row_height / 2, description, border='LRT', align='C', ln=2) # Go to next line
                    pdf.set_x(desc_x)
                    pdf.cell(140, row_height / 2, item_remark, border='LRB', align='C')
                else:
                    pdf.cell(140, row_height, description, border=1, align='C')

                weight = float(item.get('actual_weight') or 0)
                total_weight += weight

                pdf.set_xy(desc_x + 140, start_y)
                pdf.cell(30, row_height, f"{weight:.3f}" if weight > 0 else "", border=1, align='R', ln=True)

        # --- Table Footer ---
        pdf.set_font("Helvetica", '', 10)
        # Empty Sr No cell (20mm)
        pdf.cell(20, 8, '', border='LTB')

        # Type (40mm) + Set (20mm) + Remark (80mm) = 140mm (Description column width)
        pdf.cell(40, 8, f"Type: {receipt_data.get('Material', 'N/A')}", border='TB')
        pdf.cell(20, 8, f"Set: {receipt_data.get('Sets', 'N/A')}", border='TB')
        
        remark_text = f"Remark: {core_receipt_remark}" if is_core_building and core_receipt_remark else ""
        pdf.cell(80, 8, remark_text, border='TB')

        # Weight (30mm)
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(30, 8, f"Weight: {total_weight:.3f}", border=1, align='R', ln=True)
        pdf.ln(2)

        # --- Details below table ---
        pdf.set_font("Helvetica", '', 12)
        col_width = 95
        line_height = 8
        # Line 2: Deduction, Net
        pdf.cell(col_width, line_height, "Deduction : 0.00", border=0)
        pdf.cell(col_width, line_height, f"Net : {total_weight:.2f}", border=0, ln=True)
        pdf.ln(15) # Increased spacing

        # --- Signatures and Timestamps ---
        pdf.cell(col_width, line_height, "Prepared By", border=0)
        pdf.cell(col_width, line_height, "Checked By", border=0, ln=True)
        pdf.ln(10)
        
        pdf.cell(col_width, line_height, f"Date: {receipt_date}", border=0)
        pdf.cell(col_width, line_height, f"Time: {datetime.now().strftime('%H:%M:%S')}", border=0, ln=True)
        pdf.ln(10)

        # --- Final Party Name ---
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(0, 10, party_name, ln=True, align='L')
        
        return bytes(pdf.output(dest='S'))
