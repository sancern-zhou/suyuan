"""阈值与推送管控配置（分级告警 R1-R4 + M 链）。

对应《空气质量数据告警推送系统——算法需求文档》V1.0 的配置驱动要求
（§2.3、§14 配置参数总表）：全部阈值、比例、窗口、冷却期都在
AirAlertRuleConfig 中，代码不出现魔法数。默认值与文档 §14 一致；
部署可通过 JSON 文件覆盖任意子集（见 load_air_alert_config）。

限值版本表（cfg_limit）支持生效区间：过渡版 2026-03-01 起、
正式版 2031-01-01 起（文档 §4.2 仅明确 PM10 良档 100、PM2.5 良档 50，
其余档次按同比例 5/6 下收，与这两档精确一致）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# R1 分档阈值表（GB 3095—2026 过渡阶段，文档 §4.2）。
RULE_LIMIT_TIERS_2026: dict[str, dict[str, float]] = {
    "PM10": {"良": 120, "轻度": 150, "中度": 200, "重度及以上": 250},
    "PM2.5": {"良": 60, "轻度": 75, "中度": 115, "重度及以上": 150},
    "SO2": {"良": 150, "轻度": 250, "中度": 400, "重度及以上": 500},
    "NO2": {"良": 80, "轻度": 120, "中度": 180, "重度及以上": 200},
    "O3": {"良": 160, "轻度": 200, "中度": 240, "重度及以上": 300},
    "CO": {"良": 4, "轻度": 6, "中度": 8, "重度及以上": 10},
}
# 1 小时国标限值（文档 §4.2 最后一列；PM10/PM2.5 小时值无 1h 限值）。
RULE_LIMIT_1H: dict[str, float] = {"SO2": 500, "NO2": 200, "O3": 200, "CO": 10}


def _scaled_tiers(base: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    return {p: {k: round(v * 5 / 6, 1) for k, v in bins.items()} for p, bins in base.items()}


RULE_LIMIT_VERSIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "GB3095-2026过渡版",
        "effective_from": "2026-03-01",
        "tiers": RULE_LIMIT_TIERS_2026,
        "limit_1h": RULE_LIMIT_1H,
    },
    {
        "name": "GB3095正式版",
        "effective_from": "2031-01-01",
        "tiers": _scaled_tiers(RULE_LIMIT_TIERS_2026),
        "limit_1h": RULE_LIMIT_1H,
    },
)


@dataclass
class AirAlertRuleConfig:
    """分级告警全部可调参数；字段名即 JSON 覆盖文件中的键名。"""

    city: str = "许昌市"

    # 基线（§3.1）：最近 12 个 5 分钟有效值取中位数，有效值 <8 跳过相对规则。
    baseline_window: int = 12
    baseline_min_valid: int = 8
    # PM2.5 小时版基线（§8）：前 3 小时有效值中位数，<2 跳过。
    pm25_baseline_window: int = 3
    pm25_baseline_min_valid: int = 2

    # R1（§4）：二级/一级倍率与限值版本表。
    r1_secondary_multiple: float = 1.2
    r1_primary_multiple: float = 1.5
    limit_versions: tuple[dict[str, Any], ...] = field(default_factory=lambda: RULE_LIMIT_VERSIONS)

    # R2（§5）：基础抬升比例（三/二/一级）、等级修正、确认周期、绝对底线。
    r2_ratios: dict[int, float] = field(default_factory=lambda: {3: 0.30, 2: 0.50, 1: 1.00})
    r2_level_adjust_good: float = 0.10
    r2_level_adjust_heavy: float = -0.10
    r2_min_ratio: float = 0.10
    r2_confirm_periods: int = 2
    # 绝对底线 F(p)（§5.1；CO 单位 mg/m³）。
    r2_floors: dict[str, float] = field(default_factory=lambda: {
        "PM10": 100.0, "SO2": 50.0, "NO2": 60.0, "O3": 120.0, "CO": 2.0,
    })

    # R3（§6）：周期阈值与累计涨幅（三/二/一级）、持平判定。
    r3_periods: dict[int, int] = field(default_factory=lambda: {3: 4, 2: 6, 1: 8})
    r3_cum_gains: dict[int, float] = field(default_factory=lambda: {3: 0.15, 2: 0.30, 1: 0.50})
    r3_step_min: float = 0.02

    # R4（§7）：倍率（三/二/一级）、重污染放宽、持续周期、差值底线、区域豁免。
    r4_multiples: dict[int, float] = field(default_factory=lambda: {3: 1.5, 2: 2.0, 1: 3.0})
    r4_heavy_relief: float = 0.5
    r4_hold_periods: dict[int, int] = field(default_factory=lambda: {3: 3, 2: 2, 1: 0})
    # 差值底线 D(p)（§7.1；CO 单位 mg/m³）。
    r4_diff_floors: dict[str, float] = field(default_factory=lambda: {
        "PM10": 50.0, "SO2": 30.0, "NO2": 30.0, "O3": 40.0, "CO": 1.0,
    })
    r4_region_exempt_sites: int = 4

    # PM2.5 小时版（§8）：与 5 分钟规则互不复用状态。
    pm25_r2_t3_ratio: float = 0.25
    pm25_r2_t2_ratio: float = 0.50
    pm25_r2_min_abs_gain: float = 15.0
    pm25_r3_t3_periods: int = 2
    pm25_r3_t3_cum: float = 0.15
    pm25_r3_t2_periods: int = 3
    pm25_r3_t2_cum: float = 0.30
    pm25_r3_step_min: float = 0.02
    pm25_r4_t3_multiple: float = 1.5
    pm25_r4_t3_diff: float = 35.0
    pm25_r4_t3_hold_periods: int = 1
    pm25_r4_t2_multiple: float = 2.0
    pm25_r4_t2_diff: float = 35.0

    # 推送管控 M（§9）。
    cooldown_minutes: dict[int, int] = field(default_factory=lambda: {3: 120, 2: 90, 1: 60})
    recover_ratio: float = 0.90
    recover_periods: int = 3
    site_daily_quota: dict[int, int] = field(default_factory=lambda: {3: 5, 2: 8})
    global_daily_cap: int = 40
    quiet_hours_start: int = 22
    quiet_hours_end: int = 6
    quiet_suppress_levels: tuple[int, ...] = (3,)

    def active_limit_version(self, day: date) -> dict[str, Any]:
        """取生效日最新的限值版本（cfg_limit 生效区间语义）。"""
        active = self.limit_versions[0]
        for version in self.limit_versions:
            if day >= date.fromisoformat(str(version["effective_from"])):
                active = version
        return active

    def in_quiet_hours(self, hour: int) -> bool:
        start, end = self.quiet_hours_start, self.quiet_hours_end
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end


CONFIG_FILE_ENV = "XUCHANG_AIR_ALERT_CONFIG"
CONFIG_FILE_NAME = "air_alert_config.json"


def load_air_alert_config(output_root: Path | None = None) -> AirAlertRuleConfig:
    """加载配置：默认 §14 参数；存在 JSON 覆盖文件时按键合并。

    覆盖文件路径优先取环境变量 XUCHANG_AIR_ALERT_CONFIG，否则使用
    数据登记目录下的 air_alert_config.json。文件缺失不是错误（默认值即文档值）。
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
        for key, value in overrides.items():
            if not hasattr(config, key):
                continue
            current = getattr(config, key)
            if isinstance(current, dict) and isinstance(value, dict):
                current.update(value)
            elif isinstance(current, tuple) and isinstance(value, list):
                setattr(config, key, tuple(value))
            else:
                setattr(config, key, value)
        break
    return config
