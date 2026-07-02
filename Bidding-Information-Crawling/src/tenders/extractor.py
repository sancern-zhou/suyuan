from __future__ import annotations

import re
from html import unescape
from typing import Iterable, List, Optional
from urllib.parse import urljoin

from .models import TenderCandidate, TenderFilterDecision, TenderNotice

FIELD_PATTERNS = {
    "project_name": [
        r"项目名称[:：]?\s*([^\n\r]+)",
        r"采购项目名称[:：]?\s*([^\n\r]+)",
    ],
    "purchaser": [
        r"采购人[:：]\s*([^\n\r]+)",
        r"采购单位[:：]\s*([^\n\r]+)",
        r"招标人(?:（[^）]+）)?[:：]\s*([^\n\r]+)",
        r"业主单位[:：]\s*([^\n\r]+)",
    ],
    "agency": [
        r"代理机构[:：]\s*([^\n\r]+)",
        r"采购代理机构[:：]\s*([^\n\r]+)",
        r"招标代理[:：]\s*([^\n\r]+)",
    ],
    "winning_bidder": [
        r"中标(?:供应商|单位|人)[:：]\s*([^\n\r]+)",
        r"成交(?:供应商|单位)[:：]\s*([^\n\r]+)",
    ],
    "budget_amount": [
        r"预算金额(?:（元）|\(元\))?[:：]?\s*([￥¥]?[0-9][0-9,]*(?:\.[0-9]+)?(?:\s*(?:万元|万|元|千元|人民币))?)",
        r"项目预算[:：]?\s*([￥¥]?[0-9][0-9,]*(?:\.[0-9]+)?(?:\s*(?:万元|万|元|千元|人民币))?)",
    ],
    "winning_amount": [
        r"中标金额(?:（元）|\(元\))?[:：]?\s*([￥¥]?[0-9][0-9,]*(?:\.[0-9]+)?(?:\s*(?:万元|万|元|千元|人民币))?)",
        r"成交金额(?:（元）|\(元\))?[:：]?\s*([￥¥]?[0-9][0-9,]*(?:\.[0-9]+)?(?:\s*(?:万元|万|元|千元|人民币))?)",
        r"中选金额[:：]?\s*([￥¥]?[0-9][0-9,]*(?:\.[0-9]+)?(?:\s*(?:万元|万|元|千元|人民币))?)",
    ],
    "bid_open_date": [r"开标时间[:：]\s*([^\n\r]+)", r"投标截止时间[:：]\s*([^\n\r]+)"],
    "deadline": [
        r"报名截止时间[:：]\s*([^\n\r]+)",
        r"获取.*?截止时间[:：]\s*([^\n\r]+)",
    ],
}

PLACEHOLDER_FIELD_VALUES = {
    "立即查看",
    "查看详情",
    "注册/登录",
    "登录后查看",
    "****",
    "**",
}

PROVINCES = [
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "西藏",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
]


class TenderStructuredExtractor:
    def extract(
        self,
        candidate: TenderCandidate,
        html_or_text: str,
        decision: TenderFilterDecision,
    ) -> TenderNotice:
        raw_text = clean_detail_content(html_or_text)
        main_text = self._main_content_slice(raw_text)
        fields = {
            name: self._first_match(main_text, patterns)
            for name, patterns in FIELD_PATTERNS.items()
        }
        project_name = self._best_project_name(fields["project_name"], candidate.title)
        purchaser = fields["purchaser"] or self._infer_purchaser_from_title(
            candidate.title
        )
        province, city = self._extract_region(raw_text, candidate)
        budget_amount = fields["budget_amount"]
        winning_amount = fields["winning_amount"]
        if (
            budget_amount
            and "元" not in budget_amount
            and re.search(r"预算金额(?:（元）|\(元\))", raw_text)
        ):
            budget_amount = f"{budget_amount}元"
        if (
            winning_amount
            and "元" not in winning_amount
            and re.search(r"(?:中标|成交)金额(?:（元）|\(元\))", raw_text)
        ):
            winning_amount = f"{winning_amount}元"

        notice = TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=candidate.notice_type,
            raw_content=raw_text,
            project_name=project_name,
            purchaser=purchaser,
            agency=fields["agency"],
            winning_bidder=fields["winning_bidder"],
            budget_amount=budget_amount,
            budget_amount_wan_yuan=amount_to_wan_yuan(budget_amount),
            winning_amount=winning_amount,
            winning_amount_wan_yuan=amount_to_wan_yuan(winning_amount),
            province=province,
            city=city,
            publish_date=candidate.publish_date,
            bid_open_date=fields["bid_open_date"],
            deadline=fields["deadline"],
            industry_category=decision.project_category,
            environment_relevance=decision.is_relevant,
            filter_reason=decision.reason,
            filter_confidence=decision.confidence,
            summary=self._summarize(project_name, main_text),
            key_requirements=self._extract_key_requirements(main_text),
            attachment_urls=extract_attachment_urls(html_or_text, candidate.url),
        )
        notice.structured_json = self._structured_payload(notice)
        return notice

    def _first_match(self, text: str, patterns: Iterable[str]) -> Optional[str]:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = self._clean_value(match.group(1))
                if not self._is_placeholder_value(value):
                    return value
        return None

    def _clean_value(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip(" *，,；;。")

    def _is_placeholder_value(self, value: str) -> bool:
        normalized = re.sub(r"\s+", "", value or "")
        return (
            normalized in PLACEHOLDER_FIELD_VALUES
            or normalized.startswith("立即查看")
            or normalized.startswith("****")
            or normalized in {"名称:", "名称：", "企业名录"}
        )

    def _best_project_name(self, extracted_name: str | None, title: str) -> str:
        title_name = self._title_without_notice_suffix(title)
        if not extracted_name:
            return title_name
        if "**" in extracted_name and "**" not in title_name:
            return title_name
        if title_name.endswith(extracted_name) and extracted_name != title_name:
            return title_name
        return extracted_name

    def _title_without_notice_suffix(self, title: str) -> str:
        return re.sub(
            r"(成交结果公告|中标结果公告|招标公告|采购公告|中标公告|成交公告|结果公告|变更公告)$",
            "",
            title,
        ).strip()

    def _infer_purchaser_from_title(self, title: str) -> Optional[str]:
        match = re.search(
            r"^(.{2,40}?(?:生态环境局|生态环境分局|生态环境综合行政执法支队)(?:[\u4e00-\u9fa5]{0,12})?)\d{4}年",
            title,
        )
        if match:
            return match.group(1).strip()
        return None

    def _extract_region(
        self, text: str, candidate: TenderCandidate
    ) -> tuple[Optional[str], Optional[str]]:
        area_name = str(candidate.metadata.get("area_name") or "")
        if area_name:
            parts = [
                part.strip() for part in re.split(r"[-/]", area_name) if part.strip()
            ]
            if parts:
                return parts[0], parts[1] if len(parts) > 1 else None

        location_match = re.search(
            r"([^\s>]{2,8})-\s*([^\s>-]{2,12})(?:-\s*([^\s>-]{2,12}))?",
            text[:2000],
        )
        if location_match:
            province = location_match.group(1).strip()
            city = (location_match.group(3) or location_match.group(2)).strip()
            if province in PROVINCES:
                return province, city

        province = next((item for item in PROVINCES if item in text[:500]), None)
        city_match = re.search(r"([\u4e00-\u9fa5]{2,12}市)", text[:800])
        return province, city_match.group(1) if city_match else None

    def _main_content_slice(self, text: str) -> str:
        start_markers = [
            "咨询:400-688-2000查看全部商机",
            "下文中****为隐藏内容",
            "您尚未开通该权限",
        ]
        end_markers = ["相关公告", "注册会员享贴心服务", "猜你喜欢", "欢迎您："]
        start = 0
        for marker in start_markers:
            index = text.find(marker)
            if index >= 0:
                start = max(start, index + len(marker))
        end = len(text)
        for marker in end_markers:
            index = text.find(marker, start)
            if index >= 0:
                end = min(end, index)
        return text[start:end].strip() or text

    def _summarize(self, project_name: str | None, text: str) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        prefix = f"{project_name}。" if project_name else ""
        return (prefix + compact[:500]).strip()

    def _extract_key_requirements(self, text: str) -> List[str]:
        sentences = re.split(r"[。；;\n]", text)
        keywords = ["监测", "治理", "排查", "运维", "服务", "数据分析", "验收", "资质"]
        selected = []
        for sentence in sentences:
            sentence = sentence.strip()
            if 8 <= len(sentence) <= 120 and any(
                keyword in sentence for keyword in keywords
            ):
                selected.append(sentence)
            if len(selected) >= 5:
                break
        return selected

    def _structured_payload(self, notice: TenderNotice) -> dict:
        return {
            "title": notice.title,
            "url": notice.url,
            "notice_type": notice.notice_type.value,
            "project_name": notice.project_name,
            "purchaser": notice.purchaser,
            "agency": notice.agency,
            "winning_bidder": notice.winning_bidder,
            "budget_amount": notice.budget_amount,
            "budget_amount_wan_yuan": notice.budget_amount_wan_yuan,
            "winning_amount": notice.winning_amount,
            "winning_amount_wan_yuan": notice.winning_amount_wan_yuan,
            "province": notice.province,
            "city": notice.city,
            "publish_date": (
                notice.publish_date.isoformat() if notice.publish_date else None
            ),
            "bid_open_date": notice.bid_open_date,
            "deadline": notice.deadline,
            "industry_category": notice.industry_category,
            "environment_relevance": notice.environment_relevance,
            "filter_reason": notice.filter_reason,
            "filter_confidence": notice.filter_confidence,
            "summary": notice.summary,
            "key_requirements": notice.key_requirements,
            "attachment_urls": notice.attachment_urls,
        }


def clean_detail_content(html_or_text: str) -> str:
    value = html_or_text or ""
    value = re.sub(r"(?is)<script.*?>.*?</script>", " ", value)
    value = re.sub(r"(?is)<style.*?>.*?</style>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p>|</div>|</li>|</tr>", "\n", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n", value)
    return value.strip()


def extract_attachment_urls(html: str, base_url: str) -> List[str]:
    urls: List[str] = []
    for href in re.findall(
        r"href=[\'\"]([^\'\"]+)[\'\"]", html or "", flags=re.IGNORECASE
    ):
        if re.search(r"\.(pdf|doc|docx|xls|xlsx|zip|rar)(\?|$)", href, re.IGNORECASE):
            urls.append(urljoin(base_url, href))
    return list(dict.fromkeys(urls))


def amount_to_wan_yuan(value: str | None) -> Optional[float]:
    if not value:
        return None
    normalized = value.replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", normalized)
    if not match:
        return None
    amount = float(match.group(1))
    if "万元" in normalized or "万" in normalized:
        return amount
    if "千元" in normalized:
        return round(amount / 10, 4)
    if "元" in normalized or "￥" in normalized or "¥" in normalized:
        return round(amount / 10000, 4)
    return amount
