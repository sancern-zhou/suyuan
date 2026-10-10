"""许昌空气质量语义层查询工具（Cube Core REST / 127.0.0.1:4610）。

对接 xuchang-cube 语义层（projects/xuchang/data-ops/cube，Cube Core 0.35，
docker 宿主机部署）。Agent 传"度量+维度+时间范围"点数即可，不写 SQL——
指标口径唯一锁死在 schema/*.js 与采集 fetcher，同一问题永远同一个数。

口径一致性: 本文件 CATALOG 必须与 schema/*.js、采集 fetcher 三方保持一致
（采集: backend/app/fetchers/xuchang_henan_ssfb_publish.py、
xuchang_henan_ranking_recalc.py）。
查询走 JWT（CUBE_API_SECRET），连库侧为 cube_reader 只读账号，
无新增数据库权限。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

# ---------------------------------------------------------------- 语义目录
# 单一事实源(本文件内): 结构化目录 → 渲染进工具描述。改口径时三处同步:
# fetchers(采集) ↔ cube/schema/*.js ↔ 此处。
CATALOG: Dict[str, Dict[str, List[Dict[str, str]]]] = {
    # 乡镇站小时（中大国发平台口径，本地库，2025-2026 已回补完整）。
    # caliber 维度必须二选一过滤（app=审核 / src=原始），否则同站同时刻
    # 两条记录重复计数；官方结论优先 caliber='app'。数值已排除 -99 无效值。
    "TownHour": {
        "measures": [
            {"name": "count", "title": "小时记录数"},
            {"name": "avgPm25", "title": "PM2.5均值(μg/m³)"},
            {"name": "avgPm10", "title": "PM10均值(μg/m³)"},
            {"name": "avgSo2", "title": "SO2均值(μg/m³)"},
            {"name": "avgNo2", "title": "NO2均值(μg/m³)"},
            {"name": "avgCo", "title": "CO均值(mg/m³)"},
            {"name": "avgO3", "title": "O3均值(μg/m³)"},
            {"name": "maxAqi", "title": "AQI最大值"},
            {"name": "onlineSites", "title": "有数据乡镇站数(去重,76站)"},
        ],
        "dimensions": [
            {"name": "caliber", "title": "口径(app审核/src原始,必选其一过滤)"},
            {"name": "stationCode", "title": "乡镇站编码(平台内部,如1024B)"},
            {"name": "stationName", "title": "乡镇站名(前缀含区县,如建安区小召乡)"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度,2024-01-01起)"},
        ],
    },
    # 乡镇站日：本地库 2024-08 起且 2025 年起完整（2026-10 回补）。
    "TownDay": {
        "measures": [
            {"name": "count", "title": "站点日记录数"},
            {"name": "avgPm25", "title": "PM2.5日均(μg/m³)"},
            {"name": "avgPm10", "title": "PM10日均(μg/m³)"},
            {"name": "avgSo2", "title": "SO2日均(μg/m³)"},
            {"name": "avgNo2", "title": "NO2日均(μg/m³)"},
            {"name": "avgCo", "title": "CO日均(mg/m³)"},
            {"name": "avgO3", "title": "O3日均(μg/m³)"},
            {"name": "maxAqi", "title": "AQI最大值"},
            {"name": "onlineSites", "title": "有数据乡镇站数(去重,76站)"},
        ],
        "dimensions": [
            {"name": "caliber", "title": "口径(app审核/src原始,必选其一过滤)"},
            {"name": "stationCode", "title": "乡镇站编码"},
            {"name": "stationName", "title": "乡镇站名(前缀含区县)"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataDate", "title": "数据日期(时间维度,src 2024-08-01起/app 2024-09-01起)"},
        ],
    },
    # 城市小时: 18 城市组(含济源)逐小时六参数+AQI, 河南实时发布系统采集。
    "SsfbCityHour": {
        "measures": [
            {"name": "count", "title": "小时记录数"},
            {"name": "avgPm25", "title": "PM2.5均值(μg/m³)"},
            {"name": "avgPm10", "title": "PM10均值(μg/m³)"},
            {"name": "avgO3", "title": "O3均值(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h均值(μg/m³)"},
            {"name": "avgNo2", "title": "NO2均值(μg/m³)"},
            {"name": "avgSo2", "title": "SO2均值(μg/m³)"},
            {"name": "avgCo", "title": "CO均值(mg/m³)"},
            {"name": "maxAqi", "title": "AQI最大值"},
        ],
        "dimensions": [
            {"name": "city", "title": "城市名(含济源市)"},
            {"name": "cityCode", "title": "城市行政区码"},
            {"name": "groupId", "title": "城市组ID"},
            {"name": "quality", "title": "空气质量等级(优/良...)"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度)"},
        ],
    },
    # 城市日: 唯一含济源的全量城市日数据源(2026-10-03 起)。
    # 源接口 2026-10 起日值不发布 PM10, avgPm10 可能为空。
    "SsfbCityDay": {
        "measures": [
            {"name": "count", "title": "日记录数"},
            {"name": "avgPm25", "title": "PM2.5日均(μg/m³)"},
            {"name": "avgPm10", "title": "PM10日均(源10月起缺失,勿用于趋势)"},
            {"name": "avgO38h", "title": "O3-8h日均(μg/m³)"},
            {"name": "avgNo2", "title": "NO2日均(μg/m³)"},
            {"name": "avgSo2", "title": "SO2日均(μg/m³)"},
            {"name": "avgCo", "title": "CO日均(mg/m³)"},
        ],
        "dimensions": [
            {"name": "city", "title": "城市名(含济源市)"},
            {"name": "cityCode", "title": "城市行政区码"},
            {"name": "groupId", "title": "城市组ID"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataDate", "title": "数据日期(时间维度)"},
        ],
    },
    # 城市排名（本地重算）: 只做单项浓度累计与排名（不做综合指数），
    # 数值越低排名越靠前（Rank* 升序,1=最优），相同值并列（1,1,3）。
    # 排名在 18 城市组内(含济源)。
    # OfficialZong/OfficialRank 为省APP官方对照(仅≤2026-08有值, 勿与重算值混算)。
    "SsfbCityRanking": {
        "measures": [
            {"name": "count", "title": "记录数"},
            {"name": "avgPm25", "title": "PM2.5累计均值(μg/m³)"},
            {"name": "avgPm10", "title": "PM10累计均值(缺口由小时均值补齐)"},
            {"name": "avgSo2", "title": "SO2累计均值(μg/m³)"},
            {"name": "avgNo2", "title": "NO2累计均值(μg/m³)"},
            {"name": "avgO38h90", "title": "O3-8h第90百分位(μg/m³)"},
            {"name": "avgCo95", "title": "CO第95百分位(mg/m³)"},
            {"name": "rankPm25", "title": "PM2.5排名(升序,1=最优)"},
            {"name": "rankPm10", "title": "PM10排名(升序,1=最优)"},
            {"name": "rankSo2", "title": "SO2排名(升序,1=最优)"},
            {"name": "rankNo2", "title": "NO2排名(升序,1=最优)"},
            {"name": "rankO3", "title": "O3排名(升序,1=最优)"},
            {"name": "rankCo", "title": "CO排名(升序,1=最优)"},
            {"name": "officialZong", "title": "省APP官方综合指数(对照,≤2026-08)"},
            {"name": "officialRank", "title": "省APP官方排名(对照,≤2026-08,勿用)"},
        ],
        "dimensions": [
            {"name": "periodType", "title": "期次类型(daily单日/monthly/yearly)"},
            {"name": "period", "title": "期次(2026-10-09 / 2026-10 / 2026)"},
            {"name": "city", "title": "城市名(含济源市)"},
            {"name": "groupId", "title": "城市组ID"},
            {"name": "days", "title": "累计天数"},
            {"name": "validDays", "title": "六参数全有效天数"},
            {"name": "pmValidDays", "title": "PM2.5有效天数"},
            {"name": "computedAt", "title": "重算时间(时间维度)"},
        ],
    },
    # 许昌县级站小时: 站点目录见 xuchang_station_catalog(station_type=county),
    # 编码为河南实时发布系统数字编码(SiteID)。
    "SsfbSiteHour": {
        "measures": [
            {"name": "count", "title": "小时记录数"},
            {"name": "avgPm25", "title": "PM2.5均值(μg/m³)"},
            {"name": "avgPm10", "title": "PM10均值(μg/m³)"},
            {"name": "avgO3", "title": "O3均值(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h均值(μg/m³)"},
            {"name": "avgNo2", "title": "NO2均值(μg/m³)"},
            {"name": "avgSo2", "title": "SO2均值(μg/m³)"},
            {"name": "avgCo", "title": "CO均值(mg/m³)"},
            {"name": "maxAqi", "title": "AQI最大值"},
            {"name": "onlineSites", "title": "有数据站点数(去重)"},
        ],
        "dimensions": [
            {"name": "siteId", "title": "县级站编码(SiteID)"},
            {"name": "siteName", "title": "站点名"},
            {"name": "onlineType", "title": "站点类别(县级市控SK/县级省控SCK)"},
            {"name": "city", "title": "所属城市"},
            {"name": "county", "title": "归属区县(区县口径按此分组)"},
            {"name": "area", "title": "源平台区域"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "grade", "title": "AQI级别(1-6)"},
            {"name": "primaryPollutant", "title": "首要污染物"},
            {"name": "dataTime", "title": "数据时间(时间维度)"},
        ],
    },
    # 许昌县级站日值: 仅单日接口, 历史按日累积。
    "SsfbSiteDay": {
        "measures": [
            {"name": "count", "title": "站点日记录数"},
            {"name": "avgPm25", "title": "PM2.5日均(μg/m³)"},
            {"name": "avgPm10", "title": "PM10日均(μg/m³)"},
            {"name": "avgO38h", "title": "O3-8h日均(μg/m³)"},
            {"name": "avgNo2", "title": "NO2日均(μg/m³)"},
            {"name": "avgSo2", "title": "SO2日均(μg/m³)"},
            {"name": "avgCo", "title": "CO日均(mg/m³)"},
            {"name": "onlineSites", "title": "有数据站点数(去重)"},
        ],
        "dimensions": [
            {"name": "siteId", "title": "县级站编码(SiteID)"},
            {"name": "siteName", "title": "站点名"},
            {"name": "onlineType", "title": "站点类别"},
            {"name": "city", "title": "所属城市"},
            {"name": "county", "title": "归属区县"},
            {"name": "quality", "title": "空气质量等级"},
            {"name": "dataDate", "title": "数据日期(时间维度)"},
        ],
    },
}

ALLOWED_FILTER_OPERATORS = {
    "equals", "notEquals", "contains", "notContains", "in", "notIn",
    "afterDate", "beforeDate", "afterOrOnDate", "beforeOrOnDate",
    "set", "notSet",
}

DATA_WINDOW_NOTE = "数据窗口: 2026-10-03 起(源平台仅保留约8天滚动+每日累积);"


def _render_guide() -> str:
    lines = ["", "【语义目录】(成员名 = Cube.成员; 浓度单位 μg/m³,CO 为 mg/m³)"]
    for cube, parts in CATALOG.items():
        lines.append(f"\n■ {cube}")
        lines.append("  度量(measures): " + "; ".join(
            f"{m['name']}={m['title']}" for m in parts["measures"]))
        lines.append("  维度(dimensions): " + "; ".join(
            f"{d['name']}={d['title']}" for d in parts["dimensions"]))
    lines.append("")
    lines.append(
        DATA_WINDOW_NOTE
        + "排名类问题用 SsfbCityRanking(日排名 periodType=daily+period=日期;月/年排名 periodType=monthly/yearly);"
        "排名规则为数值越低越靠前(Rank*=1 最优),相同值并列;"
        "乡镇站(76个,2024起)用 TownHour/TownDay,必须过滤 caliber(app=审核,官方结论优先),"
        "否则原始与审核重复计数;"
        "OfficialZong/OfficialRank 是省APP对照列(仅2026-08前有值),勿与重算值混用。"
    )
    return "\n".join(lines)


def _make_token(secret: str, ttl_seconds: int = 300) -> str:
    """HS256 JWT（Cube API_SECRET 鉴权, 短时效, 每次调用现签）。"""
    def b64url(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64url(json.dumps({"exp": int(time.time()) + ttl_seconds}).encode())
    signature = b64url(
        hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{signature}"


class XuchangCubeMetricsTool(LLMTool):
    """经语义层查询许昌空气质量指标（口径唯一,免写SQL）。"""

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 1000

    def __init__(self):
        self.tool_name = "xuchang_cube_metrics"
        function_schema = {
            "name": self.tool_name,
            "description": (
                "查询许昌本地空气质量指标(语义层,口径唯一):河南18城市组(含济源)小时/日"
                "六参数与AQI、月/年累计单项浓度排名(数值越低排名越靠前,相同值并列,"
                "济源已纳入)、许昌县级站(鄢陵/襄城/禹州/长葛)小时/日数据、"
                "乡镇站(76个)小时/日数据(2024起,2025年起完整,审核/原始口径二选一)。"
                "传 measures+dimensions+时间范围即可,不需要写SQL;"
                "排名问题用 SsfbCityRanking 并过滤 periodType/period;"
                "乡镇站问题用 TownHour/TownDay 并过滤 caliber(官方结论用 app)。"
                + _render_guide()
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "measures": {
                        "type": "array", "items": {"type": "string"},
                        "description": "度量成员,如 ['SsfbCityRanking.rankPm25','SsfbCityRanking.avgPm25'],须同一Cube",
                    },
                    "dimensions": {
                        "type": "array", "items": {"type": "string"},
                        "description": "(可选)分组维度,如 ['SsfbCityRanking.city']",
                    },
                    "time_dimension": {
                        "type": "string",
                        "description": "(可选)时间维度成员,如 'SsfbCityHour.dataTime'",
                    },
                    "date_range": {
                        "description": "(可选)'last 7 days'等关键字,或 ['2026-10-03','2026-10-09']",
                    },
                    "granularity": {
                        "type": "string", "enum": ["hour", "day", "week", "month", "year"],
                        "description": "(可选)时间粒度,给趋势序列时用",
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "member": {"type": "string"},
                                "operator": {"type": "string"},
                                "values": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["member", "operator"],
                        },
                        "description": "(可选)过滤条件,如 SsfbCityRanking.period equals 2026-10、SsfbCityHour.city in [济源市,许昌市]",
                    },
                    "order": {
                        "type": "object",
                        "description": "(可选)排序,如 {'SsfbCityRanking.rankPm25':'asc'}",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回行数上限(默认50,最大1000)",
                        "default": 50,
                    },
                },
                "required": ["measures"],
            },
        }
        super().__init__(
            name=self.tool_name,
            description="查询许昌空气质量指标(语义层REST,口径唯一,免SQL,含济源排名)",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True,
        )

    # ------------------------------------------------------------ 校验
    def _member_cube(self, member: str, kind: str) -> Optional[str]:
        if "." not in member:
            return None
        cube, name = member.split(".", 1)
        part = CATALOG.get(cube)
        if not part:
            return None
        key = "measures" if kind == "measure" else "dimensions"
        if name not in {m["name"] for m in part[key]}:
            return None
        return cube

    def _validate(self, measures, dimensions, time_dimension, filters):
        if not measures:
            return None, "measures 不能为空"
        cubes = set()
        for m in measures:
            c = self._member_cube(m, "measure")
            if c is None:
                return None, f"未知度量 {m}(不在语义目录中)"
            cubes.add(c)
        for d in dimensions or []:
            c = self._member_cube(d, "dimension")
            if c is None:
                return None, f"未知维度 {d}(不在语义目录中)"
            cubes.add(c)
        if time_dimension:
            c = self._member_cube(time_dimension, "dimension")
            if c is None:
                return None, f"未知时间维度 {time_dimension}"
            cubes.add(c)
        for f in filters or []:
            member = str(f.get("member", ""))
            c = self._member_cube(member, "dimension")
            if c is None:
                return None, f"过滤条件成员未知或不是维度: {member}"
            if f.get("operator") not in ALLOWED_FILTER_OPERATORS:
                return None, f"不支持的过滤操作符: {f.get('operator')}"
            cubes.add(c)
        if len(cubes) > 1:
            return None, f"一次查询只能用一个 Cube 的成员,当前跨了: {sorted(cubes)}"
        return cubes.pop(), None

    # ------------------------------------------------------------ 执行
    async def execute(
        self,
        context: Optional["ExecutionContext"] = None,
        measures: Optional[List[str]] = None,
        dimensions: Optional[List[str]] = None,
        time_dimension: Optional[str] = None,
        date_range: Any = None,
        granularity: Optional[str] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
        order: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        cube, err = self._validate(measures, dimensions, time_dimension, filters)
        if err:
            return {"success": False, "data": None, "summary": f"参数校验失败: {err}"}

        query: Dict[str, Any] = {"measures": measures}
        if dimensions:
            query["dimensions"] = dimensions
        if time_dimension:
            td: Dict[str, Any] = {"dimension": time_dimension}
            if date_range:
                td["dateRange"] = date_range
            if granularity:
                td["granularity"] = granularity
            query["timeDimensions"] = [td]
        if filters:
            query["filters"] = filters
        if order:
            query["order"] = order
        query["limit"] = min(limit or self.DEFAULT_LIMIT, self.MAX_LIMIT)

        status, error, row_count = "ok", None, 0
        started = time.monotonic()
        try:
            base_url = os.getenv("CUBE_API_URL", "http://127.0.0.1:4610/cubejs-api/v1")
            secret = os.getenv("CUBE_API_SECRET", "")
            if not secret:
                raise RuntimeError("CUBE_API_SECRET 未配置(语义层鉴权)")

            token = _make_token(secret)
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{base_url}/load",
                    json={"query": query},
                    headers={"Authorization": token},
                )
                if resp.status_code != 200:
                    detail = resp.text[:500]
                    raise RuntimeError(f"语义层返回 {resp.status_code}: {detail}")
                body = resp.json()
                if "error" in body:
                    raise RuntimeError(f"语义层错误: {body['error']}")

            results = [
                {k: (v.get("value") if isinstance(v, dict) else v)
                 for k, v in row.items()}
                for row in body.get("data", [])
            ]
            row_count = len(results)
        except Exception as exc:
            logger.error(
                "xuchang_cube_metrics_failed",
                cube=cube,
                query=json.dumps(query, ensure_ascii=False),
                error=str(exc),
            )
            return {
                "success": False,
                "data": None,
                "metadata": {"tool_name": self.tool_name, "cube": cube},
                "summary": f"语义层查询失败: {exc}",
            }

        elapsed = round(time.monotonic() - started, 2)
        sample_data = results
        if context and len(results) > 24:
            saved_path = context.save_data(
                data=results,
                schema="metrics_query_result",
                metadata={"cube": cube, "query": query, "row_count": row_count},
            )
            sample_data = results[:12] + results[-12:]
            logger.info(
                "xuchang_cube_metrics_large_result_saved",
                path=str(saved_path),
                row_count=row_count,
            )

        summary = f"查询 {cube} 返回 {row_count} 行({elapsed}s)"
        return {
            "success": True,
            "data": sample_data,
            "metadata": {
                "tool_name": self.tool_name,
                "cube": cube,
                "row_count": row_count,
                "elapsed_seconds": elapsed,
                "truncated_to_sample": len(sample_data) < row_count,
            },
            "summary": summary,
        }
