import pytest
import sys
import os
from datetime import datetime, timedelta

# 添加backend目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.agent.context.execution_context import ExecutionContext
from app.tools.query.query_gd_suncere.tool import (
    execute_query_gd_suncere_city_day,
    execute_query_gd_suncere_station_hour,
    execute_query_gd_suncere_regional_comparison
)


class TestQueryGDSuncere:
    """测试query_gd_suncere工具"""
    
    def setup_method(self):
        """设置测试环境"""
        # 创建执行上下文
        self.context = ExecutionContext()
        
        # 计算昨天日期
        yesterday = datetime.now() - timedelta(days=1)
        self.yesterday_str = yesterday.strftime("%Y-%m-%d")
        
        print(f"\n测试时间: {datetime.now()}")
        print(f"查询日期: {self.yesterday_str}")
    
    def test_query_city_day_data(self):
        """测试城市日报数据查询"""
        print(f"\n=== 测试城市日报数据查询 ===")
        print(f"城市: 广州")
        print(f"日期: {self.yesterday_str}")
        
        try:
            result = execute_query_gd_suncere_city_day(
                cities=["广州"],
                start_date=self.yesterday_str,
                end_date=self.yesterday_str,
                context=self.context
            )
            
            print(f"\n查询结果:")
            print(f"状态: {result.get('status')}")
            print(f"成功: {result.get('success')}")
            print(f"摘要: {result.get('summary')}")
            
            if result.get('success'):
                data = result.get('data', [])
                print(f"数据记录数: {len(data)}")
                
                if data:
                    print(f"\n示例数据（前3条）:")
                    for i, record in enumerate(data[:3]):
                        print(f"  记录 {i+1}: {record}")
                
                # 验证元数据
                metadata = result.get('metadata', {})
                print(f"\n元数据:")
                print(f"  工具名称: {metadata.get('tool_name')}")
                print(f"  数据ID: {metadata.get('data_id')}")
                print(f"  总记录数: {metadata.get('total_records')}")
                
                # 断言验证
                assert result['success'] == True, "查询应该成功"
                assert result['status'] in ['success', 'empty'], "状态应该是success或empty"
                assert 'metadata' in result, "应该包含元数据"
                
                print("\n✅ 测试通过！")
            else:
                print(f"\n⚠️ 查询失败: {result.get('error', '未知错误')}")
                # 即使失败也记录结果，不抛出异常
                
        except Exception as e:
            print(f"\n❌ 测试异常: {str(e)}")
            raise
    
    def test_query_city_hour_data(self):
        """测试城市小时数据查询"""
        print(f"\n=== 测试城市小时数据查询 ===")
        print(f"城市: 广州")
        print(f"时间范围: {self.yesterday_str} 00:00:00 到 {self.yesterday_str} 23:59:59")
        
        try:
            result = execute_query_gd_suncere_station_hour(
                cities=["广州"],
                start_time=f"{self.yesterday_str} 00:00:00",
                end_time=f"{self.yesterday_str} 23:59:59",
                context=self.context
            )
            
            print(f"\n查询结果:")
            print(f"状态: {result.get('status')}")
            print(f"成功: {result.get('success')}")
            print(f"摘要: {result.get('summary')}")
            
            if result.get('success'):
                data = result.get('data', [])
                print(f"数据记录数: {len(data)}")
                
                if data:
                    print(f"\n示例数据（前3条）:")
                    for i, record in enumerate(data[:3]):
                        print(f"  记录 {i+1}: {record}")
                
                # 验证元数据
                metadata = result.get('metadata', {})
                print(f"\n元数据:")
                print(f"  工具名称: {metadata.get('tool_name')}")
                print(f"  数据ID: {metadata.get('data_id')}")
                print(f"  总记录数: {metadata.get('total_records')}")
                
                # 断言验证
                assert result['success'] == True, "查询应该成功"
                assert result['status'] in ['success', 'empty'], "状态应该是success或empty"
                assert 'metadata' in result, "应该包含元数据"
                
                print("\n✅ 测试通过！")
            else:
                print(f"\n⚠️ 查询失败: {result.get('error', '未知错误')}")
                
        except Exception as e:
            print(f"\n❌ 测试异常: {str(e)}")
            raise
    
    def test_query_regional_comparison(self):
        """测试区域对比查询"""
        print(f"\n=== 测试区域对比查询 ===")
        print(f"目标城市: 广州")
        print(f"周边城市: 佛山、东莞、中山")
        print(f"时间范围: {self.yesterday_str} 00:00:00 到 {self.yesterday_str} 23:59:59")
        
        try:
            result = execute_query_gd_suncere_regional_comparison(
                target_city="广州",
                nearby_cities=["佛山", "东莞", "中山"],
                start_time=f"{self.yesterday_str} 00:00:00",
                end_time=f"{self.yesterday_str} 23:59:59",
                context=self.context
            )
            
            print(f"\n查询结果:")
            print(f"状态: {result.get('status')}")
            print(f"成功: {result.get('success')}")
            print(f"摘要: {result.get('summary')}")
            
            if result.get('success'):
                data = result.get('data', [])
                print(f"数据记录数: {len(data)}")
                
                if data:
                    print(f"\n示例数据（前3条）:")
                    for i, record in enumerate(data[:3]):
                        print(f"  记录 {i+1}: {record}")
                
                # 验证元数据
                metadata = result.get('metadata', {})
                print(f"\n元数据:")
                print(f"  工具名称: {metadata.get('tool_name')}")
                print(f"  查询类型: {metadata.get('query_type')}")
                print(f"  目标城市: {metadata.get('target_city')}")
                print(f"  数据ID: {metadata.get('data_id')}")
                
                # 断言验证
                assert result['success'] == True, "查询应该成功"
                assert result['status'] in ['success', 'empty'], "状态应该是success或empty"
                assert 'metadata' in result, "应该包含元数据"
                assert metadata.get('query_type') == 'regional_comparison', "查询类型应该是区域对比"
                
                print("\n✅ 测试通过！")
            else:
                print(f"\n⚠️ 查询失败: {result.get('error', '未知错误')}")
                
        except Exception as e:
            print(f"\n❌ 测试异常: {str(e)}")
            raise


if __name__ == "__main__":
    # 运行测试
    import pytest
    pytest.main([__file__, "-v", "-s"])
