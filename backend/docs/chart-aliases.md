# 图表短别名

绘图工具仍通过 `visuals[].id` 和统一会话资源交付真实图表。执行器在工具结果中
追加 `visual_refs` 映射及可复制的 `[[chart:chart_N]]` 标记，减少模型照抄完整
`visual_id` 时出现的错误；Python 静态图、ECharts 和业务图使用同一机制。

- 别名按会话隔离，多个 web worker 通过同一个 Redis 实例共享分配与解析。
- 流式回复会暂存跨 chunk 拆开的标记，完整解析后才向客户端发送。
- 最终回复在保存前再次解析；现有资源 ID 占位符归一化、DSML 过滤和真实 ID
  模糊纠错仍然保留，不需要前端增加另一套图表 ID 协议。
- Redis 不可用时不分配进程内别名，工具保留真实 ID，模型按 `visuals[].id`
  引用图表；旧别名解析失败时原样保留，不猜测其他会话或其他图表。

## 配置与生命周期

`AGENT_VISUAL_ALIAS_REDIS_PREFIX` 指定 Redis 键前缀；多个部署实例共用 Redis
时应配置不同前缀。`AGENT_VISUAL_ALIAS_TTL_SECONDS` 控制映射有效期，默认
1209600 秒（14 天），每次绑定刷新；web worker 应使用一致的配置。

每个会话的映射保存在 `<prefix>:map:<session_id>`，计数器保存在
`<prefix>:seq:<session_id>`。计数器不随映射过期，以免旧标记重号后错误指向新图。
清理计数器或切换 Redis 前应确认对应会话不再继续使用旧别名；不能单独清除
仍在使用中的计数器。已经正常保存的回复使用真实 ID，不依赖别名映射继续展示。

## 回归测试

在 `backend_py311` 环境、项目根目录运行：

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_visual_alias.py \
  backend/tests/test_visual_id_protocol.py \
  backend/tests/test_dsml_markup_sanitizer.py \
  backend/app/agent/resources/chart_placeholders_test.py \
  backend/app/agent/runtime/agent_runtime_multimodal_test.py -q
```
