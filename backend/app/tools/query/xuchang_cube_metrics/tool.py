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

import asyncio
import base64
import difflib
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.path_config import resolve_agent_path
from .quality_policy import quality_guidance
from .result_contract import validate_result
from .semantic_registry import cube_metadata

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

# ---------------------------------------------------------------- 语义目录
# 成员真相: data-ops 管道生成产物 catalog.generated.json（cube/schema/*.js ×
# semantic/registry.yaml，生成器 projects/xuchang/data-ops/semantic/
# gen_semantic_artifacts.py，--check 漂移门）。改口径只改 schema/registry 后重跑生成器。
# fail-closed: 成员白名单是查询校验的地基，产物缺失/损坏必须启动即失败，不降级。
CATALOG_PATH = resolve_agent_path(
    "backend/app/tools/query/xuchang_cube_metrics/catalog.generated.json")


def _load_catalog() -> Dict[str, Dict[str, List[Dict[str, str]]]]:
    from pathlib import Path as _Path
    try:
        payload = json.loads(_Path(CATALOG_PATH).read_text(encoding="utf-8"))
        cubes = payload.get("cubes")
        if not isinstance(cubes, dict) or not cubes:
            raise ValueError("cubes 为空")
        return cubes
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"语义目录产物缺失: {CATALOG_PATH}; "
            "运行 projects/xuchang/data-ops/semantic/gen_semantic_artifacts.py 生成"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"语义目录产物损坏: {CATALOG_PATH} ({exc})") from exc


CATALOG: Dict[str, Dict[str, List[Dict[str, str]]]] = _load_catalog()

ALLOWED_FILTER_OPERATORS = {
    "equals", "notEquals", "contains", "notContains", "in", "notIn",
    "afterDate", "beforeDate", "afterOrOnDate", "beforeOrOnDate",
    "set", "notSet",
}

DATA_WINDOW_NOTE = "数据窗口: 2026-10-03 起(源平台仅保留约8天滚动+每日累积);"


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


async def cube_load(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    """执行一次 Cube Core /load 查询，返回解包 value 后的扁平行。

    工具执行路径（XuchangCubeMetricsTool.execute）与大屏快照 fetcher
    共用此入口，鉴权、排队等待与错误语义只维护一份。
    """
    base_url = os.getenv("CUBE_API_URL", "http://127.0.0.1:4610/cubejs-api/v1")
    secret = os.getenv("CUBE_API_SECRET", "")
    if not secret:
        raise RuntimeError("CUBE_API_SECRET 未配置(语义层鉴权)")

    token = _make_token(secret)
    wait_seconds = float(os.getenv("CUBE_API_WAIT_SECONDS", "60"))
    started = time.monotonic()
    deadline = started + wait_seconds
    body: Dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.post(
                f"{base_url}/load",
                json={"query": query},
                headers={"Authorization": token},
            )
            if resp.status_code != 200:
                detail = resp.text[:500]
                raise RuntimeError(f"语义层返回 {resp.status_code}: {detail}")
            body = resp.json()
            pending = str(body.get("error") or "")
            if "continue wait" not in pending.lower():
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"语义层查询排队超时({round(time.monotonic() - started, 1)}s): {pending}"
                )
            await asyncio.sleep(1.5)
    if body.get("error"):
        raise RuntimeError(f"语义层错误: {body['error']}")

    return [
        {k: (v.get("value") if isinstance(v, dict) else v)
         for k, v in row.items()}
        for row in body.get("data", [])
    ]


class XuchangCubeMetricsTool(LLMTool):
    """经语义层查询许昌空气质量指标（口径唯一,免写SQL）。"""

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 1000

    def __init__(self):
        self.tool_name = "xuchang_cube_metrics"
        function_schema = {
            "name": self.tool_name,
            "description": (
                "查询许昌本地空气质量指标(语义层,口径唯一,免SQL):河南18城市组(含济源)小时/日"
                "六参数与AQI、城市/区县/站点排名、全省区县(190个)与许昌县级站小时/日、"
                "乡镇站(76个,2024起)、官方月度统计(CountyMonth*/ProvinceMonth*)、"
                "年度目标(XuchangCityYearTarget等3个)、168城市排名(Rank168CityMonthly)。"
                "【路由】城市日排名=SsfbCityRanking(仅periodType=daily);"
                "区县排名=SsfbCounty*Rank,站点排名=SsfbSite*Rank(排名规则:数值越低越靠前,并列);"
                "月度及以上统计只用官方口径Cube(ProvinceMonth/Cum按level,CountyMonth/Cum),"
                "禁止把日值自算成月度及以上(自算走airdata_calc_report_summary或官方值);"
                "乡镇站小时/日用TownHour/TownDay且必须过滤caliber(官方结论用app,"
                "app断档时回退src并注明未审核);5分钟实时用TownFiveMinute(原始口径,AQI按HJ633推算)。"
                "【数据窗口】2026-10-03起(源仅保留约8天滚动+每日累积);月报/年度Cube窗口见describe。"
                "【成员目录】先用 describe_cube='cubes' 列全部Cube索引,"
                "再 describe_cube='<Cube名>' 取成员(measures/dimensions中文名)与口径/窗口/限制;"
                "成员名=Cube.成员,须同一Cube。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "measures": {
                        "type": "array", "items": {"type": "string"},
                        "description": "度量成员,如 ['SsfbCityRanking.rankPm25','SsfbCityRanking.avgPm25'],须同一Cube",
                    },
                    "describe_cube": {
                        "type": "string",
                        "description": "(可选)只查语义目录不执行查询:'cubes'列出全部Cube索引;传Cube名取其成员目录(中文名)、口径、窗口与限制",
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
                "required": [],
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

    def _suggest(self, member: str) -> str:
        """未知成员的相近名召回（错误信息即召回钩子）。"""
        cube, _, name = member.partition(".")
        part = CATALOG.get(cube) or {}
        candidates = [f"{cube}.{m['name']}" for m in part.get("measures", [])] + [
            f"{cube}.{d['name']}" for d in part.get("dimensions", [])
        ]
        close = difflib.get_close_matches(member, candidates, n=3, cutoff=0.6)
        return f";相近成员: {', '.join(close)}" if close else ";用 describe_cube='<Cube名>' 查该Cube成员目录"

    def _validate(self, measures, dimensions, time_dimension, filters):
        if not measures:
            return None, "measures 不能为空"
        cubes = set()
        for m in measures:
            c = self._member_cube(m, "measure")
            if c is None:
                return None, f"未知度量 {m}(不在语义目录中){self._suggest(m)}"
            cubes.add(c)
        for d in dimensions or []:
            c = self._member_cube(d, "dimension")
            if c is None:
                return None, f"未知维度 {d}(不在语义目录中){self._suggest(d)}"
            cubes.add(c)
        if time_dimension:
            c = self._member_cube(time_dimension, "dimension")
            if c is None:
                return None, f"未知时间维度 {time_dimension}{self._suggest(time_dimension)}"
            cubes.add(c)
        for f in filters or []:
            member = str(f.get("member", ""))
            c = self._member_cube(member, "dimension")
            if c is None:
                return None, f"过滤条件成员未知或不是维度: {member}{self._suggest(member)}"
            if f.get("operator") not in ALLOWED_FILTER_OPERATORS:
                return None, f"不支持的过滤操作符: {f.get('operator')}"
            cubes.add(c)
        if len(cubes) > 1:
            return None, f"一次查询只能用一个 Cube 的成员,当前跨了: {sorted(cubes)}"
        cube = cubes.pop()
        if cube in {"TownHour", "TownDay"}:
            caliber_filters = [
                f for f in filters or []
                if f.get("member") == f"{cube}.caliber"
            ]
            if not caliber_filters:
                return None, f"{cube} 必须明确过滤 caliber=app 或 caliber=src，避免原始与审核口径重复计数"
            values = {
                str(value) for item in caliber_filters for value in (item.get("values") or [])
            }
            if not values.intersection({"app", "src"}):
                return None, f"{cube}.caliber 只能使用 app 或 src"
        return cube, None

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
        describe_cube: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if describe_cube:
            if describe_cube in {"cubes", "all", "index", "目录", "全部"}:
                items = []
                for name in sorted(CATALOG):
                    meta = cube_metadata(name, CATALOG)
                    items.append({
                        "cube": name,
                        "measures": len(CATALOG[name]["measures"]),
                        "dimensions": len(CATALOG[name]["dimensions"]),
                        "applicability": meta.get("applicability"),
                        "source_window": meta.get("source_window"),
                    })
                return {
                    "success": True,
                    "cubes": items,
                    "summary": f"共 {len(items)} 个 Cube；传具体 Cube 名取成员目录",
                }
            if describe_cube not in CATALOG:
                close = difflib.get_close_matches(describe_cube, list(CATALOG), n=3, cutoff=0.6)
                hint = f"相近 Cube: {', '.join(close)}; " if close else ""
                return {
                    "success": False,
                    "summary": f"未知 Cube: {describe_cube}。{hint}用 describe_cube='cubes' 列出全部 Cube。",
                }
            semantic = cube_metadata(describe_cube, CATALOG)
            members = CATALOG[describe_cube]
            payload = {
                "success": True,
                "cube": describe_cube,
                "members": {
                    "measures": [
                        {"name": f"{describe_cube}.{m['name']}", "title": m.get("title", m["name"])}
                        for m in members["measures"]
                    ],
                    "dimensions": [
                        {"name": f"{describe_cube}.{d['name']}", "title": d.get("title", d["name"])}
                        for d in members["dimensions"]
                    ],
                },
                "semantic_context": {
                    "registry_version": semantic.get("registry_version", 0),
                    "dataset": semantic.get("dataset"),
                    "grain": semantic.get("grain"),
                    "applicability": semantic.get("applicability"),
                    "source_window": semantic.get("source_window"),
                    "limitations": semantic.get("limitations", []),
                    "metric_definitions": semantic.get("measures", {}),
                },
                "summary": f"{describe_cube} 成员目录与指标定义（registry v{semantic.get('registry_version', 0)}）",
            }
            contract_errors = validate_result("metric_definition", payload)
            if contract_errors:
                logger.warning("xuchang_metric_definition_contract_violation", errors=contract_errors)
            return payload
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
            results = await cube_load(query)
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

        semantic = cube_metadata(cube, CATALOG)
        data_as_of = self._infer_data_as_of(results)
        if not row_count:
            quality_status = "blocked"
        elif data_as_of:
            quality_status = "ok"
        else:
            quality_status = "degraded"
        payload = {
            "success": True,
            "data": sample_data,
            "metadata": {
                "tool_name": self.tool_name,
                "cube": cube,
                "row_count": row_count,
                "elapsed_seconds": elapsed,
                "truncated_to_sample": len(sample_data) < row_count,
            },
            "count": row_count,
            "sample_count": len(sample_data),
            "data_as_of": data_as_of,
            "quality_status": quality_status,
            "semantic_context": {
                "registry_version": semantic.get("registry_version", 0),
                "dataset": semantic.get("dataset"),
                "grain": semantic.get("grain"),
                "applicability": semantic.get("applicability"),
                "source_window": semantic.get("source_window"),
                "limitations": semantic.get("limitations", []),
                "metric_definitions": {
                    member.split(".", 1)[-1]: semantic.get("measures", {}).get(member.split(".", 1)[-1], {})
                    for member in measures or []
                },
                "quality_guidance": quality_guidance(quality_status),
            },
            "summary": f"查询 {cube} 返回 {row_count} 行({elapsed}s，数据截至 {data_as_of or '未能从结果推断'})",
        }
        contract_errors = validate_result("metric_query", payload)
        if contract_errors:
            logger.warning("xuchang_metric_result_contract_violation", errors=contract_errors)
        return payload

    _TIME_KEY_NAMES = frozenset({
        "datatime", "datadate", "computedat", "period", "datamonth",
        "periodend", "month", "day", "hour",
    })
    _DATE_LIKE = re.compile(r"^\d{4}-\d{2}(-\d{2})?")

    @classmethod
    def _infer_data_as_of(cls, results: List[Dict[str, Any]]) -> Optional[str]:
        values = []
        for row in results:
            for key, value in row.items():
                short_key = str(key).lower().rsplit(".", 1)[-1]
                if short_key not in cls._TIME_KEY_NAMES or value is None:
                    continue
                text = str(value).strip()
                if cls._DATE_LIKE.match(text):
                    values.append(text)
        return max(values) if values else None
