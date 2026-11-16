# suyuan 监控自治体系改造总结

> 2026-11-14 ~ 11-15 · main 分支 · 15 个提交（已推送 origin/main）
> 改造目标：后台故障能及时发现、能自行处置、能被运维随时追问

---

## 一、这次更新做了什么

### 1. 问题起点

suyuan 后台运行出现故障（数据抓取失败、定时任务异常、LLM 调用失败）时
长期无人察觉——留痕都在，但没有东西去看、去归因、去通知人。

### 2. 体系设计（五层）

```
┌─ 发现 ────────────────────────────────────────────────────┐
│ L0 宿主机探针    进程宕机/端口不可达        1 分钟   带外 webhook │
│ 实时事件路径     失败落库→冷却去重→诊断     分钟级   应用内       │
│ 小时巡检         每小时 :05 全量回看        ≤1 小时  兜底         │
│ 主动质询         运维白名单对话查询         按需     助手会话      │
│ 长任务派发       spawn 后台执行+落库查询    不阻塞   PostgreSQL   │
└──────────────────────────────────────────────────────────┘
┌─ 处置 ────────────────────────────────────────────────────┐
│ 任务级自愈   retry_scheduled_task / trigger_fetcher（硬缰绳） │
│ 分级修复     P1 定位→修复→测试→推送待人重启                     │
│             P0 同上 + 自主重启（规则判级+健康核实+失败回滚）     │
└──────────────────────────────────────────────────────────┘
```

### 3. 提交清单（15 个，均已推送）

| 提交 | 内容 |
|---|---|
| `6bc685fd` | A1 巡检种子任务（Watchdog 小时全量回看） |
| `25ea422a` | A2 L0 宿主机探针 + 带外告警（宕机/恢复/冷却重报） |
| `c88e256c` | A3 失败点事件发射 + 实时诊断任务（分钟级响应） |
| `e2ad6e0c` | A4a 任务级自愈工具（重跑/触发，六层硬缰绳） |
| `4207d295` | A4b Watchdog 对话质询白名单（运维直接问助手） |
| `205b3c30` | A4c Web 助手后台长任务派发闭环（spawn/wait_task） |
| `a02cb38f` | B1 spawn 任务状态切 PostgreSQL（跨进程可见） |
| `ef14fc67` | 三个共享层潜在 bug 修复（全新部署才暴露） |
| `155ef0a4` | 本地开发部署编排 deploy/local（Windows Docker） |
| `e3d6315e` | 本地 nginx 入口（前端白屏修复） |
| `86735074` | B 阶段分级自治修复（P0 判级/AI 决断重启/自动回滚） |
| `e0a6b8a8` | 维护守护进程持久化（缰绳落盘+自启+systemd） |

### 4. 安全边界（判级权绝不交给模型）

- **P0 判级是确定性代码**（`severity.py`）：抓取器瘫痪 ≥5 且 ≥80%、
  任务失败风暴 ≥5、会话错误风暴 ≥20——`restart_service` 放行前用
  **实时数据重判**，prompt 注入或模型幻觉无法绕过
- **双层缰绳**：应用侧 Redis（冷却/日限）+ 守护进程侧独立计数（落盘，
  重启不重置）
- **源码修复三条件**：任务 tag `source-repair` + 白名单目录 + git 快照
  就绪；`config/.env/deploy` 敏感面第二道硬边界永不可写
- **失败自动回滚**：重启后健康核实不过 → 自动 checkout 回滚快照再重启

### 5. 验证情况

- 全量回归 **277 passed / 0 failed**（含 21 例新增分级/门禁/授权测试）
- 本机 Docker 生产级验收 7 项全过（真实停启容器、真实 fetcher 失败触发
  事件链、L0 状态机四场景、快照-修改-回滚精确恢复、web 重启 healthy）
- **真实故障处置已发生**：许昌预报抓取连续 28 次失败 → 事件触发诊断 →
  正确定位"数据库口令未注入，非代码缺陷" → 执行 `trigger_fetcher` 重抓 →
  拒绝不必要重启（"重启也不会补口令"） → 给出治理建议

---

## 二、实战暴露的问题（按优先级）

### 🔴 P0：推送最后一公里断裂

诊断结论质量很高，但 `broadcast_social_users` 对 `android_demo` 连续
两次发送 **0 成功 / 1 失败**——本地该账号无注册 App 设备，所有通报
实际没有送达任何人。闭环的"通知人"环节失效。

**修复方向**：本地配通用 webhook 接通报警（最快），或注册有效 App 账号；
生产部署需核实目标用户有效性。

### 🟡 P1：实时诊断任务无界搜索

- 现象：整点事件并发时连续 timeout（600s 撞满），success 的也要
  360~570s（正常应 ~30s）
- 根因：`MAX_ITERATIONS=100` 无收敛条件（单轮 search_files 250 次、
  read_file 215 次）+ `execute_python` 缺 bubblewrap 不可用加剧重试
- 影响：每小时烧约 20 分钟算力；诊断超时自身成为新错误源（自污染）

**修复方向**（五项，均已设计待执行）：
1. custom 任务 `max_iterations` 限 15
2. prompt 加搜索预算（最多读 5 文件/3 次搜索必须给结论）
3. 超时 600s → 360s
4. 种子移除 `execute_python`（本地无 bwrap）
5. 事件冷却 30 → 60 分钟（削整点并发热点）

### 🟢 P2：无关监控对象造成噪声

诊断任务自己发现："污染过程巡检、数据质量巡检监控对象为外地城市，
与本级业务无关，建议在项目配置中停用"——default 部署跑了许昌专属
fetcher，持续产生无意义告警。

**修复方向**：default 项目 manifest 收敛 fetcher 清单。

### 附带：时区口径

容器 UTC vs 调度 Asia/Shanghai vs DB 裸 UTC——查库对时间差 8 小时。
建议给容器加 `TZ=Asia/Shanghai` 统一口径。

---

## 三、下一步

| 优先级 | 事项 | 工作量 |
|---|---|---|
| 🔴 | 配置可达的告警通道（webhook/有效账号），验证通报送达 | 小 |
| 🟡 | 实时诊断五项收敛修复（迭代/预算/超时/工具/冷却） | 小 |
| 🟢 | default manifest 停用无关 fetcher | 很小 |
| 🟢 | 容器统一时区 | 很小 |
| 白 | B2 第三进程 `APP_ROLE=assistant`（技术前提已被 B1 解决，剩余是部署契约） | 大 |
| 白 | 服务器生产同步：拉 main → pytest → restart_server.sh → 补三项 env 配置 → 部署守护进程 | 中 |

### 运行中的观察

- 每 30 分钟自动巡检一轮（容器/健康/错误/任务/抓取/资源六项）
- 小时巡检 + 实时诊断 + L0 探针持续在跑
- 12 个提交已推送 origin/main，工作树干净

---

## 四、关键文件索引

```
backend/app/monitoring/
  ├─ anomaly_emitter.py    事件发射器（Fast Path 冷却去重）
  └─ severity.py           P0/P1 确定性分级器
backend/app/tools/runtime_monitor/
  ├─ tool.py               query_runtime_anomalies（质询白名单）
  ├─ collector.py          五类留痕采集
  ├─ self_heal.py          retry_scheduled_task / trigger_fetcher
  ├─ service_ops.py        restart_service / verify_service_health
  └─ repair_auth.py        源码修复授权（tag+白名单+快照）
backend/app/social/
  ├─ subagent_manager.py   spawn 后台任务（owner 透传）
  └─ task_status_store.py  PostgreSQL 任务状态
projects/default/scheduled_tasks/
  ├─ task_runtime_monitor.json          小时巡检种子
  └─ task_runtime_monitor_realtime.json 实时诊断种子（分级处置）
deploy/
  ├─ monitoring/          L0 探针 + 带外告警
  ├─ maintenance/         维护守护进程（重启/快照/回滚）
  └─ local/               本地 Docker 部署编排
```
