from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

from .categories import normalize_project_category
from .models import TenderCandidate, TenderFilterDecision

DEFAULT_POSITIVE_KEYWORDS = [
    "生态环境",
    "环境监测",
    "污染治理",
    "污染源",
    "水质监测",
    "空气质量",
    "大气污染",
    "废气",
    "废水",
    "污水",
    "固废",
    "危废",
    "危险废物",
    "固体废物",
    "土壤污染",
    "地下水",
    "VOCs",
    "挥发性有机物",
    "排污",
    "环保管家",
    "环保系统",
    "智慧环保",
    "智慧监管",
    "智慧执法",
    "信息化",
    "数据平台",
    "监管平台",
    "实验室",
    "试剂",
    "标准物质",
    "应急物资",
    "生态保护",
    "生物多样性",
    "生态红线",
    "超低排放",
    "排放改造",
    "环评",
    "环境影响评价",
    "在线监测",
    "自动监测站",
    "走航监测",
    "执法监测",
    "重污染",
    "应急响应",
    "污染环境防治",
]

DEFAULT_NEGATIVE_KEYWORDS = [
    "打印",
    "复印",
    "复印纸",
    "硒鼓",
    "墨盒",
    "办公用品",
    "办公耗材",
    "耗材",
    "办公设备",
    "办公家具",
    "桌椅",
    "电脑",
    "服务器",
    "网络安全",
    "会议",
    "广告服务",
    "培训",
    "宣传品",
    "宣传活动",
    "宣传服务",
    "环境日宣传",
    "制服",
    "物业",
    "保洁",
    "食堂",
    "餐饮",
    "车辆维修",
    "车辆定点维修",
    "车辆保险",
    "维修",
    "公车",
    "保险",
    "空调",
    "电梯",
    "装修",
    "LED",
    "显示屏",
    "基础电信服务",
    "互联网接入",
    "网上超市",
    "合同履约验收",
    "定点议价",
    "档案整理",
    "审批决定",
    "审批公告",
    "受理公示",
]

CATEGORY_KEYWORDS = {
    "digital_platform": [
        "智慧环保",
        "智慧监管",
        "智慧执法",
        "信息化",
        "数据平台",
        "监管平台",
        "管理系统",
        "AI",
        "大数据",
        "环保系统",
    ],
    "operation_maintenance": [
        "运维",
        "运行维护",
        "运营维护",
        "维护服务",
        "自动监测站",
        "空气站",
        "水站",
        "在线监测设备",
    ],
    "equipment_supplies": [
        "仪器",
        "设备",
        "耗材",
        "试剂",
        "标准物质",
        "采样设备",
        "实验室",
        "配件",
    ],
    "emergency_response": [
        "应急",
        "应急响应",
        "应急物资",
        "突发环境事件",
        "应急预案",
        "应急监测",
    ],
    "ecology_conservation": [
        "生态保护",
        "生物多样性",
        "自然保护地",
        "生态红线",
        "生态状况",
        "生态质量",
        "生态修复",
    ],
    "environment_monitoring": [
        "监测",
        "在线监测",
        "自动监测站",
        "走航",
        "空气质量",
        "水质",
    ],
    "pollution_control": [
        "污染治理",
        "污水",
        "废水",
        "废气",
        "VOCs",
        "挥发性有机物",
        "固废",
        "危废",
        "危险废物",
        "固体废物",
        "重污染",
        "超低排放",
        "排放改造",
    ],
    "environment_consulting": [
        "环评",
        "环境影响评价",
        "环保管家",
        "排污许可",
        "咨询",
        "调查评估",
        "方案编制",
        "验收评估",
        "绩效评估",
    ],
    "law_enforcement_support": [
        "执法监测",
        "污染源排查",
        "监督性监测",
        "排查",
        "应急响应",
    ],
}


@dataclass(slots=True)
class TenderRelevanceFilter:
    positive_keywords: Sequence[str] = field(
        default_factory=lambda: DEFAULT_POSITIVE_KEYWORDS
    )
    negative_keywords: Sequence[str] = field(
        default_factory=lambda: DEFAULT_NEGATIVE_KEYWORDS
    )
    min_positive_hits: int = 1

    def prefilter_decision(
        self, candidate: TenderCandidate
    ) -> TenderFilterDecision | None:
        title = self._normalize(candidate.title)
        raw_text = self._normalize(candidate.raw_list_text)
        combined = title + raw_text

        patterns = [
            ("行政审批、公示或环评批准信息，不属于招投标采购项目", [
                r"环境影响.*报告.*审批",
                r"环境影响.*报告.*批准",
                r"环境影响评价文件审批",
                r"环评.*审批",
                r"审批.*公示",
                r"受理公示",
                r"已批准公告",
                r"拟批准.*公示",
            ]),
            ("网上超市或合同履约验收公告，非目标招投标公告", [
                r"网上超市",
                r"合同履约验收",
                r"定点采购",
                r"定点议价",
                r"服务市场采购",
            ]),
            ("采购意向信息，不属于正式招标公告或中标公告", [
                r"采购意向",
                r"政府采购意向",
            ]),
            ("招标代理或采购代理服务，非环境业务主体项目", [
                r"(?:招标代理|采购代理)(?:服务|机构)?(?:框架|征集|招募|采购|项目)",
                r"选取.*代理",
                r"招募.*代理",
            ]),
            ("印刷、宣传或广告服务，非环境业务主体项目", [
                r"印刷",
                r"宣传品",
                r"宣传服务",
                r"广告",
            ]),
            ("车辆或用车保障服务，非环境业务主体项目", [
                r"业务用车",
                r"车辆保障",
                r"车辆维修",
                r"车辆保险",
                r"租车",
            ]),
            ("办公、耗材或通用实验耗材采购，非环境业务主体项目", [
                r"办公",
                r"复印",
                r"打印",
                r"办公耗材",
            ]),
            ("政务信息化、档案、会议或通用管理支撑，非环境业务主体项目", [
                r"政务信息化",
                r"档案",
                r"人事档案",
                r"干部人事",
                r"大会",
                r"会议",
                r"会务",
                r"展会",
            ]),
        ]
        for reason, regexes in patterns:
            if any(re.search(pattern, combined, re.IGNORECASE) for pattern in regexes):
                return TenderFilterDecision(
                    is_relevant=False,
                    reason=f"规则预过滤: {reason}",
                    confidence=0.95,
                    decision_source="rules",
                )
        return None

    def decide(
        self, candidate: TenderCandidate, detail_text: str = ""
    ) -> TenderFilterDecision:
        prefilter_decision = self.prefilter_decision(candidate)
        if prefilter_decision is not None:
            return prefilter_decision

        title_text = self._normalize(candidate.title)
        text = self._normalize(
            " ".join([candidate.title, candidate.raw_list_text, detail_text])
        )
        positive_hits = self._find_keywords(text, self.positive_keywords)
        title_positive_hits = self._find_keywords(title_text, self.positive_keywords)
        negative_hits = self._find_keywords(text, self.negative_keywords)
        title_negative_hits = self._find_keywords(title_text, self.negative_keywords)

        if self._is_administrative_public_notice(candidate.title):
            return TenderFilterDecision(
                is_relevant=False,
                reason="环境行政审批或公示信息，不属于招投标采购项目",
                confidence=0.9,
                matched_positive_keywords=positive_hits,
                matched_negative_keywords=negative_hits,
                project_category=self._infer_category(positive_hits),
            )

        if (
            positive_hits
            and not title_positive_hits
            and self._is_body_only_keyword_hit(candidate.raw_list_text)
        ):
            return TenderFilterDecision(
                is_relevant=False,
                reason="关键词只在正文命中，标题缺少环境业务采购信号",
                confidence=0.84,
                matched_positive_keywords=positive_hits,
                matched_negative_keywords=negative_hits,
                project_category=self._infer_category(positive_hits),
            )

        if (
            positive_hits
            and not title_positive_hits
            and not self._has_procurement_signal(candidate.title)
        ):
            return TenderFilterDecision(
                is_relevant=False,
                reason="标题缺少环境业务或采购信号，疑似正文推荐区误命中",
                confidence=0.82,
                matched_positive_keywords=positive_hits,
                matched_negative_keywords=negative_hits,
                project_category=self._infer_category(positive_hits),
            )

        if (
            title_negative_hits
            and not self._has_strong_environment_signal(positive_hits)
            and not self._is_environment_equipment_supply(candidate.title)
        ):
            return TenderFilterDecision(
                is_relevant=False,
                reason=f"标题命中非环境业务采购关键词: {', '.join(title_negative_hits[:5])}",
                confidence=0.88,
                matched_positive_keywords=positive_hits,
                matched_negative_keywords=negative_hits,
                project_category=self._infer_category(positive_hits),
            )

        if (
            negative_hits
            and self._is_office_procurement(candidate.title)
            and not self._is_environment_equipment_supply(candidate.title)
        ):
            return TenderFilterDecision(
                is_relevant=False,
                reason=f"生态环境部门普通办公或基础保障采购: {', '.join(negative_hits[:5])}",
                confidence=0.92,
                matched_positive_keywords=positive_hits,
                matched_negative_keywords=negative_hits,
                project_category=self._infer_category(positive_hits),
            )

        if len(positive_hits) >= self.min_positive_hits:
            confidence = min(0.95, 0.68 + len(set(positive_hits)) * 0.08)
            return TenderFilterDecision(
                is_relevant=True,
                reason=f"命中环境业务关键词: {', '.join(positive_hits[:6])}",
                confidence=confidence,
                matched_positive_keywords=positive_hits,
                matched_negative_keywords=negative_hits,
                project_category=self._infer_category(positive_hits),
            )

        return TenderFilterDecision(
            is_relevant=False,
            reason="未命中环境业务关键词，等待人工或LLM进一步确认",
            confidence=0.55,
            matched_positive_keywords=positive_hits,
            matched_negative_keywords=negative_hits,
            project_category=None,
        )

    def _find_keywords(self, text: str, keywords: Iterable[str]) -> List[str]:
        hits: List[str] = []
        for keyword in keywords:
            if self._normalize(keyword) in text:
                hits.append(keyword)
        return hits

    def _has_strong_environment_signal(self, positive_hits: Sequence[str]) -> bool:
        strong = {
            "污染治理",
            "污染源",
            "VOCs",
            "挥发性有机物",
            "废气",
            "废水",
            "水质监测",
            "在线监测",
            "走航监测",
            "超低排放",
            "排放改造",
            "重污染",
            "应急响应",
            "危险废物",
            "固体废物",
            "污染环境防治",
        }
        return any(hit in strong for hit in positive_hits)

    def _is_administrative_public_notice(self, title: str) -> bool:
        normalized_title = self._normalize(title)
        admin_patterns = [
            r"环评.*审批",
            r"环境影响.*审批",
            r"环境影响评价.*公示",
            r"环评.*公示",
            r"审批.*公示",
            r"拟批准.*公示",
            r"第二次公示",
            r"受理公示",
            r"办理确认函公示",
            r"审批决定.*公告",
        ]
        return any(
            re.search(pattern, normalized_title, re.IGNORECASE)
            for pattern in admin_patterns
        )

    def _is_body_only_keyword_hit(self, raw_list_text: str) -> bool:
        normalized_text = self._normalize(raw_list_text)
        return "正文中" in normalized_text or "在正文中" in normalized_text

    def _is_office_procurement(self, title: str) -> bool:
        normalized_title = self._normalize(title)
        office_patterns = [
            r"办公.*采购",
            r"打印.*采购",
            r"复印.*采购",
            r"桌椅.*采购",
            r"耗材.*采购",
            r"公车.*保险",
            r"车辆.*保险",
            r"车辆.*维修",
            r"广告服务",
            r"宣传活动",
            r"宣传服务",
            r"环境日宣传",
            r"基础电信服务",
            r"互联网接入",
            r"网上超市",
            r"合同履约验收",
            r"定点议价",
            r"审批决定",
        ]
        return any(
            re.search(pattern, normalized_title, re.IGNORECASE)
            for pattern in office_patterns
        )

    def _is_environment_equipment_supply(self, title: str) -> bool:
        normalized_title = self._normalize(title)
        return bool(
            re.search(
                r"(?:环境监测|生态环境|实验室|水质|空气|污染源|在线监测).*(?:仪器|设备|试剂|耗材|标准物质|采样|配件)",
                normalized_title,
                re.IGNORECASE,
            )
        )

    def _has_procurement_signal(self, title: str) -> bool:
        normalized_title = self._normalize(title)
        procurement_patterns = [
            r"采购",
            r"招标",
            r"投标",
            r"中标",
            r"成交",
            r"中选",
            r"选取",
            r"政府采购意向",
            r"公开选取",
        ]
        return any(
            re.search(pattern, normalized_title, re.IGNORECASE)
            for pattern in procurement_patterns
        )

    def _infer_category(self, positive_hits: Sequence[str]) -> str | None:
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword in positive_hits for keyword in keywords):
                return normalize_project_category(category)
        return "other_environment_procurement" if positive_hits else None

    def _normalize(self, value: str) -> str:
        return re.sub(r"\s+", "", value or "").lower()
