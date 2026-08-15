项目的运行环境是conda activate /root/miniconda3/envs/backend_py311

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

- 正式前端静态资源唯一来源：`/home/xckj/suyuan/frontend/dist`，由 `suyuan-nginx` 提供服务。
- 构建完成后重新加载 Nginx：

  ```bash
  docker exec suyuan-nginx nginx -s reload
  ```

- 禁止在项目根目录直接执行 `npm run build`，禁止维护第二套 `/app` 前端 bundle。
- 前端部署后必须确认构建产物包含统一资源接口，并且不再包含旧接口：

  ```bash
  grep -R "resources?presentation_type=document" /home/xckj/suyuan/frontend/dist/assets
  ! grep -R "/office-documents" /home/xckj/suyuan/frontend/dist/assets
  ! grep -R "/visualizations" /home/xckj/suyuan/frontend/dist/assets
  ```

## 分支与更新归属规范

- 共享层改动一律提交到 `main`：`backend/app`（除 `tools/jiangsu/`、`fetchers/jiangsu_*`、`fetchers/weather/jiangsu_*`）、`backend/tests`（除 jiangsu 专用测试）、`backend/config`、`frontend/src` 公共组件与配置、CI、`.gitignore`、`AGENTS.md`。
- 项目改动提交到对应 `project/*` 分支：`backend/app/tools/jiangsu/**`、`fetchers/jiangsu_*`、`backend/app/db/repositories/jiangsu_*`、`backend/app/db/models` 中的项目模型、`projects/jiangsu-ops/**`、`backend/tests/test_jiangsu_*`、`backend/tests/project_config/test_jiangsu_*`、项目专属前端（如 StationhouseInspectionPanel）。
- 判定准则：路径含 jiangsu/项目名、或内容依赖 `projects/*/project.yaml`、`settings.project_id` 分支逻辑的，归项目分支；其余归 main。混合文件（如 `tools/__init__.py`、`tool_registry.py`）先在 main 提交共享部分，项目分支合并后再叠加项目部分。
- 工作流程：先在 main 提交共享改动 → 项目分支 `git merge main` → 再提交项目改动。禁止在项目分支直接修改共享文件而不回合 main。
- 项目分支每天开工先 `git merge main`；共享文件的改动永远以 main 为准。
- 禁止提交：`backend/.env.*`（模板除外）、`frontend/dist-*`、`backend/backend_data_registry*`、`suncere*/`（见 .gitignore）。
