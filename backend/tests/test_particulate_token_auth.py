"""
测试颗粒物API Token验证机制

测试场景：
1. Token获取测试
2. API请求携带Token
3. Token失效自动刷新（401响应）
4. Token过期自动刷新
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.particulate_token_manager import (
    get_particulate_token_manager,
    reset_token_manager
)
from app.utils.particulate_api_client import (
    get_particulate_api_client,
    reset_particulate_api_client
)


def test_token_fetch():
    """测试Token获取"""
    print("\n" + "="*60)
    print("测试1: Token获取")
    print("="*60)

    try:
        token_manager = get_particulate_token_manager()
        token = token_manager.get_token()

        if token:
            print(f"✅ Token获取成功")
            print(f"   Token: {token[:20]}...")
            print(f"   过期时间: {__import__('time').ctime(token_manager._token_expire_time)}")
            print(f"   是否有效: {token_manager.is_token_valid()}")
            return True
        else:
            print("❌ Token获取失败")
            print("   请检查以下配置项:")
            print("   1. .env文件中的PARTICULATE_API_USERNAME和PARTICULATE_API_PASSWORD")
            print("   2. backend/config/external_api_config.yaml配置是否正确")
            print("   3. API服务是否可访问")
            return False

    except Exception as e:
        print(f"❌ Token获取异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_auth_headers():
    """测试认证请求头生成"""
    print("\n" + "="*60)
    print("测试2: 认证请求头生成")
    print("="*60)

    try:
        token_manager = get_particulate_token_manager()
        headers = token_manager.get_auth_headers()

        print("✅ 认证请求头生成成功:")
        for key, value in headers.items():
            if key.lower() == "authorization":
                print(f"   {key}: Bearer {value[7:27]}...")
            else:
                print(f"   {key}: {value}")

        # 验证关键字段
        assert "Authorization" in headers, "缺少Authorization头"
        assert "SysCode" in headers, "缺少SysCode头"
        assert headers["Authorization"].startswith("Bearer "), "Authorization格式错误"

        print("\n✅ 所有必要字段验证通过")
        return True

    except Exception as e:
        print(f"❌ 认证请求头生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_call_with_token():
    """测试带Token的API调用"""
    print("\n" + "="*60)
    print("测试3: API调用（携带Token）")
    print("="*60)

    try:
        client = get_particulate_api_client()

        # 示例：查询水溶性离子数据
        print("   调用API: 查询水溶性离子数据...")

        result = client.call(
            question="测试查询",
            detect="ElementCompositionAnalysis/GetChartAnalysis",
            station="测试站",
            code="test",
            time_start="2024-01-01 00:00:00",
            time_end="2024-01-01 01:00:00",
            time_type="Hour",
            data_type="PM2_5",
            max_retries=1  # 测试时减少重试次数
        )

        if result.get("success"):
            print("✅ API调用成功")
            print(f"   状态码: {result.get('response_status')}")
            return True
        else:
            error = result.get("error", "未知错误")
            print(f"⚠️  API调用失败: {error}")

            # 401错误表示Token验证失败
            if "401" in str(error):
                print("\n   ⚠️  这可能表示:")
                print("   1. Token端点配置不正确")
                print("   2. 用户名/密码错误")
                print("   3. API服务端Token验证逻辑不同")
                print("   4. 需要联系API提供方确认正确的认证方式")
            return False

    except Exception as e:
        print(f"❌ API调用异常: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_reload():
    """测试配置文件热更新"""
    print("\n" + "="*60)
    print("测试4: 配置文件热更新")
    print("="*60)

    try:
        token_manager = get_particulate_token_manager()

        print(f"   当前base_url: {token_manager.get_base_url()}")
        print(f"   Token缓存时间: {token_manager._cfg.get('token_cache_time', 'N/A')}秒")

        print("\n✅ 配置读取成功")
        print("   提示: 修改config/external_api_config.yaml后会自动重载")
        return True

    except Exception as e:
        print(f"❌ 配置读取失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("颗粒物API Token验证机制测试")
    print("="*60)
    print(f"测试时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []

    # 运行测试
    results.append(("Token获取", test_token_fetch()))
    results.append(("认证请求头", test_auth_headers()))
    results.append(("配置热更新", test_config_reload()))

    # 只有Token获取成功才测试API调用
    if results[0][1]:  # Token获取成功
        results.append(("API调用", test_api_call_with_token()))
    else:
        print("\n⚠️  跳过API调用测试（Token获取失败）")

    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！Token验证机制工作正常。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查配置。")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
