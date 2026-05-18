# Mimo API 调试报告

## 问题描述

测试 API 时成功，但 Agent 使用时失败，出现 404 和 401 错误。

## 根本原因

### 原因1: URL 路径错误（404）

**现象**：SDK 请求的 URL 是 `/anthropic/v1/v1/messages`（双 `/v1`）

**原因**：
- 初始配置：`MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic/v1`
- SDK 行为：SDK 会在 base_url 后自动添加 `/v1`
- 结果：`/anthropic/v1` + `/v1` = `/anthropic/v1/v1/` ❌

**解决**：
```bash
# 正确配置（不含 /v1）
MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic
```

SDK 会自动添加 `/v1`，最终请求：`/anthropic/v1/messages` ✅

### 原因2: 认证冲突（401）

**现象**：即使 URL 正确，仍然返回 401 Invalid API Key

**原因**：
- 系统环境变量：`ANTHROPIC_AUTH_TOKEN=33d14b5b112b4aa7a868c8f1c019681b.QHm2vn1cGvkGbphw`（智谱AI的token）
- SDK 行为：读取环境变量，添加 `Authorization: Bearer {智谱token}` header
- 结果：Mimo API 收到两个认证头冲突
  - `x-api-key: tp-cs6jt5x8jiy111q6uom7gzqy1vdlnyury4q35oy9dto4sdpk` ✅
  - `authorization: Bearer 33d14b5b...` ❌（智谱token）

**解决**：
在创建 Mimo 客户端前临时清除环境变量：
```python
saved_auth_token = os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
try:
    client = AsyncAnthropic(api_key=..., base_url=...)
finally:
    if saved_auth_token:
        os.environ["ANTHROPIC_AUTH_TOKEN"] = saved_auth_token
```

## 测试对比

| 测试场景 | URL | Authorization Header | 结果 |
|---------|-----|---------------------|------|
| 直接HTTP请求 | `/anthropic/v1/messages` | 无 | ✅ 200 |
| SDK base_url=`/anthropic/v1` | `/anthropic/v1/v1/messages` | Bearer 智谱token | ❌ 404 |
| SDK base_url=`/anthropic` | `/anthropic/v1/messages` | Bearer 智谱token | ❌ 401 |
| SDK base_url=`/anthropic` + 清除env | `/anthropic/v1/messages` | 无 | ✅ 200 |

## 正确配置

### .env 配置
```bash
LLM_PROVIDER=mimo
MIMO_API_KEY=tp-cs6jt5x8jiy111q6uom7gzqy1vdlnyury4q35oy9dto4sdpk
MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic  # 不含 /v1
MIMO_MODEL=mimo-v2.5-pro
```

### 代码修改（llm_service.py）
```python
# 创建 Mimo 客户端前临时清除 ANTHROPIC_AUTH_TOKEN
saved_auth_token = os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
try:
    self.anthropic_client = AsyncAnthropic(
        api_key=self.api_key,
        base_url=anthropic_base_url,
        auth_token=None
    )
finally:
    if saved_auth_token:
        os.environ["ANTHROPIC_AUTH_TOKEN"] = saved_auth_token
```

## 验证结果

```bash
$ python test_success.py
✅ API 调用成功!
Model: mimo-v2.5-pro
Input Tokens: 65
Output Tokens: 92

响应内容:
  Block 0 (text): 你好！我是小米的MiMo，一个充满好奇心、喜欢帮人解答问题的AI伙伴~ 很高兴遇见你！
```

## 关键发现

1. **SDK URL 拼接逻辑**：Anthropic SDK 会自动在 base_url 后添加 `/v1`
2. **环境变量优先级**：`ANTHROPIC_AUTH_TOKEN` 环境变量优先级高于 `auth_token=None` 参数
3. **双重认证冲突**：Mimo API 不支持同时使用 `x-api-key` 和 `Authorization: Bearer`
4. **域名差异**：
   - 套餐域名：`https://token-plan-cn.xiaomimimo.com/anthropic` ✅
   - 标准域名：`https://api.xiaomimimo.com/anthropic` ❌（返回401）

## 后续建议

1. 考虑在系统级别移除 `ANTHROPIC_AUTH_TOKEN` 环境变量，避免影响其他 Anthropic SDK 客户端
2. 如果需要使用智谱AI，应该使用其专用的 SDK，而不是复用 Anthropic SDK 的环境变量
3. 文档化不同 LLM provider 的环境变量要求，避免冲突

## 相关文件

- `/home/xckj/suyuan/backend/.env` - 环境变量配置
- `/home/xckj/suyuan/backend/app/services/llm_service.py` - LLM 服务（已修复）
- 测试脚本：
  - `test_mimo_http.py` - 直接 HTTP 请求测试
  - `test_compare_requests.py` - 对比 SDK 和 HTTP 请求
  - `test_success.py` - 成功验证
