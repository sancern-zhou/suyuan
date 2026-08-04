# Suyuan 前端运行说明

当前前端由 `/home/xckj/suyuan/frontend` 中的 Vite 进程提供服务，监听
`5174` 端口；项目部署不依赖 Docker 或 Nginx。

## 构建与验证

```bash
cd /home/xckj/suyuan/frontend
npm run test:auth
npm run test:event-tasks
npm run build:standalone

grep -R "resources?presentation_type=document" dist/assets
! grep -R "/office-documents" dist/assets
! grep -R "/visualizations" dist/assets
```

构建会更新 `dist`，但 Vite 开发服务直接使用源码，无需重载任何容器或
Web 服务器。

## 项目选择

后端与前端必须使用来自 `projects/<id>/project.yaml` 的同一项目标识。构建前先校验后端读取结果：

```bash
export PROJECT=xuchang
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 python -c \
  "from app.project_config.loader import load_project_context; print(load_project_context('$PROJECT').model_dump_json())"

cd /home/xckj/suyuan/frontend
npm run build:standalone
```

此部署仓库的 standalone 默认构建目标为 `xuchang`（见
`frontend/.env.standalone`）。临时构建其他项目时可在命令前显式覆盖，例如：

```bash
PROJECT=default npm run build:standalone
```

每次部署记录 `PROJECT`、Git commit SHA、项目清单校验和及构建产物版本。客户发布标签用于标识部署快照，例如 `jiyuan/v2026.07.1`，不创建永久客户分支。
