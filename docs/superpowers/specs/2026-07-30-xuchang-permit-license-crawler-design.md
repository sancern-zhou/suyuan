# 许昌市排污许可证一次性采集设计

## 目标与范围

实现一个独立、低速、可断点续跑的命令行采集程序，从全国排污许可证管理信息平台公开页面分批采集河南省许昌市的许可证信息。程序先保存列表数据，再按许可证逐条获取详情和公开附件，最终将结构化数据写入现有 PostgreSQL，将原始文件写入数据登记目录。

本期采集以下列表字段：

- 省/直辖市
- 地市
- 许可证编号
- 单位名称
- 行业类别
- 有效期限
- 发证日期
- 管理类别

本期采集以下详情字段：

- 主要污染物类别
- 大气主要污染物种类
- 大气污染物排放规律
- 大气污染物排放执行标准
- 废水主要污染物种类
- 废水污染物排放规律
- 废水污染物排放执行标准
- 排污权使用和交易信息

同时保存许可证版本沿革、排污许可证正本、排污许可证副本、原始详情 HTML 和文件校验信息。

本程序位于数据管理的抓取代码目录，但本期不注册到 Fetcher 调度器，不新增 API，不修改前端，也不配置定时任务。它只通过显式 CLI 命令运行。

## 已验证的平台行为

许可信息列表使用服务端 HTML 分页。河南省代码为 `410000000000`，许昌市代码为 `411000000000`。设计调研时，许昌市查询结果约为 134 页、约 1,340 条记录；实际运行必须以页面返回的总页数和记录数为准。

详情页包含许可证版本表和目标污染字段。版本表可能同时出现“申领”“变更”“延续”“重新申请”“注销”等业务类型，因此“重新申请”不等同于无效许可证，必须结合最新版本和有效期判断当前状态。

平台的“排污许可证副本”链接当前返回 HTML 查看页，而非 PDF 二进制。查看页提供 `imgCount`、`pkid` 和 `dataid`，并按页加载图片。不同记录未来可能直接返回 PDF，因此下载器必须基于响应内容类型和文件签名选择处理方式，不能只依赖 URL 后缀。

## 总体架构

采集分为两个可独立运行的阶段：

1. **列表阶段**：低速遍历列表页，解析并幂等写入许可证主表，记录详情 URL 和平台 `dataid`。
2. **详情阶段**：从数据库领取未完成的许可证，获取详情和版本沿革，然后下载正本、副本及原始 HTML。

每个阶段都接受上限参数并记录游标。进程正常退出、网络失败或平台阻断后，下一次运行从数据库状态继续，不重新请求已经校验完成的页面或文件。

数据流为：

```text
公开列表页
  -> 许可证主表
  -> 详情页
       -> 许可证版本表
       -> 污染详情表
       -> 原始详情 HTML
       -> 正本文件
       -> 副本 PDF，或分页图片后合并 PDF

所有步骤
  -> 运行记录
  -> 失败记录与下次重试时间
```

## 代码位置与模块边界

新代码放置于 `backend/app/fetchers/emission/permit_license_crawler/`：

- `cli.py`：解析命令行参数，编排列表、详情和附件阶段，输出运行汇总。
- `client.py`：维护 HTTP 会话、固定单并发、请求间隔、重试、冷却和挑战页检测。
- `list_parser.py`：解析列表行、详情链接、当前页和总页数。
- `detail_parser.py`：解析目标污染字段、企业补充信息和版本沿革，并计算当前状态。
- `document_downloader.py`：识别并下载正本、副本 PDF 或副本分页图片。
- `pdf_builder.py`：将副本分页图片按原顺序合并为 PDF。
- `models.py`：本采集功能的 SQLAlchemy 表模型。
- `repository.py`：运行状态、许可证、版本、污染详情、文档和失败记录的幂等读写。
- `storage.py`：安全路径生成、原子写入、文件类型检查和 SHA-256 计算。
- `fixtures/`：测试使用的最小化列表、详情、副本查看页和挑战页 HTML。

现有 `backend/app/fetchers/emission/national_inventory_fetcher.py` 是未完成占位实现。本期不扩展、不删除它，也不从新 CLI 导入它。`backend/app/fetchers/__init__.py` 保持不变，确保新程序不会出现在数据管理页面或调度器中。

数据库结构通过新的 Alembic 迁移创建，不由 CLI 临时建表。

## 数据模型

### `permit_crawl_runs`

记录每次 CLI 运行：

- `id`
- `phase`：`list` 或 `detail`
- `province_code`、`city_code`
- `start_page`、`max_pages`、`max_licenses`
- `status`：`running`、`completed`、`stopped`、`blocked`、`failed`
- `started_at`、`finished_at`
- `success_count`、`failure_count`、`skipped_count`
- `stop_reason`

### `permit_licenses`

每个公开详情 `dataid` 保存一条许可证记录：

- `id`
- `source_data_id`，唯一
- `province_code`、`province_name`
- `city_code`、`city_name`
- `permit_number`
- `enterprise_name`
- `industry_category`
- `valid_from`、`valid_to`
- `issue_date`
- `management_category`
- `current_status`：`valid`、`expired`、`cancelled`、`not_yet_effective`、`unknown`
- `latest_business_type`
- `detail_url`
- `list_page_no`
- `detail_status`、`documents_status`
- `first_seen_at`、`last_seen_at`、`updated_at`

`source_data_id` 是采集幂等键。许可证完整编号用于识别许可证；能够可靠提取时，许可证编号前 18 位另存为统一社会信用代码，用于企业级关联，但不作为唯一键。单位名称不能作为去重键。

### `permit_license_versions`

保存详情页版本沿革：

- `license_id`
- `version_no`
- `permit_number`
- `business_type`
- `completion_date`
- `valid_from`、`valid_to`
- `source_order`

以 `license_id + version_no + source_order` 幂等更新，以兼容版本号缺失或页面出现特殊业务行。

### `permit_pollution_details`

与许可证一对一，保存用户要求的八个详情字段以及 `parsed_at`、`source_html_sha256`。字段使用可空文本，解析规则保留三种不同状态：页面没有该字段为 `NULL`，存在但空白为空字符串，页面明确给出 `/` 时保存 `/`。

### `permit_documents`

记录每个下载或生成文件：

- `license_id`
- `document_type`：`detail_html`、`original`、`copy_page`、`copy_merged_pdf`
- `page_no`
- `source_url`
- `relative_path`
- `mime_type`
- `size_bytes`
- `sha256`
- `status`：`pending`、`downloading`、`complete`、`failed`
- `downloaded_at`

同一许可证、文件类型和页码唯一。只在文件完成原子写入、文件签名与大小检查通过并计算校验值后标记为 `complete`。

### `permit_crawl_failures`

记录许可证、阶段、URL、错误分类、重试次数、错误摘要、首次/最后发生时间和 `next_retry_at`。不保存 Cookie、完整请求头或其他会话敏感数据。

## 当前状态判定

状态判定以采集时点和详情页版本历史为依据：

1. 按可解析的版本号排序；版本号缺失时，以办结日期和页面顺序辅助排序。
2. 找出最新的实质业务记录。
3. 最新记录为“注销”且其后没有更新的有效业务版本时，状态为 `cancelled`。
4. 当前有效期开始日期晚于采集日期时，状态为 `not_yet_effective`。
5. 当前有效期结束日期早于采集日期时，状态为 `expired`。
6. 当前日期位于有效期内且未被后续注销时，状态为 `valid`。
7. 缺少必要日期或业务信息、无法可靠判断时，状态为 `unknown`，不进行猜测。

“重新申请”“延续”“变更”记录保存为 `latest_business_type`，不直接映射成无效状态。

## 文件存储

根目录为：

`backend/backend_data_registry/permit_licenses/河南省/许昌市/`

每条许可证使用安全化后的许可证编号作为目录；若编号缺失，则使用 `dataid`：

```text
<许可证编号>/
  detail.html
  original/
    permit_original.<检测到的扩展名>
  copy/
    pages/
      001.png
      002.png
    permit_copy.pdf
```

数据库只保存相对根目录的路径。所有文件先写入同目录临时文件，校验后原子替换目标文件。路径组件剔除目录分隔符和控制字符，程序拒绝任何逃逸存储根目录的路径。

若副本响应是 PDF，则直接保存平台原始 PDF，并将它登记为 `copy_merged_pdf`；若响应是 HTML 查看页，则保存所有原始分页图片，再生成 `permit_copy.pdf`。合并 PDF 不替代分页图片。已完成且校验值匹配的文件不会重复下载。

## 低速访问与阻断处理

程序始终单并发。默认每个网络请求后随机等待 2 至 5 秒，包括副本分页图片请求。普通连接错误、超时和 5xx 使用指数退避，单个请求最多重试 3 次。

以下情况视为平台阻断或响应异常：

- HTTP 403 或 429；
- 页面包含验证码、访问过于频繁等挑战特征；
- 预期 HTML、PDF 或图片却返回登录页、首页或未知内容；
- 连续页面结构解析失败。

发生阻断后停止发出新请求，记录游标和失败原因，进入长冷却。一次运行只进行有限次数的新会话恢复；仍失败则以 `blocked` 安全退出。后续可以重新运行相同命令继续。程序不使用代理池、不破解验证码、不伪造大量身份，也不承诺平台触发验证后能在同一次运行中完成。

## CLI 与分批运行

CLI 在项目指定 Conda 环境中运行：

```bash
conda run -p /root/miniconda3/envs/backend_py311 \
  python -m app.fetchers.emission.permit_license_crawler.cli \
  --phase list --max-pages 2
```

详情试跑：

```bash
conda run -p /root/miniconda3/envs/backend_py311 \
  python -m app.fetchers.emission.permit_license_crawler.cli \
  --phase detail --max-licenses 3 --resume
```

CLI 支持至少以下参数：

- `--phase list|detail`
- `--start-page`
- `--max-pages`
- `--max-licenses`
- `--resume`
- `--min-delay-seconds`、`--max-delay-seconds`
- `--storage-root`

列表阶段必须显式提供 `--max-pages`，详情阶段必须显式提供 `--max-licenses`，防止误操作启动全量抓取。默认区域固定为河南省许昌市；本期不提供全国或任意地区批量模式。

## 首次试跑与验收

首次真实试跑严格限制为列表前 2 页及其中 3 条许可证。试跑不会自动扩大范围。

列表阶段验收：

- 请求页数不超过 2 页；
- 数据库记录的省市均为河南省许昌市；
- 每条记录包含 `dataid`、详情 URL 和列表页码；
- 重复运行不会产生重复许可证记录；
- 解析到的总页数和平台显示一致，实际记录数写入运行汇总。

详情阶段验收：

- 最多领取 3 条未完成许可证；
- 八个污染字段按原始语义保存；
- 版本历史和当前状态可追溯；
- 正本文件类型、大小和 SHA-256 已登记；
- 副本分页完整，页码连续，合并 PDF 页数与原始分页数相同；
- 中途终止后再次运行只补齐缺失步骤；
- 挑战页不会被错误保存为许可证文件或成功详情。

## 测试策略

自动化测试不访问真实平台。测试使用最小化固件覆盖：

- 单页和多页列表解析；
- 许昌区域过滤与总页数解析；
- 八个详情字段，包括空白、`/` 和缺失；
- 申领、注销后重新申请、过期和尚未生效等状态判定；
- PDF、HTML 副本查看页和错误内容类型识别；
- 分页图片路径排序与 PDF 页数；
- 原子文件写入、SHA-256 和路径逃逸防护；
- 数据库幂等写入、断点领取和失败重试状态；
- 403、429、验证码页和首页跳转检测；
- CLI 上限参数强制校验。

真实站点验证只通过明确的限量试跑命令执行，并在结果汇总后由开发者决定是否启动下一批。

## 非目标

本期不包含：

- 注册 Fetcher 或定时调度；
- 数据管理前端页面或 API；
- 自动验证码识别或规避平台访问控制；
- 代理池、并发抓取或全国范围扩展；
- 将附件二进制写入 PostgreSQL；
- 自动执行超过首次 2 页、3 条许可证的扩大采集。
