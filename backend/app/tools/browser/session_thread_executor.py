"""专用线程执行器 - 为每个 session 分配专用线程

解决 Playwright 对象的线程亲和性问题：
- 每个 session_id 分配一个专用线程
- 该 session 的所有操作都在同一线程执行
- 支持多 session 并发，每个 session 独立线程

修复版本：使用真正专用线程，而不是线程池
"""
import threading
import structlog
import queue
from typing import Dict, Any, Callable, Optional, Tuple
from enum import Enum


logger = structlog.get_logger()


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionWorkerThread(threading.Thread):
    """Session专用工作线程

    每个session有一个专用线程，所有操作都在该线程执行
    """

    def __init__(self, session_id: str, daemon: bool = True):
        """初始化工作线程

        Args:
            session_id: Session ID
            daemon: 是否设为守护线程
        """
        super().__init__(
            daemon=daemon,
            name=f"browser_session_{session_id}"
        )
        self.session_id = session_id
        self.task_queue: queue.Queue = queue.Queue()
        self.result_dict: Dict[int, Any] = {}
        self.result_events: Dict[int, threading.Event] = {}
        self.lock = threading.Lock()
        self.task_counter = 0
        self.running = True
        self.thread_id = None

        logger.info(
            "[SESSION_WORKER] Thread created",
            session_id=session_id,
            thread_name=self.name
        )

    def run(self):
        """线程主循环"""
        self.thread_id = threading.get_ident()

        logger.info(
            "[SESSION_WORKER] Thread started",
            session_id=self.session_id,
            thread_id=self.thread_id
        )

        while self.running:
            try:
                # 获取任务（带超时，避免永久阻塞）
                try:
                    task_id, task_func, args, kwargs = self.task_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # 执行任务
                try:
                    logger.debug(
                        "[SESSION_WORKER] Executing task",
                        session_id=self.session_id,
                        task_id=task_id,
                        thread_id=self.thread_id
                    )

                    result = task_func(*args, **kwargs)

                    # 存储结果
                    with self.lock:
                        self.result_dict[task_id] = (True, result)

                    logger.debug(
                        "[SESSION_WORKER] Task completed",
                        session_id=self.session_id,
                        task_id=task_id
                    )

                except Exception as e:
                    # 存储错误
                    with self.lock:
                        self.result_dict[task_id] = (False, e)

                    logger.error(
                        "[SESSION_WORKER] Task failed",
                        session_id=self.session_id,
                        task_id=task_id,
                        error=str(e),
                        exc_info=True
                    )

                finally:
                    # 通知等待者
                    if task_id in self.result_events:
                        self.result_events[task_id].set()

            except Exception as e:
                logger.error(
                    "[SESSION_WORKER] Unexpected error in thread loop",
                    session_id=self.session_id,
                    error=str(e),
                    exc_info=True
                )

        logger.info(
            "[SESSION_WORKER] Thread stopped",
            session_id=self.session_id,
            thread_id=self.thread_id
        )

    def submit_task(
        self,
        task_func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        timeout: float = 120.0
    ) -> Any:
        """提交任务到线程

        Args:
            task_func: 要执行的函数
            args: 位置参数
            kwargs: 关键字参数
            timeout: 超时时间（秒）

        Returns:
            任务执行结果

        Raises:
            TimeoutError: 任务超时
            RuntimeError: 任务执行失败
        """
        if kwargs is None:
            kwargs = {}

        # 分配任务ID
        with self.lock:
            task_id = self.task_counter
            self.task_counter += 1
            self.result_events[task_id] = threading.Event()

        try:
            # 提交任务到队列
            self.task_queue.put((task_id, task_func, args, kwargs))

            # 等待结果
            if not self.result_events[task_id].wait(timeout=timeout):
                raise TimeoutError(
                    f"Task {task_id} timed out after {timeout}s"
                )

            # 获取结果
            with self.lock:
                success, result = self.result_dict.pop(task_id)
                self.result_events.pop(task_id)

            if success:
                return result
            else:
                raise RuntimeError(f"Task failed: {result}")

        finally:
            # 清理
            with self.lock:
                if task_id in self.result_events:
                    self.result_events.pop(task_id)
                if task_id in self.result_dict:
                    self.result_dict.pop(task_id)

    def stop(self):
        """停止线程"""
        logger.info(
            "[SESSION_WORKER] Stopping thread",
            session_id=self.session_id
        )
        self.running = False

        # 等待线程结束
        if self.is_alive():
            self.join(timeout=5.0)


class SessionThreadExecutor:
    """为每个 session 分配专用线程的执行器

    修复版本：每个session有真正专用的线程
    """

    def __init__(self, max_workers: int = 20):
        """初始化执行器

        Args:
            max_workers: 最大工作线程数（默认20，支持最多20个并发session）
        """
        # session_id -> SessionWorkerThread 映射
        self._session_threads: Dict[str, SessionWorkerThread] = {}

        # 锁保护
        self._lock = threading.Lock()

        self._max_workers = max_workers

        logger.info(
            "[SESSION_EXECUTOR] Initialized (v2.0 - dedicated threads)",
            max_workers=max_workers
        )

    def submit(
        self,
        session_id: str,
        task_func: Callable,
        *args,
        timeout: float = 120.0,
        **kwargs
    ) -> Any:
        """提交 session 任务到专用线程

        Args:
            session_id: Session ID
            task_func: 要执行的任务函数
            *args: 位置参数
            timeout: 超时时间（秒）
            **kwargs: 关键字参数

        Returns:
            任务执行结果

        Raises:
            TimeoutError: 任务超时
            RuntimeError: 任务执行失败
        """
        # 获取或创建session专用线程
        worker = self._get_or_create_worker(session_id)

        # 提交任务
        logger.debug(
            "[SESSION_EXECUTOR] Submitting task",
            session_id=session_id,
            thread_id=worker.thread_id,
            task_func=task_func.__name__
        )

        result = worker.submit_task(
            task_func=task_func,
            args=args,
            kwargs=kwargs,
            timeout=timeout
        )

        return result

    def _get_or_create_worker(self, session_id: str) -> SessionWorkerThread:
        """获取或创建session专用工作线程

        Args:
            session_id: Session ID

        Returns:
            SessionWorkerThread实例
        """
        with self._lock:
            # 检查是否已存在
            if session_id in self._session_threads:
                worker = self._session_threads[session_id]

                # 检查线程是否还存活
                if not worker.is_alive():
                    logger.warning(
                        "[SESSION_EXECUTOR] Worker thread died, recreating",
                        session_id=session_id
                    )
                    del self._session_threads[session_id]
                else:
                    return worker

            # 检查是否超过最大线程数
            if len(self._session_threads) >= self._max_workers:
                raise RuntimeError(
                    f"Maximum sessions ({self._max_workers}) reached. "
                    f"Cannot create new session '{session_id}'"
                )

            # 创建新的工作线程
            worker = SessionWorkerThread(session_id)
            worker.start()

            self._session_threads[session_id] = worker

            logger.info(
                "[SESSION_EXECUTOR] Worker created",
                session_id=session_id,
                thread_id=worker.thread_id,
                active_sessions=len(self._session_threads)
            )

            return worker

    def get_session_thread(self, session_id: str) -> Optional[int]:
        """获取 session 分配的线程 ID

        Args:
            session_id: Session ID

        Returns:
            线程ID，如果session未分配则返回None
        """
        with self._lock:
            if session_id in self._session_threads:
                return self._session_threads[session_id].thread_id
            return None

    def close_session(self, session_id: str):
        """关闭session并停止其专用线程

        Args:
            session_id: Session ID
        """
        with self._lock:
            if session_id in self._session_threads:
                worker = self._session_threads.pop(session_id)
                worker.stop()

                logger.info(
                    "[SESSION_EXECUTOR] Session closed",
                    session_id=session_id,
                    remaining_sessions=len(self._session_threads)
                )

    def shutdown(self, wait: bool = True):
        """关闭执行器

        Args:
            wait: 是否等待任务完成
        """
        with self._lock:
            logger.info(
                "[SESSION_EXECUTOR] Shutting down executor",
                active_sessions=len(self._session_threads)
            )

            # 停止所有工作线程
            for session_id, worker in list(self._session_threads.items()):
                try:
                    worker.stop()
                except Exception as e:
                    logger.error(
                        "[SESSION_EXECUTOR] Error stopping worker",
                        session_id=session_id,
                        error=str(e)
                    )

            self._session_threads.clear()

            logger.info("[SESSION_EXECUTOR] Executor shutdown complete")

    @property
    def active_sessions(self) -> int:
        """获取活跃 session 数量"""
        with self._lock:
            return len(self._session_threads)

    @property
    def active_threads(self) -> int:
        """获取活跃线程数量"""
        with self._lock:
            return len(self._session_threads)

    def get_status(self) -> Dict[str, Any]:
        """获取执行器状态"""
        with self._lock:
            return {
                "version": "2.0 (dedicated threads)",
                "active_sessions": len(self._session_threads),
                "max_workers": self._max_workers,
                "session_mappings": {
                    sid: worker.thread_id
                    for sid, worker in self._session_threads.items()
                }
            }


# 全局单例
_session_executor: Optional[SessionThreadExecutor] = None
_executor_lock = threading.Lock()


def get_session_executor() -> SessionThreadExecutor:
    """获取全局 session 执行器单例（线程安全）"""
    global _session_executor

    if _session_executor is None:
        with _executor_lock:
            # 双重检查锁定
            if _session_executor is None:
                _session_executor = SessionThreadExecutor()
                logger.info("[SESSION_EXECUTOR] Global executor created (v2.0)")

    return _session_executor


def shutdown_session_executor():
    """关闭全局 session 执行器"""
    global _session_executor

    with _executor_lock:
        if _session_executor is not None:
            _session_executor.shutdown()
            _session_executor = None
            logger.info("[SESSION_EXECUTOR] Global executor shutdown")
