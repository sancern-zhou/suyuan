"""④污染原因分析触发口径与事件类型常量。"""

EVENT_TYPE = "xuchang.pollution_cause_analysis.triggered"

# 对比城市口径：地理相邻五市（用户 2026-11 定版）。SsfbCityDay 的 City 列
# 存平台规范名（带"市"后缀，济源示范区已归一为济源市）。
XUCHANG_CITY = "许昌市"
NEIGHBOR_CITIES = ("郑州市", "开封市", "平顶山市", "漯河市", "周口市")

# 触发规则：许昌 PM2.5 日均 > 相邻五市均值 × (1 + 20%)
TRIGGER_RATIO_THRESHOLD = 0.20

EVIDENCE_SCHEMA_VERSION = "xuchang_pollution_cause_trigger/v1"
WECHAT_MESSAGE_PREFIX = "【污染原因分析】"

# 连续触发天数回看的证据文件窗口（天），避免长期缺文件时无限扫描
STREAK_LOOKBACK_DAYS = 7
