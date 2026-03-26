"""Social platform monitoring and metrics."""

import time
import asyncio
from collections import deque
from typing import Dict, Any
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ChannelMetrics:
    """Metrics for a single channel."""

    channel_name: str
    messages_received: int = 0
    messages_sent: int = 0
    errors: int = 0
    last_error: str = ""
    last_error_time: float = 0
    avg_response_time: float = 0
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))

    def record_receive(self):
        """Record a received message."""
        self.messages_received += 1

    def record_send(self, response_time: float | None = None):
        """Record a sent message."""
        self.messages_sent += 1
        if response_time is not None:
            self.response_times.append(response_time)
            # Update average
            if self.response_times:
                self.avg_response_time = sum(self.response_times) / len(self.response_times)

    def record_error(self, error: str):
        """Record an error."""
        self.errors += 1
        self.last_error = error
        self.last_error_time = time.time()

    def get_error_rate(self) -> float:
        """Calculate error rate."""
        total = self.messages_sent + self.errors
        if total == 0:
            return 0.0
        return self.errors / total

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "channel_name": self.channel_name,
            "messages_received": self.messages_received,
            "messages_sent": self.messages_sent,
            "errors": self.errors,
            "error_rate": f"{self.get_error_rate():.2%}",
            "last_error": self.last_error,
            "last_error_time": self.last_error_time,
            "avg_response_time": f"{self.avg_response_time:.3f}s",
            "uptime_samples": len(self.response_times),
        }


class SocialPlatformMonitor:
    """
    Monitor social platform integration.

    Tracks metrics for all channels:
    - Message throughput
    - Response times
    - Error rates
    - Health status
    """

    def __init__(self):
        self.channels: Dict[str, ChannelMetrics] = {}
        self._start_time = time.time()
        self._lock = asyncio.Lock()

    def get_or_create_channel(self, channel_name: str) -> ChannelMetrics:
        """Get or create channel metrics."""
        if channel_name not in self.channels:
            self.channels[channel_name] = ChannelMetrics(channel_name=channel_name)
        return self.channels[channel_name]

    async def record_message_received(self, channel_name: str):
        """Record a received message."""
        async with self._lock:
            metrics = self.get_or_create_channel(channel_name)
            metrics.record_receive()

    async def record_message_sent(
        self,
        channel_name: str,
        response_time: float | None = None
    ):
        """Record a sent message."""
        async with self._lock:
            metrics = self.get_or_create_channel(channel_name)
            metrics.record_send(response_time)

    async def record_error(self, channel_name: str, error: str):
        """Record an error."""
        async with self._lock:
            metrics = self.get_or_create_channel(channel_name)
            metrics.record_error(error)

    async def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics."""
        async with self._lock:
            uptime = time.time() - self._start_time
            return {
                "uptime_seconds": int(uptime),
                "uptime_formatted": self._format_uptime(uptime),
                "channels": {
                    name: metrics.to_dict()
                    for name, metrics in self.channels.items()
                },
                "total_messages_received": sum(
                    m.messages_received for m in self.channels.values()
                ),
                "total_messages_sent": sum(
                    m.messages_sent for m in self.channels.values()
                ),
                "total_errors": sum(
                    m.errors for m in self.channels.values()
                ),
            }

    async def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all channels."""
        async with self._lock:
            status = {}
            for name, metrics in self.channels.items():
                error_rate = metrics.get_error_rate()
                # Health criteria:
                # - Error rate < 5%
                # - At least one message processed
                # - No recent errors (last 5 minutes)
                recent_error = (time.time() - metrics.last_error_time) < 300

                is_healthy = (
                    error_rate < 0.05 and
                    (metrics.messages_received + metrics.messages_sent) > 0 and
                    not recent_error
                )

                status[name] = {
                    "healthy": is_healthy,
                    "error_rate": f"{error_rate:.2%}",
                    "recent_error": recent_error,
                    "messages_processed": metrics.messages_received + metrics.messages_sent,
                }

            return {
                "overall_healthy": all(s["healthy"] for s in status.values()) if status else True,
                "channels": status,
            }

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """Format uptime in human-readable format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}h {minutes}m {secs}s"

    async def reset_metrics(self, channel_name: str | None = None):
        """Reset metrics for a channel or all channels."""
        async with self._lock:
            if channel_name:
                if channel_name in self.channels:
                    self.channels[channel_name] = ChannelMetrics(
                        channel_name=channel_name
                    )
            else:
                self.channels.clear()


# Global monitor instance
_monitor: SocialPlatformMonitor | None = None


def get_monitor() -> SocialPlatformMonitor:
    """Get the global monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = SocialPlatformMonitor()
    return _monitor
