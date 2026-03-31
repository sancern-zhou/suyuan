# 配置统一化说明

## 修改日期
2026-03-29

## 修改目的
统一后端配置管理，清除多处冗余的配置读取，所有配置统一通过 `config.settings.settings` 读取。

## 修改内容

### 1. Settings 类增强 (`config/settings.py`)

添加了两个新配置字段：

```python
# Backend URL Configuration (用于生成图片等资源的完整URL)
backend_host: str = Field(
    default="http://localhost:8000",
    description="Backend server host URL (for generating image URLs)"
)
api_base_url: Optional[str] = Field(
    default=None,
    description="Frontend API base URL (for callback URLs, overrides auto-detection)"
)
```

### 2. 统一图片URL生成策略

**原则**：所有工具统一返回**相对路径** `/api/image/{image_id}`，不再拼接完整URL。

**原因**：
- 前端通过 vite 代理（开发环境）或同域访问（生产环境）自动处理
- 避免硬编码IP地址和端口
- 支持多网络环境访问

### 3. 移除的冗余配置

以下文件移除了 `BACKEND_HOST` 的直接读取：

1. **app/agent/experts/weather_executor.py**
   - 移除: `backend_host = os.getenv("BACKEND_HOST", "http://localhost:8000")`
   - 原因: 现在统一使用相对路径 `/api/image/{image_id}`

2. **app/agent/experts/component_executor.py**
   - 移除: `backend_host = os.getenv("BACKEND_HOST", "http://localhost:8000")`
   - 原因: 现在统一使用相对路径 `/api/image/{image_id}`

3. **app/tools/analysis/meteorological_trajectory_analysis/tool.py**
   - 移除: `BACKEND_HOST = os.getenv("BACKEND_HOST", "http://localhost:8000")`
   - 原因: 现在统一使用相对路径 `/api/image/{image_id}`

4. **app/tools/visualization/particulate_visualizer.py**
   - 移除: `BACKEND_HOST = os.getenv("BACKEND_HOST", "http://localhost:8000")`
   - 修改: `image_url = f"{BACKEND_HOST}{image_relative_path}"` → `image_url = f"/api/image/{saved_image_id}"`

5. **app/tools/browser/config.py**
   - 移除: `BACKEND_HOST = os.getenv("BACKEND_HOST", "http://localhost:8000")`

6. **app/tools/browser/actions/screenshot.py**
   - 修改: `image_url = f"{config.BACKEND_HOST}{image_relative_path}"` → `image_url = f"/api/image/{image_id}"`

### 4. 保持不变的配置

以下文件已经正确使用 `settings`，无需修改：

- **app/agent/experts/report_executor.py**: 使用 `getattr(settings, "BACKEND_HOST", ...)`
  - 注：实际上也已改为使用相对路径，这个变量不再使用

- **app/services/real_api_client.py**: 使用 `os.getenv()` 读取外部API配置（合理）
- **app/api/upload_routes.py**: 使用 `os.getenv("API_BASE_URL")` 读取前端URL（合理）

## 环境变量配置 (.env)

保留以下配置（虽然不再在代码中直接使用，但保留用于文档说明）：

```bash
# Backend Host URL (用于生成图片等资源的完整URL)
BACKEND_HOST=http://219.135.180.51:8000

# API Base URL（用于返回给LLM的完整URL）
API_BASE_URL=http://219.135.180.51:56041
```

**注意**：虽然代码不再使用 `BACKEND_HOST` 拼接URL，但保留此配置项用于：
1. 文档说明当前部署环境
2. 未来可能的其他用途
3. Settings 类会自动读取此配置（如需使用）

## 迁移指南

### 对于新开发的功能

**正确做法**：
```python
# ❌ 错误：直接读取环境变量
BACKEND_HOST = os.getenv("BACKEND_HOST", "http://localhost:8000")
image_url = f"{BACKEND_HOST}/api/image/{image_id}"

# ✅ 正确：使用相对路径
image_url = f"/api/image/{image_id}"
```

**如果需要读取其他配置**：
```python
from config.settings import settings

# 读取外部API配置
api_url = settings.station_api_base_url

# 读取LLM配置
llm_config = settings.get_llm_config()
```

## 测试验证

1. **重启后端服务**（重要！）
2. **测试图片显示**：
   - 轨迹分析图
   - AQI日历图
   - 颗粒物组分图
   - 浏览器截图
3. **验证不同访问方式**：
   - 本地访问: `http://localhost:5174`
   - 内网访问: `http://219.135.180.51:56041`
   - 其他网络环境

## 影响范围

- ✅ **无破坏性修改**：所有改动向后兼容
- ✅ **简化配置**：移除冗余代码，统一配置来源
- ✅ **提升灵活性**：支持多网络环境访问
- ⚠️ **需要重启后端**：让代码修改生效
