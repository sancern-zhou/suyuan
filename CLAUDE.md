# 项目协作说明

项目协作规范已统一收敛到 [AGENTS.md](AGENTS.md)，本文件不再单独维护规则副本（历史副本曾硬编码过期的 `/home/xckj/suyuan` 路径，与实际工作树不符）。

请直接阅读 AGENTS.md，重点关注：

- Agent 文件系统路径规范（以 git 仓库根为基准，使用 `backend/app/utils/path_config.py`）
- 构建与部署规范
- 后台任务与事件循环隔离规范
- 分支与更新归属规范
