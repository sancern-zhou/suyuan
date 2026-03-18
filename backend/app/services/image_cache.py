"""
图片缓存服务 - 存储和检索生成的图表图片

功能：
- 将base64图片保存到磁盘
- 通过image_id检索图片
- 支持图片URL生成
"""

import os
import uuid
import base64
from datetime import datetime
from typing import Optional
import structlog

logger = structlog.get_logger()

# 图片存储目录（相对于backend）
IMAGE_CACHE_DIR = "backend_data_registry/images"


class ImageCache:
    """图片缓存管理器"""

    def __init__(self, cache_dir: Optional[str] = None):
        """初始化图片缓存

        Args:
            cache_dir: 图片存储目录，默认为 backend_data_registry/images
        """
        if cache_dir:
            self.cache_dir = cache_dir
        else:
            # 相对于当前工作目录
            self.cache_dir = os.path.join(os.getcwd(), IMAGE_CACHE_DIR)

        os.makedirs(self.cache_dir, exist_ok=True)
        logger.info("image_cache_initialized", cache_dir=self.cache_dir)

    def save(self, base64_data: str, chart_id: Optional[str] = None) -> dict:
        """保存base64图片，返回图片信息

        Args:
            base64_data: base64编码的图片数据（不带data:image/png;base64,前缀）
            chart_id: 可选的图表ID，如果不提供则自动生成

        Returns:
            {
                "image_id": str,        # 图片ID
                "local_path": str,      # 本地文件路径（绝对路径）
                "url": str,            # HTTP访问URL
                "size_kb": float       # 文件大小（KB）
            }
        """
        # 去除可能的前缀
        if base64_data.startswith("data:image"):
            base64_data = base64_data.split(",", 1)[1]

        # 检测图片格式（检查前几个字节）
        image_bytes = base64.b64decode(base64_data[:100] + "==")  # 解码前100字节用于检测
        is_gif = image_bytes[:3] == b'GIF'

        # 生成唯一的image_id
        if not chart_id:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            chart_id = f"img_{timestamp}_{uuid.uuid4().hex[:8]}"

        # 保存为文件（总是使用.png扩展名，内部会处理GIF格式）
        filepath = os.path.join(self.cache_dir, f"{chart_id}.png")
        try:
            full_image_bytes = base64.b64decode(base64_data)
            with open(filepath, 'wb') as f:
                f.write(full_image_bytes)

            logger.info(
                "image_saved",
                image_id=chart_id,
                size_kb=len(full_image_bytes) / 1024,
                format="GIF" if is_gif else "PNG"
            )

            # 返回完整信息（本地路径 + URL）
            return {
                "image_id": chart_id,
                "local_path": os.path.abspath(filepath),
                "url": self.get_url(chart_id),
                "size_kb": len(full_image_bytes) / 1024
            }
        except Exception as e:
            logger.error("image_save_failed", image_id=chart_id, error=str(e))
            raise

    def get(self, image_id: str) -> Optional[str]:
        """获取base64图片数据（不带data:image前缀）

        Args:
            image_id: 图片ID

        Returns:
            base64编码的图片数据，如果不存在返回None
        """
        filepath = os.path.join(self.cache_dir, f"{image_id}.png")
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        return None

    def get_full(self, image_id: str) -> Optional[str]:
        """获取完整的data URL

        Args:
            image_id: 图片ID

        Returns:
            完整的data URL，如 "data:image/png;base64,..."
        """
        base64_data = self.get(image_id)
        if base64_data:
            return f"data:image/png;base64,{base64_data}"
        return None

    def get_url(self, image_id: str) -> str:
        """获取图片访问URL

        Args:
            image_id: 图片ID

        Returns:
            图片访问URL
        """
        return f"/api/image/{image_id}"

    def exists(self, image_id: str) -> bool:
        """检查图片是否存在"""
        filepath = os.path.join(self.cache_dir, f"{image_id}.png")
        return os.path.exists(filepath)

    def delete(self, image_id: str) -> bool:
        """删除图片

        Args:
            image_id: 图片ID

        Returns:
            是否删除成功
        """
        filepath = os.path.join(self.cache_dir, f"{image_id}.png")
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info("image_deleted", image_id=image_id)
            return True
        return False

    def cleanup_old(self, days: int = 7) -> int:
        """清理指定天数之前的图片

        Args:
            days: 天数，清理此天数之前的图片

        Returns:
            删除的图片数量
        """
        import time

        cutoff = time.time() - (days * 24 * 60 * 60)
        deleted = 0

        for filename in os.listdir(self.cache_dir):
            filepath = os.path.join(self.cache_dir, filename)
            if os.path.isfile(filepath):
                mtime = os.path.getmtime(filepath)
                if mtime < cutoff:
                    os.remove(filepath)
                    deleted += 1

        logger.info("image_cleanup_completed", deleted=deleted, days=days)
        return deleted


# 单例实例（懒加载）
_image_cache: Optional[ImageCache] = None


def get_image_cache() -> ImageCache:
    """获取图片缓存单例"""
    global _image_cache
    if _image_cache is None:
        _image_cache = ImageCache()
    return _image_cache
