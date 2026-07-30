# 江西省噪声查询工具修复设计

## 目标

将江西省噪声平台查询能力修复为可注册、可异步执行、可配置并且只在江西项目启用的 LLM 工具。当前交付范围只包括平台实际提供的站点小时值、站点日均值和城市小时值。

## 分支与项目隔离

- 代码保留在长期分支 `project/jiangxi-noise`，江西部署环境检出该分支，其他项目继续使用各自分支或 `main`。
- 新增模块 `jiangxi-noise`，依赖现有 `legacy` 模块。
- 新增项目清单 `projects/jiangxi/project.yaml`，启用 `legacy`、`jiangxi-noise` 和工具 `get_jiangxi_noise_data`。
- 全局工具注册表仅在 `is_project_tool_enabled(context, "jiangxi-noise", "get_jiangxi_noise_data")` 为真时导入并注册该工具。
- 即使误在非江西项目中运行此分支，该工具也不会进入工具注册表。

## 代码结构

### API 客户端

只保留 `backend/app/external_apis/jiangxi_noise_api_client.py` 作为平台访问层。删除 `app/utils` 下的两份重复客户端、`external_apis` 下的同步包装器以及不能作为包模块可靠运行的示例脚本。

客户端保持全异步：认证和数据请求都通过 `httpx.AsyncClient` 完成。客户端允许注入 HTTP transport/client，便于单元测试在不访问真实平台的情况下验证请求参数、认证和重试行为。

公开查询方法为：

- `query_station_hour_data`
- `query_station_day_data`
- `query_city_hour_data`

客户端只公开上述三个查询方法，API 端点表也只声明对应的三个真实端点。

### LLM 工具

`GetJiangxiNoiseDataTool.execute()` 直接 `await` 异步客户端，不再通过同步包装器或 `asyncio.run()`。

工具参数调整为：

- `scope`: `station` 或 `city`。
- `granularity`: `hour` 或 `day`；`scope=city` 时只允许 `hour`。
- `review_status`: `raw` 或 `audited`，分别映射平台的 `dataType=0` 和 `dataType=1`。
- `station_codes`: 站点查询必填，接受非空的字母、数字、下划线和短横线代码。
- `city_names`: 城市查询必填，接受已知江西城市名称或 6 位城市代码。
- `start_time`、`end_time`: ISO 8601 时间。
- `max_results`: 默认 50，范围 1 至 100。

工具拒绝冲突或含糊的调用，不再使用 `locations`、`query_type` 或一参多义的旧 `data_type`。

## 配置与安全

运行时读取以下环境变量：

- `JIANGXI_NOISE_BASE_URL`：平台根地址，必填。
- `JIANGXI_NOISE_SECRET_NAME`：认证所需的 secret name，必填。
- `JIANGXI_NOISE_TIMEOUT_SECONDS`：请求超时，默认 30 秒。

代码和日志不记录 Token 或 Token 前缀。客户端缓存 Token；数据请求收到 401 时清除缓存、重新认证并只重试一次。其他 HTTP 错误转换为不包含 Authorization 头和内部堆栈的稳定错误信息。

平台当前只提供 HTTP 地址时，部署侧必须通过网络访问控制、VPN 或安全反向代理限制 Token 暴露风险；代码不把 HTTP 自动伪装成 HTTPS。

## 参数与时间校验

- `start_time` 必须早于或等于 `end_time`。
- 查询跨度不能超过 30 天。
- 无时区时间按 `Asia/Shanghai` 解释；有时区时间转换为 `Asia/Shanghai` 后再格式化为平台需要的 `YYYY-MM-DD HH:MM:SS`。
- 城市名称必须在江西省城市映射中，6 位代码必须属于该映射；未知值直接返回参数错误，不转发给远端接口。
- 站点代码列表和城市列表去重并保持输入顺序。

## 返回值与错误处理

成功响应包含：

- `success`
- `scope`
- `granularity`
- `review_status`
- `data`
- `count`
- `total_count`
- `truncated`
- 规范化后的 `start_time`、`end_time`

每次最多向 LLM 返回 100 条数据。`total_count > count` 时设置 `truncated=true`，并提供提示要求缩小时间范围或地点范围。平台业务失败、认证失败、超时、HTTP 错误和输入错误分别返回清晰、稳定的错误码与中文消息，不将原始异常详情直接暴露给模型。

## 测试策略

采用 TDD，先编写失败测试再修改生产代码。测试覆盖：

1. 正常包路径可以导入工具，不依赖修改 `sys.path`。
2. 异步工具直接等待异步客户端，不触发嵌套 `asyncio.run()`。
3. 站点小时、站点日均、城市小时请求路径和参数符合接口文档。
4. Schema 和客户端端点表只包含三个真实查询能力。
5. `raw/audited` 正确映射 `dataType=0/1`。
6. 时间顺序、30 天范围、时区、城市和站点代码校验。
7. Token 不存在时认证，401 时仅刷新并重试一次。
8. 日志和工具错误响应不泄露 Token。
9. `default` 项目不注册工具，`jiangxi` 项目注册工具。
10. 结果截断标记和返回数量上限正确。

定向测试使用项目指定的 Python 3.11 环境执行，不把真实平台可用性作为单元测试前置条件。完成后额外运行一次三个已确认端点的最小只读冒烟测试；如果外部平台不可达，单元测试结果与外部连通性结果分开报告。

## 文档调整

更新 `NOISE_API_DOCUMENTATION.md`：

- 修正 `360400`、`360500`、`360600` 对应的九江、新余、鹰潭。
- 将已验证能力明确为站点小时、站点日均和城市小时。
- 文档只列出平台实际提供并已经验证的三个查询能力。
- 更新异步客户端和 LLM 工具示例，删除同步包装器、自动分页、站点名称模糊查询等与实现不符的描述。

## 非目标

- 不猜测、扫描或逆向查找平台未提供的接口。
- 不实现区县接口。
- 不实现文件导出功能。
- 不修改与江西噪声工具无关的上传、前端或其他项目代码。
