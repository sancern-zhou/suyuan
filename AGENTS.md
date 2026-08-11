## Agent 文件系统路径规范

- 所有 Agent、子 Agent、工具和 Skill 接收的文件系统相对路径，统一以项目根目录 `/home/xckj/suyuan` 为解析基准。
- 后端文件的项目相对路径必须显式包含 `backend/` 前缀，例如 `backend/app/main.py`。
- 工具返回项目内文件路径时，统一返回相对于项目根的路径；项目外临时文件可以返回规范化绝对路径。
- 禁止依赖进程当前工作目录推断项目根，统一使用 `backend/app/utils/path_config.py` 中的 `PROJECT_ROOT`、`resolve_agent_path()` 和 `format_agent_path()`。
- `/tmp/...` 以及报告包内部的 `assets/...` 等逻辑路径不属于项目相对文件系统路径。

## 构建与部署规范

- 前端源码唯一目录：`/home/xckj/suyuan/frontend`。
- 前端构建必须在该目录执行：

  ```bash
  cd /home/xckj/suyuan/frontend
  npm run build:standalone
  ```

- 前端由 `/home/xckj/suyuan/frontend` 中运行在 `5174` 端口的 Vite 进程提供服务。构建完成后无需 Docker 或 Nginx 重载。

- 禁止在项目根目录直接执行 `npm run build`，禁止维护第二套 `/app` 前端 bundle。
- 前端部署后必须确认构建产物包含统一资源接口，并且不再包含旧接口：

  ```bash
  grep -R "resources?presentation_type=document" /home/xckj/suyuan/frontend/dist/assets
  ! grep -R "/office-documents" /home/xckj/suyuan/frontend/dist/assets
  ! grep -R "/visualizations" /home/xckj/suyuan/frontend/dist/assets
  ```
