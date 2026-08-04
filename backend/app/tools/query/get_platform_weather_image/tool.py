from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import single_file_product
from app.tools.resource_refs import build_file_ref, build_url_ref, build_visual_ref
from app.tools.utility.project_root import get_project_root
from app.services.image_cache import get_image_cache

logger = structlog.get_logger()

BASE_URL = "http://10.10.10.112:8313"


@dataclass(frozen=True)
class WeatherImageProduct:
    key: str
    code: str
    name: str
    description: str
    filename_template: str
    required: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    file_extension: str = "png"
    allowed_forecast_hours: tuple[int, ...] | None = None
    allowed_hours: tuple[int, ...] | None = None
    hour_min: int | None = None
    hour_max: int | None = None
    minute_step: int | None = None


PRODUCTS: dict[str, WeatherImageProduct] = {
    "forecast_trajectory": WeatherImageProduct(
        key="forecast_trajectory",
        code="1013",
        name="城市预测轨迹图",
        description="城市预测轨迹图，每天一张，文件名为中国天气城市编码加日期。",
        filename_template="{city_code}{date}.gif",
        required=("city_code",),
        aliases=("城市预测轨迹图", "预测轨迹图", "forecast_track", "forecast_trajectory_map"),
        file_extension="gif",
    ),
    "backward_trajectory": WeatherImageProduct(
        key="backward_trajectory",
        code="1014",
        name="城市后向轨迹图",
        description="城市后向轨迹图，每日一张，文件名为中国天气城市编码加轨迹日期。",
        filename_template="{city_code}{trajectory_date}.gif",
        required=("city_code", "trajectory_date"),
        aliases=("城市后向轨迹图", "后向轨迹图", "backward_track", "backward_trajectory_map"),
        file_extension="gif",
    ),
    "national_precip_forecast": WeatherImageProduct(
        key="national_precip_forecast",
        code="1012",
        name="全国降水量预报图",
        description="中央气象台全国降水量预报图，时效使用三位数，例如024、048。",
        filename_template="--%2B--%2B--%2B--%2B{forecast_hour:03d}%2B--%2B--.png",
        required=("forecast_hour",),
        aliases=("全国降水量预报图", "降水量预报图", "national_rain_forecast"),
    ),
    "hourly_precip_forecast": WeatherImageProduct(
        key="hourly_precip_forecast",
        code="1023",
        name="逐时降水量预报图",
        description="逐时降水量预报图，每隔6小时一张，时效为06、12、18、24。",
        filename_template="00%2B--%2B--%2B--%2B{forecast_hour:02d}%2B--%2B--.png",
        required=("forecast_hour",),
        aliases=("逐时降水量预报图", "逐时降水预报", "hourly_rain_forecast"),
        allowed_forecast_hours=(6, 12, 18, 24),
    ),
    "visibility": WeatherImageProduct(
        key="visibility",
        code="1034",
        name="中央气象台能见度图",
        description="中央气象台能见度图，每小时一张。",
        filename_template="--%2B--%2B--%2B--%2B--%2B{hour:02d}%2B00.png",
        required=("hour",),
        aliases=("中央气象台能见度图", "能见度图", "visibility_map"),
        hour_min=0,
        hour_max=23,
    ),
    "radar_mosaic": WeatherImageProduct(
        key="radar_mosaic",
        code="1041",
        name="全国雷达拼图",
        description="全国雷达拼图，从08:00到23:36，每6分钟一张。",
        filename_template="--%2B--%2BACHN%2B--%2B--%2B{hour:02d}%2B{minute:02d}.png",
        required=("hour", "minute"),
        aliases=("全国雷达拼图", "雷达拼图", "radar"),
        hour_min=8,
        hour_max=23,
        minute_step=6,
    ),
    "rainfall_24h": WeatherImageProduct(
        key="rainfall_24h",
        code="1051",
        name="全国24小时降水量",
        description="全国24小时降水量，每天固定00、06、12三个小时各一张。",
        filename_template="--%2B--%2B--%2B--%2B--%2B{hour:02d}%2B--.png",
        required=("hour",),
        aliases=("全国24小时降水量", "24小时降水量", "24h_rainfall"),
        allowed_hours=(0, 6, 12),
    ),
    "hourly_wind_field": WeatherImageProduct(
        key="hourly_wind_field",
        code="1052",
        name="全国逐小时风场实况图",
        description="全国逐小时风场实况图，每天从00时开始，到07时结束。",
        filename_template="--%2B--%2B--%2B--%2B--%2B{hour:02d}%2B--.png",
        required=("hour",),
        aliases=("全国逐小时风场实况图", "逐小时风场实况图", "风场实况图", "hourly_wind"),
        hour_min=0,
        hour_max=7,
    ),
    "radar_composite_reflectivity": WeatherImageProduct(
        key="radar_composite_reflectivity",
        code="2111",
        name="全国雷达组合反射率图",
        description="全国雷达组合反射率图，每天从001时效到072时效。",
        filename_template="00%2B--%2BEBREF_ACHN_LN0_PB%2B--%2B{forecast_hour:03d}%2B--%2B--.png",
        required=("forecast_hour",),
        aliases=("全国雷达组合反射率图", "雷达组合反射率图", "组合反射率图"),
        allowed_forecast_hours=tuple(range(1, 73)),
    ),
    "precipitable_water": WeatherImageProduct(
        key="precipitable_water",
        code="2111",
        name="整层可降水量",
        description="整层可降水量，样例包含000时效，常用范围到072时效。",
        filename_template="00%2B--%2BERFA_ACHN_L00_PB%2B--%2B{forecast_hour:03d}%2B--%2B--.png",
        required=("forecast_hour",),
        aliases=("整层可降水量", "可降水量", "precipitable_water_total"),
        allowed_forecast_hours=tuple(range(0, 73)),
    ),
    "***REMOVED***": WeatherImageProduct(
        key="***REMOVED***",
        code="2111",
        name="24H内的10m最大风速",
        description="24H内的10m最大风速，分为024、048、072三个预报尺度图。",
        filename_template="00%2B--%2BEDSMAX_ACHN_L10M_P9%2B--%2B{forecast_hour:03d}%2B--%2B--.png",
        required=("forecast_hour",),
        aliases=("24H内的10m最大风速", "10m最大风速", "24小时10m最大风速", "max_10m_wind"),
        allowed_forecast_hours=(24, 48, 72),
    ),
    "***REMOVED***": WeatherImageProduct(
        key="***REMOVED***",
        code="2111",
        name="24H降水预报",
        description="24H降水预报，预报从024时开始到072时结束，每小时一张图。",
        filename_template="00%2B--%2BER24_ACHN_L88_PB%2B--%2B{forecast_hour:03d}%2B--%2B--.png",
        required=("forecast_hour",),
        aliases=("24H降水预报", "24小时降水预报", "24h_precip_forecast"),
        allowed_forecast_hours=tuple(range(24, 73)),
    ),
    "grapes_gfs_radar_reflectivity": WeatherImageProduct(
        key="grapes_gfs_radar_reflectivity",
        code="2112",
        name="GRAPES_GFS(雷达组合反射率)预报图",
        description="GRAPES_GFS(雷达组合反射率)预报图，从003时开始到240时结束，每3小时一张。",
        filename_template="00%2B--%2B--%2B--%2B{forecast_hour:03d}%2B--%2B--.png",
        required=("forecast_hour",),
        aliases=("GRAPES_GFS(雷达组合反射率)预报图", "GRAPES_GFS雷达组合反射率", "grapes_gfs"),
        allowed_forecast_hours=tuple(range(3, 241, 3)),
    ),
    "national_max_temperature_forecast": WeatherImageProduct(
        key="national_max_temperature_forecast",
        code="2114",
        name="中央气象台全国气温预报图（最高气温）",
        description="中央气象台全国气温预报图（最高气温），从024时开始到240时结束，每24小时一张。",
        filename_template="--%2B--%2BETM%2B--%2B{forecast_hour:03d}%2B--%2B--.png",
        required=("forecast_hour",),
        aliases=("全国气温预报图最高气温", "最高气温预报图", "全国最高气温预报"),
        allowed_forecast_hours=tuple(range(24, 241, 24)),
    ),
    "national_min_temperature_forecast": WeatherImageProduct(
        key="national_min_temperature_forecast",
        code="2114",
        name="中央气象台全国气温预报图（最低气温）",
        description="中央气象台全国气温预报图（最低气温），从024时开始到240时结束，每24小时一张。",
        filename_template="--%2B--%2BETN%2B--%2B{forecast_hour:03d}%2B--%2B--.png",
        required=("forecast_hour",),
        aliases=("全国气温预报图最低气温", "最低气温预报图", "全国最低气温预报"),
        allowed_forecast_hours=tuple(range(24, 241, 24)),
    ),
}

PRODUCT_ALIASES = {
    alias: product.key
    for product in PRODUCTS.values()
    for alias in (product.key, product.name, *product.aliases)
}

FORECAST_TRAJECTORY_CITY_CODES = {
    "南昌": "101240101",
    "南昌市": "101240101",
    "广州": "101280101",
    "广州市": "101280101",
    "韶关": "101280201",
    "韶关市": "101280201",
    "惠州": "101280301",
    "惠州市": "101280301",
    "梅县": "101280409",
    "汕头": "101280501",
    "汕头市": "101280501",
    "深圳": "101280601",
    "深圳市": "101280601",
    "珠海": "101280701",
    "珠海市": "101280701",
    "佛山": "101280803",
    "佛山市": "101280803",
    "高要": "101280908",
    "湛江": "101281001",
    "湛江市": "101281001",
    "新会": "101281104",
    "河源": "101281201",
    "河源市": "101281201",
    "清远": "101281301",
    "清远市": "101281301",
    "云浮": "101281401",
    "云浮市": "101281401",
    "潮州": "101281501",
    "潮州市": "101281501",
    "东莞": "101281601",
    "东莞市": "101281601",
    "中山": "101281701",
    "中山市": "101281701",
    "阳江": "101281801",
    "阳江市": "101281801",
    "揭阳": "101281901",
    "揭阳市": "101281901",
    "茂名": "101282001",
    "茂名市": "101282001",
    "汕尾": "101282101",
    "汕尾市": "101282101",
    "贵港": "101300801",
    "贵港市": "101300801",
}


def normalize_date(date: str | None) -> str:
    if not date:
        return datetime.now().strftime("%Y%m%d")
    value = str(date).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValueError(f"日期格式错误，应为YYYYMMDD或YYYY-MM-DD，当前值: {date}")


def resolve_product(product: str) -> WeatherImageProduct:
    key = PRODUCT_ALIASES.get(str(product).strip())
    if not key:
        valid = ", ".join(PRODUCTS)
        raise ValueError(f"未知图片产品: {product}。可选值: {valid}")
    return PRODUCTS[key]


def _require_int(name: str, value: int | str | None) -> int:
    if value is None or value == "":
        raise ValueError(f"缺少必填参数: {name}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是整数，当前值: {value}") from exc


def _resolve_trajectory_city_code(value: str) -> str:
    if value.isdigit() and len(value) == 9:
        return value
    city_code = FORECAST_TRAJECTORY_CITY_CODES.get(value)
    if not city_code:
        valid = "、".join(sorted(FORECAST_TRAJECTORY_CITY_CODES))
        raise ValueError(f"未知预测轨迹图城市: {value}。可选城市: {valid}，或直接传9位城市编码")
    return city_code


def _parse_compact_date(name: str, value: str) -> str:
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValueError(f"{name} 日期格式错误，应为YYYYMMDD或YYYY-MM-DD，当前值: {value}")


def _parse_time_value(product: WeatherImageProduct, time: int | str | None) -> dict[str, int | str]:
    if time is None or time == "":
        raise ValueError("缺少必填参数: time")

    raw = str(time).strip()
    if "city_code" in product.required and "trajectory_date" in product.required:
        separator = "," if "," in raw else "|" if "|" in raw else None
        if not separator:
            raise ValueError(f"{product.name} time 应为 城市,轨迹日期，例如 南昌,20260608")
        city_text, trajectory_date_text = [item.strip() for item in raw.split(separator, 1)]
        if not city_text or not trajectory_date_text:
            raise ValueError(f"{product.name} time 应为 城市,轨迹日期，例如 南昌,20260608")
        return {
            "city_code": _resolve_trajectory_city_code(city_text),
            "trajectory_date": _parse_compact_date("trajectory_date", trajectory_date_text),
        }

    if "city_code" in product.required:
        return {"city_code": _resolve_trajectory_city_code(raw)}

    if "hour" in product.required and "minute" in product.required:
        if ":" in raw:
            hour_text, minute_text = raw.split(":", 1)
        elif len(raw) in (3, 4) and raw.isdigit():
            hour_text, minute_text = raw[:-2], raw[-2:]
        else:
            raise ValueError(f"{product.name} time 应为HH:MM或HHMM，当前值: {time}")
        return {
            "hour": _require_int("hour", hour_text),
            "minute": _require_int("minute", minute_text),
        }

    if "forecast_hour" in product.required:
        return {"forecast_hour": _require_int("forecast_hour", raw)}

    if "hour" in product.required:
        return {"hour": _require_int("hour", raw)}

    raise ValueError(f"{product.name} 未配置time解析规则")


def _validate_product_time(
    product: WeatherImageProduct,
    *,
    values: dict[str, int | str],
) -> dict[str, int | str]:
    if "city_code" in values:
        return values

    if product.allowed_forecast_hours and values["forecast_hour"] not in product.allowed_forecast_hours:
        if product.key == "radar_composite_reflectivity":
            raise ValueError(f"{product.name} 只支持 forecast_hour: 001 到 072")
        if product.key == "precipitable_water":
            raise ValueError(f"{product.name} 只支持 forecast_hour: 000 到 072")
        if product.key == "***REMOVED***":
            raise ValueError(f"{product.name} 只支持 forecast_hour: 024, 048, 072")
        if product.key == "***REMOVED***":
            raise ValueError(f"{product.name} 只支持 forecast_hour: 024 到 072")
        if product.key == "grapes_gfs_radar_reflectivity":
            raise ValueError(f"{product.name} 只支持 forecast_hour: 003 到 240，每3小时一张")
        if product.key in {"national_max_temperature_forecast", "national_min_temperature_forecast"}:
            raise ValueError(f"{product.name} 只支持 forecast_hour: 024 到 240，每24小时一张")
        allowed = ", ".join(f"{item:02d}" for item in product.allowed_forecast_hours)
        raise ValueError(f"{product.name} 只支持 forecast_hour: {allowed}")

    if product.allowed_hours and values["hour"] not in product.allowed_hours:
        allowed = ", ".join(f"{item:02d}" for item in product.allowed_hours)
        raise ValueError(f"{product.name} 只支持 hour: {allowed}")

    if "hour" in values:
        if product.hour_min is not None and values["hour"] < product.hour_min:
            raise ValueError(f"{product.name} hour 不能早于 {product.hour_min:02d}")
        if product.hour_max is not None and values["hour"] > product.hour_max:
            raise ValueError(f"{product.name} hour 不能晚于 {product.hour_max:02d}")

    if "minute" in values:
        if not 0 <= values["minute"] <= 59:
            raise ValueError("minute 必须在0到59之间")
        if product.minute_step and values["minute"] % product.minute_step != 0:
            raise ValueError(f"{product.name} minute 必须按{product.minute_step}分钟间隔取值")
        if product.key == "radar_mosaic" and values["hour"] == 23 and values["minute"] > 36:
            raise ValueError("全国雷达拼图最晚到23:36")

    return values


def build_weather_image_url(
    product: str,
    *,
    date: str | None = None,
    time: int | str | None = None,
) -> str:
    product_spec = resolve_product(product)
    date_key = normalize_date(date)
    values = _validate_product_time(
        product_spec,
        values=_parse_time_value(product_spec, time),
    )
    filename = product_spec.filename_template.format(**values, date=date_key)
    return f"{BASE_URL}/{product_spec.code}/{date_key}/{filename}"


def _time_key(product: WeatherImageProduct, values: dict[str, int | str]) -> str:
    if "city_code" in values and "trajectory_date" in values:
        return f"{values['city_code']}_{values['trajectory_date']}"
    if "city_code" in values:
        return str(values["city_code"])
    if "forecast_hour" in values:
        width = 3 if "{forecast_hour:03d}" in product.filename_template else 2
        return f"{values['forecast_hour']:0{width}d}"
    if "minute" in values:
        return f"{values['hour']:02d}{values['minute']:02d}"
    return f"{values['hour']:02d}"


class GetPlatformWeatherImageTool(LLMTool):
    def __init__(
        self,
        output_root: Path | str | None = None,
        client_factory: Callable[..., Any] | None = None,
    ):
        self.output_root = Path(output_root) if output_root else (
            get_project_root()
            / "backend"
            / "backend_data_registry"
            / "external_images"
            / "weather_platform"
        )
        self.client_factory = client_factory or httpx.AsyncClient

        function_schema = {
            "name": "get_platform_weather_image",
            "description": (
                "获取气象图片URL并保存。调用前必须阅读："
                "backend/app/tools/query/get_platform_weather_image/GET_PLATFORM_WEATHER_IMAGE_GUIDE.md。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product": {
                        "type": "string",
                        "description": "产品标准值，见指导文档。",
                    },
                    "date": {
                        "type": "string",
                        "description": "日期YYYYMMDD或YYYY-MM-DD，默认当天。",
                    },
                    "time": {
                        "type": "string",
                        "description": "时间/时效字符串，格式按指导文档，如024、06、15:12。",
                    },
                    "download": {
                        "type": "boolean",
                        "description": "是否下载，默认true。",
                        "default": True,
                    },
                },
                "required": ["product", "time"],
            },
        }
        super().__init__(
            name="get_platform_weather_image",
            description="Generate and download weather image URLs from the Suncere data platform",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        product: str,
        date: str | None = None,
        time: int | str | None = None,
        download: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        try:
            product_spec = resolve_product(product)
            date_key = normalize_date(date)
            values = _validate_product_time(
                product_spec,
                values=_parse_time_value(product_spec, time),
            )
            source_url = build_weather_image_url(
                product_spec.key,
                date=date_key,
                time=time,
            )
            time_key = _time_key(product_spec, values)
            local_path = (
                self.output_root
                / product_spec.key
                / date_key
                / f"{time_key}.{product_spec.file_extension}"
            )

            downloaded = False
            frontend_image_url = None
            image_id = None
            if download:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                async with self.client_factory(timeout=20.0, follow_redirects=True) as client:
                    response = await client.get(source_url)
                    response.raise_for_status()
                    local_path.write_bytes(response.content)
                    image_id = f"weather_platform_{product_spec.key}_{date_key}_{time_key}"
                    cached = get_image_cache().save(
                        base64.b64encode(response.content).decode("utf-8"),
                        chart_id=image_id,
                    )
                    frontend_image_url = cached["url"]
                    downloaded = True

            logger.info(
                "platform_weather_image_ready",
                product=product_spec.key,
                date=date_key,
                time_key=time_key,
                downloaded=downloaded,
            )
            visual = None
            if frontend_image_url:
                visual = {
                    "id": image_id,
                    "type": "image",
                    "title": f"{date_key} {product_spec.name} {time_key}",
                    "image_url": frontend_image_url,
                    "local_path": str(local_path),
                    "markdown_image": f"![{date_key} {product_spec.name} {time_key}]({frontend_image_url})",
                }
            file_ref = build_file_ref(
                local_path,
                type="image",
                format=product_spec.file_extension,
                usage="tool_input",
                preferred_for=["read_file"],
            )
            url_refs = [build_url_ref(source_url, usage="source", source="source_url")]
            visual_refs = []
            if visual:
                url_refs.insert(0, build_url_ref(frontend_image_url, usage="display", source="image_url"))
                visual_refs.append(
                    build_visual_ref(
                        id=image_id,
                        type="image",
                        title=visual["title"],
                        image_url=frontend_image_url,
                        local_path=str(local_path),
                    )
                )
            refs = {
                "files": [file_ref],
                "urls": url_refs,
            }
            if visual_refs:
                refs["visuals"] = visual_refs

            result = {
                "success": True,
                "status": "success",
                "data": {
                    "product": product_spec.key,
                    "product_name": product_spec.name,
                    "date": date_key,
                    "time_key": time_key,
                    "source_url": source_url,
                    "image_url": frontend_image_url,
                    "image_id": image_id,
                    "local_path": str(local_path),
                    "downloaded": downloaded,
                    "visuals": [visual] if visual else [],
                    "source": "环境大数据管理云平台",
                },
                "refs": refs,
                "llm_resume": {
                    "tool_hint": (
                        f"Use read_file(path='{local_path}', as_multimodal_attachment=true) "
                        "to inspect this image."
                    ),
                },
                "metadata": {
                    "schema_version": "v1.0",
                    "generator": "get_platform_weather_image",
                    "product_code": product_spec.code,
                    "output_root": str(self.output_root),
                },
                "resources": [single_file_product(local_path, tool_name=self.name)],
                "summary": f"已获取{date_key} {product_spec.name} {time_key} 图片",
            }
            if visual:
                result["visuals"] = [visual]
            return result
        except Exception as exc:
            return {
                "success": False,
                "status": "failed",
                "error": str(exc),
                "data": None,
                "metadata": {
                    "schema_version": "v1.0",
                    "generator": "get_platform_weather_image",
                },
                "summary": f"获取平台气象图片失败：{str(exc)[:80]}",
            }
