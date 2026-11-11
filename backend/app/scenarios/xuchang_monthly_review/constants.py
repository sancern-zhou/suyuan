"""①月度特征分析口径常量。"""

EVENT_TYPE = "xuchang.monthly_review.completed"
REPORT_ROLES = ("局长", "科长")
MESSAGE_TITLE = "【月度特征分析】"

EVIDENCE_SCHEMA_VERSION = "xuchang_monthly_review/v1"

# 六参数（SsfbCityDay 列名 → 展示名），CO 单位 mg/m³，其余 μg/m³
MONTH_FACTORS = ("PM25", "PM10", "O3", "NO2", "SO2", "CO")
FACTOR_LABELS = {
    "PM25": "PM2.5", "PM10": "PM10", "O3": "O3",
    "NO2": "NO2", "SO2": "SO2", "CO": "CO",
}

# 站点告警月度统计的 episode_state.json 兜底路径（相对 data registry）
EPISODE_STATE_RELATIVE_PATH = "xuchang_station_deviation_alerts/episode_state.json"
