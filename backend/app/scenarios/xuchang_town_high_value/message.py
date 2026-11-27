"""LLM 根据高值与气象证据组织提醒文案，代码不拼接业务句子。"""

from __future__ import annotations

import json
from typing import Any

from app.scenarios.xuchang_pollution_cause.notification import _extract_response_text


def message_evidence(group: dict[str, Any], weather: dict[str, Any]) -> dict[str, Any]:
    return {
        "hour": group["hour"].isoformat(),
        "pollutant": group["pollutant"],
        "delivery_mode": group["delivery_mode"],
        "stations": group["stations"],
        "weather": weather,
    }


async def render_message(
    group: dict[str, Any], weather: dict[str, Any], *, llm: Any | None = None
) -> str:
    if llm is None:
        from app.services.llm_service import llm_service
        llm = llm_service
    evidence = json.dumps(message_evidence(group, weather), ensure_ascii=False, indent=2)
    system = (
        "你是许昌市空气质量站点高值提醒编辑。证据包是唯一事实来源，不得补充、推断或修改任何数字。"
        "请用简洁、自然、适合微信工作群的中文组织一条【乡镇高值提醒】。"
        "同一污染物的全部高值站合并为一条，不得拆成多条；写清数据小时、站点名称、PM2.5或PM10实时小时浓度（微克/立方米）；"
        "每个站点均按GB 3095—2026过渡限值达到轻度污染及以上、连续高值，"
        "并与所在区县其他站点的小时中位数比较判定为空间离群；"
        "可自然概括空间对比（如明显高于所在区县其他站点水平），不要表述为全市对比，不要机械罗列全部判定字段。"
        "随后按证据中的county_name提醒对应属地加强上风向及站点周边污染源排查；"
        "county_name和station_type是站点目录提供的结构化事实，不得自行改判行政归属。"
        "气象证据包含温度、湿度、风向和风速时，用自然中文表达；缺测时明确写暂无可用气象观测。"
        "不要输出推理过程、JSON、Markdown或证据包原文。"
    )
    response = await llm.chat_anthropic(
        [{"role": "user", "content": f"请根据证据生成提醒：\n```json\n{evidence}\n```"}],
        system=system,
        max_tokens=1200,
    )
    message = llm.clean_thinking_tags(_extract_response_text(response)).strip()
    if not message:
        raise RuntimeError("LLM 未生成乡镇高值提醒")
    return message
