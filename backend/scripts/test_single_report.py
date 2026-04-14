#!/usr/bin/env python3
"""
单份报告测试脚本

用于测试臭氧垂直报告处理流程，处理单份报告并输出详细日志。

使用方法：
python test_single_report.py --file "/path/to/report.docx"
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime

# 导入主处理脚本
from batch_ozone_report_processor import BatchProcessor, logger

# 测试配置
TEST_CONFIG = {
    "reports_dir": ".",  # 当前目录
    "output_dir": "./test_output",
    "progress_file": "./test_progress.json",
    "report_file": "./test_report.json",
    "concurrent_tasks": 1,
    "test_mode": True
}


class TestProcessor(BatchProcessor):
    """测试处理器"""

    def __init__(self, test_file: str):
        # 使用测试配置初始化
        self.reports_dir = Path(test_file).parent
        self.output_dir = Path(TEST_CONFIG["output_dir"])
        self.progress_file = Path(TEST_CONFIG["progress_file"])
        self.report_file = Path(TEST_CONFIG["report_file"])

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 加载进度
        self.progress = self._load_progress()

        # 统计信息
        self.stats = {
            "total": 1,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "start_time": None,
            "end_time": None,
            "test_file": test_file
        }

        self.test_file = Path(test_file)

    def get_reports(self):
        """获取测试报告"""
        if not self.test_file.exists():
            logger.error("test_file_not_exists", path=str(self.test_file))
            return []
        return [self.test_file]

    async def run(self):
        """运行测试"""
        logger.info("test_processor_starting", file=str(self.test_file))

        # 获取待处理报告
        reports = self.get_reports()

        if not reports:
            logger.error("no_test_file")
            print(f"错误：测试文件不存在：{self.test_file}")
            return

        self.stats["start_time"] = datetime.now().isoformat()

        # 处理单份报告
        success = await self.process_report(reports[0])

        self.stats["end_time"] = datetime.now().isoformat()

        if success:
            self.stats["success"] = 1
            print(f"\n✅ 测试成功：{self.test_file.name}")
        else:
            self.stats["failed"] = 1
            print(f"\n❌ 测试失败：{self.test_file.name}")

        # 保存报告
        self._save_report()

        # 打印详细日志
        self._print_detailed_summary()

    def _print_detailed_summary(self):
        """打印详细测试总结"""
        print("\n" + "="*60)
        print("测试报告处理详情")
        print("="*60)
        print(f"测试文件：{self.stats['test_file']}")
        print(f"处理状态：{'成功' if self.stats['success'] > 0 else '失败'}")
        print(f"开始时间：{self.stats['start_time']}")
        print(f"结束时间：{self.stats['end_time']}")
        print(f"\n处理报告：{self.report_file}")
        print(f"输出文件：{self.output_dir / self.test_file.name}")
        print("="*60)

        # 读取并显示处理报告
        if self.report_file.exists():
            try:
                with open(self.report_file, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                print("\n详细处理报告：")
                print(json.dumps(report, ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"无法读取处理报告：{e}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='测试单份臭氧垂直报告处理')
    parser.add_argument('--file', required=True, help='报告文件路径')
    parser.add_argument('--verbose', action='store_true', help='显示详细日志')

    args = parser.parse_args()

    # 检查文件是否存在
    if not Path(args.file).exists():
        print(f"错误：文件不存在：{args.file}")
        sys.exit(1)

    # 运行测试处理器
    processor = TestProcessor(args.file)
    await processor.run()


if __name__ == "__main__":
    # 检查配置
    if not os.getenv("QWEN_VL_API_KEY"):
        print("警告：未配置 QWEN_VL_API_KEY 环境变量")
        print("请设置环境变量：export QWEN_VL_API_KEY='your-api-key'")

    # 运行测试
    asyncio.run(main())
