# jiangsu-cube — 江苏运维语义层（Cube Core）

## 这是什么

指标口径的**唯一定义与对外供数 API**。上游是 dbt 建好的 `jiangsu_mart` 宽表，
下游是智能体/前端——它们不再各自拼 SQL 算指标，而是传"指标+维度+时间范围"点数，
口径锁死在 `schema/*.js` 里，同一问题永远同一个数。

数据链路：SQL Server 原库 → (sync_table.py) → jiangsu_ods → (dbt) → jiangsu_mart
→ **(本项目) → REST API (127.0.0.1:4610)**

## 部署形态

- 常驻计划任务 `SuyuanJiangsu-Cube`（开机自启，PT0S 不限时），启动脚本
  `E:\Tools\suyuan-jiangsu\start-cube.cmd`，日志 `logs\cube.log`
- 只监听 127.0.0.1（消费方都在本机）；production 模式强制 JWT（无 token 返回 403）
- 连库账号 agent_reader（只读、仅 jiangsu_mart、statement_timeout 15s）——与智能体
  SQL 工具同权限，语义层不引入任何新数据库权限
- 版本：@cubejs-backend/server 0.35.81（Node 20 可跑的稳定线）

## 已建模的指标（口径与 datasets/*.yaml、dbt 模型一致）

- **WorkOrder**：工单量、超期率、2h响应率（分母=可评估单）、4h恢复率（分母=可评估单）、
  30天重复故障率、平均响应/处理/修复时长
- **AlarmEvent**：告警量、未处理率、告警转工单率、平均持续/处理时长
- **QcExecution**：质控执行量、合格率
- **Inspection**：任务量、完成率、超期率、转工单率

获取率/有效率等平台口径指标不在本地（原始监测数据未同步，批次3 待启动），故未建模。

## 查询方法

```cmd
cd /d E:\Tools\suyuan-jiangsu\cube
for /f %t in ('node gen-token.js') do set TOKEN=%t
curl -X POST http://127.0.0.1:4610/cubejs-api/v1/load ^
  -H "Authorization: %TOKEN%" -H "Content-Type: application/json" ^
  -d "{\"query\":{\"measures\":[\"WorkOrder.overdueRate\"],\"dimensions\":[\"WorkOrder.cityName\"]}}"
```

PowerShell/Python 消费同理：先 `POST /cubejs-api/v1/login`（body `{"token": "<API_SECRET>"}`）
拿临时 token，或用 gen-token.js 的 HS256 方式签长期 token。API_SECRET 在 start-cube.cmd。

## 修改口径的正确姿势

1. 改 `sync/datasets/*.yaml`（契约）与 `dbt/models/*.sql`（实现）
2. 同步改本目录 `schema/*.js`（三者口径必须一致；盘点底稿见 `../指标口径盘点.md`）
3. 重启 Cube 任务：`schtasks /end /tn SuyuanJiangsu-Cube && schtasks /run /tn SuyuanJiangsu-Cube`

## 坑（重装时必读）

- **node_modules 是 `--ignore-scripts` 装的**：cubestore/native 的 postinstall 会被
  GitHub 直连下载卡死（本机 GitHub 需代理）。native 二进制已手动放置：
  `node_modules/@cubejs-backend/native/native/index.node`（来源
  `ghfast.top/https://github.com/cube-js/cube.js/releases/download/v0.35.81/native-win32-x64-unknown-fallback.tar.gz`）。
  **重装依赖后必须重新解压该文件到原位，否则服务启动即崩。**
- 1.7.x 线在本机不可用：schema 编译强依赖 native（Windows 无对应资产），且 CLI 要 Node 22
- production 模式默认队列驱动指向 Cube Store → 必须设 `CUBEJS_CACHE_AND_QUEUE_DRIVER=memory`
- FileRepository 的路径参数必须相对（内部与 process.cwd() 拼接）
- .cmd 文件保持纯 ASCII：UTF-8 中文注释会让 GBK 代码页下的 cd 失效
- 360 需把 SuyuanJiangsu-Cube 加入白名单（历史上有删任务的前科）
