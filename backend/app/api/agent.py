"""
ReAct Agent API Routes

ReAct Agent 的 REST API 路由
"""

from fastapi import APIRouter, HTTPException, Body, Depends, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import json
import structlog

from app.agent import create_react_agent
from app.agent.active_contexts import (
    ACTIVE_CONTEXTS_KEY,
    active_contexts_metadata,
    effective_active_context_items,
    resolve_active_contexts,
)
from app.agent.session import Session, get_session_manager
from app.agent.session.conversation_persistence import ConversationPersistenceService
from app.agent.runtime.cancellation import PauseCheckpointError, cancellation_registry
from app.agent.runtime.steering import steering_registry
from app.agent.runtime.ownership import run_ownership_registry
from app.agent.selection_context import (
    InvalidContextReference,
    resource_refs_to_message_attachments,
    select_conversation_resources,
)
from app.agent.resources.resource_service import SessionResourceService
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.boards.application import BoardApplicationService
from app.boards.service import BoardNotFound, BoardVersionConflict, BoardVersionNotFound
from app.conversations import ConversationSource
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService
from app.core.sse import create_sse_response
from app.db.database import async_session
from app.services.llm_service import llm_service
from app.tools import global_tool_registry

logger = structlog.get_logger()

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _safe_preview(value: Any, max_chars: int = 100) -> str:
    if value is None:
        return "empty"
    if isinstance(value, str):
        return value[:max_chars] if value else "empty"
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:max_chars]
    except Exception:
        return repr(value)[:max_chars]


async def _await_cancellation_resistant(awaitable):
    """Finish a transcript commit even if the disconnected SSE is cancelled again."""
    task = asyncio.create_task(awaitable)
    current = asyncio.current_task()
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if current is not None and hasattr(current, "uncancel"):
                while current.cancelling():
                    current.uncancel()
    return task.result()


def _build_user_message_for_history(
    query: str,
    attachments: Optional[List[dict]],
    *,
    timestamp: str,
) -> Dict[str, Any]:
    """Build the canonical persisted user-message contract."""
    message: Dict[str, Any] = {
        "type": "user",
        "content": query,
        "timestamp": timestamp,
    }
    normalized_attachments = [
        dict(attachment)
        for attachment in attachments or []
        if isinstance(attachment, dict)
    ]
    if normalized_attachments:
        message["attachments"] = normalized_attachments
    return message


def _append_attachment_text_for_history(
    query: str,
    attachments: Optional[List[dict]],
) -> str:
    """Legacy formatter retained for non-persistence compatibility callers."""
    if not attachments:
        return query

    lines = ["", "", "**用户上传的附件**："]
    for index, attachment in enumerate(attachments, start=1):
        if not isinstance(attachment, dict):
            continue
        attachment_type = attachment.get("type", "file")
        name = attachment.get("name") or attachment.get("filename") or "unknown"
        path = (
            attachment.get("local_path")
            or attachment.get("file_path")
            or attachment.get("path")
            or attachment.get("url")
            or attachment.get("file_id")
            or ""
        )
        lines.append(f"{index}. {'图片' if attachment_type == 'image' else '文件'}: {name}")
        if path:
            lines.append(f"   路径: {path}")

    return query if len(lines) <= 3 else query + "\n".join(lines)


def merge_map_scene_metadata(
    metadata: Optional[Dict[str, Any]],
    map_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    next_metadata = dict(metadata or {})
    if not isinstance(map_context, dict):
        return next_metadata

    current_program = map_context.get("current_program")
    if not isinstance(current_program, dict) or not current_program.get("program_id"):
        return next_metadata

    existing_scene = next_metadata.get("map_scene")
    if not isinstance(existing_scene, dict):
        existing_scene = {}
    existing_program = existing_scene.get("current_map_program")
    if not isinstance(existing_program, dict):
        existing_program = existing_scene.get("currentMapProgram")
    if isinstance(existing_program, dict):
        current_program = merge_map_programs(existing_program, current_program)

    next_metadata["map_scene"] = {
        **existing_scene,
        "current_map_program": current_program,
        "updated_at": datetime.now().isoformat(),
    }
    return next_metadata


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _lifecycle_group(item: Dict[str, Any]) -> str:
    lifecycle = item.get("lifecycle") if isinstance(item.get("lifecycle"), dict) else {}
    return lifecycle.get("group") or "current_answer"


def _merge_items_by_id(existing_items: Any, incoming_items: Any) -> list:
    merged: list[Dict[str, Any]] = []
    index_by_id: dict[str, int] = {}
    replace_groups = {
        _lifecycle_group(item)
        for item in _as_list(incoming_items)
        if isinstance(item, dict)
        and isinstance(item.get("lifecycle"), dict)
        and item["lifecycle"].get("replace_policy") == "replace_group"
    }

    for item in _as_list(existing_items):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        lifecycle = item.get("lifecycle") if isinstance(item.get("lifecycle"), dict) else {}
        if _lifecycle_group(item) in replace_groups and not lifecycle.get("pinned"):
            continue
        index_by_id[item["id"]] = len(merged)
        merged.append(item)

    for item in _as_list(incoming_items):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if item["id"] in index_by_id:
            merged[index_by_id[item["id"]]] = item
            continue
        index_by_id[item["id"]] = len(merged)
        merged.append(item)

    return merged


def merge_map_programs(
    current_program: Optional[Dict[str, Any]],
    incoming_program: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(current_program, dict):
        return incoming_program if isinstance(incoming_program, dict) else None
    if not isinstance(incoming_program, dict):
        return current_program

    current_state = current_program.get("state") if isinstance(current_program.get("state"), dict) else {}
    incoming_state = incoming_program.get("state") if isinstance(incoming_program.get("state"), dict) else {}
    incoming_view = incoming_state.get("view") if isinstance(incoming_state.get("view"), dict) else {}
    current_lineage = current_program.get("lineage") if isinstance(current_program.get("lineage"), dict) else {}
    incoming_lineage = incoming_program.get("lineage") if isinstance(incoming_program.get("lineage"), dict) else {}

    source_data_ids = list(dict.fromkeys([
        *_as_list(current_lineage.get("source_data_ids")),
        *_as_list(incoming_lineage.get("source_data_ids")),
    ]))
    dashboard_layer_ids = list(dict.fromkeys([
        *_as_list(current_lineage.get("dashboard_layer_ids")),
        *_as_list(incoming_lineage.get("dashboard_layer_ids")),
    ]))

    return {
        **current_program,
        **incoming_program,
        "state": {
            **current_state,
            **incoming_state,
            "view": incoming_view if incoming_view else current_state.get("view", {}),
            "layers": _merge_items_by_id(current_state.get("layers"), incoming_state.get("layers")),
            "dashboard_layers": _merge_items_by_id(
                current_state.get("dashboard_layers"),
                incoming_state.get("dashboard_layers"),
            ),
        },
        "lineage": {
            **current_lineage,
            **incoming_lineage,
            "source_data_ids": source_data_ids,
            "dashboard_layer_ids": dashboard_layer_ids,
        },
    }


def extract_map_program_from_tool_result_event(event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    result = event_data.get("result")
    if not isinstance(result, dict):
        return None
    for candidate in (
        result.get("map_program"),
        (result.get("data") or {}).get("map_program") if isinstance(result.get("data"), dict) else None,
        (result.get("metadata") or {}).get("map_program") if isinstance(result.get("metadata"), dict) else None,
    ):
        if isinstance(candidate, dict) and candidate.get("program_id"):
            return candidate
    return None


def merge_map_program_into_scene_metadata(
    metadata: Optional[Dict[str, Any]],
    map_program: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    next_metadata = dict(metadata or {})
    if not isinstance(map_program, dict) or not map_program.get("program_id"):
        return next_metadata

    existing_scene = next_metadata.get("map_scene")
    if not isinstance(existing_scene, dict):
        existing_scene = {}
    existing_program = existing_scene.get("current_map_program")
    if not isinstance(existing_program, dict):
        existing_program = existing_scene.get("currentMapProgram")

    next_metadata["map_scene"] = {
        **existing_scene,
        "current_map_program": merge_map_programs(existing_program, map_program),
        "updated_at": datetime.now().isoformat(),
    }
    return next_metadata


def _event_run_id(event: Dict[str, Any]) -> Optional[str]:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    return data.get("run_id") or event.get("run_id")


def _build_final_message(event_data: Dict[str, Any]) -> Dict[str, Any]:
    final_message = {
        "type": "final",
        "content": event_data["answer"],
        "data": event_data,
        "timestamp": event_data.get("timestamp", datetime.now().isoformat()),
    }

    if "visuals" in event_data and isinstance(event_data["visuals"], list):
        final_message["visuals"] = event_data["visuals"]
    return final_message


def _drawio_xml_from_result(result: Dict[str, Any]) -> str:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    for field in ("current_xml", "currentXml", "xml", "drawio_xml", "mxfile"):
        value = data.get(field)
        if isinstance(value, str) and value:
            return value

    candidate_refs: List[Dict[str, Any]] = []
    xml_ref = data.get("xml_ref")
    if isinstance(xml_ref, dict):
        candidate_refs.append(xml_ref)
    refs = result.get("refs") if isinstance(result.get("refs"), dict) else {}
    artifacts = refs.get("artifacts") if isinstance(refs.get("artifacts"), list) else []
    candidate_refs.extend(item for item in artifacts if isinstance(item, dict))

    for ref in candidate_refs:
        path_value = ref.get("local_path") or ref.get("path") or ref.get("file_path")
        if not isinstance(path_value, str) or not path_value:
            continue
        try:
            path = Path(path_value).expanduser().resolve()
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("drawio_board_xml_ref_read_failed", path=path_value, error=str(exc))
    return ""


def is_drawio_board_tool_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    return (
        metadata.get("generator") == "create_drawio_board"
        or metadata.get("tool_name") == "create_drawio_board"
        or data.get("artifact_kind") == "drawio_board"
    )


def merge_board_execution_context(
    board_context: Optional[Dict[str, Any]],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """Persist a compact, structured board execution receipt for the next turn."""
    merged = dict(board_context or {})
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    merged["last_execution"] = {
        "success": result.get("success") is True,
        "changed": bool(data.get("changed", False)),
        "changed_cells": list(data.get("changed_cells") or []),
        "applied_operations": int(data.get("applied_operations") or 0),
        "error_code": data.get("error_code"),
        "operation_index": data.get("operation_index"),
        "field": data.get("field"),
        "retryable": bool(data.get("retryable", False)),
    }
    return merged


def is_incompatible_chart_board_session(stored_mode: Optional[str], requested_mode: Optional[str]) -> bool:
    return {stored_mode, requested_mode} == {"chart", "board"}


# ========================================
# Request/Response Models
# ========================================

DEFAULT_MAX_ITERATIONS = 120
MAX_ITERATIONS_CAP = 200


class ConversationFileContextRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(pattern="^conversation_file$")
    resource_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=512)


class ActiveContextRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["skill", "fixed_policy"]
    id: str = Field(min_length=1, max_length=255)
    label: Optional[str] = Field(default=None, max_length=512)


class AgentAnalyzeRequest(BaseModel):
    """Agent 分析请求"""
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "query": "分析广州天河站2025-08-09的O3污染",
                "skill_ids": [],
                "context_refs": [],
                "session_id": None,
                "mode": "expert",
                "user_id": "john_doe",
                "enhance_with_history": True,
                "max_iterations": 10,
                "knowledge_base_ids": ["kb_123", "kb_456"],
            }
        },
    )

    query: str = Field(..., description="用户自然语言查询")
    skill_ids: List[str] = Field(..., max_length=1, description="本轮显式选择的技能，最多一个")
    context_refs: List[ConversationFileContextRef] = Field(..., description="本轮引用的会话文件")
    active_contexts: Optional[List[ActiveContextRef]] = Field(
        default=None,
        max_length=20,
        description="会话级活动上下文；null 表示沿用，空数组表示清除，非空数组表示替换",
    )
    session_id: Optional[str] = Field(None, description="会话ID（可选，用于会话恢复）")
    enhance_with_history: bool = Field(True, description="是否使用长期记忆增强")
    max_iterations: int = Field(DEFAULT_MAX_ITERATIONS, ge=1, le=MAX_ITERATIONS_CAP, description="最大迭代次数")
    mode: Optional[str] = Field(
        "expert",
        description="✅ Agent模式：'assistant' - 助手模式（办公任务），'ppt' - 幻灯片模式（可编辑演示文稿），'expert' - 专家模式（数据分析），'query' - 问数模式（数据查询），'report' - 报告模式（报告生成），'chart' - 图表模式（数据可视化），'ops' - 运维管理模式（工单审核、异常分析）"
    )
    user_id: Optional[str] = Field(None, description="""✅ 用户标识（用于跨会话记忆）
- 如果提供：同一用户在不同session共享记忆
- 如果不提供：每个session独立记忆""")
    assistant_mode: Optional[str] = Field(
        None,
        description="""助手模式（旧版，已弃用，建议使用mode参数）：
        'meteorology-expert' - 气象专家单专家模式
        'data-visualization-expert' - 数据可视化专家单专家模式
        'report-generation-expert' - 报告生成专家（预留）
        'template-report-expert' - 模板报告生成专家（方案B，推荐使用 /api/report/generate-from-template-agent）
        'general-agent' 或 None - 通用Agent单专家模式（支持ReAct循环）"""
    )
    knowledge_base_ids: Optional[List[str]] = Field(
        None,
        description="选中的知识库ID列表，用于检索增强生成"
    )
    enable_reasoning: bool = Field(
        False,
        description="是否启用思考模式（默认False，启用后会显示LLM的推理过程，适用于MiniMax等支持思考模式的模型）"
    )
    is_interruption: bool = Field(
        False,
        description="是否为用户中断后的对话（默认False，用户暂停后继续对话时为True）"
    )
    previous_paused_run_id: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("previous_paused_run_id", "previousPausedRunId"),
        description="新一轮开始前必须完成落盘的上一轮暂停 run ID",
    )
    board_context: Optional[Dict[str, Any]] = Field(
        None,
        validation_alias=AliasChoices("board_context", "boardContext"),
        description="画板模式上下文，仅 mode=board 时传入，例如 {current_xml, selected_cells}"
    )
    map_context: Optional[Dict[str, Any]] = Field(
        None,
        validation_alias=AliasChoices("map_context", "mapContext"),
        description="问数模式地图交互上下文，仅 mode=query 时传入，例如 {current_program, events}"
    )
    model_tier: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("model_tier", "modelTier"),
        description="模型档位：flash 使用 LLM_FLASH_MODELS 优先级；pro 使用 LLM_PRO_MODELS 优先级"
    )
    skip_auto_followup: bool = Field(
        False,
        validation_alias=AliasChoices("skip_auto_followup", "skipAutoFollowup"),
        description="是否跳过报告模式自动复核钩子，用于自动复核轮防止递归触发"
    )

    @model_validator(mode="after")
    def validate_turn_content(self) -> "AgentAnalyzeRequest":
        if not self.query.strip() and not self.skill_ids and not self.context_refs:
            raise ValueError("query, skill_ids and context_refs cannot all be empty")
        return self

class AgentQueryRequest(BaseModel):
    """Agent 简单查询请求（非流式）"""
    query: str = Field(..., description="用户查询")
    max_iterations: int = Field(DEFAULT_MAX_ITERATIONS, ge=1, le=MAX_ITERATIONS_CAP, description="最大迭代次数")
    session_id: Optional[str] = Field(None, description="会话ID（可选，用于保持会话连续性和记忆）")
    user_identifier: Optional[str] = Field(None, description="用户标识（可选，用于跨会话记忆共享）")
    assistant_mode: Optional[str] = Field(
        None,
        description="""助手模式：
        'meteorology-expert' - 气象专家单专家模式
        'data-visualization-expert' - 数据可视化专家单专家模式
        'report-generation-expert' - 报告生成专家（预留，暂未实现）
        'general-agent' 或 None - 通用Agent多专家模式"""
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "查询广州今天的天气",
                "max_iterations": 5,
                "assistant_mode": "meteorology-expert"
            }
        }


class AgentSteerRequest(BaseModel):
    """执行中用户补充/纠偏输入。"""
    message: str = Field(..., description="追加到当前 active run 的用户输入")
    input_id: Optional[str] = Field(default=None, description="客户端追加输入唯一标识")


class AgentCancelRequest(BaseModel):
    run_id: Optional[str] = None
    reason: Literal["user_paused", "client_cancelled"] = "user_paused"


async def persist_new_web_session(
    *,
    manager,
    session: Session,
    catalog: ConversationCatalogService,
    user: CurrentUser,
    mode: str,
) -> None:
    """Persist a new source session and roll it back if cataloging fails."""
    saved = await manager.save_session_metadata(session)
    if not saved:
        raise RuntimeError("session_create_failed")
    try:
        await catalog.register(
            session_id=session.session_id,
            user=user,
            source=ConversationSource.WEB,
            mode=mode,
            title=session.query[:256],
        )
    except Exception:
        await manager.delete_session(session.session_id)
        raise


class AgentQueryResponse(BaseModel):
    """Agent 查询响应"""
    answer: str = Field(..., description="分析答案")
    session_id: str = Field(..., description="会话ID")
    iterations: Optional[int] = Field(None, description="实际迭代次数")
    completed: bool = Field(..., description="是否成功完成")


class ToolInfo(BaseModel):
    """工具信息"""
    name: str
    description: str
    category: str
    status: str
    version: str
    requires_context: bool
    priority: int
    registered_at: Optional[str]
    statistics: Dict[str, Any]
    metadata: Dict[str, Any]
    function_schema: Optional[Dict[str, Any]]
    has_input_adapter: bool
    has_return_schema: bool


class ToolListResponse(BaseModel):
    """工具列表响应"""
    tools: List[Dict[str, Any]]
    count: int


# ========================================
# Global Agent Instances
# ========================================

# 通用Agent实例（使用默认 max_iterations=120）
multi_expert_agent_instance = create_react_agent(
    with_test_tools=False
)

# 气象专家模式全局实例（使用默认 max_iterations=120）
meteorology_expert_agent_instance = create_react_agent(
    with_test_tools=False,
    max_working_memory=25
)

# 数据可视化专家模式全局实例（专注图表，减少迭代）
data_viz_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=8,  # ⚠️ 特殊配置：可视化只需8次
    max_working_memory=15
)

# 幻灯片模式独立实例：隔离 PPT 源码项目、质量闭环与会话工作记忆。
ppt_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=80,
    max_working_memory=32,
)

# 画板模式独立实例：共享运行框架，但使用 board 专属 prompt、工具和完成协议。
board_agent_instance = create_react_agent(
    with_test_tools=False,
    max_iterations=12,
    max_working_memory=20,
)


def select_agent_instance(request):
    """Select the dedicated top-level agent for an analyze request."""
    if request.mode == "board":
        return board_agent_instance
    if request.mode == "chart":
        return data_viz_agent_instance
    if request.mode == "ppt":
        return ppt_agent_instance
    if request.assistant_mode == "meteorology-expert":
        return meteorology_expert_agent_instance
    if request.assistant_mode == "data-visualization-expert":
        return data_viz_agent_instance
    return multi_expert_agent_instance

logger.info(
    "agent_instances_created",
    multi_expert_tools=len(multi_expert_agent_instance.get_available_tools()),
    meteorology_expert_tools=len(meteorology_expert_agent_instance.get_available_tools()),
    data_viz_tools=len(data_viz_agent_instance.get_available_tools())
)


# ========================================
# API Endpoints
# ========================================

@router.post("/analyze")
async def analyze_stream(
    request: AgentAnalyzeRequest,
    raw_request: Request,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """
    流式分析接口（Server-Sent Events）

    实时返回 ReAct Agent 的思考、行动、观察过程。

    **可用工具**:
    - Query Tools (7个):
      - get_air_quality - 空气质量查询
      - get_weather_data - 气象数据查询
      - get_weather_forecast - 天气预报查询
      - get_current_weather - 实时天气查询
      - get_fire_hotspots - 火点数据查询
      - get_dust_data - 扬尘数据查询
      - get_component_data - 组分数据查询（广东省超级站）

    - Analysis Tools (1个):
      - analyze_upwind_enterprises - 上风向企业分析（广东省）

    - Visualization Tools:
      - execute_echarts_python - 交互式 ECharts 图表生成
      - create_report_chart - 正式报告静态图表生成
      - generate_map - 地图生成

    **助手模式**:
    - 'meteorology-expert': 气象专家单专家模式（专注气象 + 默认可视化）
    - 'general-agent' 或 None: 多专家模式（天气+组分+可视化+报告）

    **事件类型**:
    - `start`: 分析开始
    - `thought`: LLM 思考
    - `action`: 行动决策（工具调用或完成）
    - `observation`: 工具执行结果
    - `complete`: 任务成功完成
    - `incomplete`: 达到最大迭代次数
    - `error`: 迭代错误
    - `fatal_error`: 致命错误
    """
    # The frontend assigns an ID before the first analyze request. An absent ID
    # is therefore a creation request, while a cataloged ID is a continuation
    # and must pass the normal ownership check. Never let an uncataloged source
    # session be claimed through the creation path.
    session_manager = get_session_manager()
    preloaded_source_session = None
    source_session_checked = False
    if request.session_id:
        catalog_record = await catalog.find(request.session_id)
        if catalog_record is not None:
            await catalog.require_write(request.session_id, user)
            if is_incompatible_chart_board_session(catalog_record.mode, request.mode):
                raise HTTPException(status_code=409, detail="session_mode_mismatch")
        else:
            load_session = getattr(session_manager, "load_session_light", None)
            if load_session is None:
                load_session = session_manager.load_session
            preloaded_source_session = await load_session(request.session_id)
            source_session_checked = True
            if preloaded_source_session is not None:
                raise HTTPException(status_code=404, detail="session_not_found")

    if request.mode == "board" and request.board_context:
        try:
            request.board_context = await BoardApplicationService(
                async_session
            ).resolve_context_reference(
                request.board_context,
                expected_session_id=request.session_id,
            )
        except BoardVersionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": exc.code, "current_revision": exc.current_revision},
            ) from exc
        except (BoardNotFound, BoardVersionNotFound) as exc:
            raise HTTPException(status_code=404, detail=exc.code) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail="board_version_load_failed") from exc

    raw_body = await raw_request.json()
    if request.model_tier is None and isinstance(raw_body, dict):
        raw_model_tier = raw_body.get("model_tier") or raw_body.get("modelTier")
        if raw_model_tier:
            request.model_tier = str(raw_model_tier)
        else:
            logger.warning(
                "agent_analyze_model_tier_missing",
                body_keys=sorted(raw_body.keys()),
                session_id=request.session_id,
            )

    # 针对报告生成专家模式：在进入 ReAct 之前，显式告知 LLM 这是基于已有模板报告的连续对话，
    # 避免其误判为“首次对话、无历史上下文”。
    original_query = request.query
    if request.assistant_mode == "report-generation-expert" and request.session_id:
        request.query = (
            "【报告生成连续对话模式】\n"
            "你正在与用户就之前已经生成的一份基于模板的空气质量报告进行后续对话。\n"
            "该报告的完整 Markdown 内容以及相关数据已经保存在当前会话（session_id="
            f"{request.session_id}）的记忆中，必须把它视为历史上下文的一部分，不要认为这是第一次对话。\n"
            "后续所有用户提问（尤其包含“报告”“表格”“按模板”“修改”“补充”“为什么没按模板输出”等字样）"
            "都应理解为对这份已生成报告的修改、解释或补充，而不是一个全新的独立任务。\n"
            "在思考（Thought）时，请先简要回顾历史报告中与本问题相关的内容（尤其是表格和数据填充情况），"
            "再决定是直接解释/修改，还是需要调用工具获取更多数据。\n"
            f"当前用户的具体问题是：{original_query}"
        )

    logger.info(
        "agent_analyze_request",
        query=request.query[:100],
        session_id=request.session_id,
        max_iterations=request.max_iterations,
        assistant_mode=request.assistant_mode,
        knowledge_base_ids=request.knowledge_base_ids,
        is_interruption=request.is_interruption,
        model_tier=request.model_tier,
        mode=request.mode,
        context_refs_count=len(request.context_refs),
    )

    active_context_request_started_at = datetime.now(timezone.utc)
    try:
        # 根据助手模式选择 Agent
        if request.mode in {"board", "chart", "ppt"}:
            agent = select_agent_instance(request)
            logger.info("使用独立模式智能体", mode=request.mode, session_id=request.session_id, agent_id=id(agent))
        elif request.assistant_mode == 'meteorology-expert':
            agent = meteorology_expert_agent_instance
            logger.info(
                "使用气象专家模式",
                session_id=request.session_id,
                agent_id=id(agent)
            )
        elif request.assistant_mode == 'data-visualization-expert':
            agent = data_viz_agent_instance
            logger.info(
                "使用数据可视化专家模式",
                session_id=request.session_id,
                agent_id=id(agent),
                max_iterations=8
            )
        elif request.assistant_mode == 'report-generation-expert':
            agent = multi_expert_agent_instance
            logger.info(
                "使用报告生成专家模式",
                session_id=request.session_id,
                agent_id=id(agent)
            )
        elif request.assistant_mode == 'template-report-expert':
            raise HTTPException(
                status_code=400,
                detail="模板报告生成请调用 /api/report/generate-from-template-agent（需提供模板内容和时间范围）"
            )
        else:
            # 默认使用通用Agent
            agent = multi_expert_agent_instance
            logger.info(
                "使用通用Agent模式",
                session_id=request.session_id,
                agent_id=id(agent)
            )

        # 构建分析参数
        analyze_kwargs = {
            "user_query": request.query,
            "session_id": request.session_id,
            "enhance_with_history": request.enhance_with_history,
            "max_iterations": request.max_iterations,
            "knowledge_base_ids": request.knowledge_base_ids,
            "enable_reasoning": request.enable_reasoning,
            "is_interruption": request.is_interruption,
            "manual_mode": request.mode,
            # Web conversations always use the canonical DB store. Runtime
            # behavior (including social prompts/tools) is an independent axis.
            "session_storage_mode": "assistant",
            "attachments": None,
            "user_identifier": request.user_id,  # ✅ 直接传递 user_id，允许 None（None 时使用模式内共享记忆）
            "skip_auto_followup": request.skip_auto_followup
        }
        if request.mode == "board" and request.board_context:
            analyze_kwargs["board_context"] = request.board_context
            current_xml = request.board_context.get("current_xml") or request.board_context.get("currentXml") or ""
            previous_xml = request.board_context.get("previous_xml") or request.board_context.get("previousXml") or ""
            selected_cells = request.board_context.get("selected_cells") or request.board_context.get("selectedCells") or []
            logger.info(
                "board_context_received",
                session_id=request.session_id,
                current_xml_length=len(current_xml),
                previous_xml_length=len(previous_xml),
                selected_count=len(selected_cells) if isinstance(selected_cells, list) else 0,
                version=request.board_context.get("version"),
                dirty=request.board_context.get("dirty"),
                updated_at=request.board_context.get("updated_at") or request.board_context.get("updatedAt"),
            )
        if request.mode in {"query", "graph"} and request.map_context:
            analyze_kwargs["map_context"] = request.map_context
            map_events = request.map_context.get("events") or []
            current_program = request.map_context.get("current_program") or {}
            logger.info(
                "agent_map_context_received",
                mode=request.mode,
                session_id=request.session_id,
                program_id=current_program.get("program_id") if isinstance(current_program, dict) else None,
                event_count=len(map_events) if isinstance(map_events, list) else 0,
            )
        drawio_board_context = request.board_context if request.mode == "board" else None

        # 初始化会话管理器（使用全局单例，确保内存缓存一致）
        persistence = ConversationPersistenceService()
        actual_session_id = request.session_id
        conversation_history = []
        latest_drawio_board = None

        if not actual_session_id:
            import uuid
            actual_session_id = f"session_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"
            analyze_kwargs["session_id"] = actual_session_id

        load_session = getattr(session_manager, "load_session_light", None)
        if load_session is None:
            load_session = session_manager.load_session
        preloaded_session = (
            preloaded_source_session
            if source_session_checked and actual_session_id == request.session_id
            else await load_session(actual_session_id) if actual_session_id else None
        )

        requested_active_contexts = (
            [item.model_dump(exclude_none=True) for item in request.active_contexts]
            if request.active_contexts is not None
            else None
        )
        effective_active_contexts = effective_active_context_items(
            preloaded_session.metadata if preloaded_session else None,
            requested_active_contexts,
            request.skill_ids,
        )

        try:
            requested_ids = [ref.resource_id for ref in request.context_refs]
            needs_resources = bool(requested_ids) or any(
                item["type"] == "fixed_policy" for item in effective_active_contexts
            )
            resource_page = (
                await SessionResourceService.database().list_resources(actual_session_id, limit=1000)
                if needs_resources
                else None
            )
            available_resources = resource_page.resources if resource_page else []
            selected_resource_refs = select_conversation_resources(
                available_resources,
                requested_ids,
            )
            resolved_active_contexts = resolve_active_contexts(
                effective_active_contexts,
                mode=request.mode or "expert",
                resources=available_resources,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=422, detail="selected_skill_not_found") from exc
        except InvalidContextReference as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "invalid_context_reference", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "active_context_incompatible", "message": str(exc)},
            ) from exc
        except Exception as exc:
            logger.error("active_context_resolution_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="resource_store_unavailable") from exc

        selected_skill = resolved_active_contexts.skill
        active_contexts_payload = active_contexts_metadata(
            resolved_active_contexts.items,
            updated_at=active_context_request_started_at,
        )
        analyze_kwargs["selected_skill_context"] = selected_skill.content if selected_skill else None
        analyze_kwargs["fixed_policy_context"] = resolved_active_contexts.fixed_policy_context
        analyze_kwargs["selected_resource_refs"] = selected_resource_refs or None
        if (
            preloaded_session
            and request.mode == "board"
            and drawio_board_context is None
            and isinstance(preloaded_session.metadata, dict)
        ):
            stored_drawio_board = preloaded_session.metadata.get("drawio_board")
            if isinstance(stored_drawio_board, dict):
                try:
                    drawio_board_context = await BoardApplicationService(
                        async_session
                    ).resolve_context_reference(
                        stored_drawio_board,
                        expected_session_id=actual_session_id,
                    )
                    analyze_kwargs["board_context"] = drawio_board_context
                except BoardVersionConflict as exc:
                    raise HTTPException(
                        status_code=409,
                        detail={"code": exc.code, "current_revision": exc.current_revision},
                    ) from exc
                except (BoardNotFound, BoardVersionNotFound) as exc:
                    raise HTTPException(status_code=404, detail=exc.code) from exc
                except FileNotFoundError as exc:
                    raise HTTPException(status_code=409, detail="board_version_load_failed") from exc

        async def event_generator():
            """SSE 事件生成器"""
            nonlocal actual_session_id, conversation_history, latest_drawio_board, drawio_board_context, preloaded_session
            cancel_event = None
            latest_event_run_id = None

            # ✅ 用于统计（不输出日志）
            event_count = 0
            streaming_chunk_count = 0
            partial_answer_chunks: List[str] = []

            # The pause barrier must complete before loading conversation
            # history; otherwise a fast next turn can retain a stale preload.
            try:
                if request.previous_paused_run_id:
                    await cancellation_registry.cancel(
                        actual_session_id,
                        expected_run_id=request.previous_paused_run_id,
                        reason="user_paused",
                    )
                    await cancellation_registry.ensure_pause_succeeded(
                        actual_session_id,
                        request.previous_paused_run_id,
                    )
                cancel_event = await cancellation_registry.register(actual_session_id)
            except PauseCheckpointError as pause_error:
                error_event = {
                    "type": "fatal_error",
                    "data": {
                        "error": "暂停记录保存失败，请重试当前消息",
                        "code": "pause_checkpoint_failed",
                        "detail": str(pause_error),
                    },
                }
                yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
                return
            current_task = asyncio.current_task()
            if current_task is not None:
                await cancellation_registry.attach_run_task(actual_session_id, current_task)
            analyze_kwargs["cancel_event"] = cancel_event
            if actual_session_id:
                preloaded_session = await load_session(actual_session_id)

            # 创建或加载会话
            if actual_session_id:
                logger.info(
                    "route_session_load_start",
                    session_id=actual_session_id,
                    include_messages="display_light",
                )
                session = preloaded_session
                if session:
                    session_already_exists = True
                    logger.info(
                        "session_restored",
                        session_id=actual_session_id,
                        has_conversation_history=bool(session.conversation_history),
                        conversation_history_length=len(session.conversation_history) if session.conversation_history else 0,
                        resource_store="unified",
                    )
                    conversation_history = session.conversation_history or []
                    if request.mode == "board" and drawio_board_context is not None:
                        logger.info(
                            "board_context_restored_from_session_metadata",
                            session_id=actual_session_id,
                            current_xml_length=len(
                                drawio_board_context.get("current_xml")
                                or drawio_board_context.get("currentXml")
                                or drawio_board_context.get("xml")
                                or ""
                            ),
                            selected_count=len(
                                drawio_board_context.get("selected_cells")
                                or drawio_board_context.get("selectedCells")
                                or []
                            ),
                            version=drawio_board_context.get("version"),
                            updated_at=drawio_board_context.get("updated_at")
                            or drawio_board_context.get("updatedAt"),
                        )

                    # ✅ 不再传递 initial_messages，因为 react_agent._get_or_create_session 会自动从 SessionManager 恢复会话
                    # 避免重复加载历史消息
                else:
                    session_already_exists = False
                    logger.warning(
                        "session_not_found_creating_new",
                        session_id=actual_session_id,
                        hint="SessionManager中未找到该会话，将创建新会话"
                    )
                    session = Session(session_id=actual_session_id, query=request.query)
                    conversation_history = []
            else:
                session_already_exists = False
                session = Session(session_id=actual_session_id, query=request.query)
                conversation_history = []
                logger.info("session_created", session_id=actual_session_id)
                # 更新 analyze_kwargs 中的 session_id
                analyze_kwargs["session_id"] = actual_session_id

            if request.mode == "query" and request.map_context:
                session.metadata = merge_map_scene_metadata(session.metadata, request.map_context)
            session.metadata = dict(session.metadata or {})
            session.metadata[ACTIVE_CONTEXTS_KEY] = active_contexts_payload

            # 只保存/刷新会话元数据，不在首个 SSE 事件前同步历史消息。
            # 历史消息在本轮完成或异常时走增量保存，避免 DELETE + INSERT
            # 阻塞用户看到首个响应事件。
            if session_already_exists:
                async def _save_initial_session_metadata() -> None:
                    try:
                        await session_manager.save_session_metadata(session)
                    except Exception as save_err:
                        logger.warning(
                            "initial_session_metadata_save_failed",
                            session_id=actual_session_id,
                            error=str(save_err)
                        )

                asyncio.create_task(_save_initial_session_metadata())
            else:
                await persist_new_web_session(
                    manager=session_manager,
                    session=session,
                    catalog=catalog,
                    user=user,
                    mode=request.mode or "assistant",
                )

            # ✅ 添加用户消息到对话历史
            user_message = _build_user_message_for_history(
                request.query,
                resource_refs_to_message_attachments(selected_resource_refs),
                timestamp=datetime.now().isoformat(),
            )
            user_message["skill_ids"] = (
                [selected_skill.skill_id] if selected_skill else []
            )
            user_message["context_refs"] = [ref.model_dump(mode="json") for ref in request.context_refs]
            user_message["active_contexts"] = list(resolved_active_contexts.items)
            conversation_history.append(user_message)
            logger.debug("user_message_added", query_preview=request.query[:100])

            try:
                await cancellation_registry.arm_run_task(actual_session_id, cancel_event)
                with llm_service.use_model_tier(request.model_tier):
                    async for event in agent.analyze(**analyze_kwargs):
                        event_count += 1
                        event_type = event.get("type")
                        latest_event_run_id = _event_run_id(event) or latest_event_run_id
                        if latest_event_run_id:
                            await cancellation_registry.attach_run_id(
                                actual_session_id,
                                cancel_event,
                                latest_event_run_id,
                            )

                        # ✅ 关闭流式文本事件的所有日志
                        if event_type != "streaming_text":
                            # ✅ 非流式事件：正常记录
                            logger.debug("received_event", event_type=event_type, has_data="data" in event)
                        else:
                            # ✅ 流式事件：静默处理，只统计不输出
                            streaming_chunk_count += 1

                        # 收集对话历史（转换为前端格式，添加 content 字段）
                        if event["type"] in ["thought", "tool_use", "tool_result"]:
                            # 创建前端格式的消息
                            event_data = event.get("data", {})

                            # 【验证】检查 tool_result 事件的 data 字段
                            if event["type"] == "tool_result":
                                result = event_data.get("result") or {}
                                logger.info("[tool_result_debug] 验证 event.data 结构",
                                    has_data="data" in event,
                                    data_keys=list(event_data.keys()) if isinstance(event_data, dict) else "not_dict",
                                    has_result="result" in event_data,
                                    result_keys=list(result.keys()) if isinstance(result, dict) else "not_dict",
                                    has_visuals="visuals" in result,
                                    visuals_count=len(result.get("visuals") or [])
                                )
                                if (
                                    request.mode == "board"
                                    and is_drawio_board_tool_result(result)
                                ):
                                    result_data = result.get("data") or {}
                                    if isinstance(result_data, dict):
                                        drawio_xml = _drawio_xml_from_result(result)
                                        if drawio_xml:
                                            latest_drawio_board = {
                                                **result_data,
                                                "current_xml": drawio_xml,
                                                "xml": drawio_xml,
                                            }
                                            latest_drawio_board = merge_board_execution_context(
                                                latest_drawio_board,
                                                result,
                                            )
                                            drawio_board_context = latest_drawio_board
                                        else:
                                            drawio_board_context = merge_board_execution_context(
                                                latest_drawio_board or drawio_board_context,
                                                result,
                                            )

                            frontend_message = {
                                "type": event["type"],
                                "data": event_data,
                                "timestamp": event_data.get("timestamp") if "timestamp" in event_data else None
                            }

                            # 提取 content 字段（前端显示用）
                            if event["type"] == "thought":
                                frontend_message["content"] = event_data.get("thought", "思考中...")
                            elif event["type"] == "tool_use":
                                tool_name = event_data.get("tool_name", "")
                                frontend_message["content"] = f"调用工具: {tool_name}" if tool_name else "执行行动"
                            elif event["type"] == "tool_result":
                                result_data = event_data.get("result", {})
                                if isinstance(result_data, dict):
                                    frontend_message["content"] = (
                                        result_data.get("summary_text")
                                        or _safe_preview(result_data.get("summary"), 500)
                                        or "获得结果"
                                    )
                                else:
                                    frontend_message["content"] = str(result_data)

                            conversation_history.append(frontend_message)
                            # 防御性代码：确保 content 不为 None
                            content = frontend_message.get("content", "")
                            content_preview = _safe_preview(content, 50)
                            logger.debug("conversation_history_appended",
                                        event_type=event["type"],
                                        history_length=len(conversation_history),
                                        content_preview=content_preview)

                        # ✅ streaming_text 事件：流式输出但不保存到历史（由 complete 事件统一保存）
                        elif event["type"] == "streaming_text":
                            # 流式文本直接转发，不保存到对话历史
                            # 等待 complete 事件时再保存完整的最终答案
                            event_data = event.get("data") or {}
                            chunk = event_data.get("chunk")
                            if isinstance(chunk, str) and chunk:
                                partial_answer_chunks.append(chunk)

                        elif event["type"] == "synthetic_user_message":
                            event_data = event.get("data") or {}
                            synthetic_message = {
                                "type": "user",
                                "content": event_data.get("content", ""),
                                "timestamp": event_data.get("timestamp", datetime.now().isoformat()),
                                "source": event_data.get("source", "auto_hook"),
                                "hook_name": event_data.get("hook_name")
                            }
                            conversation_history.append(synthetic_message)
                            logger.info(
                                "synthetic_user_message_added",
                                session_id=actual_session_id,
                                hook_name=event_data.get("hook_name"),
                                content_preview=synthetic_message["content"][:100]
                            )

                        # 地图程序仍由传输层负责即时展示；资源引用由 ReActAgent 统一持久化。
                        if event["type"] == "tool_result" and "data" in event:
                            data = event.get("data", {})
                            map_program = extract_map_program_from_tool_result_event(data)
                            if map_program:
                                session.metadata = merge_map_program_into_scene_metadata(
                                    session.metadata,
                                    map_program,
                                )

                        # ✅ 如果是完成或致命错误，先保存会话（在 yield 之前）
                        if event["type"] == "complete":
                            event_run_id = _event_run_id(event)
                            if not await run_ownership_registry.can_write(actual_session_id, event_run_id):
                                logger.info(
                                    "stale_run_complete_discarded",
                                    session_id=actual_session_id,
                                    run_id=event_run_id,
                                )
                                event_data = json.dumps(event, ensure_ascii=False, default=str)
                                yield f"data: {event_data}\n\n"
                                break
                            # ✅ 添加最终答案消息
                            event_data = event.get("data") or {}
                            if event_data.get("answer"):
                                final_message = _build_final_message(event_data)
                                conversation_history.append(final_message)
                                logger.debug("response_message_added", answer_preview=event["data"]["answer"][:100])

                            # ✅ 关闭流式统计日志
                            # if streaming_chunk_count > 0:
                            #     logger.info(
                            #         "streaming_statistics",
                            #         session_id=actual_session_id,
                            #         total_events=event_count,
                            #         streaming_chunks=streaming_chunk_count
                            #     )

                            logger.info("saving_session_on_complete",
                                       session_id=actual_session_id,
                                       conversation_history_length=len(conversation_history))

                            persistence.append_complete(
                                session,
                                display_history=conversation_history,
                                drawio_board=latest_drawio_board or drawio_board_context,
                            )
                            saved = await session_manager.append_session_transcript(session)
                            if not saved:
                                raise RuntimeError("complete_transcript_save_failed")
                            agent._session_store[actual_session_id]["display_history_persisted"] = True
                            await run_ownership_registry.complete(actual_session_id, event_run_id)
                        elif event["type"] in ["incomplete", "fatal_error", "interrupted"]:
                            event_run_id = _event_run_id(event)
                            if not await run_ownership_registry.can_write(actual_session_id, event_run_id):
                                logger.info(
                                    "stale_run_terminal_discarded",
                                    session_id=actual_session_id,
                                    run_id=event_run_id,
                                    event_type=event["type"],
                                )
                                event_data = json.dumps(event, ensure_ascii=False, default=str)
                                yield f"data: {event_data}\n\n"
                                break
                            # ✅ 将收集的数据存入 _session_store，供 react_agent.py 的 finally 块统一保存
                            if actual_session_id not in agent._session_store:
                                agent._session_store[actual_session_id] = {}

                            agent._session_store[actual_session_id]["has_error"] = event["type"] != "interrupted"
                            agent._session_store[actual_session_id]["error_type"] = event["type"]
                            event_data = event.get("data") or {}
                            if "error" in event_data:
                                agent._session_store[actual_session_id]["error_message"] = event_data.get("error", "Unknown error")
                            if event["type"] == "interrupted":
                                terminal_content = event_data.get("reason", "用户已暂停本轮分析")
                            elif event["type"] == "incomplete":
                                terminal_content = event_data.get(
                                    "reason",
                                    "分析任务较复杂，在限定步骤内未完成，是否继续？",
                                )
                            else:
                                terminal_content = event_data.get("error") or event_data.get("message") or "分析失败"
                            persistence.append_terminal(
                                session,
                                display_history=conversation_history,
                                terminal_message={
                                    "type": event["type"],
                                    "content": terminal_content,
                                    "data": event_data,
                                    "timestamp": event_data.get("timestamp") or datetime.now().isoformat(),
                                },
                                drawio_board=latest_drawio_board or drawio_board_context,
                            )
                            saved = await session_manager.append_session_transcript(session)
                            if not saved:
                                raise RuntimeError("terminal_transcript_save_failed")
                            agent._session_store[actual_session_id]["display_history_persisted"] = True
                            await run_ownership_registry.complete(actual_session_id, event_run_id)

                            logger.info("collected_data_stored_on_error", session_id=actual_session_id, error_type=event["type"])

                        # 将事件序列化为 SSE 格式
                        event_data = json.dumps(event, ensure_ascii=False, default=str)
                        yield f"data: {event_data}\n\n"

                        # 如果是完成或致命错误，结束循环
                        if event["type"] in ["complete", "incomplete", "fatal_error", "interrupted"]:
                            break

            except asyncio.CancelledError:
                if (
                    actual_session_id
                    and cancel_event is not None
                    and await cancellation_registry.can_finalize(actual_session_id, cancel_event)
                ):
                    async def persist_interrupted_transcript() -> None:
                        pause_reason = await cancellation_registry.pause_reason(
                            actual_session_id,
                            cancel_event,
                        )
                        if pause_reason == "user_paused":
                            persistence.append_paused(
                                session,
                                display_history=conversation_history,
                                run_id=latest_event_run_id or f"pending:{actual_session_id}",
                                partial_answer="".join(partial_answer_chunks),
                                drawio_board=latest_drawio_board or drawio_board_context,
                            )
                        else:
                            persistence.append_terminal(
                                session,
                                display_history=conversation_history,
                                terminal_message={
                                    "type": "interrupted",
                                    "content": "客户端已断开，本轮分析已取消",
                                    "timestamp": datetime.now().isoformat(),
                                },
                                drawio_board=latest_drawio_board or drawio_board_context,
                            )
                        saved = False
                        for attempt in range(3):
                            saved = await session_manager.append_session_transcript(session)
                            if saved:
                                break
                            if attempt < 2:
                                await asyncio.sleep(0.05)
                        if not saved:
                            raise RuntimeError("pause_checkpoint_failed")
                        if actual_session_id not in agent._session_store:
                            agent._session_store[actual_session_id] = {}
                        agent._session_store[actual_session_id]["display_history_persisted"] = True

                    try:
                        await _await_cancellation_resistant(persist_interrupted_transcript())
                    except Exception as pause_error:
                        await cancellation_registry.record_finalization_error(
                            actual_session_id,
                            cancel_event,
                            pause_error,
                        )
                        raise
                raise
            except Exception as e:
                logger.error(
                    "stream_generation_error",
                    error=str(e),
                    exc_info=True
                )
                if await run_ownership_registry.can_write(actual_session_id, latest_event_run_id):
                    # 保存失败会话
                    persistence.append_terminal(
                        session,
                        display_history=conversation_history,
                        terminal_message={
                            "type": "fatal_error",
                            "content": str(e),
                            "timestamp": datetime.now().isoformat(),
                        },
                        drawio_board=latest_drawio_board or drawio_board_context,
                    )
                    session.error = {
                        "type": "stream_error",
                        "message": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                    saved = await session_manager.append_session_transcript(session)
                    if saved and actual_session_id:
                        if actual_session_id not in agent._session_store:
                            agent._session_store[actual_session_id] = {}
                        agent._session_store[actual_session_id]["display_history_persisted"] = True
                    if saved:
                        logger.info("session_saved_on_exception", session_id=actual_session_id)
                    else:
                        logger.error(
                            "failed_to_save_session_on_exception",
                            session_id=actual_session_id,
                        )

                error_event = {
                    "type": "fatal_error",
                    "data": {
                        "error": str(e),
                        "timestamp": None
                    }
                }
                yield f"data: {json.dumps(error_event, ensure_ascii=False, default=str)}\n\n"
            finally:
                if actual_session_id and cancel_event is not None:
                    await cancellation_registry.unregister(actual_session_id, cancel_event)

        return create_sse_response(event_generator())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "agent_analyze_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"分析失败: {str(e)}"
        )


@router.post("/{session_id}/cancel")
async def cancel_analysis(
    session_id: str,
    request: Optional[AgentCancelRequest] = Body(default=None),
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Cancel an in-flight streaming analysis for a session."""
    await catalog.require_write(session_id, user)
    active_run_id = await run_ownership_registry.current_run_id(session_id)
    cancelled = await cancellation_registry.cancel(
        session_id,
        expected_run_id=request.run_id if request else None,
        reason=request.reason if request else "user_paused",
    )
    return {
        "success": True,
        "cancelled": cancelled,
        "session_id": session_id,
        "revoked_run_id": active_run_id,
        "message": "已发送取消信号" if cancelled else "没有找到运行中的分析任务",
    }


@router.post("/{session_id}/steer")
async def steer_analysis(
    session_id: str,
    request: AgentSteerRequest,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    """Append user steering input to an active steerable run."""
    await catalog.require_write(session_id, user)
    accepted = await steering_registry.add_input(
        session_id,
        request.message,
        input_id=request.input_id,
    )
    return {
        "success": True,
        "accepted": accepted,
        "session_id": session_id,
        "reason": None if accepted else "no_active_steerable_run_or_store_unavailable",
        "message": "已追加到当前执行任务" if accepted else "没有找到可追加的运行中任务",
    }


@router.post("/query", response_model=AgentQueryResponse)
async def simple_query(request: AgentQueryRequest):
    """
    简单查询接口（非流式）

    适用于不需要实时进度的简单查询。
    """
    logger.info(
        "agent_query_request",
        query=request.query[:100],
        max_iterations=request.max_iterations
    )

    try:
        # 默认使用多专家协作模式（兼容无assistant_mode参数的情况）
        agent = multi_expert_agent_instance
        assistant_mode = 'general-agent'  # 默认模式

        # 根据助手模式选择 Agent（使用全局实例以保持会话连续性）
        if hasattr(request, 'assistant_mode') and request.assistant_mode:
            if request.assistant_mode == 'meteorology-expert':
                agent = meteorology_expert_agent_instance
                assistant_mode = 'meteorology-expert'
                logger.info(
                    "使用气象专家模式",
                    agent_id=id(agent)
                )
            elif request.assistant_mode == 'data-visualization-expert':
                agent = data_viz_agent_instance
                assistant_mode = 'data-visualization-expert'
                logger.info(
                    "使用数据可视化专家模式",
                    agent_id=id(agent),
                    max_iterations=8
                )
            elif request.assistant_mode == 'report-generation-expert':
                raise HTTPException(
                    status_code=501,
                    detail="报告生成专家尚未实现，敬请期待"
                )

        logger.info(
            "agent_query_with_assistant_mode",
            assistant_mode=assistant_mode,
            agent_id=id(agent)
        )

        # 收集结果
        answer = ""
        session_id = ""
        iterations = 0
        completed = False

        async for event in agent.analyze(
            request.query,
            session_id=request.session_id,
            user_identifier=request.user_identifier,
            max_iterations=request.max_iterations
        ):
            if event["type"] == "start":
                session_id = event["data"].get("session_id", "")

            elif event["type"] == "complete":
                answer = event["data"].get("answer", "")
                iterations = event["data"].get("iterations", 0)
                completed = True
                break

            elif event["type"] == "incomplete":
                answer = event["data"].get("answer", "")
                iterations = event["data"].get("iterations", 0)
                completed = False
                break

            elif event["type"] == "fatal_error":
                raise HTTPException(
                    status_code=500,
                    detail=event["data"].get("error", "未知错误")
                )

        return AgentQueryResponse(
            answer=answer,
            session_id=session_id,
            iterations=iterations,
            completed=completed
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "agent_query_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"查询失败: {str(e)}"
        )


@router.get("/tools", response_model=ToolListResponse)
async def list_tools():
    """
    获取可用工具列表（包含完整信息）
    """
    try:
        # 从工具注册表获取详细信息
        tools_info = global_tool_registry.get_tools_info()

        logger.info("agent_tools_listed", count=len(tools_info))

        return ToolListResponse(
            tools=tools_info,
            count=len(tools_info)
        )

    except Exception as e:
        logger.error(
            "list_tools_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"获取工具列表失败: {str(e)}"
        )


@router.get("/tools/{tool_name}", response_model=ToolInfo)
async def get_tool_info(tool_name: str):
    """
    获取特定工具的详细信息
    """
    try:
        # 从工具注册表获取详细信息
        info = global_tool_registry.get_tool_info(tool_name)

        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"工具不存在: {tool_name}"
            )

        logger.info("tool_info_retrieved", tool_name=tool_name)

        return ToolInfo(**info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_tool_info_failed",
            tool_name=tool_name,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"获取工具信息失败: {str(e)}"
        )


@router.patch("/tools/{tool_name}")
async def update_tool_status(tool_name: str, enabled: bool = Body(..., embed=True)):
    """
    更新工具启用/禁用状态

    Args:
        tool_name: 工具名称
        enabled: True=启用, False=禁用
    """
    try:
        registry = global_tool_registry

        # 检查工具是否存在
        if not registry.get_tool(tool_name):
            raise HTTPException(
                status_code=404,
                detail=f"工具不存在: {tool_name}"
            )

        # 更新工具状态
        success = registry.set_tool_enabled(tool_name, enabled)

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"更新工具状态失败"
            )

        logger.info(
            "tool_status_updated",
            tool_name=tool_name,
            enabled=enabled
        )

        return {
            "success": True,
            "tool_name": tool_name,
            "enabled": enabled
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "update_tool_status_failed",
            tool_name=tool_name,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"更新工具状态失败: {str(e)}"
        )


@router.get("/tools/categories")
async def get_tools_categories():
    """
    获取所有工具类别
    """
    try:
        registry = global_tool_registry
        categories = registry.get_categories()

        logger.info("tool_categories_listed", count=len(categories))

        return {
            "categories": categories,
            "count": len(categories)
        }

    except Exception as e:
        logger.error(
            "get_tool_categories_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"获取工具类别失败: {str(e)}"
        )


@router.get("/health")
async def agent_health():
    """
    Agent 健康检查
    """
    return {
        "status": "healthy",
        "agent_type": "ReAct Agent",
        "instances": {
            "multi_expert": {
                "tools_count": len(multi_expert_agent_instance.get_available_tools()),
                "max_iterations": multi_expert_agent_instance.max_iterations,
                "description": "通用Agent模式"
            },
            "meteorology_expert": {
                "tools_count": len(meteorology_expert_agent_instance.get_available_tools()),
                "max_iterations": meteorology_expert_agent_instance.max_iterations,
                "description": "气象专家模式"
            },
            "data_visualization_expert": {
                "tools_count": len(data_viz_agent_instance.get_available_tools()),
                "max_iterations": data_viz_agent_instance.max_iterations,
                "description": "数据可视化专家模式"
            },
            "report_generation_expert": {
                "tools_count": 0,
                "max_iterations": 0,
                "description": "报告生成专家（预留，暂未实现）"
            }
        }
    }


# ========================================
# TODO: 会话管理接口（可选）
# ========================================

# @router.get("/sessions/{session_id}")
# async def get_session_status(session_id: str):
#     """获取会话状态"""
#     pass
#
# @router.delete("/sessions/{session_id}")
# async def delete_session(session_id: str):
#     """删除会话"""
#     pass
