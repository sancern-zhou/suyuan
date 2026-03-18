# 颗粒物API Token验证 - 快速参考

## 一键配置

### 1. 编辑 `.env` 文件

```bash
# 修改以下配置项
PARTICULATE_API_USERNAME=你的用户名
PARTICULATE_API_PASSWORD=你的密码
```

### 2. 运行测试

```bash
cd backend
python tests/test_particulate_token_auth.py
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `app/utils/particulate_token_manager.py` | Token管理器 |
| `app/utils/particulate_api_client.py` | API客户端（已集成Token） |
| `config/external_api_config.yaml` | 配置文件 |
| `tests/test_particulate_token_auth.py` | 测试脚本 |

## Token验证流程

```
┌─────────────┐
│ 查询工具调用 │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ TokenManager │
│ 检查Token缓存 │
└──────┬──────┘
       │
       ├─ 有效 → 使用缓存Token
       │
       └─ 无效/过期 → 刷新Token
                       │
                       ▼
               ┌───────────────┐
               │ GET /api/uqp/ │
               │    token      │
               └───────┬───────┘
                       │
                       ▼
                   缓存Token
                       │
                       ▼
┌──────────────────────────────┐
│   发送API请求（携带Token）    │
│   Authorization: Bearer xxx  │
└──────────────┬───────────────┘
               │
               ├─ 200 OK → 返回数据
               │
               └─ 401 → 刷新Token并重试
```

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `token_cache_time` | 1800秒 | Token缓存时间（30分钟） |
| `token_refresh_buffer` | 300秒 | 提前刷新时间（5分钟） |
| `max_retries` | 3次 | 最大重试次数 |
| `timeout` | 30秒 | 请求超时时间 |

## API端点

| 端点 | 用途 |
|------|------|
| `/api/uqp/token` | 获取Token |
| `/api/uqp/query` | 查询数据 |

## 认证请求头格式

```http
POST /api/uqp/query HTTP/1.1
Authorization: Bearer {token}
SysCode: SunSup
syscode: SunSup
Content-Type: application/json
```

## 常用命令

```bash
# 测试Token获取
python -c "from app.utils.particulate_token_manager import get_particulate_token_manager; print(get_particulate_token_manager().get_token())"

# 重置Token管理器（清除缓存）
python -c "from app.utils.particulate_token_manager import reset_token_manager; reset_token_manager()"

# 检查Token是否有效
python -c "from app.utils.particulate_token_manager import get_particulate_token_manager; print(get_particulate_token_manager().is_token_valid())"
```

## 故障排查

### 问题：Token获取失败

```bash
# 1. 检查环境变量
echo $PARTICULATE_API_USERNAME
echo $PARTICULATE_API_PASSWORD

# 2. 测试Token端点
curl "http://180.184.91.74:9093/api/uqp/token?UserName=用户名&Pwd=密码" \
  -H "SysCode: SunSup"
```

### 问题：401 Unauthorized

- Token已过期 → 自动刷新（无需处理）
- 用户名/密码错误 → 检查`.env`配置
- SysCode不匹配 → 检查`external_api_config.yaml`

## 文档链接

- 详细文档: `docs/particulate_token_auth_guide.md`
- 参考项目: `D:\溯源\参考\vanna广东省颗粒物`
