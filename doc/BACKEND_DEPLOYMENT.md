# 后端部署指南

本文档提供完整的后端部署步骤和说明。

## 项目概述

**位置**: `D:\溯源\backend\`

**技术栈**:
- FastAPI (Web框架)
- Uvicorn (ASGI服务器)
- Pydantic (数据验证)
- httpx (异步HTTP客户端)
- structlog (结构化日志)
- OpenAI/DeepSeek/Anthropic SDK (LLM集成)

## 快速部署（Windows）

### 前提条件
- Python 3.8+ 已安装
- 网络可访问外部API和LLM服务

### 步骤

1. **打开PowerShell或命令提示符**
   ```powershell
   cd D:\溯源\backend
   ```

2. **配置环境变量**
   ```powershell
   # 复制模板
   copy .env.example .env

   # 编辑.env文件（必须配置LLM API Key）
   notepad .env
   ```

3. **运行启动脚本**
   ```powershell
   start.bat
   ```

4. **验证服务**
   - 打开浏览器访问: http://localhost:8000/docs
   - 应该看到Swagger API文档界面

## 快速部署（Linux/macOS）

### 步骤

```bash
cd /path/to/溯源/backend

# 配置环境变量
cp .env.example .env
nano .env  # 编辑配置文件

# 启动服务
chmod +x start.sh
./start.sh
```

## 配置详解

### 必需配置项

#### 1. LLM Provider（必选其一）

**使用OpenAI (GPT-4)**:
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4-turbo-preview
```

**使用DeepSeek (推荐，性价比高)**:
```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-reasoner
```

**使用Anthropic Claude**:
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
ANTHROPIC_MODEL=claude-3-opus-20240229
```

#### 2. 高德地图Key（可选）
```env
AMAP_PUBLIC_KEY=your-amap-key-here
```
> 注：如不配置，前端地图将使用静态图兜底

#### 3. 外部API配置

根据你的实际网络环境修改以下地址：

```env
# 站点信息API
STATION_API_BASE_URL=http://180.184.91.74:9095

# 监测数据APIs
MONITORING_DATA_API_URL=http://180.184.91.74:9091
VOCS_DATA_API_URL=http://180.184.91.74:9092
PARTICULATE_DATA_API_URL=http://180.184.91.74:9093

# 气象API
METEOROLOGICAL_API_URL=http://180.184.30.94/api/AiDataService/ReportApplication/UserReportDataQuery/Query
METEOROLOGICAL_API_KEY=1882bb80-16a0-419a-ae3e-f442471909d3

# 上风向分析API
UPWIND_ANALYSIS_API_URL=http://192.168.20.2:9092
```

> **重要**: 如果你的开发机器无法直接访问这些内网IP，需要：
> - 使用VPN连接到内网
> - 或配置反向代理/端口转发
> - 或修改为可访问的公网地址

## 测试部署

### 1. 健康检查
```bash
curl http://localhost:8000/health
```

预期响应：
```json
{
  "status": "healthy",
  "service": "air-pollution-traceability-api",
  "version": "1.0.0",
  "environment": "development",
  "llm_provider": "openai"
}
```

### 2. 配置检查
```bash
curl http://localhost:8000/api/config
```

### 3. 完整分析测试

使用提供的测试脚本：
```bash
python test_api.py
```

或使用curl：
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "分析广州天河站2025-08-09的O3污染情况"}'
```

## 与前端联调

### 1. 确保后端运行
```bash
# 后端应该在8000端口运行
curl http://localhost:8000/health
```

### 2. 启动前端
```bash
cd D:\溯源\frontend
npm run dev
```

### 3. 测试连通性
在前端页面 (http://localhost:5173) 输入查询，检查：
- 浏览器控制台是否有CORS错误
- Network面板中API请求是否成功
- 后端日志是否显示请求记录

### 4. CORS问题处理

如果遇到CORS错误，在`.env`中添加前端地址：
```env
CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173
```

## 生产部署建议

### 1. 使用Gunicorn

安装：
```bash
pip install gunicorn
```

运行：
```bash
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log
```

### 2. 使用Systemd服务

创建 `/etc/systemd/system/pollution-backend.service`:
```ini
[Unit]
Description=Pollution Traceability Backend
After=network.target

[Service]
Type=notify
User=www-data
WorkingDirectory=/path/to/backend
Environment="PATH=/path/to/backend/venv/bin"
EnvironmentFile=/path/to/backend/.env
ExecStart=/path/to/backend/venv/bin/gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable pollution-backend
sudo systemctl start pollution-backend
sudo systemctl status pollution-backend
```

### 3. Nginx反向代理

配置文件 `/etc/nginx/sites-available/pollution-api`:
```nginx
server {
    listen 80;
    server_name api.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 增加超时时间（LLM调用可能较慢）
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;

        # WebSocket支持（如需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/pollution-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. Docker部署

创建 `Dockerfile`:
```dockerfile
FROM python:3.10-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

创建 `docker-compose.yml`:
```yaml
version: '3.8'

services:
  backend:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs
```

构建和运行：
```bash
docker-compose build
docker-compose up -d
docker-compose logs -f backend
```

## 常见问题处理

### 问题1：LLM API调用失败

**症状**: 日志显示`llm_extraction_failed`或`llm_analysis_failed`

**解决**:
1. 检查API Key是否正确：`echo $OPENAI_API_KEY`
2. 测试网络连通性：`curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`
3. 检查余额是否充足（OpenAI账户）
4. 尝试切换LLM Provider（如改用DeepSeek）

### 问题2：外部API无法访问

**症状**: 日志显示`http_request_exhausted`，分析结果为空

**解决**:
1. 检查网络连通性：`ping 180.184.91.74`
2. 测试端口：`telnet 180.184.91.74 9095`
3. 检查VPN是否连接
4. 修改`.env`中的API地址为可访问地址

### 问题3：导入错误ModuleNotFoundError

**症状**: 启动时报`No module named 'xxx'`

**解决**:
```bash
# 确保在虚拟环境中
source venv/bin/activate  # Linux
venv\Scripts\activate     # Windows

# 重新安装依赖
pip install -r requirements.txt

# 检查是否所有包都安装成功
pip list | grep fastapi
pip list | grep openai
```

### 问题4：CORS错误

**症状**: 前端控制台显示CORS policy错误

**解决**:
在`.env`中添加前端地址：
```env
CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://your-frontend-domain.com
```

重启后端服务。

### 问题5：端口被占用

**症状**: 启动时显示`Address already in use`

**解决**:

Windows:
```powershell
netstat -ano | findstr :8000
taskkill /PID <进程ID> /F
```

Linux:
```bash
lsof -ti:8000 | xargs kill -9
```

或修改端口：
```env
PORT=8001
```

## 性能优化

### 1. 调整Worker数量

根据CPU核心数调整：
```bash
# 推荐: workers = (2 * CPU核心数) + 1
gunicorn app.main:app --workers 4 ...
```

### 2. 启用连接池复用

在代码中（如需长期运行）：
```python
# app/utils/http_client.py
client = httpx.AsyncClient(
    timeout=30,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
)
```

### 3. 添加Redis缓存

安装Redis并配置：
```env
REDIS_HOST=localhost
REDIS_PORT=6379
```

缓存LLM响应和API结果以减少重复请求。

## 监控和日志

### 查看实时日志
```bash
# 如果使用systemd
sudo journalctl -u pollution-backend -f

# 如果使用文件日志
tail -f logs/access.log
tail -f logs/error.log
```

### 日志级别设置
```env
# 开发环境
LOG_LEVEL=DEBUG

# 生产环境
LOG_LEVEL=INFO
```

### 关键日志事件
- `application_starting`: 服务启动
- `analysis_requested`: 收到分析请求
- `params_extracted`: 参数提取完成
- `core_data_fetched`: 数据获取完成
- `llm_*_complete`: LLM分析完成
- `analysis_complete`: 整体分析完成
- `*_failed`: 各类错误

## 安全建议

1. **不要提交.env文件到版本控制**
   - 已在`.gitignore`中配置

2. **生产环境关闭DEBUG模式**
   ```env
   DEBUG=False
   ENVIRONMENT=production
   ```

3. **使用环境变量管理敏感信息**
   - 不要在代码中硬编码API Key

4. **限制CORS Origins**
   ```env
   # 只允许特定域名
   CORS_ORIGINS=https://your-production-domain.com
   ```

5. **使用HTTPS**
   - 在生产环境配置SSL证书（通过Nginx）

## 下一步

1. ✅ 后端部署完成
2. 配置前端连接后端
3. 进行端到端测试
4. 根据实际需求调整配置
5. 监控性能和错误日志

---

**文档版本**: 1.0.0
**最后更新**: 2025-10-16
