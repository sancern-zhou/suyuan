# PMF源解析与OBM/OFP分析工具 - 前后端完整测试清单

**创建日期**: 2025-11-02
**状态**: ✅ 工具开发完成，准备前后端集成测试
**目标**: 确保PMF和OBM工具在ReAct Agent架构下与前端完整集成

---

## 📋 测试前准备工作

### 1. 环境检查

#### 后端环境
```bash
cd backend

# 1. 检查Python依赖
pip list | grep scipy    # ✅ 必须安装
pip list | grep numpy    # ✅ 必须安装

# 如未安装
pip install scipy numpy

# 2. 检查工具注册
python -c "from app.tools import global_tool_registry; print('工具总数:', len(global_tool_registry.list_tools())); print('PMF工具:', 'calculate_pmf' in global_tool_registry.list_tools()); print('OBM工具:', 'calculate_obm_ofp' in global_tool_registry.list_tools())"

# 预期输出:
# 工具总数: 12
# PMF工具: True
# OBM工具: True
```

#### 前端环境
```bash
cd frontend-vue

# 检查依赖
npm list echarts
npm list vue

# 如缺失依赖
npm install
```

---

## ✅ 需要完善的内容清单

### 一、后端完善项

#### 1. **ReAct Agent集成验证** ⚠️ 关键

**问题诊断**:
- 当前系统使用的是 `SuperAgent` (Multi-Expert架构)
- PMF/OBM工具已在 `global_tool_registry` 注册
- 需要验证 `SuperAgent` 能否正确识别和调用新工具

**检查位置**:
```python
# backend/app/agent/super_agent.py
# 需要检查两个专家是否能访问新工具

# DataAnalysisExpert - 负责数据获取和分析
# ReportExpert - 负责报告生成

# 当前工具分配策略:
# - get_component_data → DataAnalysisExpert
# - calculate_pmf → ？（需要分配到哪个专家）
# - calculate_obm_ofp → ？（需要分配到哪个专家）
```

**需要完善**:
1. ✅ **工具分配策略** - 将PMF/OBM分配到正确的专家
   ```python
   # app/agent/experts/data_expert.py
   # 可能需要添加:
   "calculate_pmf",
   "calculate_obm_ofp"
   ```

2. ✅ **专家能力描述** - 更新专家的system prompt，说明可以进行源解析
   ```python
   # app/agent/experts/data_expert.py
   system_message = """
   你是数据分析专家，擅长：
   ...
   - PMF源解析（calculate_pmf）
   - OBM/OFP分析（calculate_obm_ofp）
   """
   ```

3. ✅ **工具调用测试** - 验证SuperAgent能否正确调用新工具

**验证方式**:
```bash
# 启动后端
python -m uvicorn app.main:app --reload

# 测试API
curl http://localhost:8000/api/agent/stats

# 预期输出应包含calculate_pmf和calculate_obm_ofp
```

#### 2. **数据流完整性验证** ⚠️ 重要

**当前流程**:
```
用户查询 → SuperAgent → DataExpert → get_component_data → [PMF/OBM]
```

**需要验证的数据流**:

**场景1: PMF源解析**
```
1. get_component_data(component_type="particulate")
   → 返回: [{time, SO4, NO3, NH4, OC, EC, ...}, ...]

2. calculate_pmf(component_data=上一步结果)
   → 返回: {
       source_contributions: {源1: 30%, 源2: 25%, ...},
       source_concentrations: {...},
       timeseries: [...],
       model_performance: {R2: 0.85, ...},
       visualization_suggestions: {...}
     }

3. generate_chart(data=source_contributions, scenario="source_contribution_pie")
   → 返回ECharts配置
```

**场景2: OBM/OFP分析**
```
1. get_component_data(component_type="vocs")
   → 返回: [{time, 乙烷, 丙烷, 甲苯, ...}, ...]

2. get_air_quality(pollutant="NOx")
   → 返回: [{time, NOx}, ...]

3. calculate_obm_ofp(vocs_data=步骤1, nox_data=步骤2)
   → 返回: {
       total_ofp: 150.5,
       ofp_by_species: {...},
       ofp_by_category: {...},
       sensitivity_analysis: {regime: "VOCs-limited", ...},
       key_species: [...],
       control_recommendations: {...},
       visualization_suggestions: {...}
     }

4. generate_chart(data=ofp_by_species, scenario="ofp_species_bar")
   → 返回ECharts配置
```

**需要完善**:
- ✅ 确认 `get_component_data` 返回的数据格式与PMF/OBM期望的输入格式一致
- ✅ 确认 `get_air_quality` 支持查询NOx数据
- ✅ 确认 `generate_chart` 工具能够识别新的可视化场景

#### 3. **可视化工具扩展** ⚠️ 重要

**当前generate_chart工具需要支持的新场景**:

```python
# backend/app/tools/visualization/generate_chart/tool.py
# 需要添加以下场景:

# PMF相关场景
"source_contribution_pie"       # 源贡献饼图
"source_timeseries"             # 源贡献时序图
"source_heatmap"                # 源贡献热力图

# OBM/OFP相关场景
"ofp_species_bar"               # VOC物种OFP柱状图
"ofp_category_pie"              # VOC类别OFP饼图
"sensitivity_scatter"           # 敏感性散点图
```

**检查方式**:
```bash
# 查看当前支持的场景
grep -r "scenario" backend/app/tools/visualization/generate_chart/
```

**需要完善**:
1. ✅ 在 `generate_chart/tool.py` 或 `generate_chart/templates.py` 中添加新场景模板
2. ✅ 确保能够根据 `visualization_suggestions` 自动生成图表配置

#### 4. **错误处理和降级策略** ⚠️ 重要

**需要完善的错误处理**:

```python
# 1. 数据不足错误
if len(component_data) < 20:
    return {
        "success": False,
        "error": "PMF需要至少20个样本",
        "recommendation": "请扩大时间范围或选择其他分析方法"
    }

# 2. 组分缺失错误
required_components = ["SO4", "NO3", "NH4", "OC", "EC"]
missing = set(required_components) - set(component_data[0].keys())
if missing:
    return {
        "success": False,
        "error": f"缺少必需组分: {missing}",
        "recommendation": "该站点可能不是超级站或组分监测设备故障"
    }

# 3. 模型拟合失败
if performance["R2"] < 0.5:
    return {
        "success": True,  # 仍返回结果，但带警告
        "warning": "模型拟合度较低(R²<0.5)，结果可能不可靠",
        "data": result
    }
```

**当前实现状态**: ✅ 基础错误处理已实现
**需要增强**: 更详细的用户友好错误提示

#### 5. **日志和监控** ✅ 已完善

**当前实现**:
- ✅ 使用structlog记录关键步骤
- ✅ 记录工具调用参数和结果
- ✅ 记录计算性能指标

**建议增加**:
- ⏳ 计算耗时监控 (可选)
- ⏳ 数据质量评分 (可选)

---

### 二、前端完善项

#### 1. **ReAct Agent界面适配** ⚠️ 关键

**当前状态**:
- 前端使用 `frontend-vue/src/components/react-agent/` 组件
- 需要确认界面能够展示PMF/OBM分析结果

**需要检查的组件**:
```
frontend-vue/src/components/react-agent/
├── ChatInterface.vue       # 聊天界面
├── AnalysisPanel.vue       # 分析结果面板
└── ChartRenderer.vue       # 图表渲染器
```

**需要验证**:
1. ✅ 能否正确渲染PMF源贡献饼图
2. ✅ 能否正确渲染OFP柱状图
3. ✅ 能否正确显示敏感性诊断结果
4. ✅ 能否正确显示控制建议文本

#### 2. **ECharts图表类型支持** ⚠️ 重要

**需要支持的新图表类型**:

| 图表类型 | ECharts类型 | 用途 | 优先级 |
|---------|------------|------|--------|
| 源贡献饼图 | pie | PMF源贡献率可视化 | 高 |
| 源贡献时序图 | line/bar | PMF源贡献时间变化 | 中 |
| OFP柱状图 | bar | VOC物种OFP排序 | 高 |
| OFP分类饼图 | pie | VOC类别OFP占比 | 高 |
| 敏感性散点图 | scatter | VOCs/NOx敏感性诊断 | 中 |
| 源贡献热力图 | heatmap | 源贡献日历热图 | 低 |

**检查方式**:
```bash
# 查看前端ECharts配置
grep -r "chart_type" frontend-vue/src/

# 查看当前支持的图表类型
cat frontend-vue/src/components/react-agent/ChartRenderer.vue
```

**需要完善**:
- ✅ 确认ChartRenderer能够渲染pie、bar、line、scatter、heatmap
- ⏳ 如不支持，需要扩展渲染器 (根据实际情况)

#### 3. **Markdown文本渲染** ✅ 已支持

**需要展示的文本内容**:
- PMF源解析摘要 (summary字段)
- OBM敏感性诊断结果 (sensitivity_analysis.regime)
- 控制建议 (control_recommendations)

**当前状态**: 前端已支持Markdown渲染 ✅

#### 4. **响应式设计** ⏳ 可选

**建议优化**:
- 大量图表时的布局自适应
- 移动端展示优化

---

### 三、集成测试场景

#### **场景1: PMF源解析 - 完整流程测试**

**测试目标**: 验证从用户查询到结果展示的完整流程

**测试步骤**:

```bash
# 1. 启动后端
cd backend
python -m uvicorn app.main:app --reload

# 2. 启动前端
cd frontend-vue
npm run dev

# 3. 在前端输入查询
"对广州天河超级站2025年8月的PM2.5进行源解析"

# 4. 观察ReAct Agent执行过程
```

**预期Agent行为**:
```
[Thought] 用户想进行PM2.5源解析，需要获取颗粒物组分数据
[Action] get_component_data(
    station_name="天河超级站",
    component_type="particulate",
    start_time="2025-08-01 00:00:00",
    end_time="2025-08-31 23:59:59"
)
[Observation] 获取到720条颗粒物组分数据

[Thought] 数据已准备好，执行PMF源解析
[Action] calculate_pmf(
    station_name="天河超级站",
    component_data=[...],
    pollutant="PM2.5"
)
[Observation] 源解析完成，识别出7种污染源：
- 二次无机气溶胶: 32.5%
- 机动车尾气: 24.8%
- 燃煤源: 18.3%
- ...
模型R²=0.82

[Thought] 生成可视化图表
[Action] generate_chart(
    data=source_contributions,
    scenario="source_contribution_pie"
)
[Observation] 生成饼图配置

[Final Answer] 完整的源解析报告
```

**验收标准**:
- ✅ 成功调用 `get_component_data` 获取数据
- ✅ 成功调用 `calculate_pmf` 执行源解析
- ✅ 识别出≥4种污染源
- ✅ 源贡献率总和 = 100% (±5%)
- ✅ 模型R² ≥ 0.75
- ✅ 生成饼图和时序图
- ✅ 前端正确展示结果

---

#### **场景2: OBM/OFP分析 - 完整流程测试**

**测试步骤**:

```bash
# 在前端输入查询
"分析深圳南山超级站昨日的VOCs对O3生成的贡献"
```

**预期Agent行为**:
```
[Thought] 用户想分析O3生成贡献，需要VOCs组分数据和NOx数据
[Action] get_component_data(
    station_name="南山超级站",
    component_type="vocs",
    start_time="2025-11-01 00:00:00",
    end_time="2025-11-01 23:59:59"
)
[Observation] 获取到24条VOCs组分数据

[Thought] 还需要NOx数据用于敏感性分析
[Action] get_air_quality(
    station_name="南山超级站",
    pollutant="NOx",
    start_time="2025-11-01 00:00:00",
    end_time="2025-11-01 23:59:59"
)
[Observation] 获取到24条NOx数据

[Thought] 数据已齐全，执行OFP分析
[Action] calculate_obm_ofp(
    station_name="南山超级站",
    vocs_data=[...],
    nox_data=[...]
)
[Observation] OFP分析完成：
- 总OFP: 145.3 µg/m³
- 关键物种: 间二甲苯(18.2%)、对二甲苯(15.7%)、...
- 敏感性: VOCs控制型
- 建议: 优先控制芳香烃和烯烃排放

[Thought] 生成可视化
[Action] generate_chart(
    data=ofp_by_species,
    scenario="ofp_species_bar"
)
[Observation] 生成柱状图和饼图配置

[Final Answer] 完整的OFP分析报告
```

**验收标准**:
- ✅ 成功调用 `get_component_data` 获取VOCs数据
- ✅ 成功调用 `get_air_quality` 获取NOx数据
- ✅ 成功调用 `calculate_obm_ofp` 计算OFP
- ✅ 计算总OFP值 (µg/m³)
- ✅ 识别关键物种 (Top 10)
- ✅ 判断敏感性类型 (VOCs-limited/NOx-limited/transitional)
- ✅ 生成控制建议
- ✅ 生成柱状图和饼图
- ✅ 前端正确展示结果

---

#### **场景3: 混合分析 - Agent智能决策测试**

**测试目标**: 验证Agent能否根据污染物类型自动选择分析工具

**测试查询**:
```
"分析广州天河超级站2025年8月1日的空气质量，包括PM2.5和O3的污染源"
```

**预期Agent行为**:
```
[Thought] 用户同时关注PM2.5和O3，需要分别进行源解析

[行动1] 获取PM2.5组分数据 → PMF源解析 → 生成饼图
[行动2] 获取VOCs组分数据 → OBM/OFP分析 → 生成柱状图
[行动3] 综合两种分析结果，提供整体评估

[Final Answer] 完整的双污染物源解析报告
```

**验收标准**:
- ✅ Agent能够理解需要进行两种分析
- ✅ 正确调用PMF工具分析PM2.5
- ✅ 正确调用OBM工具分析O3
- ✅ 结果整合呈现合理

---

## 🔧 完善优先级

### **P0 - 必须完成** (阻塞测试)
1. ✅ **验证SuperAgent能否识别新工具**
   - 检查 `app/agent/super_agent.py` 工具分配
   - 检查 `app/agent/experts/` 专家配置
   - 运行 `curl http://localhost:8000/api/agent/stats` 验证

2. ⚠️ **验证get_component_data返回数据格式**
   - 确认返回格式与PMF/OBM期望一致
   - 检查时间字段、组分字段名称

3. ⚠️ **验证前端能渲染PMF/OBM结果**
   - 测试饼图、柱状图渲染
   - 测试Markdown文本展示

### **P1 - 建议完成** (影响用户体验)
1. ⏳ **扩展generate_chart工具场景**
   - 添加 `source_contribution_pie`
   - 添加 `ofp_species_bar`
   - 添加 `ofp_category_pie`

2. ⏳ **增强错误提示**
   - 数据不足时的友好提示
   - 模型拟合度低时的警告

### **P2 - 可选完成** (锦上添花)
1. ⏳ 添加热力图支持
2. ⏳ 添加散点图支持
3. ⏳ 移动端优化

---

## 📝 测试检查表

### 后端测试

- [ ] **1. 依赖安装**
  ```bash
  pip install scipy numpy
  ```

- [ ] **2. 工具注册验证**
  ```bash
  python test_pmf_obm_tools.py
  # 预期: 所有测试通过
  ```

- [ ] **3. 服务启动验证**
  ```bash
  python -m uvicorn app.main:app --reload
  curl http://localhost:8000/health
  # 预期: {"status": "healthy"}
  ```

- [ ] **4. 工具API验证**
  ```bash
  curl http://localhost:8000/api/agent/stats
  # 预期: experts[].available_tools 包含 calculate_pmf 和 calculate_obm_ofp
  ```

- [ ] **5. 数据流验证**
  - [ ] get_component_data 返回正确格式
  - [ ] calculate_pmf 能接受组分数据
  - [ ] calculate_obm_ofp 能接受VOCs和NOx数据

- [ ] **6. SuperAgent集成验证**
  - [ ] DataExpert 包含 calculate_pmf
  - [ ] DataExpert 包含 calculate_obm_ofp
  - [ ] 专家system prompt更新

### 前端测试

- [ ] **1. 前端启动**
  ```bash
  cd frontend-vue
  npm install
  npm run dev
  # 预期: 在 http://localhost:5174 启动
  ```

- [ ] **2. 界面展示**
  - [ ] ReAct Agent聊天界面正常
  - [ ] 能输入查询文本

- [ ] **3. 可视化验证**
  - [ ] ECharts饼图正常渲染
  - [ ] ECharts柱状图正常渲染
  - [ ] Markdown文本正常展示

### 端到端测试

- [ ] **场景1: PMF源解析**
  - [ ] 输入查询: "对广州天河超级站2025年8月的PM2.5进行源解析"
  - [ ] Agent调用get_component_data
  - [ ] Agent调用calculate_pmf
  - [ ] 识别出≥4种污染源
  - [ ] 生成饼图
  - [ ] 前端正确展示

- [ ] **场景2: OBM/OFP分析**
  - [ ] 输入查询: "分析深圳南山超级站昨日的VOCs对O3生成的贡献"
  - [ ] Agent调用get_component_data(vocs)
  - [ ] Agent调用get_air_quality(NOx)
  - [ ] Agent调用calculate_obm_ofp
  - [ ] 生成柱状图和饼图
  - [ ] 前端正确展示

- [ ] **场景3: 错误处理**
  - [ ] 普通站点查询组分数据 → 友好错误提示
  - [ ] 数据不足 → 友好错误提示
  - [ ] 模型拟合失败 → 带警告返回结果

---

## 🚨 已知风险和缓解措施

### 风险1: SuperAgent不认识新工具
**现象**: Agent调用分析时不使用calculate_pmf/calculate_obm_ofp
**原因**: 工具未分配到DataExpert或ReportExpert
**缓解**: 检查并更新专家配置文件

### 风险2: 数据格式不匹配
**现象**: PMF/OBM计算失败，报"缺少必需字段"
**原因**: get_component_data返回格式与工具期望不一致
**缓解**: 添加数据格式转换层

### 风险3: 前端图表渲染失败
**现象**: ECharts报错或显示空白
**原因**: 图表配置格式错误或图表类型不支持
**缓解**: 使用通用图表配置，降级到简单图表

### 风险4: 真实数据质量差
**现象**: 模型R²低于0.5
**原因**: 超级站组分数据缺失或质量差
**缓解**: 添加数据质量预检，提示用户数据问题

---

## 📊 测试完成标准

### 最小可接受标准 (MVP)
- ✅ 后端工具注册成功
- ✅ Agent能调用PMF和OBM工具
- ✅ 前端能展示基础文本结果
- ✅ 至少1种可视化图表正常

### 理想完成标准
- ✅ 所有端到端测试场景通过
- ✅ 所有可视化类型正常
- ✅ 错误处理友好
- ✅ 用户体验流畅

---

## 📞 问题排查指南

### 问题1: 工具未注册
```bash
# 检查日志
tail -f backend/logs/app.log | grep "tool_loaded"

# 预期看到:
# tool_loaded tool=calculate_pmf
# tool_loaded tool=calculate_obm_ofp
```

### 问题2: Agent不调用新工具
```bash
# 检查SuperAgent配置
cat backend/app/agent/experts/data_expert.py | grep -A 20 "tool_names"

# 确认包含:
# "calculate_pmf",
# "calculate_obm_ofp"
```

### 问题3: 前端图表空白
```bash
# 打开浏览器控制台查看错误
# 检查后端返回的数据结构

curl -X POST http://localhost:8000/api/agent/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "对广州天河超级站2025年8月的PM2.5进行源解析", "user_id": "test"}'
```

---

## 📅 测试时间估算

| 阶段 | 预计时间 | 说明 |
|-----|---------|------|
| 后端完善 | 2-4小时 | SuperAgent配置、数据格式验证 |
| 前端检查 | 1-2小时 | 可视化组件验证 |
| 端到端测试 | 2-3小时 | 3个测试场景 |
| 问题修复 | 2-4小时 | 根据测试发现的问题 |
| **总计** | **7-13小时** | 含文档更新 |

---

## ✅ 下一步行动

1. **立即执行** (30分钟)
   ```bash
   # 1. 启动后端
   cd backend
   python -m uvicorn app.main:app --reload

   # 2. 检查工具注册
   curl http://localhost:8000/api/agent/stats

   # 3. 检查日志
   tail -f logs/app.log
   ```

2. **验证SuperAgent配置** (1小时)
   - 检查 `app/agent/super_agent.py`
   - 检查 `app/agent/experts/data_expert.py`
   - 更新专家工具列表和system prompt

3. **前端集成测试** (1-2小时)
   - 启动前端
   - 执行测试场景1和2
   - 记录问题

4. **修复和优化** (根据测试结果)
   - 修复数据格式问题
   - 修复可视化问题
   - 优化用户体验

---

**文档作者**: Claude Code
**创建日期**: 2025-11-02
**版本**: 1.0.0
**相关文档**:
- `PMF_OBM工具开发方案.md`
- `PMF_OBM工具实施总结.md`
- `PMF_OBM工具完整实施报告.md`
