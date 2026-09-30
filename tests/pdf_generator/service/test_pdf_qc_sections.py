from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure submodule is loaded for patch to work
import src.slitting_plan.service.slitting_plan_service

with patch('src.slitting_plan.service.slitting_plan_service.SlittingPlanService', MagicMock()):
    from src.pdf_generator.service.pdf_service import PDFService

QC_ROW = {
    "QCStatus": "EXCEPTION",
    "QCExceptions": "No dent",
    "QCExceptionReason": "Customer approved on call",
    "QCSignedByName": "QC Lead",
    "QCSignedBy": "qc@amba.example",
    "QCSignedAt": "14/09/2026 17:05:09",
    "QCFloorCheckedBy": "Ramesh",
}


@pytest.fixture
def pdf_service():
    with patch('src.pdf_generator.service.pdf_service.WeightReceiptService', MagicMock()):
        return PDFService(sales_order_service=MagicMock())


def _pdf(y=100):
    pdf = MagicMock()
    pdf.get_y.return_value = y
    pdf.get_x.return_value = 10
    pdf.h, pdf.w, pdf.b_margin, pdf.l_margin, pdf.r_margin, pdf.t_margin = 297, 210, 20, 10, 10, 10
    pdf.output.return_value = b"%PDF"
    return pdf


def _cell_text(pdf):
    return [c.args[2] for c in pdf.cell.call_args_list if len(c.args) > 2]


def _all_text(pdf):
    calls = pdf.cell.call_args_list + pdf.multi_cell.call_args_list
    return " ".join(str(c.args[2]) for c in calls if len(c.args) > 2)


@pytest.mark.parametrize("job_card, has_core_row", [
    ({"order_type": "CORE_BUILDING"}, True),
    ({"order_type": "LOOSE_STRIPS"}, False),
])
def test_job_card_checklist_prints_core_gap_row_only_for_cores(pdf_service, job_card, has_core_row):
    pdf = _pdf(y=60)
    module = 'src.pdf_generator.service.pdf_service.qc_icons'
    with patch(f'{module}.draw_tick') as tick, patch(f'{module}.draw_cross') as cross:
        pdf_service._draw_job_card_qc_checklist(pdf, job_card)

    text = _cell_text(pdf)
    assert "Material grade & thickness as per job card" in text
    assert "Free of rust" in text
    assert ("No gaps in core" in text) is has_core_row
    assert "Lot 5" in text
    # Lot cells are left blank for pen marks: the tick and cross appear once each, in the legend.
    assert tick.call_count == 1 and cross.call_count == 1
    pdf.add_page.assert_not_called()


def test_job_card_checklist_starts_a_new_page_when_it_does_not_fit(pdf_service):
    pdf = _pdf(y=200)
    pdf_service._draw_job_card_qc_checklist(pdf, {"order_type": "LOOSE_STRIPS"})
    pdf.add_page.assert_called_once()


@pytest.mark.parametrize("qc_fields, expected_line", [
    (QC_ROW, "QC checked by: QC Lead"),
    ({}, None),
])
def test_weight_receipt_pdf_prints_only_the_qc_signer(pdf_service, qc_fields, expected_line):
    pdf = _pdf()
    receipt = {
        "WeightReceiptNumber": "10400",
        "Date": "14/09/2026",
        "JobCardNumber": "JC-1",
        "PartyName": "Party",
        "DesignDetailsWithWeightsJSON": "[]",
        "WeightEntryType": "Loose Strips",
        "Deduction": "0",
        **qc_fields,
    }

    pdf_service._draw_weight_receipt(pdf, receipt)

    qc_lines = [t for t in _cell_text(pdf) if str(t).startswith("QC checked by")]
    assert qc_lines == ([expected_line] if expected_line else [])
    text = _all_text(pdf)
    for private in ("Customer approved on call", "No dent", "Ramesh", "17:05:09"):
        assert private not in text


@patch('src.pdf_generator.service.pdf_service.FPDF')
def test_delivery_challan_lists_qc_signoffs_in_note(mock_fpdf, pdf_service):
    pdf = _pdf()
    mock_fpdf.return_value = pdf
    data = {
        "challan_details": {"to_customer": "Party", "from_company": {"name": "AEL", "address": "Pune"}},
        "items": [],
        "grand_total_weight": 0,
        "receipts": pd.DataFrame(),
        "qc_signoffs": [f"WR {n}: QC checked by: QC Lead" for n in range(10400, 10405)],
    }

    pdf_service.generate_delivery_challan_pdf(data)

    notes = [c.args[2] for c in pdf.multi_cell.call_args_list if len(c.args) > 2 and "QC checked" in str(c.args[2])]
    assert len(notes) == 1
    assert notes[0].splitlines() == [
        "WR 10400: QC checked by: QC Lead",
        "WR 10401: QC checked by: QC Lead",
        "WR 10402: QC checked by: QC Lead",
        "+ 2 more receipts QC signed off",
    ]
