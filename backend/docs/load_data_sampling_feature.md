# load_data_from_memory 智能采样功能 - 实现总结

## 📋 功能概述

为 `load_data_from_memory` 工具添加了**智能采样功能**，在工具调用时就控制数据量，避免加载大量数据导致 token 超限。

## ✅ 实现内容

### 1. 工具参数增强

**文件**: `backend/app/agent/tool_adapter.py`

```python
async def load_data_from_memory(
    data_id: str,
    max_records: int = 100,  # 新增参数
    context=None,
    **kwargs
)
```

**参数说明**:
- `data_id`: 数据引用ID（完整ID，如 'vocs_unified:v1:abc123'）
- `max_records`: 最大返回记录数（默认100，用于控制token消耗）

### 2. 智能采样算法

**函数**: `_smart_sample_data_for_load(data, max_records)`

**采样策略**: **首尾30% + 中间40%均匀采样**

- **首部30%**：保留时间序列起点数据（`data[:head_count]`）
- **中部40%**：均匀采样中间部分（`data[middle_start:middle_end:step]`）
- **尾部30%**：保留时间序列终点数据（`data[-tail_count:]`）

**示例**：
- 原始数据：1000条
- `max_records=100`
- 采样结果：前30条 + 中间40条（均匀） + 后30条 = 100条

### 3. 返回元数据增强

```python
{
    "status": "success",
    "success": True,
    "data": [...],  # 采样后的数据
    "metadata": {
        "data_id": "vocs_unified:v1:abc123",
        "original_count": 1000,      # 原始记录数
        "truncated": True,            # 是否被截断
        "sampling_info": {            # 采样详细信息
            "strategy": "head_tail_middle_sampling",
            "head_samples": 30,
            "middle_samples": 40,
            "tail_samples": 30,
            "retention_ratio": 0.1,
            "original_count": 1000,
            "sampled_count": 100
        }
    },
    "summary": "成功加载数据 vocs_unified:v1:abc123（共1000条记录，返回100条）"
}
```

### 4. 工具Schema更新

**文件**: `backend/app/agent/tool_adapter.py:767-800`

```python
{
    "name": "load_data_from_memory",
    "description": "从外部化存储读取数据（智能采样，避免token超限）...",
    "parameters": {
        "data_id": {"type": "string", ...},
        "max_records": {
            "type": "integer",
            "default": 100,
            "description": "最大返回记录数，用于控制token消耗..."
        }
    }
}
```

## 🎯 设计原则

### 1. 工具层控制数据量
- **在工具调用时**就进行采样，而不是依赖上层截断
- 减轻后续层级的压力

### 2. 适合时间序列数据
- 保留首尾数据（时间序列的起点和终点）
- 中间均匀采样（保留趋势）

### 3. 完整的元数据
- `original_count`: 原始数据量
- `truncated`: 是否被截断
- `sampling_info`: 详细的采样信息

### 4. 向后兼容
- 小数据集（`<= max_records`）不采样
- 默认 `max_records=100`，LLM可以自定义

## 📊 测试结果

**测试文件**: `backend/tests/test_load_data_simple.py`

```
✅ 测试1：小数据集（10条 < max_records=100）- 不采样
✅ 测试2：大数据集（1000条 > max_records=100）- 智能采样
   - 采样比例：首30 + 中40 + 尾30 = 100
   - 保留比例：10%
✅ 测试3：自定义max_records=50 - 正常工作
✅ 测试4：数据连续性验证 - 首尾ID正确（0 → 999）
```

## 🔍 与其他层级的配合

### 当前数据截断机制（4层防护）

1. **工具层（本次修改）**：`load_data_from_memory` 智能采样
   - **触发时机**：工具调用时
   - **采样策略**：首尾30% + 中间40%
   - **控制参数**：`max_records`

2. **上下文加载器**：`IntelligentContextLoader._format_data_for_llm`
   - **触发时机**：上下文构造时
   - **采样策略**：最多100条样本
   - **Token预算**：30K tokens

3. **Token预算管理器**：`TokenBudgetManager._truncate_to_tokens`
   - **触发时机**：构造prompt时
   - **采样策略**：二分查找最佳截断点
   - **精确计算**：使用tiktoken

4. **两阶段工具加载**：`Planner._extract_relevant_context`
   - **触发时机**：第二阶段参数构造
   - **压缩比**：60-80%
   - **保留内容**：最近3轮 + data_id

## 📝 使用示例

### 示例1：默认参数
```python
# LLM调用
load_data_from_memory(data_id="vocs_unified:v1:abc123")
# 返回：最多100条记录
```

### 示例2：自定义记录数
```python
# LLM调用
load_data_from_memory(
    data_id="vocs_unified:v1:abc123",
    max_records=50
)
# 返回：最多50条记录
```

### 示例3：大数据集采样
```python
# 原始数据：10000条VOCs样本
result = load_data_from_memory(
    data_id="vocs_unified:v1:large_data",
    max_records=100
)

# 返回结果
{
    "data": [...],  # 100条采样数据
    "metadata": {
        "original_count": 10000,
        "truncated": True,
        "sampling_info": {
            "strategy": "head_tail_middle_sampling",
            "head_samples": 30,
            "middle_samples": 40,
            "tail_samples": 30,
            "retention_ratio": 0.01  # 只保留1%
        }
    }
}
```

## 🎁 优势

1. **提前控制**：在工具调用时就控制数据量，避免不必要的数据传输
2. **智能采样**：保留时间序列特征，适合趋势分析
3. **灵活可调**：LLM可以根据需要调整 `max_records`
4. **完整追溯**：元数据记录采样详情，便于分析
5. **向后兼容**：不影响现有功能

## 📌 后续优化建议

1. **更智能的采样策略**：
   - 基于污染程度采样（保留高污染样本）
   - 基于时间密度的采样（高峰期密集采样）

2. **自适应 max_records**：
   - 根据数据类型自动调整
   - VOCs数据默认100，气象数据默认50

3. **统计摘要**：
   - 即使采样也返回统计信息（均值、最大值、最小值等）
   - 帮助LLM理解完整数据分布

## 📂 修改文件清单

- ✅ `backend/app/agent/tool_adapter.py` - 工具定义和Schema
- ✅ `backend/tests/test_load_data_simple.py` - 测试脚本

## ⚠️ 注意事项

1. **采样数据不代表完整数据**：LLM需要在总结中说明数据已采样
2. **时间序列分析**：采样策略适合时间序列，其他类型数据可能需要不同策略
3. **max_records不是硬限制**：如果数据量小于max_records，返回全部数据
