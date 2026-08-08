import pytest

from app.services.tenders.extractor import amount_to_wan_yuan


@pytest.mark.parametrize(
    ("raw_amount", "expected"),
    [
        ("5600000元", 560.0),
        ("560万元", 560.0),
        ("1.47亿元", 14700.0),
        ("2377万元", 2377.0),
        ("5600000", 560.0),
        ("2377", 2377.0),
        ("332.56万元,318.00万元,298.316万元", 948.876),
    ],
)
def test_amount_to_wan_yuan_normalizes_common_units(raw_amount, expected):
    assert amount_to_wan_yuan(raw_amount) == expected
