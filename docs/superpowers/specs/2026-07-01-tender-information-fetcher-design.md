# 招投标信息抓取 Fetcher 设计

## 背景

需要将 `Bidding-Information-Crawling` 项目整合为本项目的后台数据抓取能力。目标是每天定时触发招投标信息抓取、语义筛选、详情页清洗和结构化存储，并把结果写入本项目已有 SQL Server 数据库。

本项目已经具备 `DataFetcher`、`FetcherScheduler`、APScheduler 生命周期管理、SQL Server 配置和手动触发接口。导入项目已经具备千里马候选抓取、LLM 初筛、详情抓取、结构化抽取、二次复核和 SQLite 存储流程。因此集成重点是保留导入项目核心能力，替换存储层和运行入口。

## 目标

- 新增一个标准后台抓取器 `tender_information_fetcher`。
- 每天北京时间 06:30 自动运行。
- 默认抓取运行日前一天发布的公告。
- 默认关键词为：`生态环境局`、`环境监测中心`、`生态环境厅`、`环境监测站`。
- 默认公告类型为：招标公告和中标公告。
- 对候选公告去重、筛选、详情抓取、清洗、结构化抽取和复核。
- 将候选、最终公告和运行摘要写入 SQL Server。
- 支持通过现有 fetcher API 手动触发。

## 非目标

- 不重写千里马爬虫和 LLM 抽取逻辑。
- 不把该任务接入 Agent 自然语言定时任务链路。
- 不新增前端管理页面。
- 不在设计阶段调整本项目已有 SQL Server 账号配置。

## 架构

新增模块分为两层：

- `backend/app/services/tenders/`：招投标业务模块。迁入并适配导入项目的 `client`、`pipeline`、`extractor`、`filters`、`llm`、`models`，并新增 SQL Server repository。
- `backend/app/fetchers/tenders/`：本项目 Fetcher 外壳。负责默认配置、目标日期计算、运行日志、调用业务模块。

`TenderInformationFetcher` 继承 `DataFetcher`：

- `name`: `tender_information_fetcher`
- `description`: `招投标信息每日抓取、筛选和结构化入库`
- `schedule`: `30 6 * * *`
- `version`: `1.0.0`

Fetcher 注册到 `backend/app/services/lifecycle_manager.py` 的 `initialize_fetchers()`，并同步加入 `backend/app/fetchers/__init__.py` 的 `create_scheduler()`。现有 `/api/fetchers/trigger/{fetcher_name}` 可用于手动触发。

## 数据流

每天 06:30 运行时：

1. 计算 `target_date = today - 1 day`。
2. 遍历默认关键词和公告类型。
3. 调用千里马搜索接口获取候选公告。
4. 将候选公告写入 `tender_candidates`，使用 `url` 唯一键防重复。
5. 对新候选执行 LLM 初筛。
6. 对通过初筛的候选抓取详情页。
7. 清洗详情正文并执行结构化字段抽取。
8. 使用详情正文进行二次复核。
9. 将最终有效公告 upsert 到 `tender_notices`。
10. 将本次运行统计和错误摘要写入 `tender_fetch_runs`。

单个关键词、公告类型或公告详情失败不终止整次任务。失败信息进入运行摘要，后续运行可以继续补抓。

## SQL Server 表设计

### tender_candidates

保存候选公告和筛选状态。

关键字段：

- `id` bigint identity primary key
- `title` nvarchar(500) not null
- `url` nvarchar(1000) not null unique
- `notice_type` nvarchar(50) not null
- `keyword` nvarchar(100) null
- `source` nvarchar(100) not null default `qianlima`
- `publish_date` date null
- `raw_list_text` nvarchar(max) null
- `metadata_json` nvarchar(max) not null default `{}`
- `filter_status` nvarchar(30) not null default `pending`
- `filter_reason` nvarchar(max) null
- `filter_confidence` float null
- `decision_source` nvarchar(50) null
- `created_at` datetime2 not null default sysdatetime()
- `updated_at` datetime2 not null default sysdatetime()

索引：

- unique index on `url`
- index on `filter_status`
- index on `publish_date`
- index on `keyword`

### tender_notices

保存最终有效公告详情和结构化结果。

关键字段：

- `id` bigint identity primary key
- `title` nvarchar(500) not null
- `url` nvarchar(1000) not null unique
- `notice_type` nvarchar(50) not null
- `project_name` nvarchar(500) null
- `purchaser` nvarchar(300) null
- `agency` nvarchar(300) null
- `winning_bidder` nvarchar(300) null
- `budget_amount` nvarchar(100) null
- `budget_amount_wan_yuan` decimal(18,4) null
- `winning_amount` nvarchar(100) null
- `winning_amount_wan_yuan` decimal(18,4) null
- `province` nvarchar(100) null
- `city` nvarchar(100) null
- `publish_date` date null
- `bid_open_date` nvarchar(100) null
- `deadline` nvarchar(100) null
- `industry_category` nvarchar(200) null
- `environment_relevance` bit not null default 0
- `filter_reason` nvarchar(max) null
- `filter_confidence` float null
- `raw_content` nvarchar(max) not null
- `summary` nvarchar(max) null
- `key_requirements_json` nvarchar(max) not null default `[]`
- `attachment_urls_json` nvarchar(max) not null default `[]`
- `structured_json` nvarchar(max) not null default `{}`
- `created_at` datetime2 not null default sysdatetime()
- `updated_at` datetime2 not null default sysdatetime()

索引：

- unique index on `url`
- index on `publish_date`
- index on `purchaser`
- index on `province, city`

### tender_fetch_runs

保存每次抓取运行摘要。

关键字段：

- `id` bigint identity primary key
- `target_date` date not null
- `keywords_json` nvarchar(max) not null
- `notice_types_json` nvarchar(max) not null
- `total_candidates` int not null default 0
- `duplicate_candidates` int not null default 0
- `filtered_out` int not null default 0
- `detail_fetch_failures` int not null default 0
- `saved_notices` int not null default 0
- `errors_json` nvarchar(max) not null default `[]`
- `status` nvarchar(30) not null
- `started_at` datetime2 not null default sysdatetime()
- `finished_at` datetime2 null

索引：

- index on `target_date`
- index on `status`

## 配置

新增 settings/env 配置，提供默认值：

- `tender_fetcher_enabled=true`
- `tender_fetcher_schedule=30 6 * * *`
- `tender_keywords=生态环境局,环境监测中心,生态环境厅,环境监测站`
- `tender_notice_types=tender,winning_bid`
- `tender_max_pages=0`
- `qianlima_storage_state=backend_data_registry/tenders/qianlima_storage_state.json`
- `qianlima_username` 可选
- `qianlima_password` 可选
- `tender_llm_api_key` 可选，未设置时继续兼容 `OPENAI_API_KEY`、`DASHSCOPE_API_KEY`、`QWEN_API_KEY`
- `tender_llm_base_url` 可选
- `tender_llm_model` 可选

`tender_max_pages=0` 表示按目标日期尽量翻页，直到目标日期数据结束或达到千里马客户端内部完整翻页上限。

## 错误处理和幂等

- `url` 是候选和公告的幂等键。
- 候选重复时跳过，不重复触发详情抓取。
- SQL Server 写入使用 upsert 或等价的 `MERGE`/事务逻辑。
- 单条公告失败记录错误并继续处理下一条。
- `FetcherScheduler` 已配置 `max_instances=1`，避免同一 Fetcher 并发运行。
- 详情页失败的候选保留状态，后续可通过补跑逻辑继续处理。
- 运行摘要记录整体状态：`success`、`partial_failed` 或 `failed`。

## 测试策略

单元测试不访问真实千里马或真实 LLM，避免常规测试受账号、网络和额度影响。真实千里马和真实 LLM 覆盖通过显式集成测试提供：设置 `RUN_TENDER_REAL_INTEGRATION=1`，并配置 `TENDER_LLM_API_KEY`、`OPENAI_API_KEY`、`DASHSCOPE_API_KEY` 或 `QWEN_API_KEY` 后运行集成测试。

需要覆盖：

- SQL Server repository：使用 mock connection/cursor 验证候选插入、决策更新、公告 upsert 和运行摘要写入。
- Pipeline：使用 fake client、fake llm、fake repository 验证候选去重、筛选、详情抓取和保存路径。
- Fetcher：验证默认 schedule、默认关键词、默认公告类型和默认目标日期为昨天。
- 配置解析：验证逗号分隔关键词和公告类型解析。
- 迁移脚本：验证 SQL 文件包含三张表和唯一索引。
- 真实集成测试：访问真实千里马搜索和真实 LLM，默认跳过，只有显式设置环境变量时运行。

## 实施顺序

1. 迁入招投标核心模块到 `backend/app/services/tenders/`。
2. 新增 SQL Server repository 和建表迁移脚本。
3. 新增 `TenderInformationFetcher`。
4. 注册 Fetcher 到现有生命周期和 scheduler factory。
5. 补充配置项。
6. 增加单元测试和迁移脚本测试。
7. 在 conda 环境中运行相关 pytest。

## 风险

- 千里马接口和登录状态可能变化，需要保留浏览器 fallback 和 storage state。
- LLM 输出 JSON 可能不稳定，需要复用已有重试和 JSON 清洗逻辑。
- SQL Server 的 `MERGE` 在并发场景有锁风险，第一版可以优先使用事务内 `UPDATE` 后判断 rowcount 再 `INSERT` 的方式。
- 真实外网抓取速度受目标网站限制，需要保留请求间隔和失败重试配置。
