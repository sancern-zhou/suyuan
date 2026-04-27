"""
File Manager API Routes

提供文件浏览和下载功能，限制访问范围在/tmp目录内。
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
import os
from typing import List, Dict, Any
from datetime import datetime
import logging

# 测试重新加载
try:
    from test_reload import TEST_VERSION
    logger = logging.getLogger(__name__)
    logger.info(f"Loading file_manager_routes version: {TEST_VERSION}")
except ImportError:
    pass

router = APIRouter()

@router.get("/file-manager/test")
async def test_path():
    """测试路径解析"""
    test_cases = [
        ("", "空字符串"),
        ("/", "斜杠"),
        ("subdir", "相对路径"),
    ]

    results = []
    for path, desc in test_cases:
        if path and path != "/":
            target_path = ALLOWED_ROOT / path
        else:
            target_path = ALLOWED_ROOT

        results.append({
            "desc": desc,
            "path": path,
            "target_path": str(target_path),
            "resolved": str(target_path.resolve()),
            "safe": is_safe_path(target_path)
        })

    return {"results": results}

# 允许访问的根目录
ALLOWED_ROOT = Path("/tmp")

# 路径安全检查
def is_safe_path(path: Path) -> bool:
    """检查路径是否在允许的范围内"""
    try:
        # 解析为绝对路径并解析符号链接
        resolved = path.resolve()
        allowed_root_resolved = ALLOWED_ROOT.resolve()
        # 检查是否在允许的根目录下
        try:
            return resolved.is_relative_to(allowed_root_resolved)
        except AttributeError:
            # Python < 3.9 不支持 is_relative_to，使用备用方法
            try:
                resolved.relative_to(allowed_root_resolved)
                return True
            except ValueError:
                return False
    except (OSError, ValueError):
        return False

def format_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def get_file_info(file_path: Path, relative_path: str) -> Dict[str, Any]:
    """获取文件/目录信息"""
    try:
        stat = file_path.stat()
        return {
            "name": file_path.name,
            "path": relative_path,
            "is_dir": file_path.is_dir(),
            "size": stat.st_size if not file_path.is_dir() else 0,
            "size_formatted": format_size(stat.st_size) if not file_path.is_dir() else "",
            "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "modified_time_formatted": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
    except OSError as e:
        logger.error(f"Failed to get file info: {e}")
        return None

@router.get("/file-manager/list")
async def list_directory(path: str = Query("", description="目录路径，相对于/tmp")):
    """
    列出目录内容

    参数:
        path: 目录路径，相对于/tmp（例如 "subdir" 或 "" 表示/tmp根目录）

    返回:
        当前路径信息、父目录路径、文件和目录列表
    """
    # 调试：查看path的值和类型
    logger.info(f"list_directory called: path={repr(path)}, type={type(path)}")

    try:
        # 构建完整路径
        if path and path != "/":
            target_path = ALLOWED_ROOT / path
        else:
            target_path = ALLOWED_ROOT

        # 调试日志
        logger.info(f"File manager: path={repr(path)}, target_path={target_path}, resolved={target_path.resolve()}")

        # 安全检查
        if not is_safe_path(target_path):
            logger.error(f"Path safety check failed: {target_path.resolve()}")
            raise HTTPException(status_code=403, detail="访问被拒绝：路径超出允许范围")

        # 检查路径是否存在
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="路径不存在")

        # 必须是目录
        if not target_path.is_dir():
            raise HTTPException(status_code=400, detail="路径不是目录")

        # 获取相对路径
        try:
            relative_path = str(target_path.relative_to(ALLOWED_ROOT))
        except ValueError:
            relative_path = ""

        # 计算父目录路径
        parent_path = None
        if relative_path:
            parent = target_path.parent
            if parent != ALLOWED_ROOT:
                parent_path = str(parent.relative_to(ALLOWED_ROOT))

        # 列出内容
        items = []
        try:
            for entry in target_path.iterdir():
                entry_relative = entry.relative_to(ALLOWED_ROOT)
                info = get_file_info(entry, str(entry_relative))
                if info:
                    items.append(info)
        except PermissionError as e:
            logger.warning(f"Permission denied listing directory: {e}")
            raise HTTPException(status_code=403, detail="无权限访问此目录")

        # 排序：目录在前，文件在后；名称排序
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

        return {
            "success": True,
            "current_path": relative_path,
            "parent_path": parent_path,
            "root_path": "",
            "items": items,
            "item_count": len(items),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List directory failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"列出目录失败: {str(e)}")

@router.get("/file-manager/download")
async def download_file(path: str = Query(..., description="文件路径，相对于/tmp")):
    """
    下载文件

    参数:
        path: 文件路径，相对于/tmp（例如 "subdir/file.txt"）

    返回:
        文件内容
    """
    try:
        # 构建完整路径
        if path.startswith("/"):
            # 防止路径穿越攻击：拒绝绝对路径
            raise HTTPException(status_code=400, detail="不允许使用绝对路径")
        target_path = ALLOWED_ROOT / path

        # 安全检查
        if not is_safe_path(target_path):
            raise HTTPException(status_code=403, detail="访问被拒绝：路径超出允许范围")

        # 检查路径是否存在
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        # 必须是文件
        if not target_path.is_file():
            raise HTTPException(status_code=400, detail="路径不是文件")

        # 返回文件
        return FileResponse(
            path=target_path,
            filename=target_path.name,
            media_type='application/octet-stream'
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download file failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"下载文件失败: {str(e)}")

@router.get("/file-manager/info")
async def get_file_info_api(path: str = Query(..., description="文件/目录路径，相对于/tmp")):
    """
    获取文件/目录详细信息

    参数:
        path: 文件/目录路径，相对于/tmp

    返回:
        文件/目录详细信息
    """
    try:
        # 构建完整路径
        if path.startswith("/"):
            # 防止路径穿越攻击：拒绝绝对路径
            raise HTTPException(status_code=400, detail="不允许使用绝对路径")
        target_path = ALLOWED_ROOT / path

        # 安全检查
        if not is_safe_path(target_path):
            raise HTTPException(status_code=403, detail="访问被拒绝：路径超出允许范围")

        # 检查路径是否存在
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="路径不存在")

        # 获取相对路径
        relative_path = str(target_path.relative_to(ALLOWED_ROOT))

        # 获取文件信息
        info = get_file_info(target_path, relative_path)
        if not info:
            raise HTTPException(status_code=500, detail="无法获取文件信息")

        return {
            "success": True,
            "info": info
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get file info failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取文件信息失败: {str(e)}")
