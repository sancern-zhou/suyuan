# 许昌市排污许可证临时采集脚本

脚本不会注册到 Fetcher 调度器。所有命令在 `backend` 目录、项目 Python 3.11 Conda 环境中执行。

首次创建数据表：

```bash
conda run -p /root/miniconda3/envs/backend_py311 \
  python -m app.alembic.versions.add_xuchang_permit_license_crawler
```

分批抓取列表，例如先抓 2 页：

```bash
conda run -p /root/miniconda3/envs/backend_py311 \
  python -m app.fetchers.emission.permit_license_crawler.cli \
  --phase list --start-page 1 --max-pages 2 --resume
```

从数据库中的未完成记录选择 3 家，抓取详情和附件：

```bash
conda run -p /root/miniconda3/envs/backend_py311 \
  python -m app.fetchers.emission.permit_license_crawler.cli \
  --phase detail --max-licenses 3 --resume
```

列表和详情阶段都必须显式提供数量上限。列表阶段使用 `--resume` 时，会从数据库中已有的最大列表页码之后继续。默认请求间隔为随机 2–5 秒，始终单并发。遇到 403、429 或验证码页面时脚本停止，稍后使用相同命令和 `--resume` 继续。

默认文件目录：

`backend/backend_data_registry/permit_licenses/河南省/许昌市/`

结构化数据位于以下 PostgreSQL 表：

- `permit_crawl_runs`
- `permit_licenses`
- `permit_license_versions`
- `permit_pollution_details`
- `permit_documents`
- `permit_crawl_failures`
