# LLM 网关 504 定位报告（2026-11-15）

## 一句话结论

504 不是应用侧超时，而是**网关（nginx/APISIX 前置）在"上游 6.00s 内无任何响应字节"时直接返回 504**。
上游 vLLM（DeepSeek-V4.1-Flash, tp8）prefill 吞吐约 **7,300–7,500 tok/s**，因此在 prefix cache 未命中时，
只要请求需要 prefill 的 token 数超过约 **43K–45K**，prefill 就必然越过 6s，网关必定 504。
同一请求体第二次发送命中 prefix cache 后 **0.2s** 即返回 200。

## 504 响应的确定特征

```
HTTP/1.1 504 Gateway Time-out
Server: nginx/1.25.5
X-APISIX-Upstream-Status: 504
{"message":"504 Gateway Timeout"}

time_total = 6.00 -- 6.02s（与请求体大小、max_tokens、stream 均无关）
```

- 应用侧配置 `LLM_REQUEST_TIMEOUT_SECONDS=180`、`LLM_FIRST_TOKEN_TIMEOUT_SECONDS=45`；
  日志中 504 耗时恒为 6.02s，说明超时由网关产生，不是应用产生的。
- 与 `enable_thinking`（true/false）无关。
- 与请求体上传耗时无关：350KB–600KB body 上传本身不超时，是上传完成后上游无字节返回才超时。

## 实测证据

### 1. prefill 耗时与 prompt 长度（单并发、唯一随机文本、8 输出 token）

| 请求字符数 | prompt_tokens | 首字节耗时 | 结果 |
| --- | --- | --- | --- |
| 10,000 | 5,144 | 0.93s | 200 |
| 40,000 | 20,383 | 2.80s | 200 |
| 60,000 | 30,475 | 4.04s | 200 |
| 80,000 | 40,720 | 5.41s | 200 |
| 88,000 | ~43,700 | 5.80s | 200（贴边） |
| 90,000 | - | 6.00s | **504** |
| 96,000 | - | 6.00s | **504** |

线性拟合约 **7,500 tok/s**，6s 对应约 **45K token** 的 prefill 上限。
固定 85,000 字符 + 每次全新唯一文本连续 12 次：12/12 成功，首字节 5.77–5.85s
（距 6s 仅 0.15–0.23s 余量），说明阈值附近是"卡点"而非随机抖动。

### 2. prefix cache 命中即可绕过

同一 96,000 字符请求体连续发送 4 次：

```
第 1 次: 504 / 6.01s
第 2 次: 200 / 1.58s   (prompt_tokens=50864)
第 3 次: 200 / 0.20s
第 4 次: 200 / 0.19s
```

三轮复测结果完全一致（首请求 504，随后 200/0.19–0.67s）。
即：缓存未命中 → prefill > 6s → 504；命中缓存 → 0.2s → 200。
"重发一次就好了"是缓存效应，不是网关抖动。

### 3. 并发成倍放大（共享同一 prefill 预算）

| 并发数 | 每请求 prompt | 成功 / 504 |
| --- | --- | --- |
| 8 | ~15K token | 2 / 6 |
| 8 | ~20K token | 2 / 6 |
| 8 | ~25K token | 0 / 8 |
| 16 | ~10K token | 0 / 16 |
| 12 | ~2K token | 12 / 0 |

6s 窗口内上游总共只能完成约 45K token 的 prefill，并发请求按比例分摊。

### 4. 非流式请求即使 prompt 很小也会 504

`stream=False` 时上游要生成完整响应才回第一个字节，因此**解码时间也计入这 6s**：

| prompt | max_tokens | 实际生成 | 结果 |
| --- | --- | --- | --- |
| 小 | 200 | 200 | 200 / 1.7s |
| 小 | 400 | 400 | 200 / 3.1s |
| 小 | 600 | 600 | 504 / 6.0s（同配置另一次 200 / 4.95s） |
| 小 | 800 | 686 | 504 / 6.0s（另一次 200 / 5.22s） |
| 小 | 2048（压缩摘要） | - | 504 / 6.0s |
| 小 | 7000（OCR） | - | 504 / 6.0s |

同样的 prompt 用 `stream=True` 时 `max_tokens=2000` 可以正常跑完（23.2s，1053 token），
证明网关卡的是"首字节"，不是总时长。

### 5. 应用日志侧统计（2026-11-15 11:27–13:12）

- 344 次 chat_completions 流式请求，77 次出现 `504 Gateway Time-out`。
- 504 从请求发起到失败恒为 **6.02s（min 6.02 / p50 6.02 / max 6.59）**。
- 504 事件与 `planner_context_with_tools` 估算上下文正相关：
  20–40K token 约 3%，60–80K 约 18%，80–100K 约 29%，140–160K 达 60%。
- 失败后 `llm_failover` 把 provider 打 cooldown（60/120/240s），
  单候选配置（`LLM_FALLBACKS=openai`）下后续请求被跳过 177 次，进一步放大排队。


## 复现脚本

最小复现（不依赖项目代码）：

```bash
BASE=http://<llm-gateway>:41080/large-model/api/v1
KEY=<jcmp-token>

python3 - <<'PY'
import json, random, string, urllib.request
random.seed()
words = [''.join(random.choices(string.ascii_lowercase, k=7)) for _ in range(12000)]
body = json.dumps({
    "model": "MDDEEPSEEKB9D44FA457FF",
    "messages": [{"role": "user", "content": ' '.join(words)[:96000]},
                 {"role": "user", "content": "summary"}],
    "max_tokens": 8, "stream": True,
}).encode()
req = urllib.request.Request("$BASE/chat/completions", body,
    {"Authorization": "Bearer $KEY", "jcmp-token": "$KEY", "Content-Type": "application/json"})
try:
    print(urllib.request.urlopen(req, timeout=120).status)
except Exception as e:
    print("ERR", e)
PY
```

预期：首次 504（约 6.0s），再次发送同一 body 200（约 0.2s）。

## 对服务商的诉求

1. **调大网关首字节（upstream read/response）超时**。当前 6s 对 vLLM 长上下文不可用：
   45K token 以上的 prefill、以及任何非流式长输出都会必然超时。建议 ≥120s，
   或至少分段：首字节 60s + 空闲 30s。
2. **504 不应由 APISIX 在 upstream 已接受请求后产生**；若必须保留短超时，
   请改为 429/503 并带 `Retry-After`，避免客户端误判为可重试的过载。
3. 确认 vLLM 侧 `--enable-prefix-caching` 与最大模型长度配置；当前 prefill ~7.5K tok/s
   （tp8）偏慢，若为 8 卡部署建议排查是否启用了 chunked prefill 与合适 batch。

## 本侧可先做的缓解

- 长上下文迭代时优先保持**稳定前缀**（system + tools 在前、只追加），提升 prefix cache 命中率。
- 压缩上下文上限：把 `planner_context_with_tools` 压到 60K token 以下，可把 504 率从 ~20% 降到 ~3%。
- 减少非流式调用：`COMPACT_SUMMARY_MAX_TOKENS=2048`、OCR `max_tokens=7000`、
  `evaluation max_tokens=2500`、`knowledge_qa max_tokens=4096` 等在 6s 网关下都会 504。
- 增加备用 provider/model（`LLM_FALLBACKS`），避免单候选 cooldown 期间全部排队失败。

## 已落地的本侧修复（2026-11-16）

所有 `chat_completions` 非流式调用统一改为「流式请求上游 + 本地聚合」，
对外返回结构与原非流式完全一致，调用点（OCR、评估、知识库问答、招投标抽取、
快速溯源等）无需改动：

- 新增 `backend/app/services/chat_completions_collect.py`：
  `collect_chat_completions_stream()` 走 SSE 拉取并用
  `ChatCompletionsStreamAdapter` 适配后聚合为一次性响应；空流自动重投一次；
  `first_block_timeout` 墙钟看门狗兜住「上游只推空 delta 心跳」（此时 httpx
  read timeout 永不触发）。
- `LLMService._chat_completions_stream_collect()` 接管
  `_chat_completions_create()`，保留 `ToolCallArgumentsError` 的
  `tool_choice` 定向重试；开关 `LLM_CHAT_COMPLETIONS_STREAM_COLLECT`
  （默认 true）可一键回退旧路径。
- 实测（同网关、同模型）：`max_tokens` 600/1200/2000 长输出分别 11.7s/10.7s/20.6s
  全部 200（原非流式同 prompt 一律 6.0s 504）；带 1 个工具的 agent 调用 0.5s 返回
  `tool_use` 且参数完整。

