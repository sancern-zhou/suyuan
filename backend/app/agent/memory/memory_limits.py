"""常驻长期记忆（MEMORY.md）的共享容量策略。

MEMORY.md 每次会话全文注入上下文，因此所有写入方（会话 Agent 的 edit_file、
write_file、人工编辑 API）必须执行同一个容量上限：任何一条路径单独放宽，
都会让其他路径在超限后永久被拒（先写爆的人不走 edit_file，Agent 却再也改不动）。
"""

MEMORY_MD_MAX_CHARS = 12_000
"""MEMORY.md 编辑/写入后的总字符数硬上限。"""

MEMORY_MD_HINT_CHARS = 10_000
"""超限提示中的建议目标：精简到该水位以下再添加新内容。"""


def memory_capacity_error(current_chars: int) -> str:
    """统一的超限拒绝文案，供各写入方复用。"""
    return (
        f"MEMORY.md 超出容量上限（编辑后 {current_chars} 字符 > 上限 {MEMORY_MD_MAX_CHARS}）。"
        f"长期记忆常驻注入每次会话，请先删除过时或低价值条目，"
        f"将总量精简到 {MEMORY_MD_HINT_CHARS} 字符以内后再添加新内容。"
    )
