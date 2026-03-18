"""
LLM API 监控工具

监控和统计 LLM API 调用情况
"""

import time
import asyncio
from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict
import json
import csv
from pathlib import Path
import structlog

from .token_counter import TokenCounter

logger = structlog.get_logger()


@dataclass
class LLMCallRecord:
    """单次 LLM 调用记录"""

    timestamp: float
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    ttft: float = 0.0  # Time To First Token (首字延迟，秒)
    output_rate: float = 0.0  # Token 输出速率 (tokens/秒)
    total_time: float = 0.0  # 总耗时（秒）
    success: bool = True
    error: Optional[str] = None
    cost: float = 0.0  # 估算成本（美元）
    stream_mode: bool = False  # 是否为流式调用

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class LLMMonitor:
    """LLM API 监控器"""

    # 模型定价（每 1K tokens，美元）
    # 输入价格 / 输出价格
    MODEL_PRICING = {
        "gpt-4": (0.03, 0.06),
        "gpt-4-turbo": (0.01, 0.03),
        "gpt-4-turbo-preview": (0.01, 0.03),
        "gpt-3.5-turbo": (0.0015, 0.002),
        "deepseek-chat": (0.00014, 0.00028),
        "deepseek-reasoner": (0.00055, 0.002),
        "minimax-m2": (0.001, 0.002),
        "mimo-v2-flash": (0.0001, 0.0002),
    }

    def __init__(self, persistence_file: Optional[str] = None):
        """
        初始化监控器
        
        Args:
            persistence_file: 持久化文件路径（可选）。如果提供，会自动加载和保存数据
        """
        self.records: List[LLMCallRecord] = []
        self._lock = asyncio.Lock()
        self.token_counter = TokenCounter()
        self.persistence_file = persistence_file
        
        # 如果指定了持久化文件，尝试加载历史数据
        if self.persistence_file:
            self._load_from_file()
    
    def _load_from_file(self):
        """从文件加载历史数据"""
        if not self.persistence_file:
            return
        
        try:
            file_path = Path(self.persistence_file)
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 将字典转换回 LLMCallRecord 对象
                    records_data = data.get('records', [])
                    self.records = [
                        LLMCallRecord(**record) if isinstance(record, dict) else record
                        for record in records_data
                    ]
                logger.info("llm_monitor_loaded_history", record_count=len(self.records))
        except Exception as e:
            logger.warning("llm_monitor_load_failed", error=str(e))
    
    def _save_to_file(self):
        """保存数据到文件"""
        if not self.persistence_file:
            return
        
        try:
            file_path = Path(self.persistence_file)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "last_updated": datetime.now().isoformat(),
                "total_records": len(self.records),
                "records": [record.to_dict() for record in self.records]
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.warning("llm_monitor_save_failed", error=str(e))

    async def record_call(
        self,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        ttft: float,
        total_time: float,
        success: bool = True,
        error: Optional[str] = None,
        stream_mode: bool = False
    ) -> LLMCallRecord:
        """
        记录一次 LLM 调用

        Args:
            model: 模型名称
            provider: Provider 名称
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
            ttft: 首字延迟（秒）
            total_time: 总耗时（秒）
            success: 是否成功
            error: 错误信息
            stream_mode: 是否为流式调用

        Returns:
            调用记录
        """
        total_tokens = input_tokens + output_tokens
        output_rate = output_tokens / total_time if total_time > 0 else 0.0
        cost = self._calculate_cost(model, input_tokens, output_tokens)

        record = LLMCallRecord(
            timestamp=time.time(),
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            ttft=ttft,
            output_rate=output_rate,
            total_time=total_time,
            success=success,
            error=error,
            cost=cost,
            stream_mode=stream_mode
        )

        async with self._lock:
            self.records.append(record)
        
        # 自动保存到文件（如果启用了持久化）
        if self.persistence_file:
            self._save_to_file()

        logger.info(
            "llm_call_recorded",
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            ttft=ttft,
            output_rate=output_rate,
            cost=cost
        )

        return record

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """计算成本"""
        # 检查完整匹配
        if model in self.MODEL_PRICING:
            input_price, output_price = self.MODEL_PRICING[model]
        else:
            # 检查部分匹配
            pricing = None
            for key, prices in self.MODEL_PRICING.items():
                if key in model or model in key:
                    pricing = prices
                    break

            if pricing:
                input_price, output_price = pricing
            else:
                # 默认使用 GPT-3.5 定价
                input_price, output_price = self.MODEL_PRICING["gpt-3.5-turbo"]

        input_cost = (input_tokens / 1000) * input_price
        output_cost = (output_tokens / 1000) * output_price
        return input_cost + output_cost

    async def track_stream_call(
        self,
        model: str,
        provider: str,
        messages: List[Dict[str, Any]],
        stream_generator: Awaitable
    ) -> str:
        """
        跟踪流式调用

        Args:
            model: 模型名称
            provider: Provider 名称
            messages: 输入消息
            stream_generator: 流式生成器

        Returns:
            完整响应内容
        """
        start_time = time.time()
        first_token_time = None
        content_parts = []
        input_tokens = self.token_counter.count_messages(messages)

        try:
            async for chunk in stream_generator:
                # 记录首字时间
                if first_token_time is None:
                    first_token_time = time.time()
                    ttft = first_token_time - start_time
                else:
                    ttft = 0.0

                # 提取内容
                try:
                    choices = getattr(chunk, "choices", None) or []
                    if choices:
                        delta = choices[0].delta or {}
                        piece = getattr(delta, "content", None)
                        if piece:
                            content_parts.append(piece)
                except Exception:
                    pass

            end_time = time.time()
            total_time = end_time - start_time
            full_content = "".join(content_parts)
            output_tokens = self.token_counter.count_tokens(full_content)

            if first_token_time is None:
                ttft = total_time  # 如果没有收到任何 token，使用总时间

            await self.record_call(
                model=model,
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                ttft=ttft,
                total_time=total_time,
                success=True,
                stream_mode=True
            )

            return full_content

        except Exception as e:
            end_time = time.time()
            total_time = end_time - start_time
            await self.record_call(
                model=model,
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=0,
                ttft=total_time,
                total_time=total_time,
                success=False,
                error=str(e),
                stream_mode=True
            )
            raise

    async def track_non_stream_call(
        self,
        model: str,
        provider: str,
        messages: List[Dict[str, Any]],
        response: Any
    ) -> str:
        """
        跟踪非流式调用

        Args:
            model: 模型名称
            provider: Provider 名称
            messages: 输入消息
            response: API 响应对象

        Returns:
            响应内容
        """
        start_time = time.time()

        try:
            # 提取响应内容
            if hasattr(response, "choices") and response.choices:
                content = response.choices[0].message.content
            elif hasattr(response, "content"):
                content = response.content[0].text if isinstance(response.content, list) else response.content
            else:
                content = str(response)

            end_time = time.time()
            total_time = end_time - start_time

            # 计算 token
            input_tokens = self.token_counter.count_messages(messages)
            output_tokens = self.token_counter.count_tokens(content)

            # 获取 usage 信息（如果可用）
            if hasattr(response, "usage"):
                usage = response.usage
                if hasattr(usage, "prompt_tokens"):
                    input_tokens = usage.prompt_tokens
                if hasattr(usage, "completion_tokens"):
                    output_tokens = usage.completion_tokens

            # TTFT 对于非流式调用，近似为总时间的 10%
            ttft = total_time * 0.1

            await self.record_call(
                model=model,
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                ttft=ttft,
                total_time=total_time,
                success=True,
                stream_mode=False
            )

            return content

        except Exception as e:
            end_time = time.time()
            total_time = end_time - start_time
            input_tokens = self.token_counter.count_messages(messages)

            await self.record_call(
                model=model,
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=0,
                ttft=total_time,
                total_time=total_time,
                success=False,
                error=str(e),
                stream_mode=False
            )
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        if not self.records:
            return {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "average_ttft": 0.0,
                "average_output_rate": 0.0,
                "success_rate": 0.0,
                "by_model": {},
            }

        total_calls = len(self.records)
        successful_calls = [r for r in self.records if r.success]
        total_input_tokens = sum(r.input_tokens for r in self.records)
        total_output_tokens = sum(r.output_tokens for r in self.records)
        total_tokens = sum(r.total_tokens for r in self.records)
        total_cost = sum(r.cost for r in self.records)

        if successful_calls:
            avg_ttft = sum(r.ttft for r in successful_calls) / len(successful_calls)
            avg_output_rate = sum(r.output_rate for r in successful_calls) / len(successful_calls)
        else:
            avg_ttft = 0.0
            avg_output_rate = 0.0

        success_rate = len(successful_calls) / total_calls if total_calls > 0 else 0.0

        # 按模型统计
        model_stats = defaultdict(lambda: {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": 0.0,
        })

        for record in self.records:
            model_stats[record.model]["calls"] += 1
            model_stats[record.model]["input_tokens"] += record.input_tokens
            model_stats[record.model]["output_tokens"] += record.output_tokens
            model_stats[record.model]["cost"] += record.cost

        return {
            "total_calls": total_calls,
            "successful_calls": len(successful_calls),
            "failed_calls": total_calls - len(successful_calls),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "average_ttft": avg_ttft,
            "average_output_rate": avg_output_rate,
            "success_rate": success_rate,
            "by_model": dict(model_stats),
        }

    def print_report(self):
        """打印统计报告"""
        stats = self.get_statistics()

        if stats["total_calls"] == 0:
            print("暂无 LLM 调用记录")
            return

        print("=" * 60)
        print("LLM API 调用统计报告")
        print("=" * 60)
        print(f"\n总调用次数: {stats['total_calls']}")
        print(f"  - 成功: {stats['successful_calls']}")
        print(f"  - 失败: {stats['failed_calls']}")
        print(f"\n总 Token 消耗: {stats['total_tokens']:,}")
        print(f"  - 输入 Token: {stats['total_input_tokens']:,}")
        print(f"  - 输出 Token: {stats['total_output_tokens']:,}")
        print(f"\n平均首字延迟 (TTFT): {stats['average_ttft']:.3f} 秒")
        print(f"平均 Token 输出速率: {stats['average_output_rate']:.2f} tokens/秒")
        print(f"\n总成本估算: ${stats['total_cost']:.4f}")
        print(f"成功率: {stats['success_rate']*100:.1f}%")

        if stats["by_model"]:
            print("\n按模型统计:")
            for model, model_stat in stats["by_model"].items():
                print(f"  {model}:")
                print(f"    - 调用次数: {model_stat['calls']}")
                print(f"    - Token: {model_stat['input_tokens'] + model_stat['output_tokens']:,}")
                print(f"    - 成本: ${model_stat['cost']:.4f}")

        print("=" * 60)

    def export_to_csv(self, filepath: str):
        """导出为 CSV"""
        if not self.records:
            logger.warning("no_records_to_export")
            return

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp", "model", "provider", "input_tokens", "output_tokens",
                "total_tokens", "ttft", "output_rate", "total_time", "success",
                "error", "cost", "stream_mode"
            ])
            writer.writeheader()
            for record in self.records:
                row = record.to_dict()
                row["timestamp"] = datetime.fromtimestamp(row["timestamp"]).isoformat()
                writer.writerow(row)

        logger.info("statistics_exported_to_csv", filepath=str(filepath))

    def export_to_json(self, filepath: str):
        """导出为 JSON"""
        if not self.records:
            logger.warning("no_records_to_export")
            return

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "statistics": self.get_statistics(),
            "records": [record.to_dict() for record in self.records]
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        logger.info("statistics_exported_to_json", filepath=str(filepath))


# 全局监控器实例
_global_monitor: Optional[LLMMonitor] = None


def get_monitor(persistence_file: Optional[str] = None) -> LLMMonitor:
    """
    获取全局监控器实例（单例模式）
    
    Args:
        persistence_file: 持久化文件路径（仅在首次调用时有效）
                         如果为 None，默认使用 tmp/monitoring/llm_monitor.json
    """
    global _global_monitor
    if _global_monitor is None:
        # 默认持久化到临时目录
        if persistence_file is None:
            data_dir = Path("tmp/monitoring")
            data_dir.mkdir(parents=True, exist_ok=True)
            persistence_file = str(data_dir / "llm_monitor.json")
        
        _global_monitor = LLMMonitor(persistence_file=persistence_file)
    return _global_monitor


def get_statistics() -> Dict[str, Any]:
    """获取统计信息"""
    return get_monitor().get_statistics()


def print_report():
    """打印统计报告"""
    get_monitor().print_report()


def export_to_csv(filepath: str):
    """导出为 CSV"""
    get_monitor().export_to_csv(filepath)


def export_to_json(filepath: str):
    """导出为 JSON"""
    get_monitor().export_to_json(filepath)


def monitor_llm_call(func: Callable) -> Callable:
    """
    装饰器：自动监控 LLM 调用

    使用示例:
        @monitor_llm_call
        async def my_llm_function():
            ...
    """
    async def wrapper(*args, **kwargs):
        # 这里可以添加自动监控逻辑
        # 目前需要手动调用 track 方法
        return await func(*args, **kwargs)
    return wrapper

