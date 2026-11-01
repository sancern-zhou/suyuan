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

8. 双击 `start_agent.bat` 常驻运行。开机自启：`Win+R` 输入 `shell:startup`，
   把 `start_agent.bat` 的快捷方式放进去。

## 运行注意事项（都是实测坑）

- **微信主窗口保持打开**：可最小化到任务栏，不要关闭到托盘、不要多开。
- **电脑不能睡眠**；如通过远程桌面操作，断开 RDP 会停掉 UI 自动化
  （远程场景用 `tscon <会话id> /dest:console` 把会话切回控制台再断开）。
- 发送是 GUI 操作，锁屏一般仍可用，但**注销/重启后未登录微信必然失败**，
  agent 会保留消息并持续重试。
- 首次发送前 wechatauto 要做一次布局校准（约 2 秒），属正常。
- 发送失败重试耗尽后回执 `failed`，后端累计 3 次即归档停发（`failed/` 目录），
  避免故障期间无限刷群；处理完故障后需人工在群里补发。

## 日常检查与排障

- 后端侧：管理员登录浏览器访问 `/api/xuchang-wechat-push/status`
  （或带 `Authorization: Bearer <token>`），看 `pending_count`（积压）、
  `failed_count`、`agent.last_seen_at`（agent 心跳，agent 在线即持续刷新）。
- 本机侧：`data/agent.log`。

| 现象 | 处理 |
|---|---|
| 401 token 不正确 | 核对 config.toml 与后端 `.env` 的 token |
| 403 wechat_push_disabled | 后端 `.env` 未配置 prefix/token，或漏重启 web |
| 初始化微信失败 / 找不到主窗口 | 微信未登录 / 关到托盘；确认装的是 wechatauto-replica 而非旧 wxauto |
| 发送失败：找不到会话 | 群名不唯一或不在会话列表，置顶目标群 |
| 心跳有但积压上涨 | 微信掉线或窗口不可用，看 agent.log |

## 常见问题

- **为什么安装时跳过 winsdk？** winsdk（WinRT 绑定）仅用于 wechatauto 的
  OCR 兜底识别通道，且 Python 3.13 无预编译 wheel、源码构建需要 MSVC。
  跳过它只少一层 OCR 兜底，UIA 主通道发送完全不受影响。
- **微信自动升级到 4.3+ 会失效吗？** wechatauto 依赖微信内部布局与无障碍
  闸门特征，大版本更新可能需要等它适配；因此**关闭微信自动更新**，
  升级前先在 `--test` 模式验证。
- **能不能发图片/@所有人**：当前版本只发文本（wechatauto 的 SendMsg 支持
  @，接上来即可）。图片、@所有人、"快讯先行+详报后补"为二期计划。
- **换一台电脑部署**：整目录拷贝 → 重跑 install.bat → 新填 config.toml →
  重复「本机部署步骤」4-8。注意同一时刻只应有一个 agent 拉同一后端。
