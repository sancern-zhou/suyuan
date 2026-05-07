"""
统一路径配置管理

解决项目中路径混乱的问题，确保所有模块使用一致的路径。

重要说明：
- 所有数据、报告、图片等文件统一存储在 backend/backend_data_registry/
- 禁止使用绝对路径或相对路径硬编码
- 所有工具必须使用此配置获取路径
"""
from pathlib import Path
from functools import lru_cache
import structlog

logger = structlog.get_logger()

# 项目根目录：backend/ 目录
# __file__ 位于 backend/app/utils/path_config.py
# parents[1] = backend/app
# parents[2] = backend
BACKEND_ROOT = Path(__file__).resolve().parents[2]

# 项目根目录：suyuan/ 目录（如果需要）
PROJECT_ROOT = BACKEND_ROOT.parent


@lru_cache(maxsize=1)
def get_data_registry() -> Path:
    """
    获取 data registry 的绝对路径

    统一规范：backend/backend_data_registry/

    Returns:
        Path: backend_data_registry 目录的绝对路径
    """
    return (BACKEND_ROOT / "backend_data_registry").resolve()


def get_datasets_dir() -> Path:
    """获取数据集目录"""
    return get_data_registry() / "datasets"


def get_reports_dir() -> Path:
    """获取报告目录"""
    return get_data_registry() / "reports"


def get_images_dir() -> Path:
    """获取图片缓存目录"""
    return get_data_registry() / "images"


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
