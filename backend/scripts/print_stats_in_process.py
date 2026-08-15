"""
在服务进程中打印 LLM 统计的辅助脚本

这个脚本应该在 Agent 运行后调用，可以添加到 Agent 的回调中
"""

from app.monitoring import print_report, get_statistics


def print_llm_stats_callback():
    """
    在 Agent 完成任务后调用此函数打印统计
    """
    print("\n" + "="*80)
    print("LLM 调用统计")
    print("="*80)
    
    stats = get_statistics()
    
    if stats["total_calls"] == 0:
        print("暂无调用记录")
        return
    
    print_report()
    print("="*80 + "\n")


# 示例：如何在 Agent 中使用
"""
from scripts.print_stats_in_process import print_llm_stats_callback

# 在 Agent 运行后调用
result = await agent.run(query)
print_llm_stats_callback()  # 打印统计
"""

