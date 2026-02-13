"""
图片获取API - 前端按需获取图表图片

提供以下接口：
- GET /api/image/{image_id} - 获取图片（返回base64）
- GET /api/image/{image_id}/info - 获取图片元信息
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from typing import Optional
import base64
import structlog

logger = structlog.get_logger()

router = APIRouter()


@router.get("/image/{image_id}")
async def get_image(image_id: str):
    """获取指定图片（直接返回图片数据）

    Args:
        image_id: 图片ID（由可视化器生成）

    Returns:
        图片数据（直接返回，不是JSON）
    """
    from app.services.image_cache import get_image_cache
    import base64 as b64_module

    cache = get_image_cache()
    base64_data = cache.get(image_id)

    if base64_data is None:
        logger.warning("image_not_found", image_id=image_id)
        raise HTTPException(status_code=404, detail="Image not found")

    # 检测图片格式
    try:
        image_bytes = b64_module.b64decode(base64_data[:100] + "==")
        if image_bytes[:3] == b'GIF':
            media_type = "image/gif"
        elif image_bytes[:4] == b'\x89PNG':
            media_type = "image/png"
        elif image_bytes[:4] == b'\xff\xd8\xff':
            media_type = "image/jpeg"
        else:
            media_type = "image/png"  # 默认
    except Exception:
        media_type = "image/png"

    # 直接返回图片数据（不是JSON）
    return Response(
        content=b64_module.b64decode(base64_data),
        media_type=media_type
    )


@router.get("/image/{image_id}/info")
async def get_image_info(image_id: str):
    """获取图片元信息

    Args:
        image_id: 图片ID

    Returns:
        {
            "image_id": "xxx",
            "exists": true,
            "url": "/api/image/xxx"
        }
    """
    from app.services.image_cache import get_image_cache

    cache = get_image_cache()

    return {
        "image_id": image_id,
        "exists": cache.exists(image_id),
        "url": f"/api/image/{image_id}"
    }


@router.delete("/image/{image_id}")
async def delete_image(image_id: str):
    """删除指定图片

    Args:
        image_id: 图片ID

    Returns:
        {
            "success": true,
            "message": "Image deleted"
        }
    """
    from app.services.image_cache import get_image_cache

    cache = get_image_cache()
    success = cache.delete(image_id)

    if not success:
        raise HTTPException(status_code=404, detail="Image not found")

    return {
        "success": True,
        "message": "Image deleted"
    }
