"""
统一路径配置管理

解决项目中路径混乱的问题，确保所有模块使用一致的路径。

重要说明：
- 所有数据、报告、图片等文件统一存储在 backend/backend_data_registry/
- 禁止使用绝对路径或相对路径硬编码
- 所有工具必须使用此配置获取路径
"""
import os
from pathlib import Path
import tempfile
import re
from typing import Iterable
import structlog

logger = structlog.get_logger()

# 安装位置可由部署配置覆盖；未配置时才从本模块位置推导。
_DISCOVERED_BACKEND_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(
    os.environ.get("SUYUAN_BACKEND_ROOT", str(_DISCOVERED_BACKEND_ROOT))
).expanduser().resolve()
PROJECT_ROOT = Path(
    os.environ.get("SUYUAN_PROJECT_ROOT", str(BACKEND_ROOT.parent))
).expanduser().resolve()
TEMP_ROOT = Path(tempfile.gettempdir()).resolve()


def resolve_agent_path(path: str | Path) -> Path:
    """Resolve an Agent-facing filesystem path using the one shared contract.

    Relative paths are always relative to ``PROJECT_ROOT`` (the ``suyuan``
    repository root). Absolute paths are
    accepted and normalized. Access control is deliberately handled separately
    by :func:`is_path_within`, because each tool has a different permission
    boundary.
    """
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("path is required")
    # Do not interpret a path from another OS as a relative server path.
    if os.name != "nt" and (
        re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith(("\\\\", "//"))
    ):
        raise ValueError("path belongs to a different operating system")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def is_path_within(path: str | Path, allowed_roots: Iterable[str | Path]) -> bool:
    """Return whether a resolved path is contained by any allowed root."""
    resolved = Path(path).expanduser().resolve()
    return any(
        resolved.is_relative_to(Path(root).expanduser().resolve())
        for root in allowed_roots
    )


def format_agent_path(path: str | Path) -> str:
    """Format a filesystem path for Agent output without an ambiguous base.

    Paths inside the repository are returned relative to ``PROJECT_ROOT``. A
    backend path therefore always starts with ``backend/``. Paths outside the
    repository (for example temporary files) remain canonical absolute paths.
    """
    resolved = Path(path).expanduser().resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def get_data_registry() -> Path:
    """
    获取 data registry 的绝对路径

    统一规范：backend/backend_data_registry/

    Returns:
        Path: backend_data_registry 目录的绝对路径
    """
    from config.settings import settings

    configured = Path(settings.data_registry_dir).expanduser()
    if not configured.is_absolute():
        configured = BACKEND_ROOT / configured
    return configured.resolve()


def get_datasets_dir() -> Path:
    """获取数据集目录"""
    return get_data_registry() / "datasets"


def get_reports_dir() -> Path:
    """获取报告目录"""
    return get_data_registry() / "reports"


def get_images_dir() -> Path:
    """获取图片缓存目录"""
    return get_data_registry() / "images"


def get_uploads_dir() -> Path:
    """获取上传文件目录"""
    return get_data_registry() / "uploads"


def get_charts_dir() -> Path:
    """获取图表和可下载报告输出目录"""
    return get_data_registry() / "charts"


def get_memory_dir() -> Path:
    """获取记忆目录"""
    return get_data_registry() / "memory"


def get_sessions_dir() -> Path:
    """获取会话目录"""
    return get_data_registry() / "sessions"


def get_social_dir() -> Path:
    """获取社交数据目录"""
    return get_data_registry() / "social"


def get_social_memory_dir() -> Path:
    """获取社交记忆目录"""
    return get_social_dir() / "memory"


def get_python_output_dir() -> Path:
    """获取Python脚本输出目录"""
    return get_data_registry() / "python_output_files"


def get_chart_images_dir() -> Path:
    """获取图表图片输出目录"""
    return get_data_registry() / "chart_images"


# 验证路径存在
def ensure_directories():
    """确保所有必要的目录存在"""
    directories = [
        get_data_registry(),
        get_datasets_dir(),
        get_reports_dir(),
        get_images_dir(),
        get_uploads_dir(),
        get_charts_dir(),
        get_memory_dir(),
        get_sessions_dir(),
        get_social_dir(),
        get_social_memory_dir(),
        get_python_output_dir(),
        get_chart_images_dir(),
    ]

    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("directory_creation_failed", path=str(directory), error=str(e))


# 启动时验证
ensure_directories()

# 日志记录
logger.info(
    "path_config_initialized",
    data_registry=str(get_data_registry()),
    backend_root=str(BACKEND_ROOT)
)
