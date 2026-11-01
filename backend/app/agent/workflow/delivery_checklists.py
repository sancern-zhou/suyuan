"""交付验收清单（助手单入口方案 · 阶段 C）。

两层设计，对应方案"机制现在开发、内容观察期定稿"：

- ``checklist_text(mode)``：交付前注入子 Agent 提示词的定性验收条目
  （"什么算完成"）。v1 内容源自 target_mode_contract 的产出定义与
  ORCHESTRATION.md 的缺口纪律；试运行观察期按真实 would_reject 案例
  修订——改的是本文件的数据，不是校验逻辑。
- ``evaluate_delivery_checklist(mode, structured_result, mandate)``：交付
  路径上的机械化核验（键存在性与类型），违规以 {"path","expected","got"}
  形状返回，与 result_schema 校验错误同通道（喂给既有修复轮）。

开关 ``settings.delivery_checklist_mode``：off / observe / enforce，
默认 observe——只记录不拦截，由调用方决定是否并入校验错误。
B2 落地后父模型经常只看摘要卡，验收必须代码化在交付路径上，
不能依赖父模型通读全量结果。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_EXPERT_MODES = frozenset(
    {"expert", "expert_meteorology", "expert_analysis", "expert_component"}
)
_QUERY_MODES = frozenset(
    {
        "query",
        "query_monitoring",
        "query_monitoring_station",
        "query_monitoring_city",
        "query_forecast",
        "query_component",
    }
)

# 通用定性条目：所有结构化交付共用（C4 缺口纪律的提示词侧）。
_GENERIC_TEXT: tuple[str, ...] = (
    "结果必须包含 `data_gaps` 字段：无缺口给空数组；缺失数据必须声明，"
    "不得当作零或省略。",
    "结论必须能追溯到证据或交付文件；无法支撑的表述降级为不确定性。",
)

# 定性验收条目（"什么算完成"），按模式追加；试运行期按案例修订。
CHECKLIST_TEXT: Dict[str, tuple[str, ...]] = {
    "expert": (
        "结论逐条对应证据；气象/成因判断引用数据或上游节点结论并注明来源。",
    ),
    "expert_meteorology": (
        "气象条件判断须引用观测/预报数据或上游节点产物，注明起报时间与时效。",
    ),
    "expert_analysis": (
        "浓度特征与超标统计注明时间范围、层级（城市/站点）与数据口径。",
    ),
    "expert_component": (
        "组分结论注明站点、小时窗口与数据质量口径（原始/审核）。",
    ),
    "query_monitoring_station": (
        "站点数据注明站点清单、时间粒度与口径；乡镇站编码须来自目录解析。",
    ),
    "query_monitoring_city": (
        "城市数据注明城市清单、时间粒度与口径；全国对比注明样本范围。",
    ),
    "query_forecast": (
        "预报数据注明起报时间、时效与要素口径；只交付数据不做研判。",
    ),
    "query_component": (
        "组分数据注明站点、小时窗口（≤24h）与质量口径；无组分站点的城市如实声明。",
    ),
    "ppt": (
        "交付可编辑 PPTX 文件；逐页检查内容溢出与布局，附检查说明。",
    ),
    "board": (
        "交付可编辑图形文件；元素结构与连接关系完整可再编辑。",
    ),
    "office": (
        "交付经核对的办公文件与处理说明；文件路径真实存在。",
    ),
    "knowledge": (
        "回答附知识库与文档出处；识别资料冲突与缺口。",
    ),
    "ops": (
        "处置结论附工单/日志依据；建议可执行且标注前提条件。",
    ),
}


def checklist_text(mode: str) -> str:
    """交付前注入子 Agent 的验收清单文本（通用 + 按模式）。"""
    items = list(_GENERIC_TEXT) + list(CHECKLIST_TEXT.get(str(mode), ()))
    return "".join(f"- {item}\n" for item in items)


def _violation(path: str, expected: str, got: Any) -> Dict[str, Any]:
    return {"path": path, "expected": expected, "got": got}


def evaluate_delivery_checklist(
    mode: str,
    structured_result: Dict[str, Any],
    mandate: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """机械化核验：只查键存在性与类型，不做内容判断。

    - data_gaps（或别名 gaps）必须存在且为数组——C4 缺口纪律的统一落点
      （EXPERT_ANALYSIS_RESULT_SCHEMA 已 required，这里覆盖自定义 schema）。
    - 提供 mandate 时，结果必须带 scope 对象，声明对授权边界的实际覆盖。
    """
    violations: List[Dict[str, Any]] = []
    if not isinstance(structured_result, dict):
        return violations
    gaps = structured_result.get("data_gaps")
    if gaps is None:
        gaps = structured_result.get("gaps")
    if gaps is None:
        violations.append(
            _violation(
                "$.data_gaps",
                "缺口声明字段（缺失数据不得当作零或省略）",
                "字段缺失",
            )
        )
    elif not isinstance(gaps, list):
        violations.append(
            _violation("$.data_gaps", "array", type(gaps).__name__)
        )
    if isinstance(mandate, dict) and mandate:
        scope = structured_result.get("scope")
        if scope is None:
            violations.append(
                _violation(
                    "$.scope",
                    "object（对照 mandate 授权边界声明实际覆盖范围与限制）",
                    "字段缺失",
                )
            )
        elif not isinstance(scope, dict):
            violations.append(
                _violation("$.scope", "object", type(scope).__name__)
            )
    return violations
