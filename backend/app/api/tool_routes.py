"""Single implementation of the tool management API."""
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import require_admin_user, require_current_user
from app.auth.models import CurrentUser

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(require_current_user)])


class ToolListResponse(BaseModel):
    success: bool = True
    tools: list[dict[str, Any]]
    count: int


class ToolDetailResponse(BaseModel):
    success: bool = True
    tool: dict[str, Any]


class ToolCategoriesResponse(BaseModel):
    success: bool = True
    categories: list[str]
    count: int


class ToolStatusUpdate(BaseModel):
    enabled: bool


class ToolStatusResponse(BaseModel):
    success: bool = True
    tool_name: str
    enabled: bool
    message: str


def get_registry():
    from app.tools import global_tool_registry
    return global_tool_registry


@router.get("", response_model=ToolListResponse)
async def list_tools(registry=Depends(get_registry)):
    tools = registry.get_tools_info()
    return ToolListResponse(tools=tools, count=len(tools))


# Static paths must precede /{tool_name}; "categories" is not a tool name.
@router.get("/categories", response_model=ToolCategoriesResponse)
async def get_tools_categories(registry=Depends(get_registry)):
    categories = registry.get_categories()
    return ToolCategoriesResponse(categories=categories, count=len(categories))


@router.get("/{tool_name}", response_model=ToolDetailResponse)
async def get_tool_info(tool_name: str, registry=Depends(get_registry)):
    info = registry.get_tool_info(tool_name)
    if not info:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")
    return ToolDetailResponse(tool=info)


@router.patch("/{tool_name}", response_model=ToolStatusResponse)
async def update_tool_status(
    tool_name: str,
    request: ToolStatusUpdate,
    user: CurrentUser = Depends(require_admin_user),
    registry=Depends(get_registry),
):
    if not registry.get_tool_info(tool_name):
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")
    if not registry.set_tool_enabled(tool_name, request.enabled):
        raise HTTPException(status_code=500, detail="更新工具状态失败")
    logger.info("tool_status_updated", tool_name=tool_name, enabled=request.enabled, user_id=user.id)
    return ToolStatusResponse(
        tool_name=tool_name, enabled=request.enabled,
        message=f"Tool '{tool_name}' {'enabled' if request.enabled else 'disabled'}",
    )
