# suyuan L0 存活探针

宿主机层的外部控制回路（Control Loop）：每分钟探测 web / worker / 共享嵌入服务的
`/health`，宕机与恢复通过**带外 webhook**（企业微信/飞书/钉钉）通知，不依赖
suyuan 后端进程本身。

## 为什么需要它（与应用内 Watchdog 的分工）

应用内的"后台运行监控"定时任务（`projects/default/scheduled_tasks/task_runtime_monitor.json`，
`query_runtime_anomalies` 工具链）负责**语义层**监控：任务失败归因、抓取失败分析、
LLM 供应商异常汇总与通报。但它运行在被监控的 worker 进程内、依赖 LLM 链——
后端整体挂掉或 LLM 全链失败时它会静默失效。本探针补上这个盲区：

| 层 | 覆盖故障 | 依赖后端 | 依赖 LLM |
|---|---|---|---|
| L0 探针（本目录） | 进程宕机、端口不可达 | ❌ | ❌ |
| 应用内 Watchdog | 任务失败、抓取失败、会话错误、LLM 异常、配额 | ✅ | ✅ |

**已知边界**：本探针跑在被监控的同一台宿主机上，机器本身宕机/断电/断网时它同样
失声（且无人会收到通知）。如需覆盖该场景，需再加一个外部探针（从另一台机器或
云函数探测公网入口），属于后续可选项。

## 部署（在部署机上，如 /home/xckj/suyuan-main）

```bash
# 1. 安装到 /opt（与仓库解耦，git 操作不会动到 env 配置）
sudo mkdir -p /opt/suyuan-monitor
sudo cp deploy/monitoring/l0_probe.py /opt/suyuan-monitor/
sudo cp deploy/monitoring/l0_probe.env.example /opt/suyuan-monitor/l0_probe.env
sudo vi /opt/suyuan-monitor/l0_probe.env   # 填 L0_WEBHOOK_URL，核对 L0_TARGETS

# 2. 验证：先看探测结果，再测告警通道
python3 /opt/suyuan-monitor/l0_probe.py --env-file /opt/suyuan-monitor/l0_probe.env --status
python3 /opt/suyuan-monitor/l0_probe.py --env-file /opt/suyuan-monitor/l0_probe.env --test

# 3. systemd timer 常驻（每分钟一次）
sudo cp deploy/monitoring/suyuan-l0-probe.service deploy/monitoring/suyuan-l0-probe.timer \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now suyuan-l0-probe.timer

# 4. 观察日志
journalctl -u suyuan-l0-probe.service -f
```

无 systemd 的环境可用 cron 替代：

```cron
* * * * * /usr/bin/python3 /opt/suyuan-monitor/l0_probe.py --env-file /opt/suyuan-monitor/l0_probe.env
```

## 探活目标依据

- main web `127.0.0.1:8000/health` —— `app/api/system.py` 的 health 端点，无鉴权
- main worker `127.0.0.1:8011/health` —— worker 内部 IPC API（`social_worker_api`），
  `/health` 显式豁免内部 token；worker 死亡时 web 侧 fetchers 接口的 503 即来源于此
- main embedding `127.0.0.1:8020/health` —— 共享 bge-m3 嵌入服务
  （`app/services/embedding_server.py`），全机 web/worker 的共同依赖，单点必须盯
- 江苏运维 web/worker `8001/8012` —— 第二套部署（`backend/.env.jiangsu-ops`）

nginx 容器（5174/5175）自带 docker healthcheck，不重复探测。

## 告警行为

- **宕机**：目标由可达变不可达，立即推送（含失败原因与处理提示）
- **持续宕机**：每 `L0_ALERT_REPEAT_MINUTES`（默认 6 小时）重报一次，防轰炸
- **恢复**：推送恢复通知并附宕机时长
- 状态持久化在 `L0_STATE_FILE`，探针重启不丢状态；首轮部署对在线目标静默
  （不产生通知），状态文件损坏时自动重建，仅丢失"宕机中"的记忆（重建后如
  目标仍宕机会在下轮重新告警）
