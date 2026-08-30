import pytest

from app.services.ops_audit.rf_form_names import rf_form_display_name


@pytest.mark.parametrize(
    ("rf_table", "expected"),
    [
        ("RF_HY_EnvironmentHumidity", "环境湿度校准记录表（半年）"),
        ("MONTH_FLOW_CHECK_REPORT", "月流量检查报告"),
        ("TWOWEEK_PM_FLOW_CHECK_REPORT", "两周颗粒物流量检查报告"),
        ("MULTIPOINT_CALIBRATION_CURVE", "多点校准曲线图"),
        ("O3_VALUE_PASS_REPORT", "O3动态校准仪量值传递报告"),
        ("PREVENTIVE_MAINTENANCE_REPORT", "预防性维护报告"),
        ("MONTH_STATION_MAINTAIN_PHOTOS", "站点设备维护现场照片"),
        ("VISIBILITY_CALIBRATION_EVIDENCE", "能见度校准记录附件"),
    ],
)
def test_rf_form_display_name_covers_rf_and_attachment_requirements(rf_table, expected):
    assert rf_form_display_name(rf_table) == expected
