"""
检查 LLM 监控 API 的脚本

使用方法:
    python scripts/check_monitoring_api.py
"""

import requests
import json
from datetime import datetime


def check_monitoring_api(base_url="http://localhost:8000"):
    """检查监控 API 是否正常工作"""
    
    print("="*80)
    print("LLM 监控 API 检查")
    print("="*80)
    print(f"服务地址: {base_url}")
    print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 检查统计数据
    try:
        print("[1/3] 检查统计数据 API...")
        response = requests.get(f"{base_url}/api/monitoring/stats", timeout=5)
        
        if response.status_code == 200:
            stats = response.json()
            print("✓ API 正常工作")
            print()
            print("-"*80)
            print("统计摘要:")
            print("-"*80)
            print(f"  总调用次数: {stats['total_calls']}")
            print(f"  成功调用: {stats['successful_calls']}")
            print(f"  失败调用: {stats['failed_calls']}")
            print(f"  总 Token: {stats['total_tokens']:,}")
            print(f"  输入 Token: {stats['total_input_tokens']:,}")
            print(f"  输出 Token: {stats['total_output_tokens']:,}")
            print(f"  总成本: ${stats['total_cost']:.4f}")
            print(f"  平均首字延迟: {stats['average_ttft']:.3f}s")
            print(f"  平均输出速率: {stats['average_output_rate']:.2f} tokens/s")
            print(f"  成功率: {stats['success_rate']*100:.1f}%")
            print()
            
            if stats['by_model']:
                print("-"*80)
                print("按模型统计:")
                print("-"*80)
                for model, model_stats in stats['by_model'].items():
                    print(f"\n  模型: {model}")
                    print(f"    调用次数: {model_stats['calls']}")
                    print(f"    Token: {model_stats['total_tokens']:,}")
                    print(f"    成本: ${model_stats['cost']:.4f}")
            
            print()
            return True
        else:
            print(f"✗ API 返回错误: {response.status_code}")
            print(f"  响应: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到服务")
        print(f"  请确保服务正在运行: uvicorn app.main:app --reload --port 8000")
        return False
    except Exception as e:
        print(f"✗ 检查失败: {str(e)}")
        return False
    
    # 检查报告 API
    try:
        print("[2/3] 检查报告 API...")
        response = requests.get(f"{base_url}/api/monitoring/report", timeout=5)
        
        if response.status_code == 200:
            print("✓ 报告 API 正常工作")
        else:
            print(f"✗ 报告 API 返回错误: {response.status_code}")
            
    except Exception as e:
        print(f"✗ 报告 API 检查失败: {str(e)}")
    
    print()
    print("[3/3] 完成检查")
    print("="*80)
    print()
    print("提示:")
    print("  - 在浏览器中访问: http://localhost:8000/api/monitoring/stats")
    print("  - 使用 PowerShell: Invoke-RestMethod -Uri http://localhost:8000/api/monitoring/stats")
    print("  - 导出数据: curl -X POST http://localhost:8000/api/monitoring/export/csv")
    print()


if __name__ == "__main__":
    check_monitoring_api()

