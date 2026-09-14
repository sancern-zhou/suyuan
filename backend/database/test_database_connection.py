"""
数据库连接测试脚本

功能：
1. 测试 SQL Server 连接
2. 验证表结构
3. 执行简单的CRUD操作
4. 检查索引

运行方法：
    python test_database_connection.py
"""

import asyncio
import json
import sys
import os
from datetime import datetime

# 添加backend路径到sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from app.services.history_service import history_service, AnalysisHistoryRecord
    from config.settings import settings
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请确保在 backend 目录下运行此脚本")
    sys.exit(1)


async def test_connection():
    """测试基本连接"""
    print("=" * 60)
    print("测试 1: 数据库连接")
    print("=" * 60)

    try:
        async with history_service.get_connection() as conn:
            print(f"✅ 成功连接到数据库: {settings.sqlserver_database}")
            print(f"   服务器: {settings.sqlserver_host}:{settings.sqlserver_port}")
            print(f"   用户: {settings.sqlserver_user}")
            return True
    except Exception as e:
        print(f"❌ 连接失败: {str(e)}")
        return False


async def test_table_structure():
    """验证表结构"""
    print("\n" + "=" * 60)
    print("测试 2: 验证表结构")
    print("=" * 60)

    try:
        async with history_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                # 查询列信息
                await cursor.execute("""
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'analysis_history'
                    ORDER BY ORDINAL_POSITION
                """)

                columns = await cursor.fetchall()

                if not columns:
                    print("❌ 表 analysis_history 不存在")
                    return False

                print(f"✅ 表 analysis_history 存在，共 {len(columns)} 列")
                print("\n主要列信息:")
                print(f"{'列名':<30} {'类型':<15} {'长度':<10} {'可空':<5}")
                print("-" * 60)

                important_columns = [
                    'id', 'session_id', 'query_text', 'scale',
                    'city', 'pollutant', 'meteorological_data',
                    'monitoring_data', 'comprehensive_summary', 'created_at'
                ]

                for col in columns:
                    col_name = col[0]
                    if col_name in important_columns:
                        col_type = col[1]
                        col_length = str(col[2]) if col[2] else '-'
                        col_nullable = '是' if col[3] == 'YES' else '否'
                        print(f"{col_name:<30} {col_type:<15} {col_length:<10} {col_nullable:<5}")

                return True
    except Exception as e:
        print(f"❌ 验证失败: {str(e)}")
        return False


async def test_indexes():
    """检查索引"""
    print("\n" + "=" * 60)
    print("测试 3: 检查索引")
    print("=" * 60)

    try:
        async with history_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    SELECT name, type_desc, is_unique
                    FROM sys.indexes
                    WHERE object_id = OBJECT_ID('dbo.analysis_history')
                      AND name IS NOT NULL
                    ORDER BY name
                """)

                indexes = await cursor.fetchall()

                if indexes:
                    print(f"✅ 发现 {len(indexes)} 个索引:")
                    for idx in indexes:
                        unique_flag = "唯一" if idx[2] else "非唯一"
                        print(f"   - {idx[0]} ({idx[1]}, {unique_flag})")
                    return True
                else:
                    print("⚠️  未发现索引（可能影响查询性能）")
                    return True
    except Exception as e:
        print(f"❌ 检查失败: {str(e)}")
        return False


async def test_crud_operations():
    """测试CRUD操作"""
    print("\n" + "=" * 60)
    print("测试 4: CRUD操作")
    print("=" * 60)

    test_session_id = None

    try:
        # 1. CREATE - 创建测试记录
        print("\n4.1 创建测试记录...")

        record = AnalysisHistoryRecord(
            query_text="测试查询 - 分析广州天河站2025-08-09的O3污染",
            scale="station",
            location="天河站",
            city="广州",
            pollutant="O3",
            start_time="2025-08-09 00:00:00",
            end_time="2025-08-09 23:59:59",
            status="completed",
            duration_seconds=45.2,
            meteorological_data={"test": "data", "winds": [{"speed": 2.5, "direction": 180}]},
            monitoring_data={"test": "monitoring", "values": [100, 120, 110]},
            comprehensive_summary="这是一个测试分析摘要",
        )

        test_session_id = await history_service.save_analysis(record)
        print(f"✅ 记录创建成功，session_id: {test_session_id}")

        # 2. READ - 读取记录
        print("\n4.2 读取测试记录...")

        retrieved = await history_service.get_by_session_id(test_session_id)
        if retrieved:
            print(f"✅ 记录读取成功")
            print(f"   查询文本: {retrieved['query_text']}")
            print(f"   城市: {retrieved['city']}")
            print(f"   污染物: {retrieved['pollutant']}")
            print(f"   创建时间: {retrieved['created_at']}")
        else:
            print(f"❌ 记录读取失败")
            return False

        # 3. UPDATE - 更新收藏状态
        print("\n4.3 更新收藏状态...")

        is_bookmarked = await history_service.toggle_bookmark(test_session_id)
        print(f"✅ 收藏状态更新成功: {is_bookmarked}")

        # 4. LIST - 列表查询
        print("\n4.4 查询历史列表...")

        history_list = await history_service.get_history_list(limit=5)
        print(f"✅ 列表查询成功，共 {history_list['total']} 条记录")
        if history_list['records']:
            print(f"   最新记录: {history_list['records'][0]['query_text']}")

        # 5. DELETE - 删除记录
        print("\n4.5 删除测试记录...")

        deleted = await history_service.delete_by_session_id(test_session_id)
        if deleted:
            print(f"✅ 记录删除成功")

            # 验证删除
            verify = await history_service.get_by_session_id(test_session_id)
            if not verify:
                print(f"✅ 删除验证成功（记录已不存在）")
            else:
                print(f"⚠️  删除验证失败（记录仍然存在）")
        else:
            print(f"❌ 记录删除失败")
            return False

        return True

    except Exception as e:
        print(f"❌ CRUD操作失败: {str(e)}")

        # 清理：尝试删除测试记录
        if test_session_id:
            try:
                await history_service.delete_by_session_id(test_session_id)
                print(f"🧹 已清理测试记录")
            except:
                pass

        return False


async def main():
    """主测试流程"""
    print("\n" + "=" * 60)
    print("大气污染溯源分析系统 - 数据库连接测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = {}

    # 执行测试
    results['connection'] = await test_connection()

    if results['connection']:
        results['structure'] = await test_table_structure()
        results['indexes'] = await test_indexes()
        results['crud'] = await test_crud_operations()
    else:
        print("\n⚠️  数据库连接失败，跳过后续测试")
        results['structure'] = False
        results['indexes'] = False
        results['crud'] = False

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name.replace('_', ' ').title():<20} {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n🎉 所有测试通过！数据库配置正确。")
        print("\n下一步操作:")
        print("1. 后端服务已准备就绪")
        print("2. 启动后端: cd backend && python -m uvicorn app.main:app --reload")
        print("3. 测试API: curl http://localhost:8000/api/history/list")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查配置。")
        print("\n故障排查:")
        print("1. 检查 backend/.env 文件中的数据库配置")
        print("2. 确认 SQL Server 服务运行正常")
        print("3. 验证数据库初始化脚本已执行")
        print("4. 检查 ODBC 驱动是否已安装")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试执行失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
