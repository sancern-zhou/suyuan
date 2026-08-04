项目的运行环境是conda activate /root/miniconda3/envs/backend_py311

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
