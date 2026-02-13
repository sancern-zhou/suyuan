"""
Time format normalization utilities.

解决问题：确保监测数据API和气象数据API接收到相同格式的时间参数。
"""
from datetime import datetime
from typing import Optional
import structlog

logger = structlog.get_logger()


def normalize_time_param(time_str: Optional[str], is_end_time: bool = False) -> str:
    """
    规范化时间参数为 "YYYY-MM-DD HH:MM:SS" 格式。

    Args:
        time_str: 输入的时间字符串，可能的格式:
                  - "YYYY-MM-DD HH:MM:SS" (完整格式)
                  - "YYYY-MM-DD" (仅日期)
                  - "YYYY-MM-DDTHH:MM:SS" (ISO格式)
                  - None/空字符串
        is_end_time: 是否为结束时间（影响默认时分秒）

    Returns:
        规范化后的时间字符串 "YYYY-MM-DD HH:MM:SS"

    Examples:
        >>> normalize_time_param("2025-10-19", is_end_time=False)
        "2025-10-19 00:00:00"

        >>> normalize_time_param("2025-10-19", is_end_time=True)
        "2025-10-19 23:59:59"

        >>> normalize_time_param("2025-10-19T12:30:45")
        "2025-10-19 12:30:45"
    """
    if not time_str or not isinstance(time_str, str):
        logger.warning(
            "time_param_empty_or_invalid",
            time_str=time_str,
            type=type(time_str).__name__
        )
        return ""

    time_str = time_str.strip()

    # 1. 已经是完整格式 "YYYY-MM-DD HH:MM:SS"
    if len(time_str) == 19 and ' ' in time_str:
        try:
            # 验证格式是否正确
            datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            return time_str
        except ValueError:
            pass  # 继续尝试其他格式

    # 2. ISO 8601格式 "YYYY-MM-DDTHH:MM:SS" 或 "YYYY-MM-DDTHH:MM:SSZ"
    if 'T' in time_str:
        try:
            # 移除可能的时区标识
            time_str_clean = time_str.rstrip('Z').split('+')[0].split('-')[0]

            # 尝试解析
            if '.' in time_str_clean:
                # 包含毫秒 "YYYY-MM-DDTHH:MM:SS.fff"
                dt = datetime.fromisoformat(time_str_clean.split('.')[0])
            else:
                dt = datetime.fromisoformat(time_str_clean)

            normalized = dt.strftime("%Y-%m-%d %H:%M:%S")
            logger.info(
                "time_param_normalized_from_iso",
                original=time_str,
                normalized=normalized
            )
            return normalized
        except ValueError:
            pass  # 继续尝试其他格式

    # 3. 仅日期格式 "YYYY-MM-DD"
    if len(time_str) == 10 and time_str.count('-') == 2:
        try:
            # 验证日期有效性
            datetime.strptime(time_str, "%Y-%m-%d")

            # 补充时分秒
            if is_end_time:
                normalized = f"{time_str} 23:59:59"
            else:
                normalized = f"{time_str} 00:00:00"

            logger.info(
                "time_param_normalized_from_date",
                original=time_str,
                normalized=normalized,
                is_end_time=is_end_time
            )
            return normalized
        except ValueError:
            pass

    # 4. 其他格式 - 尝试智能解析
    try:
        # 尝试多种常见格式
        for fmt in [
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
            "%Y-%m-%d %H:%M",
            "%Y年%m月%d日",
        ]:
            try:
                dt = datetime.strptime(time_str, fmt)
                normalized = dt.strftime("%Y-%m-%d %H:%M:%S")
                logger.info(
                    "time_param_parsed_with_format",
                    original=time_str,
                    format=fmt,
                    normalized=normalized
                )
                return normalized
            except ValueError:
                continue
    except Exception as e:
        logger.error(
            "time_param_parse_failed",
            time_str=time_str,
            error=str(e)
        )

    # 5. 解析失败 - 返回原字符串并记录警告
    logger.warning(
        "time_param_unrecognized_format",
        time_str=time_str,
        returning="original_string"
    )
    return time_str


def validate_time_range(start_time: str, end_time: str) -> bool:
    """
    验证时间范围是否合法（开始时间早于结束时间）。

    Args:
        start_time: 开始时间
        end_time: 结束时间

    Returns:
        True if valid, False otherwise
    """
    if not start_time or not end_time:
        return False

    try:
        dt_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")

        if dt_start >= dt_end:
            logger.warning(
                "time_range_invalid",
                start_time=start_time,
                end_time=end_time,
                reason="start >= end"
            )
            return False

        return True
    except ValueError as e:
        logger.error(
            "time_range_validation_failed",
            start_time=start_time,
            end_time=end_time,
            error=str(e)
        )
        return False
