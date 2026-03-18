"""
查看 LLM 调用统计的脚本

使用方法:
    python scripts/view_llm_stats.py          # 打印报告
    python scripts/view_llm_stats.py --csv    # 导出 CSV
    python scripts/view_llm_stats.py --json    # 导出 JSON
    python scripts/view_llm_stats.py --all     # 打印报告并导出所有格式
"""

import sys
import argparse
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.monitoring import print_report, get_statistics, export_to_csv, export_to_json
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="查看 LLM 调用统计")
    parser.add_argument("--csv", action="store_true", help="导出为 CSV")
    parser.add_argument("--json", action="store_true", help="导出为 JSON")
    parser.add_argument("--all", action="store_true", help="打印报告并导出所有格式")
    parser.add_argument("--output-dir", type=str, default=".", help="输出目录（默认当前目录）")
    
    args = parser.parse_args()
    
    # 获取统计信息
    stats = get_statistics()
    
    if stats["total_calls"] == 0:
        print("暂无 LLM 调用记录")
        return
    
    # 打印报告
    if not args.csv and not args.json or args.all:
        print_report()
    
    # 导出 CSV
    if args.csv or args.all:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = Path(args.output_dir) / f"llm_stats_{timestamp}.csv"
        export_to_csv(str(csv_path))
        print(f"\n[OK] CSV 已导出到: {csv_path}")
    
    # 导出 JSON
    if args.json or args.all:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = Path(args.output_dir) / f"llm_stats_{timestamp}.json"
        export_to_json(str(json_path))
        print(f"[OK] JSON 已导出到: {json_path}")


if __name__ == "__main__":
    main()

