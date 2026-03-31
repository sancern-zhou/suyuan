"""
检查点管理器

提供任务执行状态检查点的保存和恢复功能。
"""

import json
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import structlog

logger = structlog.get_logger()


class Checkpoint:
    """检查点数据模型"""

    def __init__(
        self,
        checkpoint_id: str,
        pipeline_state: Dict[str, Any],
        expert_results: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ):
        self.checkpoint_id = checkpoint_id
        self.pipeline_state = pipeline_state
        self.expert_results = expert_results
        self.timestamp = timestamp or datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "checkpoint_id": self.checkpoint_id,
            "pipeline_state": self.pipeline_state,
            "expert_results": self.expert_results,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        """从字典创建"""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            pipeline_state=data["pipeline_state"],
            expert_results=data["expert_results"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else None
        )


class CheckpointManager:
    """
    检查点管理器

    功能：
    1. 保存检查点（pipeline状态和专家结果）
    2. 恢复检查点
    3. 列出所有检查点
    4. 删除检查点
    """

    def __init__(self, checkpoint_dir: str = "backend_data_registry/checkpoints"):
        """
        初始化检查点管理器

        Args:
            checkpoint_dir: 检查点存储目录
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        pipeline_state: Dict[str, Any],
        expert_results: Dict[str, Any],
        checkpoint_id: Optional[str] = None
    ) -> str:
        """
        保存检查点

        Args:
            pipeline_state: 流水线状态
            expert_results: 专家执行结果
            checkpoint_id: 检查点ID（可选，自动生成）

        Returns:
            检查点ID
        """
        if not checkpoint_id:
            checkpoint_id = f"checkpoint_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            pipeline_state=pipeline_state,
            expert_results=expert_results
        )

        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"

        try:
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2, default=str)

            logger.info(
                "checkpoint_saved",
                checkpoint_id=checkpoint_id,
                path=str(checkpoint_path)
            )
            return checkpoint_id

        except Exception as e:
            logger.error(
                "failed_to_save_checkpoint",
                checkpoint_id=checkpoint_id,
                error=str(e)
            )
            raise

    def load_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """
        加载检查点

        Args:
            checkpoint_id: 检查点ID

        Returns:
            检查点对象，如果不存在返回None
        """
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"

        if not checkpoint_path.exists():
            logger.warning("checkpoint_not_found", checkpoint_id=checkpoint_id)
            return None

        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            checkpoint = Checkpoint.from_dict(data)

            logger.info(
                "checkpoint_loaded",
                checkpoint_id=checkpoint_id,
                timestamp=checkpoint.timestamp.isoformat()
            )
            return checkpoint

        except Exception as e:
            logger.error(
                "failed_to_load_checkpoint",
                checkpoint_id=checkpoint_id,
                error=str(e)
            )
            return None

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """
        列出所有检查点

        Returns:
            检查点信息列表
        """
        checkpoints = []

        for checkpoint_file in self.checkpoint_dir.glob("checkpoint_*.json"):
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                checkpoints.append({
                    "checkpoint_id": data["checkpoint_id"],
                    "timestamp": data.get("timestamp"),
                    "pipeline_state_keys": list(data.get("pipeline_state", {}).keys()),
                    "expert_results_keys": list(data.get("expert_results", {}).keys())
                })

            except Exception as e:
                logger.warning(
                    "failed_to_read_checkpoint",
                    file=str(checkpoint_file),
                    error=str(e)
                )

        # 按时间戳倒序排列
        checkpoints.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return checkpoints

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        删除检查点

        Args:
            checkpoint_id: 检查点ID

        Returns:
            是否删除成功
        """
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"

        if not checkpoint_path.exists():
            logger.warning("checkpoint_not_found", checkpoint_id=checkpoint_id)
            return False

        try:
            checkpoint_path.unlink()
            logger.info("checkpoint_deleted", checkpoint_id=checkpoint_id)
            return True

        except Exception as e:
            logger.error(
                "failed_to_delete_checkpoint",
                checkpoint_id=checkpoint_id,
                error=str(e)
            )
            return False

    def clear_old_checkpoints(self, keep_latest: int = 10) -> int:
        """
        清理旧检查点，只保留最新的N个

        Args:
            keep_latest: 保留最新的检查点数量

        Returns:
            删除的检查点数量
        """
        checkpoints = self.list_checkpoints()

        if len(checkpoints) <= keep_latest:
            return 0

        # 删除多余的检查点
        deleted_count = 0
        for checkpoint in checkpoints[keep_latest:]:
            if self.delete_checkpoint(checkpoint["checkpoint_id"]):
                deleted_count += 1

        logger.info(
            "old_checkpoints_cleared",
            deleted_count=deleted_count,
            remaining_count=len(checkpoints) - deleted_count
        )

        return deleted_count
