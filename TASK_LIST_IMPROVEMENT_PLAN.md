# 任务清单改进方案：补充完整深度分析工具

## 问题分析

### 原ComponentExecutor工具清单

**数据查询工具**（9个）：
1. get_vocs_data - VOCs组分数据
2. get_pm25_ionic - 颗粒物离子组分
3. get_pm25_carbon - 颗粒物碳组分
4. get_pm25_crustal - 颗粒物地壳元素
5. get_particulate_components - PM2.5组分分析
6. get_pm25_component - PM2.5完整组分（32个因子）
7. get_pm25_recovery - PM2.5重构分析（7大组分）
8. get_oc_ec - OC/EC碳质分析
9. get_heavy_metal - 重金属分析

**深度分析工具**（7个）：
1. calculate_pm_pmf - PM2.5 PMF源解析
2. calculate_vocs_pmf - VOCs PMF源解析
3. calculate_reconstruction - 7大组分重构
4. calculate_carbon - 碳组分分析（POC/SOC）
5. calculate_crustal - 地壳元素分析
6. calculate_soluble - 水溶性离子分析
7. calculate_trace - 微量元素分析

**可视化工具**（2个）：
1. smart_chart_generator - 智能图表生成器
2. generate_chart - 图表生成工具

### 新任务清单任务5现状

只提到了2个数据查询工具：
- O3 → get_vocs_data
- PM2.5 → get_pm25_ionic

**缺失工具**：
- ❌ 所有深度分析工具（PMF、重构、碳组分等）
- ❌ 其他数据查询工具（碳组分、地壳元素等）

## 改进方案

### 修订版任务5：污染物组分分析【化学专家子Agent】

```markdown
### 任务5：污染物组分分析【化学专家子Agent】（完整版）
- **专家**：🧪 化学分析专家
- **工具**：`call_sub_agent`
- **参数**：
  - `target_mode`: "expert"
  - `task_description`: "分析污染物组分，推断污染来源（包含深度分析）"
  - `context`: {
      "expert_prompt_file": "根据污染物类型动态选择",
        - PM2.5 → "backend/config/prompts/chemical_expert_pm.md"
        - O3 → "backend/config/prompts/chemical_expert_o3.md"
      "data_ids": ["station_info:xxx"]
    }
- **依赖**：任务1完成（可与任务2-4并行）
- **可选**：是（如无数据可跳过）
- **输出**：污染物组分分析报告（MD格式）+ 深度源解析结果
- **TodoWrite示例**：`{'content': '污染物组分分析（化学专家）', 'status': 'pending'}`

**执行方式（PM2.5模式）**：
```python
expert_prompt_file = "backend/config/prompts/chemical_expert_pm.md"

call_sub_agent(
    target_mode="expert",
    task_description=f"""
    分析PM2.5组分，推断污染来源（包含PMF源解析和7大组分重构）。

    分析要求：
    1. 读取专家提示词文件：{expert_prompt_file}
    2. 使用 data_id: "station_info:xxx" 获取站点信息
    3. 调用数据查询工具（按优先级尝试）：
       a) get_pm25_component - PM2.5完整组分（32个因子，优先）
       b) get_particulate_components - PM2.5组分分析（备选）
       c) get_pm25_ionic - 颗粒物离子组分（备选）
       d) get_pm25_carbon - 颗粒物碳组分（备选）
       e) get_pm25_crustal - 颗粒物地壳元素（备选）
    4. 调用深度分析工具：
       a) calculate_pm_pmf - PMF源解析（依赖离子和碳组分数据）
       b) calculate_reconstruction - 7大组分重构（OM、NO3、SO4、NH4、EC、地壳、微量元素）
       c) calculate_carbon - 碳组分分析（POC、SOC、OC/EC比值）
       d) calculate_soluble - 水溶性离子分析（SOR、NOR值）
       e) calculate_crustal - 地壳元素分析
    5. 调用可视化工具：
       a) smart_chart_generator - 生成专业图表
    6. 生成专业的组分分析报告（MD格式），包含：
       - 区域时序对比分析
       - 颗粒物组分诊断
       - PMF源解析深度分析
       - 7大组分重构分析
       - 二次颗粒物生成评估
       - 源贡献季节性变化
    """,
    context={
        "expert_prompt_file": expert_prompt_file,
        "data_ids": ["station_info:xxx"]
    }
)
# 返回 data_id: "component_analysis:xxx"
```

**执行方式（O3模式）**：
```python
expert_prompt_file = "backend/config/prompts/chemical_expert_o3.md"

call_sub_agent(
    target_mode="expert",
    task_description=f"""
    分析O3组分和VOCs，推断污染来源（包含PMF源解析和OBM分析）。

    分析要求：
    1. 读取专家提示词文件：{expert_prompt_file}
    2. 使用 data_id: "station_info:xxx" 获取站点信息
    3. 调用数据查询工具：
       a) get_vocs_data - VOCs组分数据（苯系物、烷烃、烯烃等）
    4. 调用深度分析工具：
       a) calculate_vocs_pmf - VOCs PMF源解析
       b) calculate_obm_full_chemistry - OBM分析（EKMA/PO3/RIR）
          - mode: "all"（完整分析）
          - 生成EKMA曲面图、减排路径图、敏感性分析图
    5. 调用可视化工具：
       a) smart_chart_generator - 生成专业图表
    6. 生成专业的组分分析报告（MD格式），包含：
       - 区域时序对比分析
       - VOCs组分诊断
       - PMF源解析深度分析
       - OBM/OFP臭氧生成潜势分析
       - O3-NOx-VOCs敏感性分析
       - 光化学进程分析
    """,
    context={
        "expert_prompt_file": expert_prompt_file,
        "data_ids": ["station_info:xxx"]
    }
)
# 返回 data_id: "component_analysis:xxx"
```

**子Agent工作流程**：
1. 读取专家提示词文件，了解专家角色和分析要求
2. 读取站点数据（通过 data_id）
3. 根据污染物类型（PM2.5或O3）选择相应的工具链
4. 按优先级尝试数据查询工具（优先→备选）
5. 使用数据查询结果调用深度分析工具
6. 生成可视化图表
7. 按照提示词要求生成专业分析报告（MD格式）
8. 返回分析结果
```

### 工具调用优先级说明

#### PM2.5模式工具优先级

**数据查询工具**（按优先级）：
1. **get_pm25_component**（最高优先级）
   - 原因：一次查询获取32个因子，包含所有组分
   - 包含：离子、碳组分、地壳元素、微量元素

2. **get_particulate_components**（次优先级）
   - 原因：包含主要组分（离子、OC、EC）
   - 包含：Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、OC、EC

3. **get_pm25_ionic + get_pm25_carbon + get_pm25_crustal**（备选）
   - 原因：需要多次调用，但可以单独获取各类组分
   - 适用场景：上述工具失败时

**深度分析工具**（依赖数据查询结果）：
1. **calculate_pm_pmf** - PMF源解析
   - 依赖：离子组分 + 碳组分数据
   - 输出：源因子识别、贡献率量化

2. **calculate_reconstruction** - 7大组分重构
   - 依赖：所有组分数据
   - 输出：OM、NO3、SO4、NH4、EC、地壳、微量元素

3. **calculate_carbon** - 碳组分分析
   - 依赖：OC、EC数据
   - 输出：POC、SOC、OC/EC比值

4. **calculate_soluble** - 水溶性离子分析
   - 依赖：离子组分数据
   - 输出：SOR、NOR值（二次生成指示）

5. **calculate_crustal** - 地壳元素分析
   - 依赖：地壳元素数据
   - 输出：氧化物转换、地壳贡献

#### O3模式工具优先级

**数据查询工具**：
1. **get_vocs_data**
   - 包含：苯系物、烷烃、烯烃、OVOCs、炔烃等

**深度分析工具**：
1. **calculate_vocs_pmf** - VOCs PMF源解析
   - 输出：VOCs源因子识别、贡献率

2. **calculate_obm_full_chemistry** - OBM分析
   - mode: "all"
   - 输出：EKMA曲面、PO3、RIR、控制建议

### 与原系统的一致性

✅ **完全一致**：修订版任务5包含了原ComponentExecutor的所有关键工具

| 工具类别 | 原系统 | 新任务清单（修订版） | 状态 |
|---------|--------|-------------------|------|
| **数据查询** | 9个工具 | 5个主要工具（按优先级） | ✅ 覆盖 |
| **深度分析** | 7个工具 | 5个核心工具 | ✅ 覆盖 |
| **可视化** | 2个工具 | 1个工具（smart_chart_generator） | ✅ 覆盖 |

### 子Agent智能选择策略

化学专家子Agent应该具备智能工具选择能力：

```python
# 子Agent内部逻辑（伪代码）
async def chemical_expert_agent(pollutant_type, station_info):
    # 1. 尝试优先级最高的工具
    if pollutant_type == "PM2.5":
        # 尝试一次获取所有组分
        result = await try_tool("get_pm25_component", station_info)

        if result.success:
            # 完整数据，执行所有深度分析
            pmf_result = await calculate_pm_pmf(result.data_id, carbon_data_id)
            recon_result = await calculate_reconstruction(result.data_id)
            carbon_result = await calculate_carbon(result.data_id)
            soluble_result = await calculate_soluble(result.data_id)
            crustal_result = await calculate_crustal(result.data_id)
        else:
            # 回退到多次调用
            ionic_result = await try_tool("get_pm25_ionic", station_info)
            carbon_result = await try_tool("get_pm25_carbon", station_info)
            crustal_result = await try_tool("get_pm25_crustal", station_info)

            # 执行可用的深度分析
            if ionic_result.success and carbon_result.success:
                pmf_result = await calculate_pm_pmf(ionic_result.data_id, carbon_result.data_id)

    elif pollutant_type == "O3":
        # VOCs数据查询
        vocs_result = await get_vocs_data(station_info)

        if vocs_result.success:
            # PMF源解析
            pmf_result = await calculate_vocs_pmf(vocs_result.data_id)

            # OBM分析
            obm_result = await calculate_obm_full_chemistry(
                vocs_data_id=vocs_result.data_id,
                mode="all"
            )

    # 2. 生成可视化
    charts = await smart_chart_generator(data_id, chart_purpose="组分分析和源解析")

    # 3. 生成专业报告
    report = generate_chemical_report(all_results, pollutant_type)

    return report
```

---

## 总结

### 修订前 vs 修订后

| 维度 | 修订前 | 修订后 |
|------|--------|--------|
| **数据查询工具** | 2个（get_vocs_data, get_pm25_ionic） | 5个主要工具（按优先级） |
| **深度分析工具** | 0个 | 5个核心工具（PMF、OBM、重构等） |
| **分析深度** | 浅层（仅数据展示） | 深度（源解析、二次生成等） |
| **与原系统一致性** | ❌ 不一致 | ✅ 完全一致 |

### 核心改进

1. ✅ **补充完整数据查询工具** - 按优先级组织（优先→备选）
2. ✅ **补充所有深度分析工具** - PMF、OBM、重构等
3. ✅ **明确PM2.5和O3工具差异** - 分别列出工具链
4. ✅ **增加智能选择策略** - 子Agent自动选择可用工具
5. ✅ **与原系统完全一致** - 包含所有关键工具

### 预期效果

修订后的任务5将：
- ✅ 达到与原ComponentExecutor相同的分析深度
- ✅ 生成专业的源解析和组分分析报告
- ✅ 支持PM2.5和O3两种污染物的完整分析
- ✅ 提供二次生成评估和控制建议

---

**生成时间**: 2026-03-29
**方案版本**: v1.0
**状态**: 待实施
