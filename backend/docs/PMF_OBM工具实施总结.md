# PMF源解析与OBM/OFP分析工具 - 开发实施总结

## 📋 项目概述

**开发日期**: 2025-11-02
**状态**: ✅ 开发完成 (简化版实施)
**新增工具数量**: 2个

### 工具清单

| 工具ID | 工具名称 | 类型 | 状态 | 适用范围 |
|--------|---------|------|------|----------|
| calculate_pmf | PMF源解析工具 | Analysis Tool | ✅ 已实现 | 广东省超级站 |
| calculate_obm_ofp | OBM/OFP分析工具 | Analysis Tool | 📝 设计完成 | 广东省超级站 |

---

## 一、开发成果

### 1.1 PMF源解析工具 ✅

**文件结构**:
```
backend/app/tools/analysis/calculate_pmf/
├── __init__.py           # 工具导出
├── tool.py               # LLMTool封装 (262行)
├── calculator.py         # PMF计算引擎 (350行)
└── source_profiles.py    # 源谱库 (130行)
```

**核心功能**:
1. ✅ 基于经验源谱库进行源解析
2. ✅ 自动识别7种污染源类型
   - 二次无机气溶胶
   - 燃煤源
   - 机动车尾气
   - 扬尘
   - 生物质燃烧
   - 工业排放
   - 海盐
3. ✅ 计算源贡献率(%)和平均浓度(µg/m³)
4. ✅ 生成时间序列数据
5. ✅ 模型性能评估(R²、RMSE)
6. ✅ 可视化建议(饼图、时序图、热力图)

**算法实现**:
- 方法: 约束非负最小二乘法 (NNLS)
- 库: `scipy.optimize.nnls`
- 优势: 计算快速,无需迭代优化
- 局限: 依赖源谱库准确性

**Function Schema**:
```python
{
    "name": "calculate_pmf",
    "parameters": {
        "station_name": str,     # 超级站点名称
        "component_data": List,  # 组分数据(≥20样本)
        "pollutant": str,        # "PM2.5" or "PM10"
        "start_time": str,       # 可选
        "end_time": str          # 可选
    }
}
```

**典型调用流程**:
```
1. Agent调用 get_component_data(station, "particulate", start, end)
   → 获取颗粒物组分数据

2. Agent调用 calculate_pmf(station, component_data, "PM2.5")
   → 执行源解析

3. Agent解析结果 → 生成报告
```

---

### 1.2 OBM/OFP分析工具 📝

**文件结构**:
```
backend/app/tools/analysis/calculate_obm_ofp/
├── __init__.py             # 工具导出
├── tool.py                 # LLMTool封装 (待实现)
├── calculator.py           # OBM/OFP计算引擎 (待实现)
└── mir_coefficients.py     # MIR系数表 ✅ (158行)
```

**已完成**:
- ✅ MIR系数表 (Carter 2010, 43种VOCs)
- ✅ VOC分类定义 (烷烃、烯烃、芳香烃、卤代烃、含氧VOCs)
- ✅ 敏感性诊断阈值
- ✅ 开发方案设计

**待实施** (预计2小时):
1. 📝 OFP计算器 (`calculator.py`)
   - OFP = Σ(VOCi_concentration × MIRi)
   - 按物种和类别汇总
2. 📝 敏感性诊断算法
   - VOCs/NOx比值法
   - HCHO/NOy诊断法 (如有数据)
3. 📝 LLMTool封装 (`tool.py`)
   - Function Schema定义
   - 输入验证
   - 结果格式化
4. 📝 可视化建议生成
   - OFP物种柱状图
   - OFP分类饼图
   - 敏感性散点图

---

## 二、技术实现细节

### 2.1 PMF算法实现

**数据预处理**:
```python
# 1. 验证样本数量(≥20)
# 2. 提取组分浓度矩阵 X (n_samples × n_components)
# 3. 处理缺失值(用检出限1/2填充)
```

**源谱匹配**:
```python
# 1. 读取7个源谱模板
# 2. 构建源谱矩阵 F (n_components × n_sources)
# 3. 归一化(每列和=1)
```

**NNLS拟合**:
```python
from scipy.optimize import nnls

for i in range(n_samples):
    x_i = X_matrix[i, :]
    g_i, residual = nnls(F_matrix, x_i)  # 求解: min ||x_i - F@g_i||^2, s.t. g_i ≥ 0
    G_matrix[i, :] = g_i

# 重构: X_reconstructed = G @ F
# R² = 1 - SS_res / SS_tot
```

**源识别逻辑**:
- 自动匹配: 基于组分特征向量与源谱库的余弦相似度
- 特征物种:
  - 二次无机气溶胶: SO4²⁻ + NO3⁻ + NH4⁺ 高
  - 生物质燃烧: K⁺ 高 (特征)
  - 海盐: Na⁺ + Cl⁻ 高 (特征)
  - 机动车: EC + OC 高
  - 扬尘: Ca + Si + Al + Fe 高

### 2.2 OBM/OFP算法设计

**OFP计算** (简化版):
```python
# 1. 读取VOCs组分浓度 (µg/m³)
# 2. 查找MIR系数
# 3. OFP_i = Concentration_i × MIR_i
# 4. Total_OFP = Σ OFP_i
# 5. 按类别汇总(烷烃、烯烃、芳香烃)
```

**敏感性诊断**:
```python
def diagnose_sensitivity(vocs_total, nox_conc):
    ratio = vocs_total / (nox_conc + 1e-6)

    if ratio > 8.0:
        return "VOCs-limited"  # 应优先控制VOCs
    elif ratio < 4.0:
        return "NOx-limited"   # 应优先控制NOx
    else:
        return "transitional"  # 过渡区,两者均需控制
```

---

## 三、集成步骤

### 3.1 工具注册

更新 `backend/app/tools/__init__.py`:
```python
# 在analysis工具部分添加
from app.tools.analysis.calculate_pmf import CalculatePMFTool
from app.tools.analysis.calculate_obm_ofp import CalculateOBMOFPTool

# 注册
global_tool_registry.register(CalculatePMFTool())
global_tool_registry.register(CalculateOBMOFPTool())
```

### 3.2 API文档更新

更新 `backend/app/routers/agent.py`:
- 工具列表新增两个工具
- 工具计数: 10 → 12

### 3.3 依赖安装

```bash
cd backend
pip install scipy numpy
```

---

## 四、测试计划

### 4.1 单元测试

**文件**: `backend/tests/test_pmf_calculator.py`

**测试用例**:
```python
def test_pmf_calculation():
    # 测试正常计算流程
    pass

def test_pmf_insufficient_samples():
    # 测试样本不足(<20)
    pass

def test_pmf_missing_components():
    # 测试组分缺失
    pass

def test_pmf_source_identification():
    # 测试源类型识别
    pass
```

**文件**: `backend/tests/test_obm_calculator.py`

**测试用例**:
```python
def test_ofp_calculation():
    # 测试OFP计算
    pass

def test_sensitivity_diagnosis():
    # 测试敏感性诊断
    pass

def test_category_aggregation():
    # 测试按类别汇总
    pass
```

### 4.2 集成测试

**文件**: `backend/tests/test_pmf_obm_integration.py`

**测试场景**:
1. Agent调用PMF工具完整流程
2. Agent调用OBM工具完整流程
3. 多工具协作 (先查询组分 → 再执行PMF/OBM)

### 4.3 端到端测试

**测试查询**:
```
1. "对广州天河超级站2025年8月的PM2.5进行源解析"
2. "分析深圳南山超级站昨日的VOCs对O3生成的贡献"
3. "计算珠海香洲超级站的臭氧生成敏感性"
```

---

## 五、使用示例

### 5.1 PMF源解析示例

**Agent Workflow**:
```
User: "对广州天河超级站2025年8月的PM2.5进行源解析"

Agent思考:
1. 需要颗粒物组分数据 → 调用 get_component_data
2. 执行PMF计算 → 调用 calculate_pmf
3. 生成可视化 → 调用 generate_chart
4. 综合分析 → 输出报告

Agent行动:
Step 1: get_component_data(
    station_name="天河超级站",
    component_type="particulate",
    start_time="2025-08-01 00:00:00",
    end_time="2025-08-31 23:59:59"
)
→ 返回31天 × 24小时 = 744个样本

Step 2: calculate_pmf(
    station_name="天河超级站",
    component_data=[...],  # 744个样本
    pollutant="PM2.5"
)
→ 返回结果:
{
    "success": True,
    "source_contributions": {
        "二次无机气溶胶": 32.5,
        "机动车尾气": 25.8,
        "扬尘": 18.3,
        "工业排放": 12.4,
        "燃煤源": 8.2,
        "生物质燃烧": 2.8
    },
    "model_performance": {"R2": 0.88},
    "summary": "✅ PMF源解析完成,识别出6个污染源,二次无机气溶胶贡献最大(32.5%),模型拟合度R²=0.88,基于744个PM2.5样本"
}

Step 3: generate_chart(
    data=source_contributions,
    scenario="source_contribution_pie"
)
→ 生成饼图配置

Agent输出:
# 广州天河超级站2025年8月PM2.5源解析报告

## 污染源构成

根据PMF源解析结果,天河站PM2.5主要来源于以下6个污染源:

1. **二次无机气溶胶** (32.5%) - 主导源
   - 大气中SO2、NOx等气态前体物通过光化学反应形成
   - 包含硫酸盐、硝酸盐、铵盐

2. **机动车尾气** (25.8%)
   - 汽车尾气排放,富含元素碳(EC)和有机碳(OC)

3. **扬尘** (18.3%)
   - 道路扬尘、建筑扬尘等,富含矿物元素

...

[插入饼图]

模型拟合度R²=0.88,表明源解析结果可靠。
```

### 5.2 OBM/OFP分析示例

**Agent Workflow**:
```
User: "分析深圳南山超级站昨日的VOCs对O3生成的贡献"

Step 1: get_component_data(
    station_name="南山超级站",
    component_type="vocs",
    start_time="2025-11-01 00:00:00",
    end_time="2025-11-01 23:59:59"
)

Step 2: get_air_quality(
    station_name="南山超级站",
    pollutant="NOx",
    ...
)

Step 3: calculate_obm_ofp(
    station_name="南山超级站",
    vocs_data=[...],
    nox_data=[...]
)
→ 返回结果:
{
    "success": True,
    "ofp_by_species": {
        "间二甲苯": 48.5,
        "甲苯": 42.3,
        "乙烯": 35.8,
        ...
    },
    "ofp_by_category": {
        "芳香烃": 135.2,
        "烯烃": 95.7,
        "烷烃": 38.4,
        ...
    },
    "sensitivity_analysis": {
        "regime": "VOCs-limited",
        "VOCs_NOx_ratio": 9.2
    },
    "key_species": [
        {"name": "间二甲苯", "ofp": 48.5, "contribution_pct": 16.5},
        {"name": "甲苯", "ofp": 42.3, "contribution_pct": 14.4}
    ],
    "control_recommendations": {
        "priority_species": ["芳香烃", "烯烃"],
        "control_strategy": "重点控制溶剂使用、机动车排放"
    },
    "summary": "✅ OFP分析完成:总OFP=310.8 µg/m³,O3生成为VOCs控制型,关键物种为芳香烃"
}

Agent输出:
# 深圳南山超级站VOCs臭氧生成潜势分析

## OFP分析结果

总臭氧生成潜势(OFP) = 310.8 µg/m³

### 关键VOCs物种

1. **间二甲苯**: 48.5 µg/m³ (16.5%)
2. **甲苯**: 42.3 µg/m³ (14.4%)
3. **乙烯**: 35.8 µg/m³ (12.2%)

### 按类别分析

- 芳香烃: 135.2 µg/m³ (43.5%) - 主导
- 烯烃: 95.7 µg/m³ (30.8%)
- 烷烃: 38.4 µg/m³ (12.4%)

## 敏感性诊断

- **控制类型**: VOCs控制型
- **VOCs/NOx比值**: 9.2 (>8.0)
- **建议**: 优先控制VOCs排放,重点削减芳香烃和烯烃

## 污染控制建议

1. 加强溶剂使用管理(涂料、油墨等)
2. 控制机动车尾气排放(烯烃来源)
3. 减少工业过程VOCs泄漏

[插入柱状图、饼图]
```

---

## 六、已知限制与优化方向

### 6.1 当前限制

**PMF工具**:
1. 算法简化: 使用经验源谱而非EPA PMF完整算法
2. 源谱固定: 未考虑区域差异和季节变化
3. 无不确定度分析: 缺少Bootstrap方法

**OBM工具**:
1. 未完全实现: 仅完成MIR表和算法设计
2. 敏感性诊断简化: 仅使用VOCs/NOx比值
3. 缺少动力学模拟: 未实现完整OBM模型

**通用限制**:
1. 区域限制: 仅适用于广东省超级站
2. 数据依赖: 需要高质量组分数据(≥20样本)
3. 无实时计算: 不支持流式增量更新

### 6.2 优化方向

**短期 (1个月)**:
1. 完成OBM工具实施
2. 增强PMF源谱库(收集本地化数据)
3. 添加详细的使用文档和案例

**中期 (3个月)**:
1. 升级为完整EPA PMF算法
2. 增加不确定度分析(Bootstrap)
3. 支持用户自定义源谱
4. OBM增加光化学反应动力学

**长期 (6个月+)**:
1. 机器学习增强源识别
2. 多站点联合源解析
3. 实时PMF计算(准实时更新)
4. 3D可视化(源贡献空间分布)

---

## 七、下一步行动

### 7.1 立即行动 (今日完成)

- [x] PMF工具实现 ✅
- [x] MIR系数表创建 ✅
- [ ] OBM计算器实现 (2小时)
- [ ] OBM工具封装 (1小时)
- [ ] 工具注册 (15分钟)

### 7.2 本周行动

- [ ] 编写单元测试
- [ ] 编写集成测试
- [ ] 端到端测试验证
- [ ] 更新API文档
- [ ] 更新ReAct Agent开发总结文档

### 7.3 本月行动

- [ ] 收集真实数据进行验证
- [ ] 优化源谱库(本地化)
- [ ] 性能优化(大数据量处理)
- [ ] 用户反馈收集与迭代

---

## 八、文档索引

### 8.1 设计文档
- `backend/docs/PMF_OBM工具开发方案.md` - 完整开发方案

### 8.2 代码文件
- `backend/app/tools/analysis/calculate_pmf/` - PMF工具实现
- `backend/app/tools/analysis/calculate_obm_ofp/` - OBM工具实现(部分)

### 8.3 参考文档
- `backend/docs/ReAct_Agent完整开发总结.md` - Agent架构
- `backend/docs/图表工具优化实施总结.md` - 可视化指南
- `CLAUDE.md` - 项目架构总览

---

**开发人员**: Claude Code
**审核状态**: 待测试验证
**最后更新**: 2025-11-02 (PMF工具完成,OBM设计完成)
