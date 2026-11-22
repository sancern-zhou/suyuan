"""浓度告警规则配置（判据修订版）。

依据《空气质量浓度数据告警规则体系（判据修订）》规则总表：

- 范围：PM2.5 / PM10 / SO2 / NO2 / CO 共 5 个污染物、6 个污染等级、
  3 类规则（单点突升 DS / 连续抬升 CL / 站点离群 OL），共 90 条；
- O3 暂不纳入告警；限值突破（R1）不保留；
- 触发式：Δ >= MAX(基线 × 比例阈值, 绝对增量阈值)；
- 不再输出告警级别，只输出规则类型 + 当前污染等级。

阈值矩阵的键是污染物 → 规则类型 → 污染等级，值是（比例阈值，绝对增量）。
绝对增量单位与浓度一致：CO 为 mg/m³，其余为 μg/m³。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

POLLUTANTS = ("PM2.5", "PM10", "SO2", "NO2", "CO")
FIVE_MIN_POLLUTANTS = ("PM10", "SO2", "NO2", "CO")

# 污染等级（与 HJ 633—2026 实时报口径一致，1 最清洁、6 最严重）。
LEVEL_NAMES = {
    1: "优",
    2: "良",
    3: "轻度污染",
    4: "中度污染",
    5: "重度污染",
    6: "严重污染",
}
LEVEL_CODES = {name: code for code, name in LEVEL_NAMES.items()}
LEVEL_ALIASES = {
    "优": "优",
    "良": "良",
    "轻度": "轻度污染",
    "中度": "中度污染",
    "重度": "重度污染",
    "严重": "严重污染",
}
RULE_LABELS = {
    "multi_station_rise": "多站同步抬升",
    "sudden_rise": "单点突升",
    "continuous_rise": "连续抬升",
    "spatial_outlier": "站点离群",
}
# MR 优先级最高：多站同步抬升触发时覆盖涉事站点的单站告警。
RULE_PRIORITY = {"multi_station_rise": 0, "sudden_rise": 1, "continuous_rise": 2, "spatial_outlier": 3}
POLLUTANT_ORDER = {"PM2.5": 0, "PM10": 1, "SO2": 2, "NO2": 3, "CO": 4}

# 规则总表（判据修订）逐条转写；等级顺序：优、良、轻度、中度、重度、严重。
# 值 = (突升比例阈值, 绝对值阈值)；绝对值是“增量”，不是当前浓度下限。
RULE_MATRIX: dict[str, dict[str, dict[str, tuple[float, float]]]] = {
    "PM2.5": {
        "sudden_rise": {
            "优": (0.40, 6), "良": (0.30, 8), "轻度污染": (0.25, 10),
            "中度污染": (0.20, 30), "重度污染": (0.20, 40), "严重污染": (0.20, 40),
        },
        "continuous_rise": {
            "优": (0.60, 10), "良": (0.50, 18), "轻度污染": (0.40, 25),
            "中度污染": (0.30, 30), "重度污染": (0.25, 35), "严重污染": (0.20, 40),
        },
        "spatial_outlier": {
            "优": (0.50, 8), "良": (0.40, 12), "轻度污染": (0.35, 18),
            "中度污染": (0.30, 25), "重度污染": (0.25, 35), "严重污染": (0.20, 45),
        },
    },
    "PM10": {
        "sudden_rise": {
            "优": (0.40, 10), "良": (0.30, 15), "轻度污染": (0.25, 20),
            "中度污染": (0.20, 45), "重度污染": (0.20, 60), "严重污染": (0.20, 60),
        },
        "continuous_rise": {
            "优": (0.60, 18), "良": (0.50, 25), "轻度污染": (0.40, 40),
            "中度污染": (0.30, 50), "重度污染": (0.25, 60), "严重污染": (0.20, 70),
        },
        "spatial_outlier": {
            "优": (0.50, 12), "良": (0.40, 20), "轻度污染": (0.35, 30),
            "中度污染": (0.30, 40), "重度污染": (0.25, 55), "严重污染": (0.20, 70),
        },
    },
    "SO2": {
        "sudden_rise": {
            "优": (0.50, 7), "良": (0.30, 10), "轻度污染": (0.25, 15),
            "中度污染": (0.20, 40), "重度污染": (0.20, 60), "严重污染": (0.20, 80),
        },
        "continuous_rise": {
            "优": (0.80, 12), "良": (0.50, 20), "轻度污染": (0.40, 30),
            "中度污染": (0.30, 45), "重度污染": (0.25, 60), "严重污染": (0.20, 80),
        },
        "spatial_outlier": {
            "优": (0.60, 8), "良": (0.50, 12), "轻度污染": (0.40, 20),
            "中度污染": (0.30, 30), "重度污染": (0.25, 45), "严重污染": (0.20, 60),
        },
    },
    "NO2": {
        "sudden_rise": {
            "优": (0.50, 10), "良": (0.30, 12), "轻度污染": (0.25, 18),
            "中度污染": (0.20, 30), "重度污染": (0.20, 45), "严重污染": (0.20, 60),
        },
        "continuous_rise": {
            "优": (0.80, 20), "良": (0.60, 22), "轻度污染": (0.40, 28),
            "中度污染": (0.30, 35), "重度污染": (0.25, 50), "严重污染": (0.20, 70),
        },
        "spatial_outlier": {
            "优": (0.60, 10), "良": (0.50, 15), "轻度污染": (0.40, 20),
            "中度污染": (0.30, 30), "重度污染": (0.25, 45), "严重污染": (0.20, 60),
        },
    },
    "CO": {
        "sudden_rise": {
            "优": (0.40, 0.3), "良": (0.30, 0.4), "轻度污染": (0.25, 0.6),
            "中度污染": (0.20, 1.0), "重度污染": (0.20, 1.5), "严重污染": (0.20, 2.0),
        },
        "continuous_rise": {
            "优": (0.60, 0.4), "良": (0.50, 0.6), "轻度污染": (0.40, 0.9),
            "中度污染": (0.30, 1.2), "重度污染": (0.25, 1.8), "严重污染": (0.20, 2.4),
        },
        "spatial_outlier": {
            "优": (0.60, 0.3), "良": (0.50, 0.4), "轻度污染": (0.40, 0.6),
            "中度污染": (0.30, 1.0), "重度污染": (0.25, 1.5), "严重污染": (0.20, 2.0),
        },
    },
}

# 冷却期按规则类型 + 因子分组：PM2.5 单独一档，其余四因子共用一档。
COOLDOWN_MINUTES: dict[str, dict[str, int]] = {
    "multi_station_rise": {"PM2.5": 120, "default": 60},
    "sudden_rise": {"PM2.5": 60, "default": 30},
    "continuous_rise": {"PM2.5": 120, "default": 60},
    "spatial_outlier": {"PM2.5": 60, "default": 30},
}


def normalize_level(level_name: str | None) -> str:
    """把“轻度/轻度污染”等写法统一到规则矩阵的键。"""
    if not level_name:
        return "良"
    return LEVEL_ALIASES.get(str(level_name), str(level_name))


@dataclass
class AirAlertRuleConfig:
    """全部可调参数；字段名即 JSON 覆盖文件中的键名。"""

    city: str = "许昌市"

    # 多站同步抬升（MR，2026-11-20 新增；回测 11-13~11-18 定参）：
    # - 路径 A（共升）：同槽 >=mr_min_sites 站各自 rise >= mr_amplitude_ratio × 自身
    #   DS 阈值且 >= 绝对下限（mr_absolute_floor）；CL 窗口累计抬升达
    #   mr_amplitude_ratio × 自身 CL 阈值亦可入站（渐升型共升，2026-11-22
    #   定版：3 小时爬坡的站末跳普遍不足 DS 半阈值，仅按单小时口径收站
    #   会漏掉区域性同步抬升，如 11-22 22:00 市一中/芙蓉广场案例）；
    # - 路径 B（共偏）：OL 触发站 wz < mr_wz_max（Iglewicz–Hoaglin modified
    #   z-score）且存在 >=1 个伴生站正向偏离 >= mr_companion_ratio × 自身 OL 阈值；
    # - 反弹守卫：基线当日分位 < mr_rebound_pct 时，要求抬升后进六站中位数以上
    #   或幅度 >= 全阈值；
    # - 物理上限（mr_plausibility_cap）：任一站超限视为平台数据故障，本槽不判 MR；
    # - 档位：全部涉事站 优 且主站幅度 < 全阈值 → digest（不推送，进摘要口径）；
    # - MR 触发时覆盖涉事站点的单站 DS/CL/OL 候选（suppressed，流水指回 MR）。
    mr_enabled: bool = True
    mr_min_sites: int = 2
    mr_amplitude_ratio: float = 0.5
    mr_absolute_floor: dict[str, float] = field(default_factory=lambda: {
        "PM2.5": 3.0, "PM10": 3.0, "SO2": 3.0, "NO2": 3.0, "CO": 0.1,
    })
    mr_rebound_pct: float = 30.0
    mr_companion_ratio: float = 0.5
    mr_wz_max: float = 3.5
    mr_plausibility_cap: dict[str, float] = field(default_factory=lambda: {
        "PM2.5": 800.0, "PM10": 1000.0, "SO2": 800.0, "NO2": 500.0, "CO": 10.0,
    })
    # MR 免打扰等级穿透（2026-11-22 定版）：MR 是区域过程事件，夜间静默会
    # 造成"区域事件静默、未覆盖单站照常外发"的口径倒挂（11-22 22:00 实例）。
    # 涉事主站污染等级码 >= 此值的 MR 穿透免打扰正常推送；置 0 关闭穿透。
    # spatial_outlier 不受影响，夜间维持静默。
    mr_quiet_pierce_level_code: int = 3

    # 90 条规则矩阵：污染物 → 规则类型 → 污染等级 → (比例, 绝对增量)。
    rule_matrix: dict[str, dict[str, dict[str, tuple[float, float]]]] = field(
        default_factory=lambda: json.loads(json.dumps(RULE_MATRIX))
    )
    cooldown_minutes: dict[str, dict[str, int]] = field(
        default_factory=lambda: json.loads(json.dumps(COOLDOWN_MINUTES))
    )
    rule_priority: dict[str, int] = field(default_factory=lambda: dict(RULE_PRIORITY))

    # 站点离群：全市 6 个国控站，有效站最少 4 个；对比时剔除本站。
    min_region_stations: int = 4
    # 单点突升“邻站未同向”：同污染物同窗口下，其余站中至少 N 个也达到
    # 各自 DS 阈值即视为区域同向，不判单点突升。
    neighbor_same_direction_count: int = 2
    # 连续抬升：3 段单调不减，且每段增量 >= 总增量的 15%。
    cl_segment_min_share: float = 0.15
    # 连续抬升区域合并：同污染物同窗口 >=N 个站点命中 CL 时，只推累计抬升
    # 最大的站点一条，其余站点以 regional_merge 抑制入库（0 = 不合并）。
    cl_region_merge_sites: int = 4
    # 单点突升区域合并（2026-11-18 缝隙修复）：同污染物同窗口 >=N 个站点
    # 命中 DS 时，只推跳变增量最大的站点一条，其余站点以 regional_merge
    # 抑制入库（0 = 不合并）。默认 2：恰好 2 站同窗口双命中时，彼此的
    # "邻站同向"抑制（neighbor_same_direction_count=2）都不到门槛，会推出
    # 两条互相矛盾的"单点突升"，由本合并收口为一条区域通报；>=3 站命中
    # 时引擎层已按区域同向全部抑制，合并层实际只会见到恰好 2 站的场景。
    ds_region_merge_sites: int = 2
    # 单点突升 DS 附加条件（需求方补充，2026-11-13）：告警时段浓度需高于
    # 同组其余站点剔除极值（去最高/最低）后的均值；对照站少于 N 个时无法
    # 剔除极值，该条件不启用（不拦截告警）。下限 3。
    ds_peer_trim_min_peers: int = 3

    # PM2.5 只有小时值：DS 基线取前一小时；CL 基线取抬升起点前一小时。
    pm25_ds_baseline_hours: int = 1
    pm25_cl_baseline_hours: int = 1

    # 恢复防抖（沿用既有推送链，不属于规则总表）。
    recover_ratio: float = 0.90
    recover_periods: int = 3
    # 滞回心跳（2026-11-20 运营层决议）：未恢复但距上次推送已满一个冷却
    # 窗口时强制再报一条"持续提醒"，避免同一过程长时间静默。窗口值直接
    # 沿用冷却期查表；置 False 可整体关闭（回到无上限滞回抑制）。
    hysteresis_renotify: bool = True

    # OL 长期系统性偏差：按站点×因子独立识别，不抬高全局阈值。近 7 天
    # >=6 次且覆盖 >=3 个自然日后转摘要口径；等级升级或偏差 >= 历史典型
    # 幅度 1.5 倍时穿透；连续 2 个无 OL 命中的自然日后退出。
    ol_chronic_enabled: bool = True
    ol_chronic_lookback_days: int = 7
    ol_chronic_min_events: int = 6
    ol_chronic_min_days: int = 3
    ol_chronic_escalation_ratio: float = 1.5
    ol_chronic_recovery_days: int = 2

    # 运营限额与免打扰（规则总表未定义；按规则类型执行，见下方方法）。
    site_daily_quota: int = 8
    global_daily_cap: int = 40
    quiet_hours_start: int = 22
    quiet_hours_end: int = 6
    quiet_suppress_rules: tuple[str, ...] = ("spatial_outlier", "multi_station_rise")

    def thresholds(self, pollutant: str, rule_type: str, level_name: str | None) -> tuple[float, float]:
        """返回 (比例阈值, 绝对增量阈值)。"""
        level = normalize_level(level_name)
        return tuple(self.rule_matrix[pollutant][rule_type][level])  # type: ignore[return-value]

    def cooldown_for(self, rule_type: str, pollutant: str) -> int:
        group = "PM2.5" if pollutant == "PM2.5" else "default"
        return int((self.cooldown_minutes.get(rule_type) or {}).get(group, 0))

    def in_quiet_hours(self, hour: int) -> bool:
        start, end = self.quiet_hours_start, self.quiet_hours_end
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end

    def quiet_suppresses(self, rule_type: str) -> bool:
        return rule_type in self.quiet_suppress_rules


CONFIG_FILE_ENV = "XUCHANG_AIR_ALERT_CONFIG"
CONFIG_FILE_NAME = "air_alert_config.json"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def load_air_alert_config(output_root: Path | None = None) -> AirAlertRuleConfig:
    """加载配置：默认值即规则总表；存在 JSON 覆盖文件时按键深合并。

    覆盖文件路径优先取环境变量 XUCHANG_AIR_ALERT_CONFIG，否则使用数据登记
    目录下的 air_alert_config.json。文件缺失不是错误。
    """
    config = AirAlertRuleConfig()
    candidates = []
    env_path = os.getenv(CONFIG_FILE_ENV)
    if env_path:
        candidates.append(Path(env_path))
    if output_root is not None:
        candidates.append(Path(output_root) / CONFIG_FILE_NAME)
    for path in candidates:
        try:
            overrides = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            continue
        if not isinstance(overrides, dict):
            continue
        payload = config.__dict__
        for key, value in overrides.items():
            if key not in payload:
                continue
            current = payload[key]
            if isinstance(current, dict) and isinstance(value, dict):
                _deep_merge(current, value)
            elif isinstance(current, tuple) and isinstance(value, list):
                setattr(config, key, tuple(value))
            else:
                setattr(config, key, value)
        break
    return config
