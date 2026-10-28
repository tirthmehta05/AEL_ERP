import threading
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.data_entry.service.sales_order_service import SalesOrderService


def _service(sheets):
    svc = SalesOrderService("id", "secret", "tenant")
    svc.google_service = MagicMock()
    svc.google_service.get_worksheet_data.side_effect = (
        lambda _sid, name, **kw: sheets[name].copy()
    )
    return svc


def test_job_card_number_considers_jc_sheet():
    # N-6993 was already written to Sales Order-JC but not yet to Sales Order.
    svc = _service({
        "Sales Order": pd.DataFrame({"Job Card": ["N-6992", "RN-1500"]}),
        "Sales Order-JC": pd.DataFrame({"job_card_number": ["N-6992", "N-6993"]}),
    })
    assert svc.generate_sequential_job_card_number("CRNO TL") == "N-6994"


def test_job_card_number_starts_at_one_for_new_prefix():
    svc = _service({
        "Sales Order": pd.DataFrame({"Job Card": ["N-5"]}),
        "Sales Order-JC": pd.DataFrame(),
    })
    assert svc.generate_sequential_job_card_number("CRGO TL") == "G-1"


def test_job_card_number_raises_on_read_failure():
    svc = SalesOrderService("id", "secret", "tenant")
    svc.google_service = MagicMock()
    svc.google_service.get_worksheet_data.side_effect = RuntimeError("rate limit")
    with pytest.raises(RuntimeError):
        svc.generate_sequential_job_card_number("CRNO TL")


def test_save_sales_order_is_serialized():
    svc = _service({})
    inside, overlap = [0], []

    def fake(_request):
        inside[0] += 1
        overlap.append(inside[0])
        threading.Event().wait(0.05)
        inside[0] -= 1
        return True

    svc._save_sales_order_locked = fake
    threads = [threading.Thread(target=svc.save_sales_order, args=(None,)) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert max(overlap) == 1
