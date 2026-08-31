from datetime import datetime
import io
from typing import List
import pandas as pd
import qrcode
from src.slitting_plan.service.slitting_plan_service import SlittingPlanService
from src.data_entry.service.sales_order_service import SalesOrderService
from src.pdf_generator import hole_layout
from src.data_entry.service.weight_receipt_service import WeightReceiptService
from fpdf import FPDF
import json

class PDFService:
    def __init__(self, sales_order_service: SalesOrderService):
        self.slitting_service = SlittingPlanService()
        self.sales_order_service = sales_order_service
        self.weight_receipt_service = WeightReceiptService()

    def get_sales_orders_for_job_card(self, start_date=None, end_date=None):
        return self.sales_order_service.get_sales_orders_for_job_card(start_date, end_date, include_designs=True)

    def get_available_coils_for_sticker(self, start_date=None, end_date=None) -> pd.DataFrame:
        """Fetches date-filtered available coils and prepares them for sticker printing display."""
        return self.slitting_service.get_available_coils_by_date(start_date=start_date, end_date=end_date)

    def _draw_sticker(self, pdf: FPDF, x: float, y: float, coil: pd.Series):
        """Draws a single sticker's content at the specified (x, y) coordinates."""
        sticker_width = 100.01 # Actual printable width from label spec
        sticker_height = 44.45 # Actual printable height from label spec
        margin = 2 # Internal margin within the sticker

        pdf.rect(x, y, sticker_width, sticker_height) # Re-added border per user request
        
        # 1. Company Name
        pdf.set_xy(x + margin, y + 1)
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(sticker_width - 2 * margin, 4, "Amba Enterprise Limited", align='C')

        # 2. Coil Number (Larger Font)
        pdf.set_xy(x + margin, y + 6)
        pdf.set_font("Helvetica", 'B', 18)
        pdf.multi_cell(sticker_width - 2 * margin, 8, f"{coil['Coil Number']}", align='C')

        # 3. Other Details (Original Font Size)
        qr_size = 22 # Kept original QR size
        pdf.set_xy(x + margin, y + 16)
        pdf.set_font("Helvetica", '', 9)
        details_text = (
            f"Weight: {coil['available_weight']:.2f} kg\n"
            f"Grade: {coil['grade']}\n"
            f"Thk: {coil['thickness']} mm\n"
            f"Width: {int(coil['width'])} mm\n"
            f"Coating: {coil['coating']}\n"
            f"Supplier: {coil['coil_supplier']}"
        )
        pdf.multi_cell(sticker_width - qr_size - (2 * margin), 3.8, details_text)

        # 4. QR Code (Original Data)
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
        
        with io.BytesIO() as qr_bytes:
            img.save(qr_bytes, format='PNG')
            qr_bytes.seek(0)
            pdf.image(qr_bytes, x=qr_x, y=qr_y, w=qr_size, h=qr_size, type='PNG')

    def generate_sticker_pdf(self, selected_coils: pd.DataFrame) -> bytes:
        """Generates a PDF with a 2x6 grid of stickers."""
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=False) # Disable auto page break


        # Definitive layout specifications from user
        sticker_actual_width = 99.8
        sticker_actual_height = 44.15
        margin_horiz = 4.825  # Left Margin
        margin_vert = 7.65   # Top Margin
        gap_horiz = 2        # Horizontal Gap
        gap_vert = 3         # Vertical Gap
        
        num_cols = 2
        
        sticker_count = 0
        for _, coil in selected_coils.iterrows():
            if sticker_count >= 12: # New page after 12 stickers
                pdf.add_page()
                sticker_count = 0

            col = sticker_count % num_cols
            row = sticker_count // num_cols

            # Calculate x and y positions using definitive specs
            x = margin_horiz + (col * (sticker_actual_width + gap_horiz))
            y = margin_vert + (row * (sticker_actual_height + gap_vert))

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
        elif str.lower(hole_type) == "ready entry": # Handle "Ready Entry" by drawing no holes
            pass
        elif (hole_count := hole_layout.parse_hole_count(hole_type)) is not None:
            # Any "<n>-Hole" value, so a new count needs no code change. 3-Hole
            # and 5-Hole still land here and keep their original spacing.
            circle_y = plate_y + plate_height / 2
            counted_radius = hole_layout.hole_radius(hole_count, plate_width)
            pdf.set_line_width(hole_layout.stroke_width(counted_radius))
            for pos in hole_layout.hole_positions(hole_count):
                circle_x = plate_x + plate_width * pos
                pdf.ellipse(
                    circle_x - counted_radius, circle_y - counted_radius,
                    counted_radius * 2, counted_radius * 2, 'D',
                )
        
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

    def _draw_job_card(self, pdf: FPDF, job_card_data: dict, all_used_coils_df: pd.DataFrame):
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
        formatted_order_date = pd.to_datetime(order_date_obj, dayfirst=True).strftime('%d/%m/%Y') if pd.notna(order_date_obj) else 'N/A'
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
        formatted_delivery_date = pd.to_datetime(delivery_date_obj, dayfirst=True).strftime('%d/%m/%Y') if pd.notna(delivery_date_obj) else 'N/A'
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
            description = item.get('fm_name')
            if not description:
                description = f"{item.get('width', 'N/A')} X {item.get('length', 'N/A')}"
            pdf.cell(50, row_height, description, border=1, align='C')
            
            hole_cell_width = 35
            hole_cell_x = pdf.get_x()
            hole_cell_y = pdf.get_y()
            hole_type = item.get('hole', 'Plain')
            self._draw_hole_representation(pdf, hole_cell_x, hole_cell_y, hole_cell_width, row_height, hole_type)
            pdf.rect(hole_cell_x, hole_cell_y, hole_cell_width, row_height)
            pdf.set_x(hole_cell_x + hole_cell_width)

            pdf.cell(30, row_height, "" if item.get('mm_stack') is None else f"{float(item.get('mm_stack')):.2f}", border=1, align='C')
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
        job_card_no = job_card_data['job_card_number']
        
        assigned_coils = []
        if not all_used_coils_df.empty and 'Card No' in all_used_coils_df.columns:
            assigned_coils_for_card = all_used_coils_df[all_used_coils_df['Card No'] == job_card_no]
            assigned_coils = assigned_coils_for_card.to_dict('records')

        if assigned_coils:
            for coil in assigned_coils:
                pdf.cell(100, 8, str(coil.get('Coil No', 'N/A')), border=1, align='C')
                pdf.cell(90, 8, str(coil.get('Weight', 'N/A')), border=1, align='R', ln=True)
        else:
            pdf.cell(190, 8, "Pending Coil Assignment", border=1, align='C', ln=True)

    def generate_job_card_pdf(self, selected_job_cards: List[dict]) -> bytes:
        """Generates a PDF for the selected job cards.""" 
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        all_used_coils_df = self.sales_order_service.get_all_assigned_coils_df()
        for job_card in selected_job_cards:
            self._draw_job_card(pdf, job_card, all_used_coils_df)
        return bytes(pdf.output(dest='S'))

    def generate_delivery_challan_pdf(self, data: dict) -> bytes:
        """Generates a Delivery Challan PDF from a structured dictionary using a hybrid border approach."""
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_font("Helvetica", '', 10)
        
        challan_details = data['challan_details']
        
        # --- Header Section ---
        page_width = pdf.w - 2 * pdf.l_margin
        
        pdf.rect(pdf.l_margin, pdf.t_margin, page_width / 2, 30)
        pdf.set_y(pdf.t_margin + 2)
        pdf.set_x(pdf.l_margin + 2)
        pdf.set_font("Helvetica", 'B', 10)
        pdf.cell(0, 5, "To M/S.:")
        pdf.set_y(pdf.t_margin + 8)
        pdf.set_x(pdf.l_margin + 2)
        pdf.set_font("Helvetica", '', 10)
        pdf.multi_cell(page_width / 2 - 4, 5, challan_details.get('to_customer', ''))

        start_x_from = pdf.l_margin + page_width / 2
        pdf.rect(start_x_from, pdf.t_margin, page_width / 2, 30)
        pdf.set_y(pdf.t_margin + 2)
        pdf.set_x(start_x_from + 2)
        pdf.set_font("Helvetica", 'B', 10)
        pdf.multi_cell(page_width / 2 - 4, 5, challan_details['from_company']['name'])
        pdf.set_y(pdf.t_margin + 8)
        pdf.set_x(start_x_from + 2)
        pdf.set_font("Helvetica", '', 10)
        pdf.multi_cell(page_width / 2 - 4, 5, challan_details['from_company']['address'])

        pdf.set_y(pdf.t_margin + 30)
        pdf.ln(2)

        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(0, 8, "Delivery Challan/ Receipt Inspection Report", border=1, ln=True, align='C')
        
        pdf.set_font("Helvetica", '', 10)
        detail_cell_height = 6
        pdf.cell(page_width / 3, detail_cell_height, f"Challan No: {challan_details.get('challan_no', '')}", border='L')
        pdf.cell(page_width / 3, detail_cell_height, f"Challan Date: {challan_details.get('challan_date', '')}", border='L', align='C')
        pdf.cell(page_width / 3, detail_cell_height, f"Vehicle No: {challan_details.get('vehicle_no', '')}", border='LR', ln=True, align='C')
        
        # --- Table Header ---
        pdf.set_font("Helvetica", 'B', 10)
        pdf.set_fill_color(230, 230, 230)
        header_height = 7
        # Updated Column Widths for new layout
        header_height = 7
        job_no_w = 20
        po_no_w = 25
        gross_w = 22
        deduction_w = 22
        net_w = 22
        particulars_w = page_width - job_no_w - po_no_w - gross_w - deduction_w - net_w
        
        desc_w = particulars_w * 0.65
        remark_w = particulars_w * 0.35

        pdf.cell(job_no_w, header_height, "Job No", border=1, fill=True, align='C')
        pdf.cell(po_no_w, header_height, "P O No", border=1, fill=True, align='C')
        pdf.cell(particulars_w, header_height, "Particulars", border=1, fill=True, align='C')
        pdf.cell(gross_w, header_height, "Gross Wt", border=1, fill=True, align='C')
        pdf.cell(deduction_w, header_height, "Deduction", border=1, fill=True, align='C')
        pdf.cell(net_w, header_height, "Net Wt", border=1, fill=True, align='C', ln=True)

        # --- Table Body ---
        pdf.set_font("Helvetica", '', 10)
        row_height = 7
        
        for item in data.get('items', []):
            if not item.get('line_items'): continue

            # Check for page break before starting a new job block
            num_rows_in_block = len(item['line_items']) + 1
            if pdf.get_y() + (num_rows_in_block * row_height) > (pdf.h - pdf.b_margin - 30):
                pdf.add_page()
                # Redraw table header on new page
                pdf.set_font("Helvetica", 'B', 10)
                pdf.cell(job_no_w, header_height, "Job No", border=1, fill=True, align='C')
                pdf.cell(po_no_w, header_height, "P O No", border=1, fill=True, align='C')
                pdf.cell(particulars_w, header_height, "Particulars", border=1, fill=True, align='C')
                pdf.cell(gross_w, header_height, "Gross Wt", border=1, fill=True, align='C')
                pdf.cell(deduction_w, header_height, "Deduction", border=1, fill=True, align='C')
                pdf.cell(net_w, header_height, "Net Wt", border=1, fill=True, align='C', ln=True)
                pdf.set_font("Helvetica", '', 10)

            # Draw line item rows
            for idx, line_item in enumerate(item['line_items']):
                pdf.set_font("Helvetica", 'B' if idx == 0 else '', 10)
                pdf.cell(job_no_w, row_height, str(item.get('job_no', '')) if idx == 0 else '', border='L', align='C')
                pdf.cell(po_no_w, row_height, str(item.get('po_no', '')) if idx == 0 else '', border='L', align='C')
                
                pdf.set_font("Helvetica", '', 10)
                x_before_p = pdf.get_x()
                
                # Append sets to description if present (for itemized receipts)
                description_text = line_item.get('description', '')
                if line_item.get('sets'):
                     description_text += f" ({line_item.get('sets')} sets)"

                pdf.cell(desc_w, row_height, " " + description_text, border='L', align='L')
                pdf.set_x(x_before_p + desc_w)
                pdf.cell(remark_w, row_height, str(line_item.get('remark', '')) + " ", align='R')
                pdf.set_x(x_before_p + particulars_w)

                weight_str = f"{line_item.get('weight', 0):.2f}" if line_item.get('weight') is not None else ""
                deduction_str = f"{line_item.get('deduction', 0):.2f}" if line_item.get('deduction') is not None and line_item.get('deduction', 0) > 0 else "-"
                net_str = f"{line_item.get('net_weight', 0):.2f}" if line_item.get('net_weight') is not None else ""

                pdf.cell(gross_w, row_height, weight_str, border='L', align='R')
                pdf.cell(deduction_w, row_height, deduction_str, border='L', align='R')
                pdf.cell(net_w, row_height, net_str, border='LR', align='R', ln=True)

            # --- Summary Row for Job ---
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y()) # Manual top border for summary
            pdf.set_font("Helvetica", 'B', 10)
            
            pdf.cell(job_no_w, row_height + 1, "", border='LB') # Slightly larger height
            pdf.cell(po_no_w, row_height + 1, "", border='LB')
            
            summary = item.get('summary', {})
            material_str = str(summary.get('material', ''))
            summary = item.get('summary', {})
            material_str = str(summary.get('material', ''))
            
            # Logic to handle mixed sets or single total sets
            sets_val = summary.get('sets', 0)
            try:
                sets_val_num = float(sets_val)
            except (ValueError, TypeError):
                sets_val_num = 0
                
            set_str = f"Set : {sets_val}" if sets_val_num > 0 else ""

            x_before_s = pdf.get_x()
            pdf.cell(desc_w, row_height + 1, " " + material_str, border='LB', align='L')
            pdf.set_x(x_before_s + desc_w)
            pdf.cell(remark_w, row_height + 1, set_str + " ", border='B', align='R')
            pdf.set_x(x_before_s + particulars_w)

            pdf.cell(gross_w, row_height + 1, f"{summary.get('total_weight', 0):.3f}", border='LB', align='R')
            pdf.cell(deduction_w, row_height + 1, f"{summary.get('total_deduction', 0):.3f}", border='LB', align='R')
            pdf.cell(net_w, row_height + 1, f"{summary.get('net_total_weight', 0):.3f}", border='LBR', align='R', ln=True)
            pdf.set_font("Helvetica", '', 10)

        # --- Table Footer ---
        pdf.ln(5)
        pdf.set_font("Helvetica", 'B', 10)
        total_cell_width = page_width - gross_w - deduction_w - net_w
        
        # Calculate totals from the data passed
        grand_gross = data.get('grand_total_weight', 0)
        grand_deduction = sum(pd.to_numeric(receipt.get('Deduction', 0)) for _, receipt in data.get('receipts', pd.DataFrame()).iterrows())
        grand_net = grand_gross - grand_deduction

        pdf.cell(total_cell_width, row_height, "Total", border=1, align='R')
        pdf.cell(gross_w, row_height, f"{grand_gross:.3f}", border=1, align='R')
        pdf.cell(deduction_w, row_height, f"{grand_deduction:.3f}", border=1, align='R')
        pdf.cell(net_w, row_height, f"{grand_net:.3f}", border=1, align='R', ln=True)
        pdf.ln(5)

        # --- Notes & Signature Section ---
        note_box_height = 60 # Increased height to accommodate spacing and content

        if pdf.get_y() > pdf.h - pdf.b_margin - (note_box_height + 20): # Adjusted page break check
            pdf.add_page()

        note_box_y = pdf.get_y()
        half_page_width = page_width / 2

        # Draw the outer box and the vertical divider
        pdf.rect(pdf.l_margin, note_box_y, page_width, note_box_height)
        pdf.line(pdf.l_margin + half_page_width, note_box_y, pdf.l_margin + half_page_width, note_box_y + note_box_height)

        # --- Left side of the box ---
        pdf.set_font("Helvetica", '', 9)
        current_x = pdf.l_margin + 2
        current_y = note_box_y + 2

        # "Note:"
        pdf.set_xy(current_x, current_y)
        pdf.cell(half_page_width - 4, 5, "Note:")
        current_y = pdf.get_y() + 5 # Advance y by height of "Note:"
        current_y += (5 * 5) # 5 lines space (5mm per line)

        # "E. & O.E."
        pdf.set_xy(current_x, current_y)
        pdf.cell(half_page_width - 4, 5, "E. & O.E.")
        current_y = pdf.get_y() + 5 # Advance y by height of "E. & O.E."

        # "Mentioned product(s)..."
        pdf.set_xy(current_x, current_y)
        pdf.multi_cell(half_page_width - 4, 4, "Mentioned product(s) are received in the good Condition at our side.")
        current_y = pdf.get_y() # Get new Y after multi_cell
        current_y += (2 * 4) # 2 lines space (4mm per line for multi_cell text)


        # Receiver's Signature (bottom of left half)
        final_signature_y = note_box_y + note_box_height - 8 # Anchored to bottom of box

        pdf.set_xy(pdf.l_margin, final_signature_y)
        pdf.cell(half_page_width, 5, "Receiver's Signature", align='C')

        # --- Right side of the box ---
        # For Amba Enterprise Ltd. (bottom of right half)
        pdf.set_xy(pdf.l_margin + half_page_width, final_signature_y)
        pdf.cell(half_page_width, 5, f"For {challan_details['from_company']['name']}", align='C', ln=True)

        # --- Final text below the box ---
        pdf.set_y(note_box_y + note_box_height + 10) # Position below the box with a margin
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(page_width / 2, 6, "Prepared By", align='L')
        pdf.cell(page_width / 2, 6, "Verified By", align='R', ln=True)

        return bytes(pdf.output(dest='S'))

    def _draw_weight_receipt(self, pdf: FPDF, receipt_data: dict, rate: str = 'N/A', po_date=None, material_type: str = None):
        """Draws a single Weight Receipt on the current PDF page.

        Args:
            po_date: PO/order date sourced from the Sales Order-JC sheet. Falls back
                to the receipt date if not supplied (e.g., legacy receipts whose JC
                row no longer exists).
            material_type: Material type sourced from the flat Sales Order sheet.
                Falls back to receipt_data['Material'] when missing.
        """
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15) # Re-enable auto page break for multi-page documents

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
        receipt_date = pd.to_datetime(receipt_date_obj, dayfirst=True).strftime('%d/%m/%Y') if pd.notna(receipt_date_obj) else 'N/A'
        # PO Date comes from the JC's order_date; fall back to the receipt date for legacy/missing JCs.
        po_date_display = pd.to_datetime(po_date, dayfirst=True).strftime('%d/%m/%Y') if pd.notna(po_date) else receipt_date
        card_no = receipt_data.get('JobCardNumber', 'N/A')
        # RN- prefix marks E&I orders, which have no concept of sets — suppress them in the PDF.
        is_rn_series = str(card_no).strip().upper().startswith('RN-')
        
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
        pdf.cell(0, line_height, f": {po_date_display}", border='B,R', ln=True)

        # Line 3: Card No and Job No
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(20, line_height, "Card No", border='L,B')
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(75, line_height, f": {card_no}", border='B,R')
        
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(25, line_height, "Job No", border='B')
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, line_height, f": {job_no}", border='B,R', ln=True)

        # Line 4: Rate
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(20, line_height, "Rate", border='L,B')
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, line_height, f": {rate}", border='B,R', ln=True)
        pdf.ln(10)
        
        # --- Items Table Header ---
        pdf.set_font("Helvetica", 'B', 10)
        pdf.set_fill_color(230, 230, 230)
        
        # New Column Widths
        sr_no_w = 15
        desc_w = 80
        gross_w = 30
        deduction_w = 30
        net_w = 35
        
        pdf.cell(sr_no_w, 8, "Sr No", border=1, fill=True, align='C')
        pdf.cell(desc_w, 8, "Description", border=1, fill=True, align='C')
        pdf.cell(gross_w, 8, "Gross Wt", border=1, fill=True, align='C')
        pdf.cell(deduction_w, 8, "Deduction", border=1, fill=True, align='C')
        pdf.cell(net_w, 8, "Net Wt", border=1, fill=True, align='C', ln=True)

        # --- Items Table Rows ---
        pdf.set_font("Helvetica", '', 10)
        total_weight = 0
        row_height = 8 # Use a consistent row height

        # Match "Building Core", "Building Core (Manual)", etc.
        is_core_building = 'Building Core' in str(receipt_data.get('WeightEntryType', ''))
        core_receipt_remark = ""
        if is_core_building and designs:
            core_receipt_remark = designs[0].get('remark', '')

        if is_core_building:
            total_weight = float(receipt_data.get('TotalWeight', 0))
            # Core Building Logic: Show values only on last row? Or if it's a group, show total on last and - on others.
            # But the 'TotalWeight' is the gross weight. 
            # Deduction is 'Deduction'.
            total_deduction = float(receipt_data.get('Deduction', 0.0))
            total_net = total_weight - total_deduction
            
            num_items = len(designs) if designs else 0
            
            for i, item in enumerate(designs):
                is_last = (i == num_items - 1)
                start_y = pdf.get_y()
                pdf.cell(sr_no_w, row_height, str(i + 1), border=1, align='C')
                
                desc_x = pdf.get_x()
                description = f"{item.get('width', '')} X {item.get('length', '')}"
                if item.get('mm_stack'):
                    description += f" X {float(item.get('mm_stack')):.2f}"
                
                # Use multi_cell for description but manage positioning manually
                pdf.multi_cell(desc_w, row_height, description, border=1, align='C', ln=1)
                
                # Manually set position for the next cell
                pdf.set_xy(desc_x + desc_w, start_y)
                
                if is_last:
                    pdf.cell(gross_w, row_height, f"{total_weight:.3f}", border=1, align='R')
                    pdf.cell(deduction_w, row_height, f"{total_deduction:.3f}" if total_deduction > 0 else "-", border=1, align='R')
                    pdf.cell(net_w, row_height, f"{total_net:.3f}", border=1, align='R', ln=True)
                else:
                    pdf.cell(gross_w, row_height, "", border=1, align='R')
                    pdf.cell(deduction_w, row_height, "", border=1, align='R')
                    pdf.cell(net_w, row_height, "", border=1, align='R', ln=True)

        else: # Loose strips or legacy
            # Check if total deduction is used or per-design
            receipt_deduction = float(receipt_data.get('Deduction', 0.0))
            sum_design_deductions = sum(float(d.get('design_deduction', 0.0)) for d in designs)
            
            # Logic Update:
            # If we have explicit design deductions (sum > 0), use them as the source of truth.
            # This handles cases where stored total might be 0 or stale.
            # Otherwise, fall back to the stored receipt_deduction (Legacy behavior).
            use_per_design_deduction = (sum_design_deductions > 0)
            
            # If using per-design, update the total deduction to match the sum (fix footer math)
            if use_per_design_deduction:
                receipt_deduction = sum_design_deductions
            
            for i, item in enumerate(designs):
                start_y = pdf.get_y()
                pdf.cell(sr_no_w, row_height, str(i + 1), border=1, align='C')
                
                desc_x = pdf.get_x()
                description = f"{item.get('width', '')} X {item.get('length', '')}"
                if item.get('mm_stack'):
                    description += f" X {float(item.get('mm_stack')):.2f}"
                
                # Show sets if present (Itemized Mode); suppress for RN- (E&I) job cards.
                if item.get('sets') and not is_rn_series:
                    description += f" ({item.get('sets')} sets)"
                
                item_remark = item.get('remark', '')
                if item_remark:
                    # Use a second line for remark instead of multi_cell to control height
                    pdf.cell(desc_w, row_height / 2, description, border='LRT', align='C', ln=2) # Go to next line
                    pdf.set_x(desc_x)
                    pdf.cell(desc_w, row_height / 2, item_remark, border='LRB', align='C')
                else:
                    pdf.cell(desc_w, row_height, description, border=1, align='C')

                weight = float(item.get('actual_weight') or 0)
                total_weight += weight
                
                d_deduction = float(item.get('design_deduction', 0.0)) if use_per_design_deduction else 0.0
                net_weight = weight - d_deduction

                pdf.set_xy(desc_x + desc_w, start_y)
                pdf.cell(gross_w, row_height, f"{weight:.3f}" if weight > 0 else "", border=1, align='R')
                
                ded_str = f"{d_deduction:.3f}" if (d_deduction > 0 and use_per_design_deduction) else "-"
                pdf.cell(deduction_w, row_height, ded_str, border=1, align='R')
                
                pdf.cell(net_w, row_height, f"{net_weight:.3f}" if weight > 0 else "", border=1, align='R', ln=True)

        # --- Table Footer ---
        # Type / Set / Rem each get their own line, stacked inside the Description
        # column. Avoids overflow when any one value (e.g. 'CRNO EI TRD' type or a
        # long remark) is wider than its previous narrow sub-cell.
        pdf.set_font("Helvetica", '', 10)

        row_h = 5
        footer_h = row_h * 3

        type_value = (material_type if material_type else None) or receipt_data.get('Material') or 'N/A'
        type_text = f"Type: {type_value}"
        set_text = "" if is_rn_series else f"Set: {receipt_data.get('Sets', 'N/A')}"
        remark_text = f"Rem: {core_receipt_remark}" if is_core_building and core_receipt_remark else ""

        y0 = pdf.get_y()
        x0 = pdf.get_x()

        # Sr No (empty, spans full footer height)
        pdf.cell(sr_no_w, footer_h, '', border='LTB')
        x_desc = x0 + sr_no_w

        # Three stacked lines in the Description column. Borders only on outer
        # edges (T on first row, B on last) so the footer reads as a single box.
        pdf.set_xy(x_desc, y0)
        pdf.cell(desc_w, row_h, type_text, border='T', align='L')
        pdf.set_xy(x_desc, y0 + row_h)
        pdf.cell(desc_w, row_h, set_text, border=0, align='L')
        pdf.set_xy(x_desc, y0 + 2 * row_h)
        pdf.cell(desc_w, row_h, remark_text, border='B', align='L')

        pdf.set_xy(x_desc + desc_w, y0)

        # Totals
        pdf.set_font("Helvetica", 'B', 10)

        # Recalculate based on the logic above
        if not is_core_building and sum_design_deductions > 0:
             final_deduction = sum_design_deductions
        else:
             final_deduction = float(receipt_data.get('Deduction', 0.0))

        net_weight = total_weight - final_deduction

        pdf.cell(gross_w, footer_h, f"{total_weight:.3f}", border=1, align='R')
        pdf.cell(deduction_w, footer_h, f"{final_deduction:.3f}", border=1, align='R')
        pdf.cell(net_w, footer_h, f"{net_weight:.3f}", border=1, align='R', ln=True)
        pdf.ln(2)

        # --- Details below table ---
        pdf.set_font("Helvetica", '', 12)
        col_width = 95
        line_height = 8
        deduction = float(receipt_data.get('Deduction', 0.0))
        net_weight = total_weight - deduction
        # Line 2: Deduction, Net
        # Line 2: Removed as it's now in the table footer
        # pdf.cell(col_width, line_height, f"Deduction : {deduction:.2f}", border=0)
        # pdf.cell(col_width, line_height, f"Net : {net_weight:.2f}", border=0, ln=True)
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
        
    def generate_weight_receipt_pdf(self, selected_receipts: List[dict]) -> bytes:
        """Generates a PDF for the selected weight receipts."""
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        sales_orders = self.sales_order_service.get_sales_orders_for_job_card(include_designs=False)
        sales_order_rates = {so.get('job_card_number'): so.get('rate_per_kg', 'N/A') for so in sales_orders if so.get('job_card_number')}
        sales_order_po_dates = {so.get('job_card_number'): so.get('order_date') for so in sales_orders if so.get('job_card_number')}
        # Built once per PDF generation; used as a fallback for legacy receipts whose Material column is missing/N/A.
        material_type_map = self.weight_receipt_service.get_job_card_material_type_map()
        for receipt_data in selected_receipts:
            jc = receipt_data.get('JobCardNumber')
            rate = sales_order_rates.get(jc, 'N/A')
            po_date = sales_order_po_dates.get(jc)
            material_type = material_type_map.get(str(jc).strip().lower(), '') if jc else ''
            self._draw_weight_receipt(pdf, receipt_data, rate, po_date=po_date, material_type=material_type)
        return bytes(pdf.output(dest='S'))
