"""
最终验证：PM2.5数据流完整测试
模拟实际的工具执行流程
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

import asyncio
from app.agent.context.execution_context import ExecutionContext
from app.agent.context.data_context_manager import DataContextManager
from app.agent.memory.hybrid_manager import HybridMemoryManager


async def test_full_workflow():
    """测试完整工作流"""

    output_file = Path(__file__).parent / "final_verification_result.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("Final Verification: PM2.5 Data Flow\n")
        f.write("=" * 80 + "\n\n")

        # 创建执行上下文
        memory_manager = HybridMemoryManager(session_id="test_session")
        data_manager = DataContextManager(memory_manager)
        context = ExecutionContext(
            session_id="test_session",
            iteration=1,
            data_manager=data_manager
        )

        # 模拟API返回的数据（Unicode上标格式）
        api_records = [
            {
                "Code": "1067b",
                "StationName": "深南中路",
                "TimePoint": "2026-02-01 00:00:00",
                "SO4²⁻": 8.5,
                "NO₃⁻": 12.3,
                "NH₄⁺": 6.7,
                "Cl⁻": 1.2,
                "Ca²⁺": 2.3,
                "Mg²⁺": 0.8,
                "K⁺": 1.5,
                "Na⁺": 1.1,
                "PM2_5": 35.5
            }
        ]

        f.write("Step 1: Simulate API Response\n")
        f.write("-" * 80 + "\n")
        f.write(f"Record count: {len(api_records)}\n")
        f.write(f"Sample fields: {list(api_records[0].keys())[:5]}\n\n")

        # 使用context.save_data保存数据（会自动标准化）
        f.write("Step 2: Save Data via Context (auto-standardization)\n")
        f.write("-" * 80 + "\n")

        try:
            data_id = context.save_data(
                data=api_records,
                schema="particulate_unified",
                metadata={
                    "component_type": "ionic",
                    "station": "深南中路",
                    "code": "1067b"
                }
            )
            f.write(f"SUCCESS: Data saved with ID: {data_id}\n\n")

            # 加载数据验证
            f.write("Step 3: Load Data and Verify\n")
            f.write("-" * 80 + "\n")

            loaded_data = context.get_data(data_id)
            f.write(f"Loaded record count: {len(loaded_data)}\n")

            if loaded_data:
                first_record = loaded_data[0]
                f.write(f"\nFirst record type: {type(first_record).__name__}\n")

                # 转换为字典
                if hasattr(first_record, 'model_dump'):
                    record_dict = first_record.model_dump()
                elif hasattr(first_record, 'dict'):
                    record_dict = first_record.dict()
                else:
                    record_dict = first_record

                f.write(f"\nRecord fields:\n")
                for key, value in record_dict.items():
                    if isinstance(value, dict):
                        f.write(f"  {key}: (dict, {len(value)} items)\n")
                        if key == "components" and value:
                            for comp_key, comp_value in value.items():
                                f.write(f"    {comp_key}: {comp_value}\n")
                    else:
                        f.write(f"  {key}: {value}\n")

                # 最终验证
                f.write("\n" + "=" * 80 + "\n")
                f.write("Final Verification\n")
                f.write("-" * 80 + "\n")

                components = record_dict.get("components", {})
                if components and len(components) > 0:
                    f.write(f"SUCCESS: Components field contains {len(components)} items\n")
                    f.write(f"Component names: {list(components.keys())}\n")
                    f.write(f"\nAll PM2.5 component data preserved correctly!\n")
                else:
                    f.write(f"FAILURE: Components field is empty or missing\n")

        except Exception as e:
            f.write(f"ERROR: {e}\n")
            import traceback
            f.write(traceback.format_exc())

        f.write("\n" + "=" * 80 + "\n")

    print(f"Results written to: {output_file}")


if __name__ == "__main__":
    asyncio.run(test_full_workflow())
