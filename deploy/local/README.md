# 本地开发部署（Windows 工作站 / Docker Desktop）

目标：在开发机上跑起完整的风清气智（main）web + worker 成对进程与本地
postgres/redis，用于监控体系（A1~A4）与后续 A4b/A4c/B 的开发验证。
与生产部署的差异见 `docker-compose.dev.yml` 头部注释。

## 前置

- Docker Desktop（WSL2 后端）已启动
- Node ≥ 20（前端构建用宿主机 npm）

## 首次启动

```bash
# 1. 环境文件（密钥后补；LLM 不配时基础设施链路仍可验证）
#    backend/.env.local —— 已按 deploy/local 模板创建，填 LLM 段即可

# 2. 前端构建（宿主机执行，产物经仓库挂载进容器，FastAPI 直接托管）
cd frontend
npm install
npm run build:standalone

# 3. 基础设施 + 后端（开发镜像：清华源加速，见 Dockerfile.dev；
#    生产全量镜像见 backend/Dockerfile，本地开发不需要）
cd ../deploy/local
docker compose -p suyuan-dev up -d --build

# 4. 验证
curl http://127.0.0.1:18000/health            # web
curl http://127.0.0.1:18011/health            # worker 内部 IPC
docker compose -p suyuan-dev logs worker 2>&1 | grep project_scheduled_task_synced
```

## 端口约定

| 用途 | 宿主机 | 容器 |
|---|---|---|
| web（API + 前端静态） | 18000 | 8000 |
| worker 内部 IPC | 18011 | 8011 |
| postgres | 15432 | 5432 |
| redis | 16379 | 6379 |

## 开发迭代

- 代码即挂载：改 `backend/` 下代码后 `docker compose -p suyuan-dev restart web worker`
  生效（无热重载；uvicorn 未开 --reload，与生产行为一致）
- 监控种子任务（task_runtime_monitor / task_runtime_monitor_realtime）在 worker
  启动时同步；巡检任务每小时 :05 执行，可用管理接口手动触发验证
- L0 探针可指向本机端口验证：`l0_probe.py` 的 L0_TARGETS 用
  `127.0.0.1:18000/health,127.0.0.1:18011/health`

## 已知边界（本部署刻意不做）

- 知识库/嵌入服务/qdrant 未启用：知识检索降级，监控路径不依赖
- 气象/爬虫等远端数据源未接：对应查询工具无数据，fetcher 按各自调度运行
  （失败会正常进入监控留痕，反而是事件链路的真实测试样本）
- 开发镜像（Dockerfile.dev）不含 LibreOffice/Quarto/Playwright/OCR/SQL Server
  驱动：报告渲染、浏览器自动化、OCR、SQL Server 直连在本地不可用

## 网络备注（低带宽环境）

- Docker Hub 直连不可达时，用镜像域名前缀直拉再 retag：
  `docker pull docker.1ms.run/library/python:3.11-slim-bookworm`
  `docker tag docker.1ms.run/library/python:3.11-slim-bookworm python:3.11-slim-bookworm`
- pip/apt 已在 Dockerfile.dev 内换清华源；如需更换镜像源编辑
  `~/.docker/daemon.json`（registry-mirrors）后重启 Docker Desktop
