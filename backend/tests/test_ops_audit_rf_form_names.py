from app.services.ops_audit.rf_form_names import rf_form_display_name


def test_environment_humidity_form_has_chinese_display_name():
    assert rf_form_display_name("RF_HY_EnvironmentHumidity") == "环境湿度校准记录表（半年）"
