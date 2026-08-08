"""测试专用线程执行器

验证：
1. 工作线程启动和关闭
2. 任务提交和执行
3. 线程一致性（每个 session 的任务在同一线程执行）
4. 多 session 并发（不同 session 可以在不同线程）
"""
import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from app.tools.browser.session_thread_executor import (
    SessionThreadExecutor,
    get_session_executor,
    shutdown_session_executor
)


class TestSessionThreadExecutor:
    """测试专用线程执行器"""

    def test_executor_singleton(self):
        """测试全局单例模式"""
        executor1 = get_session_executor()
        executor2 = get_session_executor()

        assert executor1 is executor2
        assert executor1.active_sessions == 0

    def test_simple_task(self):
        """测试简单任务执行"""
        executor = SessionThreadExecutor()

        def simple_task(x, y):
            return x + y

        result = executor.submit("default", simple_task, 10, 20)
        assert result == 30

        executor.shutdown()

    def test_task_with_exception(self):
        """测试任务抛出异常"""
        executor = SessionThreadExecutor()

        def failing_task():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            executor.submit("default", failing_task)

        executor.shutdown()

    def test_session_thread_consistency(self):
        """测试 session 线程一致性（核心功能）"""
        executor = SessionThreadExecutor()
        thread_ids = []

        def record_thread_id():
            thread_id = threading.get_ident()
            thread_ids.append(thread_id)
            return thread_id

        # 同一个 session 提交多个任务
        for _ in range(10):
            executor.submit("test_session", record_thread_id)

        # 所有任务应该在同一线程执行
        assert len(set(thread_ids)) == 1, f"Expected 1 thread, got {len(set(thread_ids))}"
        assert thread_ids[0] != threading.get_ident(), "Task should run in worker thread"

        # 验证映射
        assert executor.get_session_thread("test_session") == thread_ids[0]

        executor.shutdown()

    def test_multiple_sessions_different_threads(self):
        """测试多个 session 可以在不同线程执行"""
        executor = SessionThreadExecutor(max_workers=5)

        session_threads = {}

        def record_session_thread(session_id):
            thread_id = threading.get_ident()
            session_threads[session_id] = thread_id
            return thread_id

        # 提交不同 session 的任务
        sessions = ["session1", "session2", "session3"]
        for session in sessions:
            executor.submit(session, record_session_thread, session)
            # 稍微等待确保任务完成
            time.sleep(0.1)

        # 验证每个 session 都有线程分配
        for session in sessions:
            assert session in session_threads
            assert executor.get_session_thread(session) is not None

        # 注意：由于线程池可能复用线程，不同 session 可能使用相同线程
        # 只要每个 session 内部线程一致即可
        for session in sessions:
            thread_id = session_threads[session]
            sessions_on_thread = executor.get_thread_sessions(thread_id)
            assert session in sessions_on_thread

        executor.shutdown()

    def test_task_with_kwargs(self):
        """测试带关键字参数的任务"""
        executor = SessionThreadExecutor()

        def task_with_kwargs(a, b, c=10):
            return a + b + c

        result = executor.submit("default", task_with_kwargs, 5, 3, c=20)
        assert result == 28

        executor.shutdown()

    def test_get_status(self):
        """测试状态获取"""
        executor = SessionThreadExecutor()

        def dummy_task():
            return "done"

        # 初始状态
        status = executor.get_status()
        assert status["active_sessions"] == 0
        assert status["active_threads"] == 0
        assert status["max_workers"] == 20

        # 执行任务后
        executor.submit("session1", dummy_task)
        executor.submit("session2", dummy_task)

        status = executor.get_status()
        assert status["active_sessions"] == 2
        assert status["active_threads"] <= 2  # 可能复用线程
        assert "session_mappings" in status

        executor.shutdown()

    def test_shutdown_waits_for_completion(self):
        """测试关闭时等待任务完成"""
        executor = SessionThreadExecutor()
        results = []

        def task(n):
            time.sleep(0.05)
            results.append(n)
            return n

        # 提交多个任务
        for i in range(5):
            executor.submit("default", task, i)

        # 关闭并等待完成
        executor.shutdown(wait=True)

        # 所有任务应该完成
        assert len(results) == 5
        assert sorted(results) == [0, 1, 2, 3, 4]

    def test_nested_call_same_session(self):
        """测试同 session 嵌套调用"""
        executor = SessionThreadExecutor()

        def outer_task():
            def inner_task():
                return "inner"

            # 在同一线程中再次提交任务（会复用线程）
            result = executor.submit("default", inner_task)
            return f"outer: {result}"

        result = executor.submit("default", outer_task)
        assert result == "outer: inner"

        executor.shutdown()

    def test_concurrent_sessions(self):
        """测试并发多 session 操作"""
        executor = SessionThreadExecutor(max_workers=10)

        session_results = {}

        def session_task(session_id, delay):
            time.sleep(delay)
            thread_id = threading.get_ident()
            session_results[session_id] = {
                "thread_id": thread_id,
                "delay": delay
            }
            return f"{session_id}: {thread_id}"

        # 并发提交多个 session
        import concurrent.futures

        futures = []
        with ThreadPoolExecutor(max_workers=5) as submitter:
            for i in range(5):
                session_id = f"session{i}"
                future = submitter.submit(
                    executor.submit,
                    session_id,
                    session_task,
                    session_id,
                    0.05 * i
                )
                futures.append(future)

        # 等待所有任务完成
        for future in futures:
            future.result()

        # 验证
        assert len(session_results) == 5
        for session_id in session_results:
            assert executor.get_session_thread(session_id) is not None

        executor.shutdown()

    def test_thread_mapping_persistence(self):
        """测试线程映射持久性"""
        executor = SessionThreadExecutor()

        def first_task():
            return threading.get_ident()

        def second_task():
            return threading.get_ident()

        # 第一次执行
        thread1 = executor.submit("persistent", first_task)

        # 第二次执行（应该使用相同线程）
        thread2 = executor.submit("persistent", second_task)

        # 验证线程一致性
        assert thread1 == thread2
        assert executor.get_session_thread("persistent") == thread1

        executor.shutdown()

    def test_max_workers_limit(self):
        """测试最大工作线程数限制"""
        executor = SessionThreadExecutor(max_workers=3)

        def worker_task():
            time.sleep(0.1)
            return threading.get_ident()

        # 提交超过 max_workers 的任务数
        results = []
        for i in range(5):
            result = executor.submit(f"session{i}", worker_task)
            results.append(result)

        # 所有任务应该完成
        assert len(results) == 5

        # 活跃线程数不应该超过 max_workers
        # 注意：由于任务可能快速完成，这里只验证不会崩溃
        assert executor.active_threads <= 3

        executor.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
