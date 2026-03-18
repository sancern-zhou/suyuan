# 优化3: 缓存保护策略 - 实施指南

> 成本节省83%的关键优化

**优先级**: P1（立即实施）
**实施难度**: ⭐
**预计工期**: 2天
**预期收益**: 年度节省 $45,260

---

## 📋 目录

1. [背景与原理](#背景与原理)
2. [当前问题分析](#当前问题分析)
3. [解决方案设计](#解决方案设计)
4. [实施步骤](#实施步骤)
5. [测试验证](#测试验证)
6. [监控指标](#监控指标)

---

## 背景与原理

### Claude API 缓存机制

Claude API 提供 Prompt Caching 功能：
- **缓存范围**: 系统消息（system）和工具定义（tools）
- **缓存时长**: 5分钟
- **缓存条件**: 前缀完全匹配
- **成本对比**:
  - 缓存写入: 1.25x 正常价格
  - 缓存读取: 0.1x 正常价格（**节省90%**）

### 成本分析（来自 learn-claude-code）

**场景**: 每天100次调用，每次50K tokens

| 策略 | 缓存命中率 | 每天成本 | 年成本 |
|------|-----------|---------|--------|
| 无优化（破坏缓存） | 0% | $150 | $54,750 |
| 缓存优化 | 60% | $26 | $9,490 |
| **节省** | - | **$124/天** | **$45,260/年** |

### 核心原则

**"系统Prompt永不改变，动态内容只追加"**

```python
# ❌ 错误: 每次修改系统Prompt（破坏缓存）
system = f"你是专家。当前任务: {task}, 时间: {time}, 数据: {data}"

# ✅ 正确: 系统Prompt固定（保护缓存）
SYSTEM = "你是专家。你将收到任务、时间和数据。"
messages = [
    {"role": "user", "content": f"任务: {task}\n时间: {time}\n数据: {data}"}
]
```

---

## 当前问题分析

### 问题1: 动态系统Prompt

**文件**: `backend/app/agent/experts/template_report_prompts.py`

```python
# 当前实现（破坏缓存）
def build_template_analysis_prompt(template_content: str, time_range: Dict) -> str:
    display = time_range.get("display", "")

    return f"""你是一名空气质量报告生成专家。

任务：阅读以下历史报告模板，提取需要的数据指标...

历史报告模板（Markdown）：
{template_content}  # ❌ 每次不同，破坏缓存

目标时间：{display}  # ❌ 每次不同，破坏缓存
...
"""
```

**问题**:
- `template_content` 每次不同（不同报告模板）
- `time_range` 每次不同（不同时间范围）
- 导致每次调用都重新计算，缓存命中率 0%

### 问题2: 编辑消息历史

**文件**: `backend/app/agent/core/loop.py`

```python
# 可能存在的问题（需要检查）
messages.insert(0, system_message)  # ❌ 插入破坏前缀
messages[0] = updated_system  # ❌ 修改破坏前缀
```

**问题**: 任何对消息历史前缀的修改都会破坏缓存

---

## 解决方案设计

### 设计原则

1. **系统Prompt固定化**: 所有通用指令写死
2. **动态内容后置**: 模板、数据、时间等放入用户消息
3. **只追加不修改**: 消息历史只追加，不插入、不编辑
4. **工具定义固定**: 工具Schema不变

### 架构设计

```
┌─────────────────────────────────────┐
│  系统Prompt（固定，可缓存）          │
│  - 角色定义                          │
│  - 通用指令                          │
│  - 输出格式要求                      │
└─────────────────────────────────────┘
              ↓ 缓存命中
┌─────────────────────────────────────┐
│  工具定义（固定，可缓存）            │
│  - 工具Schema                        │
│  - 参数定义                          │
└─────────────────────────────────────┘
              ↓ 缓存命中
┌─────────────────────────────────────┐
│  用户消息（动态，不影响缓存）        │
│  - 模板内容                          │
│  - 时间范围                          │
│  - 数据内容                          │
└─────────────────────────────────────┘
```

---

## 实施步骤

### 步骤1: 重构 Prompt 函数（1天）

#### 1.1 修改 `build_template_analysis_prompt`

**文件**: `backend/app/agent/experts/template_report_prompts.py`

```python
# 新增: 固定的系统Prompt
TEMPLATE_ANALYSIS_SYSTEM_PROMPT = """你是一名空气质量报告生成专家。

你的任务是分析历史报告模板，提取数据需求，并为每一类内容设计查询计划。

【可用工具及适用场景】

【工具选择优先级规则】⭐⭐⭐
1. **优先使用 `get_jining_regular_stations`**：查询济宁市各区县/站点的空气质量数据
2. **次优先使用 `get_guangdong_regular_stations`**：查询广东省各城市/站点的空气质量数据
3. **最后使用 `get_air_quality`**：仅当查询的城市不属于济宁市或广东省时使用

【时间维度规则】
模板包含两种时间维度，必须分别查询：
- 【目标月份范围】→ 完整时间段
- 【目标单月】→ 仅最大月份

【查询时间粒度要求】
- 对于完整的单月份和跨月份，时间粒度一般为月度
- 对于单年份，时间粒度一般为年度
- 对于非完整的月份或者跨多日的查询，时间粒度一般为日度
- **强制禁止**：除非用户模板中明确要求"小时"数据，否则绝对不要查询小时粒度数据

【同环比数据要求】
如果模板中需要查询同比/环比数据，所有查询必须返回**两个时间段数据**：
- 当前期（TimePoint）
- 对比期（ContrastTime）

【输出格式要求】
请输出 JSON（不要添加其他解释）：
{
  "data_requirements": [
    {
      "section": "章节标题",
      "tool": "工具名",
      "question": "完整自然语言问题",
      "query_type": "查询类型"
    }
  ]
}
"""

# 修改: 返回系统Prompt和用户消息
def build_template_analysis_prompt(
    template_content: str,
    time_range: Dict[str, Any]
) -> tuple[str, str]:
    """
    构建模板分析Prompt（缓存优化版）

    Returns:
        (system_prompt, user_message): 系统Prompt和用户消息
    """
    display = (
        time_range.get("display")
        or f"{time_range.get('start', '')}至{time_range.get('end', '')}".strip("至")
        or "指定时间范围"
    )

    start_date = time_range.get('start', '')
    end_date = time_range.get('end', '')
    date_range = f"{start_date}至{end_date}"

    # 用户消息（动态内容）
    user_message = f"""请分析以下历史报告模板，提取数据需求。

【历史报告模板】
{template_content}

【目标时间】
{display}

【时间参数】
- 完整时间段: {date_range}
- 开始日期: {start_date}
- 结束日期: {end_date}

请按照系统指令中的格式输出JSON数据需求列表。
"""

    return TEMPLATE_ANALYSIS_SYSTEM_PROMPT, user_message
```

#### 1.2 修改 `build_report_generation_prompt`

```python
# 新增: 固定的系统Prompt
REPORT_GENERATION_SYSTEM_PROMPT = """你是一名空气质量报告撰写专家。

你的任务是对比历史报告模板，结合最新获取的数据，生成完整报告（Markdown）。

【核心要求】

1. **严格遵循模板结构**
   - 必须完全按照历史报告模板的结构、标题层级、章节顺序输出
   - 不得添加模板中没有的章节或内容
   - 不得删除模板中的任何章节
   - 保持与模板相同的表述风格和格式

2. **严禁编造数据**
   - **绝对禁止**编造、推测或虚构任何数据
   - **只能使用**已获取的数据中提供的数据
   - 如果某个数据不存在，必须明确标注"暂缺"或"数据未获取"
   - 不得使用"大约"、"估计"、"可能"等模糊表述

3. **数据替换原则**
   - 用最新数据替换模板中的旧数据
   - 保持数据的准确性和一致性
   - 同比/环比计算必须基于实际数据
   - 城市排名/表格必须严格按照实际数据排序

4. **数据缺失处理**
   - 如果某个指标的数据未获取到，在对应位置明确标注"暂缺"
   - 不得用其他数据替代或编造数据填充
   - 必须保留模板中的结构

5. **输出格式**
   - 输出完整的 Markdown 文本
   - 表格型内容必须用标准 Markdown 表格语法
   - 确保所有数据引用准确，可追溯
"""

# 修改: 返回系统Prompt和用户消息
def build_report_generation_prompt(
    template_content: str,
    collected_data: List[Dict[str, Any]],
    time_range: Dict[str, Any]
) -> tuple[str, str]:
    """
    构建报告生成Prompt（缓存优化版）

    Returns:
        (system_prompt, user_message): 系统Prompt和用户消息
    """
    display = (
        time_range.get("display")
        or f"{time_range.get('start', '')}至{time_range.get('end', '')}".strip("至")
        or "指定时间范围"
    )

    # 用户消息（动态内容）
    user_message = f"""请生成 {display} 的完整报告。

【历史报告模板】
{template_content}

【已获取的数据】
{collected_data}

【目标时间】
{display}

请按照系统指令中的要求生成完整的Markdown报告。
"""

    return REPORT_GENERATION_SYSTEM_PROMPT, user_message
```

### 步骤2: 修改调用逻辑（0.5天）

#### 2.1 修改 `template_report_executor.py`

**文件**: `backend/app/agent/experts/template_report_executor.py`

```python
async def _analyze_template(
    self,
    template_content: str,
    target_time_range: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """调用 LLM 生成数据需求（缓存优化版）"""
    from .template_report_prompts import build_template_analysis_prompt

    # ✅ 获取固定系统Prompt和动态用户消息
    system_prompt, user_message = build_template_analysis_prompt(
        template_content, target_time_range
    )

    # ✅ 使用固定系统Prompt调用LLM
    data = await llm_service.call_llm_with_json_response(
        prompt=user_message,  # 只传用户消息
        system=system_prompt,  # 固定系统Prompt
        max_retries=2
    )

    requirements = data.get("data_requirements", []) if isinstance(data, dict) else []
    logger.info("template_analysis_done", requirement_count=len(requirements))

    return requirements

async def _generate_report(
    self,
    template_content: str,
    collected_data: List[Dict[str, Any]],
    target_time_range: Dict[str, Any]
) -> str:
    """调用 LLM 生成最终报告（缓存优化版）"""
    from .template_report_prompts import build_report_generation_prompt

    # ✅ 获取固定系统Prompt和动态用户消息
    system_prompt, user_message = build_report_generation_prompt(
        template_content=template_content,
        collected_data=collected_data,
        time_range=target_time_range
    )

    # ✅ 使用流式接口 + 固定系统Prompt
    report = await llm_service.chat_stream(
        messages=[{"role": "user", "content": user_message}],
        system=system_prompt,  # 固定系统Prompt
        timeout=600.0,
    )

    clean = llm_service.clean_thinking_tags(report)
    return clean.strip()
```

#### 2.2 修改 `llm_service.py`（如果需要）

**文件**: `backend/app/services/llm_service.py`

确保 `call_llm_with_json_response` 和 `chat_stream` 支持独立的 `system` 参数：

```python
async def call_llm_with_json_response(
    self,
    prompt: str,
    system: Optional[str] = None,  # ✅ 新增参数
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    调用LLM并返回JSON响应（缓存优化版）

    Args:
        prompt: 用户消息
        system: 系统Prompt（固定，可缓存）
        max_retries: 最大重试次数
    """
    messages = [{"role": "user", "content": prompt}]

    # 使用传入的system或默认system
    system_prompt = system or self.default_system_prompt

    # 调用LLM...
    response = await self.client.messages.create(
        model=self.model,
        system=system_prompt,  # ✅ 固定系统Prompt
        messages=messages,
        max_tokens=8000
    )

    # 解析JSON...
    return parsed_json

async def chat_stream(
    self,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,  # ✅ 新增参数
    timeout: float = 300.0
) -> str:
    """
    流式调用LLM（缓存优化版）

    Args:
        messages: 消息历史
        system: 系统Prompt（固定，可缓存）
        timeout: 超时时间
    """
    system_prompt = system or self.default_system_prompt

    # 流式调用...
    async with self.client.messages.stream(
        model=self.model,
        system=system_prompt,  # ✅ 固定系统Prompt
        messages=messages,
        max_tokens=8000
    ) as stream:
        # 收集响应...

    return full_response
```

### 步骤3: 添加缓存监控（0.5天）

#### 3.1 添加缓存指标收集

**文件**: `backend/app/services/llm_service.py`

```python
class LLMService:
    def __init__(self):
        # ... 现有初始化 ...

        # ✅ 新增: 缓存统计
        self.cache_stats = {
            "total_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_writes": 0
        }

    async def call_llm_with_json_response(self, ...):
        # ... 调用LLM ...

        # ✅ 收集缓存统计
        self.cache_stats["total_calls"] += 1

        if hasattr(response, "usage"):
            usage = response.usage
            if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens > 0:
                self.cache_stats["cache_hits"] += 1
                logger.info(
                    "llm_cache_hit",
                    cache_read_tokens=usage.cache_read_input_tokens
                )
            else:
                self.cache_stats["cache_misses"] += 1

            if hasattr(usage, "cache_creation_input_tokens") and usage.cache_creation_input_tokens > 0:
                self.cache_stats["cache_writes"] += 1

        return parsed_json

    def get_cache_hit_rate(self) -> float:
        """获取缓存命中率"""
        if self.cache_stats["total_calls"] == 0:
            return 0.0
        return self.cache_stats["cache_hits"] / self.cache_stats["total_calls"]

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        hit_rate = self.get_cache_hit_rate()
        return {
            **self.cache_stats,
            "cache_hit_rate": hit_rate,
            "cache_hit_rate_percent": f"{hit_rate * 100:.1f}%"
        }
```

#### 3.2 添加监控端点

**文件**: `backend/app/routers/report_generation.py`

```python
@router.get("/cache-stats")
async def get_cache_stats():
    """
    获取LLM缓存统计

    Returns:
        缓存命中率、调用次数等统计信息
    """
    from app.services.llm_service import llm_service

    stats = llm_service.get_cache_stats()

    return {
        "success": True,
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }
```

---

## 测试验证

### 测试1: 缓存命中率测试

**目标**: 验证缓存命中率达到60%+

```python
# tests/test_cache_optimization.py
import pytest
from app.services.llm_service import llm_service
from app.agent.experts.template_report_executor import TemplateReportExecutor

@pytest.mark.asyncio
async def test_cache_hit_rate():
    """测试缓存命中率"""
    executor = TemplateReportExecutor()

    # 重置缓存统计
    llm_service.cache_stats = {
        "total_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "cache_writes": 0
    }

    # 执行3次相同模板的分析（应该命中缓存）
    template = "# 测试报告\n## 总体状况\n..."
    time_range = {"start": "2025-01-01", "end": "2025-07-31"}

    for i in range(3):
        await executor._analyze_template(template, time_range)

    # 验证缓存命中率
    hit_rate = llm_service.get_cache_hit_rate()
    assert hit_rate >= 0.6, f"缓存命中率过低: {hit_rate:.1%}"

    print(f"✅ 缓存命中率: {hit_rate:.1%}")
    print(f"   总调用: {llm_service.cache_stats['total_calls']}")
    print(f"   缓存命中: {llm_service.cache_stats['cache_hits']}")
    print(f"   缓存未命中: {llm_service.cache_stats['cache_misses']}")
```

### 测试2: 系统Prompt固定性测试

**目标**: 验证系统Prompt不随输入变化

```python
@pytest.mark.asyncio
async def test_system_prompt_immutability():
    """测试系统Prompt固定性"""
    from app.agent.experts.template_report_prompts import (
        build_template_analysis_prompt,
        TEMPLATE_ANALYSIS_SYSTEM_PROMPT
    )

    # 不同的输入
    inputs = [
        ("模板1", {"start": "2025-01-01", "end": "2025-07-31"}),
        ("模板2", {"start": "2024-01-01", "end": "2024-12-31"}),
        ("模板3", {"start": "2023-06-01", "end": "2023-12-31"}),
    ]

    system_prompts = []
    for template, time_range in inputs:
        system, user = build_template_analysis_prompt(template, time_range)
        system_prompts.append(system)

    # 验证所有系统Prompt完全相同
    assert all(s == TEMPLATE_ANALYSIS_SYSTEM_PROMPT for s in system_prompts), \
        "系统Prompt不固定，会破坏缓存！"

    print("✅ 系统Prompt固定性测试通过")
```

### 测试3: 成本对比测试

**目标**: 验证成本节省效果

```python
@pytest.mark.asyncio
async def test_cost_comparison():
    """测试成本对比"""
    # 模拟100次调用
    num_calls = 100
    avg_tokens = 50000

    # 价格（假设）
    price_per_1k_tokens = 0.003  # $0.003/1K tokens
    cache_read_multiplier = 0.1
    cache_write_multiplier = 1.25

    # 无缓存成本
    cost_no_cache = (num_calls * avg_tokens / 1000) * price_per_1k_tokens

    # 有缓存成本（假设60%命中率）
    cache_hit_rate = 0.6
    cache_hits = num_calls * cache_hit_rate
    cache_misses = num_calls * (1 - cache_hit_rate)

    cost_with_cache = (
        (cache_hits * avg_tokens / 1000) * price_per_1k_tokens * cache_read_multiplier +
        (cache_misses * avg_tokens / 1000) * price_per_1k_tokens * cache_write_multiplier
    )

    savings = cost_no_cache - cost_with_cache
    savings_percent = (savings / cost_no_cache) * 100

    print(f"✅ 成本对比:")
    print(f"   无缓存成本: ${cost_no_cache:.2f}")
    print(f"   有缓存成本: ${cost_with_cache:.2f}")
    print(f"   节省: ${savings:.2f} ({savings_percent:.1f}%)")

    assert savings_percent >= 80, f"成本节省不足: {savings_percent:.1f}%"
```

---

## 监控指标

### 关键指标

| 指标 | 目标值 | 监控方式 |
|------|--------|---------|
| 缓存命中率 | ≥60% | `/report/cache-stats` API |
| 平均响应时间 | -40% | 日志分析 |
| 每日成本 | ≤$30 | Claude API Dashboard |
| 系统Prompt变化次数 | 0 | 代码审查 |

### 监控命令

```bash
# 查看缓存统计
curl http://localhost:8000/report/cache-stats

# 预期输出
{
  "success": true,
  "stats": {
    "total_calls": 150,
    "cache_hits": 95,
    "cache_misses": 55,
    "cache_writes": 55,
    "cache_hit_rate": 0.633,
    "cache_hit_rate_percent": "63.3%"
  },
  "timestamp": "2026-01-27T10:30:00"
}
```

### 告警规则

- ⚠️ 缓存命中率 < 50%: 检查系统Prompt是否被修改
- ⚠️ 每日成本 > $50: 检查调用次数是否异常
- ⚠️ 响应时间增加 > 20%: 检查缓存服务是否正常

---

## 验收标准

- [ ] 系统Prompt完全固定，不包含任何动态内容
- [ ] 动态内容全部移至用户消息
- [ ] 缓存命中率达到60%以上
- [ ] 成本节省达到80%以上
- [ ] 所有测试用例通过
- [ ] 监控端点正常工作

---

**实施负责人**: [待分配]
**预计完成时间**: 2天
**文档更新**: 2026-01-27
