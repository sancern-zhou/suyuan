# 许昌站点告警 → 微信群 RPA 推送 agent

后端每 5 分钟对站点 5 分钟数据做超标判定，通报文案生成后进入待发队列；
本 agent 在 Windows 电脑上常驻轮询队列，用 [wxauto](https://github.com/cluic/wxauto)
（Windows UI 自动化，非注入）操控微信电脑版，把通报文字发进指定的个人微信群。

```
服务器后端                                  本机（Windows + 微信电脑版）
alert 通报文案 → pending/*.json   ◄────────  GET  /api/xuchang-wechat-push/pending
                                  ────────►  wxauto.SendMsg(文案, who=群名)
                                  ────────►  POST /api/xuchang-wechat-push/ack
```

仅发不收（群里 @机器人 不会触发任何动作）。整个目录拷到其他电脑即可重新部署。

## 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（需有桌面会话，不能跑在 Windows 服务/Session 0） |
| Python | 3.11+（读写 config.toml 用到内置 tomllib） |
| 微信电脑版 | **3.9.x**，安装后关闭自动更新锁版本（wxauto 按微信版本适配） |
| 微信号 | **专用小号**（实名、有一点正常使用记录），不要用任何人的主号 |

## 服务端准备（一次性）

在许昌后端部署机的 `.env` 中追加并重启 web：

```bash
XUCHANG_WECHAT_PUSH_API_PREFIX=/api/xuchang-wechat-push
XUCHANG_WECHAT_PUSH_TOKEN=<随机串>   # python -c "import secrets; print(secrets.token_urlsafe(24))"
```

两个值缺省为空 = 接口整体禁用（安全默认）。告警入队由 worker 自动完成，
无需其他配置；如需关闭入队，忽略本步即可（agent 拉不到消息）。

## 本机部署步骤

1. 把整个 `rpa_wechat_pusher/` 目录拷贝到目标电脑。
2. 运行 `install.bat`（创建 `.venv` 并安装 wxauto、httpx）。
3. 编辑 `config.toml`：填后端 `base_url`、`token`、目标 `group_name`。
4. 微信电脑版登录小号，打开目标群聊窗口确认能搜到群名（建议置顶）。
5. 验证微信环境：

   ```bat
   .venv\Scripts\python agent.py --test "许昌告警推送测试消息"
   ```

   群里收到即环境 OK。
6. 验证后端链路（不实发）：

   ```bat
   .venv\Scripts\python agent.py --dry-run
   ```

   打印 `将发到「群名」：...` 或静默退出（队列空）即链路 OK。
7. 双击 `start_agent.bat` 常驻运行。开机自启：`Win+R` 输入 `shell:startup`，
   把 `start_agent.bat` 的快捷方式放进去。

## 运行注意事项（都是实测坑）

- **微信主窗口保持打开**：可最小化到任务栏，不要关闭到托盘、不要多开。
- **电脑不能睡眠**；如通过远程桌面操作，断开 RDP 会停掉 UI 自动化
  （远程场景用 `tscon <会话id> /dest:console` 把会话切回控制台再断开）。
- 时效：轮询默认 15 秒，远快于 5 分钟告警周期；可在 config 调小（≥5 秒）。
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
| 初始化微信失败 | 微信未登录 / 关到托盘 / 版本与 wxauto 不匹配 |
| 发送失败：找不到会话 | 群名不唯一或不在会话列表，置顶目标群 |
| 心跳有但积压上涨 | 微信掉线或窗口不可用，看 agent.log |

## 常见问题

- **微信升到 4.x 怎么办**：开源 wxauto 主线适配 3.9.x；微信 4.0 目前只有
  `wxautox4`（Beta、绑定 4.0.5）。升级前先在小号环境实测，不要直接换生产。
- **能不能发图片/@所有人**：当前版本只发文本。图片、@所有人、
  "快讯先行+详报后补"为二期计划。
- **换一台电脑部署**：整目录拷贝 → 重跑 install.bat → 新填 config.toml →
  重复「本机部署步骤」4-7。注意同一时刻只应有一个 agent 拉同一后端
  （消息会被取走分摊，一般也应避免双跑）。
