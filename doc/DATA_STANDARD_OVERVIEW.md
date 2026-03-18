# 数据标准化现状调研

> 目标：梳理现有 REACT Agent 中各工具对数据的依赖、字段格式与差异，为统一 Schema 与质量校验提供输入。

## 1. 当前数据来源与流向

- **get_component_data**（`backend/app/tools/query/get_component_data/tool.py`）  
  - 上游：VOCs 接口 `settings.vocs_data_api_url`、颗粒物接口 `settings.particulate_data_api_url`。  
  - 下游：直接返回给 LLM/后续工具，当前无 Schema 校验。  
  - 数据落地：调用 `SessionMemory.save_data_to_file` 写入 `data_{n}.json`，并记录采样数据到工作记忆。
- **calculate_pmf**（`backend/app/tools/analysis/calculate_pmf/tool.py`）  
  - 输入：需要完整的 VOCs 或颗粒物样本数组（至少 30/20 条）。  
  - 目前由 LLM 将 `get_component_data` 的原始结果直接丢入，无统一字段映射与质量标记。
- **load_data_from_memory**（`backend/app/agent/tools/load_data_from_memory.py`）  
  - 输入：`data_ref`（文件名），输出：JSON 文件原文 + 简单摘要。  
  - 现状：缺少元数据描述，LLM 需要自行理解字段。
- **WorkingMemory / SessionMemory**（`backend/app/agent/memory/working_memory.py` 等）  
  - 保存的是工具返回的原始字典或采样片段，没有标准化的结构说明。

## 2. 关键字段清单与差异

| 模块 | 主要字段 | 字段来源 | 现有问题 |
| --- | --- | --- | --- |
| VOCs 小时数据 | `TimePoint`, `StationName`, 各 VOC 物种（英/中文混用） | 上游接口 JSON | 字段名中英混杂、部分值为 `"—"`/`"null"`、默认单位不统一（ppb/µg/m³） |
| 颗粒物组分 | `time`, `SO4`, `NO3`, `NH4`, `OC`, `EC` 等 | 上游接口 JSON | 字段名称大小写不一、部分缺失，暂无缺失值处理策略 |
| PMF 输入 | 期望：`time`, `component` 数值字段 | LLM 直接拼装 | 样本量、必需字段无硬校验；异常值/缺失值可能导致 PMF 失败 |
| Agent 记忆文件 | `data_{n}.json`、`sampled_data` | SessionMemory | 缺少元信息（数据类型、时间范围、单位），LLM 需猜测 |

## 3. 当前痛点

1. **字段不统一**：不同工具对同一数据的字段命名、单位要求不一致，LLM 需要推测，错误率高。  
2. **缺少 Schema 校验**：原始数据直接交给后续算法，异常值（负数、缺失字符串）不提前过滤。  
3. **无数据质量指标**：无法判断数据是否补齐、是否可信，导致 PMF 等模型容易失败。  
4. **数据引用混乱**：只用 `data_ref` 定位文件，缺乏数据类型与版本信息，跨工具复用困难。

## 4. 统一 Schema 与质量校验需求

- 需要为 VOCs、颗粒物、PMF 结果等定义标准化的 `pydantic` 模型，含字段类型、单位、可选/必填说明。
- 建立缺失值、异常值检测规则，并生成质量报告（缺失率、异常字段、修复措施）。
- 数据注册中心需记录数据类型、Schema 版本、存储位置、样本量、时间范围、质量标签。
- 工具输入/输出必须与 Schema 对齐，只接受 `data_id` + 参数，拒绝裸 JSON。

## 5. 下一步实施要点

1. 创建 `backend/app/schemas/` 目录，沉淀 VOCs、颗粒物、PMF 等数据模型。  
2. 引入 `validators/` 模块，对解析结果进行结构与逻辑双重校验。  
3. 搭建 `DataRegistryService`，统一管理数据落地与引用。  
4. 重构 `get_component_data`、`calculate_pmf` 等工具，使其入参/出参都遵循约定的数据契约。  
5. 为 LLM/工具提供 `DataAccessClient`，通过 `data_id` 获取采样/全量数据，并附带质量元信息。

---

## 6. 已落地进展（滚动更新）

- 新增 `backend/app/schemas/` 目录，定义 VOCs、颗粒物和 PMF 统一模型，以及质量报告结构。  
- 新增 `backend/app/validators/`，实现 VOCs 与颗粒物样本的结构化校验与字段统计输出。  
- 初步实现 `DataRegistryService`（`backend/app/services/data_registry.py`），支持数据集注册、采样存储、质量报告挂载。
