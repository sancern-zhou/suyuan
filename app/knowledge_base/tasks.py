"""
异步文档处理任务

提供后台文档处理队列，支持：
- 异步文档解析和向量化
- 任务状态追踪
- 失败重试
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import structlog

logger = structlog.get_logger()


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DocumentTask:
    """文档处理任务"""
    doc_id: str
    kb_id: str
    file_path: str
    user_id: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


class DocumentProcessingQueue:
    """
    异步文档处理队列

    使用asyncio.Queue实现简单的任务队列
    """

    def __init__(self, max_workers: int = 2, max_queue_size: int = 100):
        """
        初始化处理队列

        Args:
            max_workers: 最大并发工作线程数
            max_queue_size: 队列最大长度
        """
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._tasks: Dict[str, DocumentTask] = {}
        self._is_running = False
        self._workers: list = []
        self._max_workers = max_workers
        self._service = None

    async def _get_db_session(self):
        """获取数据库会话（每次任务创建新会话）"""
        from app.db.database import async_session
        return async_session()

    async def _get_service(self, db):
        """获取知识库服务"""
        from app.knowledge_base.service import KnowledgeBaseService
        return KnowledgeBaseService(db=db)

    async def enqueue(
        self,
        doc_id: str,
        kb_id: str,
        file_path: str,
        user_id: str
    ) -> DocumentTask:
        """
        添加文档到处理队列

        Args:
            doc_id: 文档ID
            kb_id: 知识库ID
            file_path: 文件路径
            user_id: 用户ID

        Returns:
            DocumentTask对象
        """
        task = DocumentTask(
            doc_id=doc_id,
            kb_id=kb_id,
            file_path=file_path,
            user_id=user_id
        )

        self._tasks[doc_id] = task

        await self._queue.put(task)

        logger.info(
            "document_task_enqueued",
            doc_id=doc_id,
            kb_id=kb_id,
            queue_size=self._queue.qsize()
        )

        return task

    async def start(self):
        """启动处理队列"""
        if self._is_running:
            return

        self._is_running = True

        # 启动worker
        for i in range(self._max_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)

        logger.info(
            "document_processing_queue_started",
            workers=self._max_workers
        )

    async def stop(self):
        """停止处理队列"""
        self._is_running = False

        # 取消所有worker
        for worker in self._workers:
            worker.cancel()

        # 等待worker完成
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        logger.info("document_processing_queue_stopped")

    async def _worker(self, worker_id: int):
        """
        工作线程

        Args:
            worker_id: 工作线程ID
        """
        logger.info("document_worker_started", worker_id=worker_id)

        while self._is_running:
            try:
                # 等待任务，超时1秒
                try:
                    task = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # 处理任务
                await self._process_task(task, worker_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "document_worker_error",
                    worker_id=worker_id,
                    error=str(e)
                )

        logger.info("document_worker_stopped", worker_id=worker_id)

    async def _process_task(self, task: DocumentTask, worker_id: int):
        """
        处理单个任务

        Args:
            task: 文档任务
            worker_id: 工作线程ID
        """
        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.utcnow()

        logger.info(
            "document_task_processing",
            doc_id=task.doc_id,
            worker_id=worker_id
        )

        # 每个任务使用独立的数据库会话
        db = await self._get_db_session()

        try:
            service = await self._get_service(db)

            # 获取知识库
            kb = await service.get_knowledge_base(task.kb_id)
            if not kb:
                raise ValueError(f"Knowledge base not found: {task.kb_id}")

            # 获取文档
            from sqlalchemy import select
            from app.knowledge_base.models import Document

            result = await db.execute(
                select(Document).where(Document.id == task.doc_id)
            )
            doc = result.scalar_one_or_none()
            if not doc:
                raise ValueError(f"Document not found: {task.doc_id}")

            # 调用服务处理文档
            await service._process_document(doc, kb)

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()

            logger.info(
                "document_task_completed",
                doc_id=task.doc_id,
                duration_s=(task.completed_at - task.started_at).total_seconds()
            )

        except Exception as e:
            task.error_message = str(e)
            task.retry_count += 1

            if task.retry_count < task.max_retries:
                # 重新入队
                task.status = TaskStatus.PENDING
                await self._queue.put(task)
                logger.warning(
                    "document_task_retry",
                    doc_id=task.doc_id,
                    retry_count=task.retry_count,
                    error=str(e)
                )
            else:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.utcnow()
                logger.error(
                    "document_task_failed",
                    doc_id=task.doc_id,
                    error=str(e)
                )

        finally:
            # 确保关闭数据库会话
            await db.close()

    def get_task_status(self, doc_id: str) -> Optional[DocumentTask]:
        """获取任务状态"""
        return self._tasks.get(doc_id)

    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计"""
        status_counts = {}
        for task in self._tasks.values():
            status = task.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "queue_size": self._queue.qsize(),
            "total_tasks": len(self._tasks),
            "workers": len(self._workers),
            "is_running": self._is_running,
            "status_counts": status_counts
        }


# 全局队列实例
_processing_queue: Optional[DocumentProcessingQueue] = None


def get_processing_queue() -> DocumentProcessingQueue:
    """获取全局处理队列"""
    global _processing_queue
    if _processing_queue is None:
        _processing_queue = DocumentProcessingQueue()
    return _processing_queue


async def start_processing_queue():
    """启动全局处理队列（应用启动时调用）"""
    queue = get_processing_queue()
    await queue.start()


async def stop_processing_queue():
    """停止全局处理队列（应用关闭时调用）"""
    global _processing_queue
    if _processing_queue:
        await _processing_queue.stop()
        _processing_queue = None
