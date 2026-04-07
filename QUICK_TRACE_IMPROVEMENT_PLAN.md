# 快速溯源任务清单改进方案

## 更新时间
2026-03-29

## 基于对比分析的改进方案

根据 `QUICK_TRACE_COMPARISON_ANALYSIS.md` 的分析结果，我们需要对 `quick_trace_standard_multi_agent.md` 进行以下改进。

---

## 一、必须修复的问题（Priority 1）

### 1. 补充区域对比分析任务

**问题**: 缺少周边城市数据对比，无法判断本地生成 vs 区域传输

**解决方案**: 在任务2和任务3之间插入新任务

```markdown
### 任务2.5：区域对比分析【气象专家子Agent】
- **专家**：🌤️ 气象分析专家
- **工具**：`call_sub_agent`
- **参数**：
  - `target_mode`: "expert"
  - `task_description`: "分析周边城市空气质量，判断本地生成vs区域传输"
  - `context`: {
      "expert_prompt_file": "backend/config/prompts/weather_expert.md",
      "data_ids": ["station_info:xxx"]
    }
- **依赖**：任务1完成
- **输出**：区域对比分析报告（MD格式）
- **TodoWrite示例**：`{'content': '区域对比分析（气象专家）', 'status': 'pending'}`

**执行方式**：
```python
call_sub_agent(
    target_mode="expert",
    task_description="""
    分析周边城市空气质量，判断本地生成vs区域传输。

    分析要求：
    1. 读取专家提示词文件：backend/config/prompts/weather_expert.md
    2. 使用 data_id: "station_info:xxx" 获取站点信息
    3. 调用工具获取周边站点空气质量数据：
       - 优先：get_nearby_stations 获取周边站点列表
       - 然后：get_guangdong_regular_stations 获取周边站点数据
    4. 进行时序对比分析：
       - 目标站点与周边站点的浓度时序对比
       - 时间滞后相关性分析
       - 峰值出现时间对比
    5. 判断成因：本地生成主导 / 区域传输主导 / 混合型
    6. 生成专业的区域对比分析报告（MD格式）
    """,
    context={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",
        "data_ids": ["station_info:xxx"]
    }
)
# 返回 data_id: "regional_comparison:xxx"
```

**子Agent工作流程**：
1. 读取专家提示词文件，了解"区域时序对比分析"框架
2. 读取站点数据（通过 data_id）
3. 获取周边站点数据
4. 进行时序对比分析
5. 判断本地生成 vs 区域传输
6. 生成专业分析报告（MD格式）
```

**气象专家提示词已包含的框架**（第1节）：
```markdown
1. **区域时序对比分析**（判断本地生成vs区域传输）
   - 目标与周边城市/站点的PM2.5/PM10浓度时序对比
   - 时间滞后相关性分析：判断传输方向和贡献大小
   - 峰值出现时间对比：周边先升高→区域传输；目标先升高→本地生成
   - 成因诊断结论：本地生成主导 / 区域传输主导 / 混合型
```

---

## 二、重要改进（Priority 2）

### 2. 补充天气预报数据

**问题**: 缺少未来15天预报，无法判断未来污染趋势

**解决方案**: 修改任务2，增加天气预报工具调用

```markdown
### 任务2：气象数据分析【气象专家子Agent】（修订版）
- **专家**：🌤️ 气象分析专家
- **工具**：`call_sub_agent`
- **参数**：
  - `target_mode`: "expert"
  - `task_description`: "分析气象条件对污染扩散的影响（包含历史数据和预报数据）"
  - `context`: {
      "expert_prompt_file": "backend/config/prompts/weather_expert.md",
      "data_ids": ["station_info:xxx"]
    }
- **依赖**：任务1完成
- **输出**：气象条件分析报告（MD格式）+ 未来趋势预测
- **TodoWrite示例**：`{'content': '气象数据分析（气象专家）', 'status': 'pending'}`

**执行方式**：
```python
call_sub_agent(
    target_mode="expert",
    task_description="""
    分析气象条件对污染扩散的影响（包含历史数据和预报数据）。

    分析要求：
    1. 读取专家提示词文件：backend/config/prompts/weather_expert.md
    2. 使用 data_id: "station_info:xxx" 获取站点信息
    3. 调用气象数据工具：
       a) get_weather_data：获取历史气象数据（前3天ERA5数据）
       b) get_weather_forecast：获取未来15天预报数据
          - forecast_days=15
          - past_days=1（获取昨天+今天00:00~当前时刻完整数据）
          - hourly=True, daily=True
    4. 生成专业的气象条件分析报告（MD格式），包含：
       - 历史气象条件分析
       - 未来气象趋势预测
       - 污染潜势判断
       - 改善时机预测
    """,
    context={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",
        "data_ids": ["station_info:xxx"]
    }
)
# 返回 data_id: "weather_analysis:xxx"
```

**气象专家提示词已包含的框架**（第8节）：
```markdown
## 8. 气象预报与污染潜势

**天气预报数据分析**（重要：如系统提供了预报数据，必须使用）
- 预报数据完整性：检查是否包含未来1-16天的预报数据
- 边界层高度预报：分析未来几天PBLH变化趋势，判断扩散条件改善时间
- 风场预报：主导风向、风速变化，预测污染传输路径变化
- 温湿度预报：温度范围、湿度变化，评估二次生成条件

**污染趋势预测**
- 未来24-48h污染潜势（基于天气形势）
- 污染过程持续性（类似条件重现概率）
- 爆发触发条件（不利气象的临界值）
- 改善时机（有利气象的时间窗口，重点：PBLH升高、风速增大、降水过程）

**应对策略**
- 提前预警时间窗口
- 应急响应启动时机
- 管控措施生效时间
```

---

## 三、建议改进（Priority 3）

### 3. 补充天气形势图解读（可选）

**问题**: 缺少大尺度天气系统分析

**解决方案**: 添加可选任务

```markdown
### 任务2.6：天气形势图解读【气象专家子Agent】（可选）
- **专家**：🌤️ 气象分析专家
- **工具**：`call_sub_agent`
- **参数**：
  - `target_mode`: "expert"
  - `task_description`: "解读中央气象台天气形势图"
  - `context`: {
      "expert_prompt_file": "backend/config/prompts/weather_expert.md",
      "data_ids": ["station_info:xxx"]
    }
- **依赖**：任务1完成
- **可选**：是（如无图片数据可跳过）
- **输出**：天气形势图解读报告（MD格式）
- **TodoWrite示例**：`{'content': '天气形势图解读（气象专家）', 'status': 'pending'}`

**执行方式**：
```python
call_sub_agent(
    target_mode="expert",
    task_description="""
    解读中央气象台天气形势图。

    分析要求：
    1. 读取专家提示词文件：backend/config/prompts/weather_expert.md
    2. 使用 data_id: "station_info:xxx" 获取站点信息
    3. 调用 get_weather_situation_map 工具：
       - date: 分析日期（格式：YYYYMMDD）
       - analysis_focus: "污染扩散条件"
    4. 生成专业的天气形势图解读报告（MD格式）
    """,
    context={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",
        "data_ids": ["station_info:xxx"]
    }
)
# 返回 data_id: "weather_situation:xxx"
```
```

---

## 四、必须修复的问题（Priority 1）

### 4. 修正化学专家提示词路径

**问题**: 任务清单中写的是 `chemical_expert.md`，实际文件是 `chemical_expert_pm.md` 和 `chemical_expert_o3.md`

**解决方案**: 根据污染物类型动态选择提示词文件

```markdown
### 任务5：污染物组分分析【化学专家子Agent】（修订版）
- **专家**：🧪 化学分析专家
- **工具**：`call_sub_agent`
- **参数**：
  - `target_mode`: "expert"
  - `task_description`: "分析污染物组分，推断污染来源"
  - **context**: {
      "expert_prompt_file": "根据污染物类型动态选择",
        - PM2.5 → "backend/config/prompts/chemical_expert_pm.md"
        - O3 → "backend/config/prompts/chemical_expert_o3.md"
      "data_ids": ["station_info:xxx"]
    }
- **依赖**：任务1完成（可与任务2-4并行）
- **可选**：是（如无数据可跳过）
- **输出**：污染物组分分析报告（MD格式）
- **TodoWrite示例**：`{'content': '污染物组分分析（化学专家）', 'status': 'pending'}`

**执行方式**：
```python
# 根据污染物类型选择提示词文件
expert_prompt_file = (
    "backend/config/prompts/chemical_expert_pm.md"
    if pollutant == "PM2.5"
    else "backend/config/prompts/chemical_expert_o3.md"
)

call_sub_agent(
    target_mode="expert",
    task_description=f"""
    分析污染物组分，推断污染来源。

    分析要求：
    1. 读取专家提示词文件：{expert_prompt_file}
    2. 使用 data_id: "station_info:xxx" 获取站点信息
    3. 根据污染物类型调用相应工具：
       - O3 → get_vocs_data
       - PM2.5 → get_pm25_ionic
    4. 生成专业的组分分析报告（MD格式）
    """,
    context={
        "expert_prompt_file": expert_prompt_file,
        "data_ids": ["station_info:xxx"]
    }
)
# 返回 data_id: "component_analysis:xxx"
```

**说明**：
- PM2.5 使用 `chemical_expert_pm.md`（颗粒物化学分析）
- O3 使用 `chemical_expert_o3.md`（臭氧光化学分析）
- 两个提示词文件已提取并更新为原版专业提示词
```

---

## 五、更新后的完整任务清单

### 任务列表（修订版）

```
任务1：定位站点
  ↓
任务2：气象数据分析【气象专家】
  ├─ 历史气象数据（ERA5）
  └─ 天气预报数据（15天预报）✨ 新增
  ↓
任务2.5：区域对比分析【气象专家】✨ 新增
  ├─ 周边站点数据获取
  └─ 时序对比分析
  ↓
任务2.6：天气形势图解读【气象专家】（可选）✨ 新增
  ↓
任务3：后向轨迹分析【轨迹专家】
  ↓
任务4：上风向企业分析【轨迹专家】
  ↓
任务5：污染物组分分析【化学专家】✨ 修订
  ├─ PM2.5 → chemical_expert_pm.md
  └─ O3 → chemical_expert_o3.md
  ↓
任务6：生成综合报告【报告专家】
  ├─ 汇总所有专家分析
  └─ 生成综合溯源结论和管控建议
```

---

## 六、实施步骤

### 步骤1：备份原文件
```bash
cp backend/config/task_lists/quick_trace_standard_multi_agent.md \
   backend/config/task_lists/quick_trace_standard_multi_agent.md.backup
```

### 步骤2：更新任务清单文件
按照上述改进方案，逐项更新 `quick_trace_standard_multi_agent.md`

### 步骤3：验证更新
- 检查所有任务依赖关系是否正确
- 确认所有提示词文件路径正确
- 确认所有工具调用参数正确

### 步骤4：测试验证
- 使用测试站点运行完整流程
- 检查每个任务的输出是否正确
- 验证数据流转是否正确

### 步骤5：文档更新
- 更新 `MULTI_AGENT_DESIGN.md`
- 更新 `PROMPT_UPDATE_SUMMARY.md`
- 创建改进说明文档

---

## 七、预期效果

### 改进前 vs 改进后

| 维度 | 改进前 | 改进后 |
|------|--------|--------|
| **完整性** | 缺少区域对比、天气预报 | ✅ 包含所有关键分析 |
| **准确性** | 无法判断本地vs传输 | ✅ 可准确判断成因 |
| **前瞻性** | 无法预测未来趋势 | ✅ 可预测改善时机 |
| **专业性** | 使用专业提示词 | ✅ 使用原版专业提示词 |
| **通用性** | 任意站点 | ✅ 任意站点 |
| **耗时** | 约3分钟 | 约3-5分钟（增加功能） |

### 核心价值提升

1. **溯源准确性提升**: 区域对比分析可准确判断本地生成 vs 区域传输
2. **管控前瞻性提升**: 天气预报可预测污染趋势和改善时机
3. **分析深度提升**: 天气形势图解读提供大尺度天气系统分析
4. **系统专业性提升**: 使用原版专业提示词，确保分析质量

---

## 八、风险评估

### 低风险改进
- ✅ 补充天气预报数据：气象专家提示词已包含相应框架
- ✅ 修正化学专家提示词路径：仅修正路径，不改变功能

### 中风险改进
- ⚠️ 补充区域对比分析：需要确认周边站点数据工具是否可用
- ⚠️ 补充天气形势图解读：依赖外部AI服务（通义千问VL）

### 缓解措施
- 区域对比分析设为可选任务，如无数据可跳过
- 天气形势图解读设为可选任务，如失败不影响主流程
- 充分测试验证，确保不影响现有功能

---

**生成时间**: 2026-03-29
**方案版本**: v1.0
**状态**: 待审核和实施
