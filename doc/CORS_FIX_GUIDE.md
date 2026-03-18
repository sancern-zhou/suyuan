# CORS跨域问题修复指南

## 问题描述

前端Vue3应用（运行在 `http://localhost:5176`）无法访问后端API（`http://localhost:8000`），报错：

```
Access to fetch at 'http://localhost:8000/api/config' from origin 'http://localhost:5176' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

## 原因分析

后端FastAPI服务没有配置CORS中间件，或者CORS配置中没有包含前端的端口号5176。

## 解决方案

### 方案1: 修复后端CORS配置（推荐）

在后端 `backend/app/main.py` 中添加/修改CORS中间件配置：

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS配置 - 允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # React版本端口
        "http://localhost:5174",  # Vue3备用端口
        "http://localhost:5175",  # Vue3备用端口2
        "http://localhost:5176",  # Vue3当前运行端口
        "http://localhost:5177",  # 预留端口
    ],
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有请求头
)
```

**或者在 `.env` 文件中配置**:

```env
CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176
```

然后在 `backend/config/settings.py` 中读取：

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    cors_origins: str = Field("http://localhost:5173")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',')]
```

在 `main.py` 中使用：

```python
from config.settings import settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 方案2: 使用Vite代理（临时方案）

如果无法修改后端，可以完全依赖Vite的代理功能。当前 `vite.config.ts` 已经配置了代理，但需要确保后端在 `localhost:8000` 运行。

**验证代理配置**:

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    port: 5176,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false
      }
    }
  }
})
```

**使用代理时的注意事项**:

1. 前端代码中使用相对路径 `/api/config`，而不是完整URL `http://localhost:8000/api/config`
2. 确保后端运行在 `http://localhost:8000`
3. 前端必须通过Vite开发服务器访问（`http://localhost:5176`）

### 方案3: 开发环境完全放开CORS（仅用于开发）

如果仅用于本地开发测试，可以暂时完全放开CORS限制：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ 仅开发环境！生产环境禁止使用
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**⚠️ 警告**: 此方法仅用于开发环境，生产环境必须指定明确的origins列表。

## 验证修复

修复后端CORS配置后，重启后端服务：

```bash
cd D:\溯源\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

然后刷新前端页面，应该可以正常访问API了。

## 检查清单

- [ ] 后端运行在 `http://localhost:8000`
- [ ] 前端运行在 `http://localhost:5176`
- [ ] 后端CORS中间件已添加
- [ ] CORS配置包含端口5176
- [ ] 后端服务已重启
- [ ] 前端页面已刷新
- [ ] 浏览器控制台无CORS错误

## 相关文档

- FastAPI CORS文档: https://fastapi.tiangolo.com/tutorial/cors/
- MDN CORS文档: https://developer.mozilla.org/zh-CN/docs/Web/HTTP/CORS
- 后端配置文件: `backend/app/main.py`
- 前端代理配置: `frontend-vue/vite.config.ts`
