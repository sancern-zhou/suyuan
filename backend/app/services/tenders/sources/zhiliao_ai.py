"""知了标讯AI开放平台 (ai.zhiliaobiaoxun.com) source via REST API.

Auth: ``X-API-Key`` header. Record actual ``meta.cost_units`` for billing;
ordinary and advanced searches have different tariffs.

    POST {base}/search_bids     keywords[], begin_date/end_date, page/page_size
    POST {base}/get_bid_detail  bid_id (+ bid_type)

Unlike the site's anonymous API, ``begin_date``/``end_date`` support arbitrary
historical windows and details include the full announcement body.
"""

from __future__ import annotations

import os
import json
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from datetime import date
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx
import structlog

from config.settings import settings
from app.utils.path_config import resolve_agent_path

from ..models import NoticeType, TenderCandidate, TenderNotice

logger = structlog.get_logger()

DEFAULT_BASE_URL = "https://mcp-server.zhiliaobiaoxun.com/api_v2"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _parse_date(value: Any) -> Optional[date]:
    text = _clean(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _notice_type(bid_type: str, bid_process: str, winner_names: list[str]) -> NoticeType:
    text = f"{bid_type or ''}{bid_process or ''}"
    if any(word in text for word in ("变更", "废标", "流标", "澄清", "更正")):
        return NoticeType.CHANGE
    if any(word in text for word in ("候选", "预成交", "评审")):
        return NoticeType.OTHER
    if any(word in text for word in ("中标", "成交", "结果", "验收", "合同")):
        return NoticeType.WINNING_BID
    if any(word in text for word in ("招标", "采购", "磋商", "询价", "比选", "竞价")):
        return NoticeType.TENDER
    return NoticeType.WINNING_BID if winner_names else NoticeType.OTHER


def apply_list_fields(notice: TenderNotice, candidate: TenderCandidate) -> None:
    """Reuse authoritative list facts even when the classifier is unavailable."""
    item = candidate.metadata.get("api_list_fields") or {}
    notice.publish_date = candidate.publish_date
    # The API's generic money/money_wan fields have no verified budget role.
    notice.budget_amount = None
    notice.budget_amount_wan_yuan = None
    notice.classification["input_scope"] = "api_list_only"
    scope_text = candidate.title + " " + " ".join(item.get("sm_names") or [])
    if "大气污染防治项目" in scope_text and not any(
        term in scope_text for term in ("技术", "服务", "监测", "管控", "工程", "施工")
    ):
        notice.classification.update(business_type="待确认", classification_status="needs_review",
                                     review_reason="列表未明确防治项目是技术服务还是工程治理")
    if "火焰监测" in scope_text and "熄火保护" in scope_text:
        notice.classification.update(business_type="待确认", classification_status="needs_review",
                                     review_reason="工业燃烧安全配套，不能直接认定为环境监测业务")
    for target, source in (("purchaser", "caller_name"), ("agency", "agency_name"),
                           ("province", "province"), ("city", "city")):
        if item.get(source):
            setattr(notice, target, _clean(item[source]))
    text = f"{candidate.title} {item.get('bid_process', '')}"
    if any(word in text for word in ("更正", "变更", "澄清", "废标", "流标")):
        stage, kind = "correction", NoticeType.CHANGE
    elif any(word in text for word in ("候选", "预成交", "评审")):
        stage, kind = "candidate", NoticeType.OTHER
    elif "合同" in text:
        stage, kind = "contract", NoticeType.WINNING_BID
    elif any(word in text for word in ("中标结果", "成交结果", "中标公告", "成交公告", "结果公告")):
        stage, kind = "final_result", NoticeType.WINNING_BID
    else:
        stage, kind = notice.classification.get("notice_stage", "unknown"), notice.notice_type
    notice.classification["notice_stage"] = stage
    notice.notice_type = kind
    names = item.get("winner_names") or []
    amounts = item.get("winner_moneys") or []
    notice.classification["api_winner_names"] = names
    notice.classification["api_winner_moneys_yuan"] = amounts
    # Never promote a budget or a preliminary offer into a final award.
    notice.winning_bidder = None
    notice.winning_amount = None
    notice.winning_amount_wan_yuan = None
    if stage not in {"final_result", "contract"}:
        if notice.notice_type == NoticeType.WINNING_BID:
            notice.notice_type = NoticeType.OTHER
        notice.summary = _list_summary(notice)
        return
    if isinstance(names, list):
        notice.winning_bidder = "；".join(_clean(n) for n in names if n) or None
    if not isinstance(amounts, list) or not amounts:
        notice.summary = _list_summary(notice)
        return
    try:
        values = [Decimal(str(amount)) for amount in amounts]
        if not all(value.is_finite() and value > 0 for value in values):
            notice.summary = _list_summary(notice)
            return
    except (InvalidOperation, ValueError):
        notice.summary = _list_summary(notice)
        return
    notice.winning_amount = "；".join(f"{value}元" for value in values)
    notice.winning_amount_wan_yuan = float(sum(values) / Decimal(10000))
    notice.summary = _list_summary(notice)


def _list_summary(notice: TenderNotice) -> str:
    """Render verified list facts so prose cannot contradict award columns."""
    stages = {"final_result": "结果公告", "candidate": "候选/预成交/评审",
              "correction": "更正/变更", "contract": "合同", "unknown": "阶段待确认"}
    classification = notice.classification
    parts = [notice.title, "信息来源：API列表", f"公告阶段：{stages.get(classification.get('notice_stage'), '其他')}"]
    if notice.purchaser:
        parts.append(f"采购人：{notice.purchaser}")
    if notice.winning_bidder:
        parts.append(f"中标供应商：{notice.winning_bidder}")
    if notice.winning_amount:
        parts.append(f"中标金额（按API分项顺序）：{notice.winning_amount}")
    elif classification.get("notice_stage") in {"final_result", "contract"}:
        parts.append("中标金额：API列表未完整提供，未计算合计")
    if classification.get("business_type"):
        parts.append(f"业务类型：{classification['business_type']}")
    if classification.get("content_tags"):
        parts.append("内容标签：" + "、".join(classification["content_tags"]))
    if classification.get("review_reason"):
        parts.append(classification["review_reason"])
    return "；".join(parts) + "。"


class ZhiliaoAiClient:
    name = "zhiliao_ai"
    search_ignores_notice_type = True

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        page_size: int = 50,
    ):
        self.api_key = (
            api_key
            or os.getenv("ZHILIAO_AI_API_KEY")
            or getattr(settings, "zhiliao_ai_api_key", None)
        )
        self.base_url = (
            base_url or getattr(settings, "zhiliao_ai_base_url", None) or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout
        self.page_size = max(1, page_size)
        self.request_audit: list[dict[str, Any]] = []
        self.search_errors: list[str] = []
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "X-API-Key": self.api_key or "",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        response = await self._client.post(f"{self.base_url}{path}", json=payload)
        response.raise_for_status()
        payload = response.json()
        self.request_audit.append({"endpoint": path, **(payload.get("meta") or {})})
        logger.info("zhiliao_ai_request_audit", **self.request_audit[-1])
        if not payload.get("success"):
            raise RuntimeError(f"zhiliao_ai {path} failed: {payload.get('error')}")
        return payload.get("data")

    async def search_plan(self, keywords, notice_types, publish_date, max_pages=0, end_date=None):
        """Run the versioned air/AI plan once, not once per legacy keyword."""
        if publish_date is None:
            raise ValueError("Zhiliao query plan requires an explicit date")
        end_date = end_date or publish_date
        if end_date < publish_date:
            raise ValueError("end_date must not precede publish_date")
        strategy = json.loads(resolve_agent_path(
            "backend/app/services/tenders/zhiliao_strategy.json"
        ).read_text(encoding="utf-8"))
        merged: dict[str, TenderCandidate] = {}
        self.search_errors.clear()
        for route in strategy["routes"]:
            if not route["recommended"]:
                continue
            page = 1
            while True:
                payload = deepcopy(route["payload"])
                payload.update(begin_date=publish_date.isoformat(), end_date=end_date.isoformat(),
                               page=page, page_size=min(self.page_size, 50))
                # The strategy is explicitly a winning-announcement profile;
                # old keyword/type loops must not multiply requests.
                try:
                    data = await self._post(route["endpoint"], payload) or {}
                except Exception as exc:
                    self.search_errors.append(f"{route['name']} page {page}: {exc}")
                    break
                items = data.get("items") or []
                for item in items:
                    candidate = self._to_candidate(item, route["name"])
                    key = str(item.get("bid_id") or item.get("uniq_key") or candidate.url)
                    if key in merged:
                        merged[key].metadata["query_routes"].append(route["name"])
                        continue
                    candidate.metadata.update(query_routes=[route["name"]],
                                              strategy_version=strategy["strategy_version"])
                    candidate.metadata["request_audit"] = self.request_audit[-1] if self.request_audit else {}
                    merged[key] = candidate
                total = data.get("total")
                complete = len(items) < payload["page_size"] or (
                    isinstance(total, int) and page * payload["page_size"] >= total
                )
                if complete:
                    break
                if max_pages and max_pages > 0 and page >= max_pages:
                    self.search_errors.append(f"{route['name']} pagination incomplete at page {page}; use max_pages=0")
                    break
                page += 1
        return list(merged.values())

    async def search(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date] = None,
        max_pages: int = 1,
    ) -> list[TenderCandidate]:
        day = publish_date.isoformat() if publish_date else None
        candidates: list[TenderCandidate] = []
        page_limit = max(1, max_pages) if max_pages and max_pages > 0 else 5
        for page in range(1, page_limit + 1):
            payload: dict[str, Any] = {
                "keywords": [keyword],
                "bid_type": "全部",
                "page": page,
                "page_size": self.page_size,
            }
            if day:
                payload["begin_date"] = day
                payload["end_date"] = day
            try:
                data = await self._post("/search_bids", payload)
            except Exception:  # noqa: BLE001
                logger.exception("zhiliao_ai_search_failed", keyword=keyword, page=page)
                break
            items = (data or {}).get("items") or []
            if not items:
                break
            candidates.extend(self._to_candidate(item, keyword) for item in items)
            if len(items) < self.page_size:
                break
        return candidates

    def _to_candidate(self, item: dict[str, Any], keyword: str) -> TenderCandidate:
        bid_id = item.get("bid_id")
        winner_names = item.get("winner_names") or []
        notice_type = _notice_type(
            str(item.get("bid_type") or ""),
            f"{item.get('bid_process') or ''} {item.get('title') or ''}", winner_names
        )
        snippet = " ".join(
            _clean(item.get(key))
            for key in ("caller_name", "winner_names", "sm_names", "industry", "bid_no")
            if _clean(item.get(key))
        )
        return TenderCandidate(
            title=_clean(item.get("title")),
            url=_clean(item.get("url")) or f"https://www.zhiliaobiaoxun.com/content/{bid_id}",
            notice_type=notice_type,
            keyword=keyword,
            source=self.name,
            publish_date=_parse_date(item.get("pub_time")),
            raw_list_text=" ".join(part for part in [_clean(item.get("title")), snippet] if part),
            metadata={
                "api_list_fields": item,
                "zhiliao_ai_bid_id": bid_id,
                "zhiliao_ai_uniq_key": item.get("uniq_key"),
                "bid_no": item.get("bid_no"),
                "province": _clean(item.get("province")),
                "city": _clean(item.get("city")),
                "county": _clean(item.get("county")),
                "caller_name": _clean(item.get("caller_name")),
                "winner_names": winner_names,
                "money_wan": item.get("money_wan"),
                "bid_method": item.get("bid_method"),
                "agency_name": _clean(item.get("agency_name")),
            },
        )

    async def get_bid_detail(self, bid_id: int, bid_type: str) -> dict[str, Any]:
        """Fetch the complete detail payload; errors must not become cached success."""
        type_code = {"招标": 1, "中标": 2}.get(bid_type)
        if type_code is None:
            raise ValueError("详情接口 bid_type 只支持招标或中标")
        data = await self._post("/get_bid_detail", {"bid_id": bid_id, "bid_type": type_code})
        if not isinstance(data, dict) or not any(data.get(k) for k in ("source", "source_ext")):
            raise ValueError("知了详情接口未返回公告正文")
        return data

    async def fetch_detail(self, candidate: TenderCandidate) -> str:
        metadata = candidate.metadata or {}
        bid_id = metadata.get("zhiliao_ai_bid_id")
        if bid_id is None:
            return ""
        payload: dict[str, Any] = {"bid_id": bid_id}
        if candidate.notice_type == NoticeType.WINNING_BID:
            payload["bid_type"] = 2
        elif candidate.notice_type == NoticeType.TENDER:
            payload["bid_type"] = 1
        try:
            data = await self._post("/get_bid_detail", payload) or {}
        except Exception:  # noqa: BLE001
            logger.exception("zhiliao_ai_detail_failed", bid_id=bid_id)
            return ""
        parts = [
            str(data.get("source") or ""),
            str(data.get("source_ext") or ""),
        ]
        attachments = data.get("attachment_urls") or []
        if attachments:
            parts.append("附件: " + " ".join(str(a) for a in attachments))
        text = "\n".join(part for part in parts if part)
        return text or json.dumps(data, ensure_ascii=False)

    async def close(self) -> None:
        await self._client.aclose()


def build_zhiliao_ai_source(config) -> ZhiliaoAiClient:
    return ZhiliaoAiClient(
        api_key=getattr(settings, "zhiliao_ai_api_key", None),
        base_url=getattr(settings, "zhiliao_ai_base_url", None),
    )
