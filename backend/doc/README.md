# 大气污染溯源系统 - 后端服务

基于 FastAPI 的大气污染源溯源分析后端服务，集成多个外部API和LLM能力，提供全面的污染源分析。

## 功能特性

### 核心功能
- **自然语言参数提取**：使用LLM从用户输入中提取站点、时间、污染物等参数
- **多源数据整合**：并行调用监测数据、气象数据、站点信息等多个外部API
- **气象条件分析**：基于风速风向分析上风向企业分布
- **组分溯源分析**：
  - VOCs组分分析（臭氧污染）
  - 颗粒物组分分析（PM2.5/PM10）
- **区域对比分析**：目标站点与周边站点的浓度对比
- **LLM智能分析**：基于多模态数据生成专业分析报告
- **动态可视化**：生成ECharts和AMap可视化配置

### 技术特性
- **异步架构**：基于asyncio的并发请求处理
- **重试机制**：自动重试失败的HTTP请求
- **结构化日志**：使用structlog记录详细的执行日志
- **多LLM支持**：支持OpenAI、DeepSeek、Anthropic等多个LLM提供商
- **跨平台**：支持Windows和Linux系统

## 架构设计

### 目录结构
```
backend/
├── app/
│   ├── main.py                          # FastAPI应用入口
│   ├── api/                             # API路由（预留）
│   ├── models/
│   │   └── schemas.py                   # Pydantic数据模型
│   ├── services/
│   │   ├── external_apis.py             # 外部API客户端
│   │   ├── llm_service.py               # LLM服务封装
│   │   └── analysis_orchestrator.py     # 分析编排器（核心）
│   └── utils/
│       ├── http_client.py               # HTTP客户端工具
│       ├── data_processing.py           # 数据处理工具
│       └── visualization.py             # 可视化生成器
├── config/
│   └── settings.py                      # 配置管理
├── tests/                               # 测试用例
├── requirements.txt                     # Python依赖
├── .env.example                         # 环境变量示例
├── start.bat                            # Windows启动脚本
├── start.sh                             # Linux/macOS启动脚本
└── README.md                            # 本文档
```

### 工作流程

```
用户查询 → 参数提取(LLM) → 并行数据获取
                              ├─ 站点信息
                              ├─ 监测数据
                              ├─ 气象数据
                              └─ 周边站点数据
                              ↓
                          气象数据处理 → 上风向企业分析
                              ↓
                      ┌─────────┴──────────┐
                      ↓                    ↓
            组分数据获取           区域对比分析
            (VOCs/颗粒物)             (LLM)
                      ↓
            组分溯源分析(LLM)
                      ↓
            ┌─────────┴──────────┐
            ↓                    ↓
      可视化生成          综合分析(LLM)
      (ECharts/AMap)
            ↓
        组装响应 → 返回前端
```

## 快速开始

### 系统要求
- **Python**: 3.8+ (推荐3.9或3.10)
- **操作系统**: Windows 10+, Linux, macOS
- **内存**: 建议4GB+
- **网络**: 需要访问外部API和LLM服务

### Windows环境安装

1. **安装Python**
   ```powershell
   # 使用winget安装Python
   winget install Python.Python.3.10

   # 或从官网下载：https://www.python.org/downloads/
   ```

2. **克隆项目并进入后端目录**
   ```powershell
   cd D:\溯源\backend
   ```

3. **配置环境变量**
   ```powershell
   # 复制环境变量模板
   copy .env.example .env

   # 编辑.env文件，配置必需的API密钥
   notepad .env
   ```

4. **启动服务**
   ```powershell
   # 直接运行启动脚本（自动创建虚拟环境并安装依赖）
   start.bat
   ```

### Linux/macOS环境安装

1. **确保Python已安装**
   ```bash
   python3 --version  # 应显示3.8+
   ```

2. **进入后端目录**
   ```bash
   cd /path/to/溯源/backend
   ```

3. **配置环境变量**
   ```bash
   cp .env.example .env
   nano .env  # 或使用你喜欢的编辑器
   ```

4. **启动服务**
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

### 手动安装（高级用户）

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 配置说明

### 必需配置

编辑`.env`文件，配置以下必需项：

#### 1. LLM配置（三选一）

**选项A：使用OpenAI**
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-4-turbo-preview
```

**选项B：使用DeepSeek**
```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_MODEL=deepseek-reasoner
```

**选项C：使用Anthropic Claude**
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-anthropic-api-key
ANTHROPIC_MODEL=claude-3-opus-20240229
```

#### 2. 高德地图Key（可选，用于前端地图显示）
```env
AMAP_PUBLIC_KEY=your-amap-key-here
```

#### 3. 外部API配置（根据实际情况修改）
```env
# 站点查询API
STATION_API_BASE_URL=http://180.184.91.74:9095

# 监测数据API
MONITORING_DATA_API_URL=http://180.184.91.74:9091
VOCS_DATA_API_URL=http://180.184.91.74:9092
PARTICULATE_DATA_API_URL=http://180.184.91.74:9093

# 气象数据API
METEOROLOGICAL_API_URL=http://180.184.30.94/api/AiDataService/ReportApplication/UserReportDataQuery/Query
METEOROLOGICAL_API_KEY=1882bb80-16a0-419a-ae3e-f442471909d3

# 上风向分析API
UPWIND_ANALYSIS_API_URL=http://192.168.20.2:9092
```

### 可选配置

```env
# 服务器配置
HOST=0.0.0.0
PORT=8000
DEBUG=True

# CORS配置
CORS_ORIGINS=http://localhost:5173,http://localhost:5174

# 分析参数
DEFAULT_SEARCH_RANGE_KM=5.0
DEFAULT_MAX_ENTERPRISES=30
DEFAULT_TOP_N_ENTERPRISES=8

# 重试配置
MAX_RETRIES=3
RETRY_INTERVAL_MS=100
REQUEST_TIMEOUT_SECONDS=30
```

## API文档

### 启动服务后自动生成的交互式文档

访问 http://localhost:8000/docs 查看完整的API文档（Swagger UI）

### 主要端点

#### 1. 获取配置
```http
GET /api/config
```

**响应示例：**
```json
{
  "amapPublicKey": "your-amap-key",
  "features": {
    "dynamicPreferred": true,
    "echarts": true
  }
}
```

#### 2. 分析请求（主要端点）
```http
POST /api/analyze
Content-Type: application/json

{
  "query": "分析广州天河站2025-08-09的O3污染情况"
}
```

**响应结构：**
```json
{
  "success": true,
  "data": {
    "query_info": {
      "location": "天河站",
      "city": "广州",
      "pollutant": "O3",
      "start_time": "2025-08-09 00:00:00",
      "end_time": "2025-08-09 23:59:59",
      "scale": "station"
    },
    "kpi_summary": {
      "peak_value": 180.5,
      "avg_value": 120.3,
      "unit": "μg/m³",
      "exceed_periods": [...],
      "main_wind_sector": "东南",
      "top_sources": ["企业A", "企业B", "企业C"],
      "confidence": 0.85
    },
    "weather_analysis": { ... },
    "regional_analysis": { ... },
    "voc_analysis": { ... },
    "comprehensive_analysis": { ... }
  },
  "message": "分析完成"
}
```

#### 3. 健康检查
```http
GET /health
```

## 开发指南

### 添加新的分析模块

1. **在`app/services/llm_service.py`中添加新的LLM分析方法**
   ```python
   async def analyze_new_module(self, ...):
       prompt = """分析任务描述..."""
       # LLM调用逻辑
       return analysis_text
   ```

2. **在`app/utils/visualization.py`中添加可视化生成器**
   ```python
   def generate_new_visual(...):
       # 生成ECharts/AMap配置
       return visual_payload
   ```

3. **在`app/services/analysis_orchestrator.py`中集成新模块**
   ```python
   async def _analyze_new_module(self, ...):
       # 数据获取
       # LLM分析
       # 可视化生成
       return ModuleResult(...)
   ```

4. **在`app/models/schemas.py`中扩展响应模型**
   ```python
   class AnalysisResponseData(BaseModel):
       # ...现有字段
       new_module_analysis: Optional[ModuleResult] = None
   ```

### 调试技巧

#### 1. 查看详细日志
```bash
# 设置日志级别为DEBUG
# 在.env中：
LOG_LEVEL=DEBUG
```

#### 2. 测试单个组件
```python
# 在Python交互式环境中测试
import asyncio
from app.services.external_apis import station_api

async def test():
    result = await station_api.get_station_by_name("天河站")
    print(result)

asyncio.run(test())
```

#### 3. 使用curl测试API
```bash
# 测试配置端点
curl http://localhost:8000/api/config

# 测试分析端点
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "分析广州天河站2025-08-09的O3污染"}'
```

## 部署指南

### Docker部署（推荐）

创建`Dockerfile`：
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

构建和运行：
```bash
docker build -t pollution-backend .
docker run -p 8000:8000 --env-file .env pollution-backend
```

### 生产环境部署

1. **使用Gunicorn + Uvicorn Workers**
   ```bash
   pip install gunicorn
   gunicorn app.main:app \
     --workers 4 \
     --worker-class uvicorn.workers.UvicornWorker \
     --bind 0.0.0.0:8000 \
     --timeout 120
   ```

2. **配置Nginx反向代理**
   ```nginx
   server {
       listen 80;
       server_name api.your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_read_timeout 300s;
       }
   }
   ```

3. **使用systemd管理服务**
   ```ini
   [Unit]
   Description=Pollution Traceability Backend
   After=network.target

   [Service]
   Type=notify
   User=www-data
   WorkingDirectory=/path/to/backend
   Environment="PATH=/path/to/backend/venv/bin"
   ExecStart=/path/to/backend/venv/bin/gunicorn app.main:app \
     --workers 4 \
     --worker-class uvicorn.workers.UvicornWorker \
     --bind 0.0.0.0:8000

   [Install]
   WantedBy=multi-user.target
   ```

## 故障排除

### 常见问题

#### 1. LLM API调用失败
**症状**：参数提取或分析步骤报错

**解决方案**：
- 检查`.env`中的API Key是否正确
- 确认LLM_PROVIDER配置正确
- 检查网络是否能访问LLM API
- 查看日志中的详细错误信息

#### 2. 外部API连接超时
**症状**：数据获取失败，返回空结果

**解决方案**：
- 检查外部API地址是否正确
- 确认网络连通性（ping、telnet测试）
- 增加REQUEST_TIMEOUT_SECONDS配置
- 检查防火墙设置

#### 3. 模块导入错误
**症状**：启动时报`ModuleNotFoundError`

**解决方案**：
```bash
# 确保在项目根目录
cd D:\溯源\backend

# 重新安装依赖
pip install -r requirements.txt

# 检查Python路径
echo $PYTHONPATH  # Linux
echo %PYTHONPATH%  # Windows
```

#### 4. CORS错误
**症状**：前端无法访问API

**解决方案**：
在`.env`中添加前端域名到CORS_ORIGINS：
```env
CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://your-frontend-domain.com
```

### 日志查看

服务运行时会输出结构化日志：

```bash
# Windows PowerShell
Get-Content logs\app.log -Tail 50 -Wait

# Linux/macOS
tail -f logs/app.log
```

日志关键字段：
- `event`: 事件类型
- `timestamp`: 时间戳
- `level`: 日志级别（INFO/WARNING/ERROR）
- `error`: 错误信息（如有）

## 性能优化

### 1. 启用Redis缓存（可选）

安装Redis并配置：
```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

### 2. 并发控制

调整Uvicorn workers数量：
```bash
uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8000
```

### 3. 数据库连接池（如需持久化）

如添加PostgreSQL/MySQL，配置连接池大小。

## 贡献指南

欢迎提交Issue和Pull Request！

### 提交代码前

1. 运行代码格式化：
   ```bash
   pip install black isort
   black app/
   isort app/
   ```

2. 运行类型检查：
   ```bash
   pip install mypy
   mypy app/
   ```

3. 运行测试：
   ```bash
   pytest tests/
   ```

## 许可证

本项目与前端遵循相同的许可协议（MIT License）。

## 技术支持

如有问题，请：
1. 查看本README的故障排除章节
2. 检查日志文件中的详细错误信息
3. 提交Issue到项目仓库

---

**版本**: 1.0.0
**最后更新**: 2025-10-16
