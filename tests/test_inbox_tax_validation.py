"""Separate VAT can explain a difference only with a complete, matching tax basis."""

import pytest
from inbox.store import normalize, validate


def receipt(lines, total, vat):
    return normalize(
        dict(
            store="Example",
            date="2026-09-06",
            currency="USD",
            total=total,
            lines=[dict(name="Service", amount=n) for n in lines],
            vat=vat,
        )
    )


def test_net_amount_and_separate_vat():
    result = validate(receipt([100], 125, [dict(rate=25, base=100, tax=25)]))
    assert "line_total_difference" not in result["issues"]
    assert result["reconciliation"] == "lines_plus_tax"
    assert result["line_sum_minor"] == 10000
    assert result["raw_line_difference_minor"] == -2500
    assert result["tax_sum_minor"] == 2500
    assert result["difference_minor"] == 0


def test_gross_lines_do_not_add_tax_twice():
    result = validate(receipt([109, 50], 159, [dict(rate=25, base=87.2, tax=21.8), dict(rate=0, base=50, tax=0)]))
    assert result["reconciliation"] == "lines"
    assert result["difference_minor"] == 0
    assert result["tax_sum_minor"] is None


@pytest.mark.parametrize(
    "vat",
    [
        [dict(rate=25, base=None, tax=25)],
        [dict(rate=None, base=100, tax=25)],
        [dict(rate=25, base=80, tax=25)],
        [dict(rate=20, base=100, tax=25)],
        [dict(rate=25, base=100, tax=24)],
        [dict(rate=25, base=100, tax=25), dict(rate=0, base=None, tax=0)],
        [dict(rate="NaN", base=100, tax=25)],
    ],
)
def test_tax_does_not_hide_unexplained_difference(vat):
    result = validate(receipt([100], 125, vat))
    assert "line_total_difference" in result["issues"]
    assert result["difference_minor"] == -2500
    assert result["reconciliation"] is None


def test_net_refund_and_multiple_rates():
    result = validate(
        receipt([-100, -100], -240, [dict(rate=25, base=-100, tax=-25), dict(rate=15, base=-100, tax=-15)])
    )
    assert result["reconciliation"] == "lines_plus_tax"
    assert result["difference_minor"] == 0
