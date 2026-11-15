# suyuan 维护守护进程（宿主机侧）

分级自治修复的**执行臂**：容器内的修复 Agent 无 docker.sock、无进程管理器，
不能重启 web/worker（更不能重启自己）。本守护进程跑在宿主机上，故障域与
被控对象隔离——后端整体挂掉时它仍能拉起服务。它只做确定性动作
（restart/snapshot/rollback），"是否该重启"的 P0 判级在应用侧由
`backend/app/monitoring/severity.py` 的规则决定。

## 能力与缰绳

| 端点 | 作用 | 缰绳 |
|---|---|---|
| `GET /health` | 存活探测 | 无鉴权 |
| `GET /status` | 服务健康 + 重启计数 | token |
| `POST /snapshot` | git 快照（stash create，不改工作区） | token |
| `POST /rollback` | 回滚到快照（checkout 精确恢复） | token |
| `POST /restart` | 重启 web/worker/all + 健康等待 240s，不健康自动回滚快照再重启 | token + 同 service 10 分钟冷却 + 每日 5 次 |

- 仅监听 `127.0.0.1`；空 token 拒绝启动
- 缰绳状态落盘 `maintenance_state.json`：守护进程重启不重置冷却/日限
- 应用侧（`restart_service` 工具）另有独立三重门禁：实时重判 P0 + Redis
  缰绳 + 守护进程可达，两层缰绳互相独立

## 本机启动（Windows）

```bat
cd deploy\maintenance
copy maintenance.env.example maintenance.env   :: 填 MAINTENANCE_TOKEN
start_local.bat
```

登录自启（HKCU Run 键，无需管理员）：

```bat
reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v SuyuanMaintenance /d "C:\path\to\deploy\maintenance\start_local.bat" /f
```

应用侧 `backend/.env` 需同步配置：

```dotenv
MAINTENANCE_DAEMON_URL=http://host.docker.internal:8013
MAINTENANCE_DAEMON_TOKEN=<与守护进程一致>
```

## 服务器部署（Linux systemd）

```bash
sudo cp suyuan-maintenance.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now suyuan-maintenance
# MAINTENANCE_RESTART_COMMAND 指向 restart_server.sh 时忽略 compose 参数，
# 容器侧 URL 改为 http://127.0.0.1:8013
```

## 自检

```bash
python maintenance_daemon.py --env-file maintenance.env --test-restart web
# 输出 TEST_RESULT {"service": "web", "healthy": true, ...}
```
