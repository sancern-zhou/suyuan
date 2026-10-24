# guangdong-cube — 广东运维语义层（Cube Core）

## 这是什么

指标口径的**唯一定义与对外供数 API**。上游是 dbt 建好的 `guangdong_mart` 宽表，
下游是智能体/前端——它们不再各自拼 SQL 算指标，而是传"指标+维度+时间范围"点数，
口径锁死在 `schema/*.js` 里，同一问题永远同一个数。

数据链路：SQL Server 源库（Operation_SC_GD）→ (sync_table.py) → guangdong_ods
→ (dbt) → guangdong_mart → **(本项目) → REST API (127.0.0.1:4611)**

与江苏语义层（127.0.0.1:4610）同机共存，端口错开。

## 已建模的指标（WorkOrder cube，全类型工单口径）

- **工单量/完成率**：count（含作废单，结论须声明口径）、finishedCount、finishRate
- **超期**：overdueEvaluable（分母=计划完成时间非空单）、overdueCount、overdueRate
  —— 与江苏不同，广东工单有计划完成时间，超期可评估
- **响应（仅故障单可评估）**：responseEvaluable、responseWithin2hCount/Rate、avgResponseMinutes
  （到站 = 首个 FaultProcess 步骤开始）
- **重复故障（仅故障单口径）**：faultCount（Fault/SupFault）、repeatFaultCount/Rate
- **附件**：hasAttachmentCount、attachmentRate（仅索引，本体在源系统）
- **时长/费用**：avgProcessMinutes、avgRepairMinutes、avgNodeCount、avgExpense

## 部署形态

- 常驻计划任务 `SuyuanGuangdong-Cube`（开机自启），监听 127.0.0.1:4611（env `PORT` 可覆盖）
- production 模式强制 JWT（无 token 返回 403）；必须设 `CUBEJS_CACHE_AND_QUEUE_DRIVER=memory`
- 连库账号 agent_reader（只读、仅 guangdong_mart、statement_timeout 15s）——与智能体
  SQL 工具同权限，语义层不引入任何新数据库权限
- 版本：@cubejs-backend/server 0.35.x（纯 JS 编译器线）

## 查询方法

```cmd
cd /d <runtime>\cube
for /f %t in ('node gen-token.js') do set TOKEN=%t
curl -X POST http://127.0.0.1:4611/cubejs-api/v1/load ^
  -H "Authorization: %TOKEN%" -H "Content-Type: application/json" ^
  -d "{\"query\":{\"measures\":[\"WorkOrder.responseWithin2hRate\",\"WorkOrder.count\"],\"dimensions\":[\"WorkOrder.stationName\"]}}"
```

后端 `guangdong_query_metrics` 工具经 `CUBE_API_URL`/`CUBE_API_SECRET` 调同一服务。

## 修改口径的正确姿势

1. 改 `../sync/datasets/mart_work_order_analysis.yaml`（契约）与 `../dbt/models/*.sql`（实现）
2. 同步改本目录 `schema/*.js` 与工具 CATALOG（四方口径必须一致）
3. `python ../semantic/validate_registry.py` 通过后提交
4. 重启 Cube 服务（dbt 改动随下次调度生效）

## 坑（重装时必读，同江苏）

- **node_modules 用 `--ignore-scripts` 装**：cubestore/native 的 postinstall 会直连
  GitHub 下载卡死；native 二进制需手动放置
  `node_modules/@cubejs-backend/native/native/index.node`（来源 cube.js releases
  `native-win32-x64-unknown-fallback.tar.gz`），**重装依赖后必须重新解压到原位**。
- 1.7.x 线在本机不可用：schema 编译强依赖 native，且 CLI 要 Node 22。
- production 模式默认队列驱动指向 Cube Store → 必须设 `CUBEJS_CACHE_AND_QUEUE_DRIVER=memory`。
- FileRepository 的路径参数必须相对（内部与 process.cwd() 拼接）。
- .cmd 文件保持纯 ASCII：GBK 代码页控制台下 UTF-8 中文注释会破坏执行。
