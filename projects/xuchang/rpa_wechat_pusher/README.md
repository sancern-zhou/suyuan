# 许昌站点告警 → 微信群 RPA 推送 agent

后端每 5 分钟对站点 5 分钟数据做超标判定，通报文案生成后进入待发队列；
本 agent 在 Windows 电脑上常驻轮询队列，用 [wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica)
驱动**微信 4.x 电脑版**把通报文字发进指定的个人微信群（UIA 热激活 +
混合驱动，非注入 hook）。

```
服务器后端                                  本机（Windows + 微信4.x电脑版）
alert 通报文案 → pending/*.json   ◄────────  GET  /api/xuchang-wechat-push/pending
                                  ────────►  quick_send(文案, who=群名)
                                  ────────►  POST /api/xuchang-wechat-push/ack
```

仅发不收（群里 @机器人 不会触发任何动作）。整个目录拷到其他电脑即可重新部署。

## 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（需有桌面会话，不能跑在 Windows 服务/Session 0） |
| Python | 3.11+（本机 3.13 实测通过） |
| 微信电脑版 | **4.x**（4.2.0.12 实测发送通过；不建议也不需要装 3.9.x，见下） |
| 微信号 | **专用小号**（实名、有一点正常使用记录），不要用任何人的主号 |

> **为什么不用微信 3.9.x + 老版 wxauto？** 2025 年 10 月起腾讯对新设备/新号
> 登录 3.9.x 拦截（提示版本过低），绕过法随时失效；开源 wxauto/wxauto4 主线
> 也分别只适配 3.9.x / 4.0.x。wechatauto-replica 明确适配 4.1.12+ 并持续维护，
> 是当前 4.x 客户端的现实解。

## 服务端准备（一次性）

在许昌后端部署机的 `.env` 中追加并重启 web：

```bash
XUCHANG_WECHAT_PUSH_API_PREFIX=/api/xuchang-wechat-push
XUCHANG_WECHAT_PUSH_TOKEN=<随机串>   # python -c "import secrets; print(secrets.token_urlsafe(24))"
```

两个值缺省为空 = 接口整体禁用（安全默认）。告警入队由 worker 自动完成，
无需其他配置。

## 本机部署步骤

1. 把整个 `rpa_wechat_pusher/` 目录拷贝到目标电脑。
2. 运行 `install.bat`（创建 `.venv` 并安装依赖；wechatauto-replica 以
   `--no-deps` 安装以跳过 winsdk，原因见「常见问题」）。
3. 编辑 `config.toml`：填后端 `base_url`、`token`，`group_name` **先填
   `filehelper`（文件传输助手）用于验证**。
4. 微信电脑版登录小号（保持主窗口打开）。
5. 验证微信发送链路（消息发到文件传输助手，只有自己可见）：

   ```bat
   .venv\Scripts\python agent.py --test "许昌告警推送测试消息"
   ```

   文件传输助手里收到即环境 OK。
6. 把 `config.toml` 的 `group_name` 改成真实群名（在微信里置顶该群、
   确保群名唯一），再跑一次 `--test` 实发一条到群里确认。
7. 验证后端链路（不实发）：

   ```bat
   .venv\Scripts\python agent.py --dry-run
   ```

8. 配置登录自启（两者都放 shell:startup 快捷方式，目标均为
   `.venv\Scripts\pythonw.exe`，无窗口运行）：
   - `pythonw.exe agent.py`（工作目录本目录）→ 常驻推送；
   - `pythonw.exe watchdog.py`（工作目录本目录）→ 看门狗，每 10 分钟
     检查 agent：进程缺失则拉起；进程在但存活心跳
     （`data/agent_liveness` mtime，agent 每轮轮询/每条消息处理前刷新）
     超过 10 分钟未更新则判定冻结，杀进程树后拉起新实例。

## 运行注意事项（都是实测坑）

- **微信主窗口保持打开**：可最小化到任务栏，不要关闭到托盘、不要多开。
- **电脑不能睡眠**；如通过远程桌面操作，断开 RDP 会停掉 UI 自动化
  （远程场景用 `tscon <会话id> /dest:console` 把会话切回控制台再断开）。
- **发送那几秒会占用真实的鼠标键盘**：wechatauto 的发送是"微信置顶抢焦点
  → 点击输入框 → Ctrl+A 清空 → 写剪贴板 Ctrl+V 粘贴 → 点发送"的真输入序列，
  单条约 3~8 秒。期间用户动鼠标/打字会互相干扰（鼠标被抢、微信被拽到前台，
  剪贴板内容会被告警文案覆盖）；撞上时该条按失败自动重试，消息不丢不重。
  **正式部署建议专用机或虚拟机**（见下），共用机请知晓此体验。
- **不能锁屏/注销**：真输入注入无法到达锁屏后的微信窗口，发送会失败；
  消息保留在队列，解锁后 agent 自动补发。电源计划设置为不睡眠、从不锁定。
- **剪贴板会被占用**：每条消息发送都经过剪贴板，发送后剪贴板内容是告警文案。
- 首次发送前 wechatauto 要做一次布局校准（约 2 秒），属正常。
- 发送失败重试耗尽后回执 `failed`，后端累计 3 次即归档停发（`failed/` 目录），
  避免故障期间无限刷群；处理完故障后需人工在群里补发。

## 日常检查与排障

- 后端侧：管理员登录浏览器访问 `/api/xuchang-wechat-push/status`
  （或带 `Authorization: Bearer <token>`），看 `pending_count`（积压）、
  `failed_count`、`agent.last_seen_at`（agent 心跳，agent 在线即持续刷新）。
- 本机侧：`data/agent.log`；看门狗日志 `data/watchdog.log`。
- **看门狗（watchdog.py）**：登录自启，每 10 分钟检查 agent——进程缺失则
  无窗口拉起（覆盖误关窗口、被杀、偶发崩溃）；进程在但心跳
  `data/agent_liveness` 超过 10 分钟未更新则判定冻结（UIA/网络调用挂死），
  杀进程树后拉起新实例（2026-11-12 冻结 36h 事故后新增，旧版只查进程
  存在性发现不了这类故障）。杀毒软件（尤其 360 主动防御）
  可能把 wechatauto 的内存操作判定为威胁而终止 python 进程——请把
  `.venv\Scripts\pythonw.exe`、`python.exe`、本目录和微信安装目录加入
  安全软件白名单，否则看门狗会陷入"拉起-被杀"循环（日志可辨）。
- **单实例锁**：agent 启动时占用 `127.0.0.1:47615`，重复启动会立即退出
  （防止双实例同时拉取导致重复发群）。

| 现象 | 处理 |
|---|---|
| 401 token 不正确 | 核对 config.toml 与后端 `.env` 的 token |
| 403 wechat_push_disabled | 后端 `.env` 未配置 prefix/token，或漏重启 web |
| 初始化微信失败 / 找不到主窗口 | 微信未登录 / 关到托盘；确认装的是 wechatauto-replica 而非旧 wxauto |
| 发送失败：找不到会话 | 群名不唯一或不在会话列表，置顶目标群 |
| 心跳有但积压上涨 | 微信掉线或窗口不可用，看 agent.log |
| agent.log 出现 "已有 agent 实例在运行" | 已有常驻实例，正常退出无需处理；确认只需一套自启（快捷方式 + 看门狗） |
| agent 反复消失 | 查安全软件白名单（见上），看门狗日志有拉起记录 |

## 常见问题

- **winsdk 报错（No module named 'winsdk'）？** wechatauto 的 OCR 兜底依赖
  winsdk，而 Python 3.11+ 官方无预编译 wheel。本目录 `winsdk_shim/` 把
  `winsdk.windows.*` 转发到现代 pywinrt 包（`winrt-*`，由 requirements.txt
  安装），agent 启动时自动挂载，OCR 兜底可用——无需再处理。
- **微信自动升级到 4.3+ 会失效吗？** wechatauto 依赖微信内部布局与无障碍
  闸门特征，大版本更新可能需要等它适配；因此**关闭微信自动更新**，
  升级前先在 `--test` 模式验证。
- **能不能发图片/@所有人**：图片已支持——告警工作流收集的证据附图（趋势图、
  上风向地图等）会在文本发出后逐张下载并发进群（`GET /media/{id}/{序号}`，
  同一 Bearer 令牌鉴权，仅允许 data registry 内文件）；单张失败不影响文本
  与其余附图，回执 detail 会记"附图 N/M 张成功"。@所有人、"快讯先行+详报
  后补"仍为二期计划。
- **换一台电脑部署**：整目录拷贝 → 重跑 install.bat → 新填 config.toml →
  重复「本机部署步骤」4-8。注意同一时刻只应有一个 agent 拉同一后端。
- **与人在用电脑冲突怎么办**：RPA 发送靠真鼠标键盘，无法后台化。三个层级：
  ①共用机可接受——告警低频、单条仅数秒，撞上会自动重试；②一台物理机彻底
  互不干扰的正解是**虚拟机**（VMware/Hyper-V 里跑 Windows + 微信 + agent，
  宿主机正常办公）；③商用后台模式（wxautox4 付费授权）不在本方案内。
