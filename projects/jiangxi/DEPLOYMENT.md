# 江西项目前端部署

本说明仅适用于 `jiangxi` 项目。前端项目类型由构建时的 `PROJECT` 环境变量决定，
不会根据 Git 分支名自动选择。部署时必须显式设置 `PROJECT=jiangxi`。

## 后端会话数据库

江西部署的会话历史必须保存在本地 PostgreSQL。后端按以下优先级选择
会话数据库：`SESSION_DATABASE_URL`、`LOCAL_DATABASE_URL`、`DATABASE_URL`。
生产环境应同时设置本地 `LOCAL_DATABASE_URL` 和 `SESSION_DATABASE_URL`，避免
共享层的 `DATABASE_URL` 更新影响会话历史；启动时会同时检查共享数据库和
会话数据库连接，不会在本地库不可用时静默回退到远程库。

## 构建

```bash
cd /home/xckj/suyuan/frontend
PROJECT=jiangxi npm run build:standalone
```

禁止省略 `PROJECT=jiangxi`，否则 Vite 会使用 `default` 项目配置生成正式静态资源。

## 构建产物检查

```bash
grep -F '<title>江西省噪声智能分析平台</title>' /home/xckj/suyuan/frontend/dist/index.html
grep -R 'project:"jiangxi"' /home/xckj/suyuan/frontend/dist/assets
grep -R "resources?presentation_type=document" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/office-documents" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/visualizations" /home/xckj/suyuan/frontend/dist/assets
```

以上检查全部通过后，重新加载正式 Nginx：

```bash
docker exec suyuan-nginx nginx -s reload
curl -fsS http://127.0.0.1:5174/ | grep -F '<title>江西省噪声智能分析平台</title>'
```
