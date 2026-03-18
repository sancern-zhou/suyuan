# PMF源解析与OBM/OFP分析工具开发方案

## 项目概述

基于ReAct Agent架构，开发两个新的分析工具：
1. **PMF源解析工具** (`calculate_pmf`) - 正定矩阵因子分解源解析
2. **OBM/OFP分析工具** (`calculate_obm_ofp`) - 臭氧生成潜势与敏感性分析

**开发日期**: 2025-11-02
**状态**: 设计阶段
**优先级**: 高

---

## 一、技术背景

### 1.1 PMF (Positive Matrix Factorization) 源解析

**定义**: 正定矩阵因子分解是一种受体模型方法,用于识别和定量化大气颗粒物(PM2.5/PM10)的来源贡献。

**原理**:
- 将观测浓度矩阵分解为源成分谱和源贡献两个非负矩阵
- 公式: `X = GF + E` (X=观测数据, G=源贡献, F=源成分谱, E=残差)
- 约束条件: G ≥ 0, F ≥ 0 (非负约束)

**输入数据**:
1. **颗粒物组分浓度** (来自超级站)
   - 离子组分: SO4²⁻, NO3⁻, NH4⁺, Cl⁻ 等
   - 碳组分: OC (有机碳), EC (元素碳)
   - 元素: Al, Si, Ca, Fe, K, Mg, Na 等
   - PM2.5/PM10总质量浓度
2. **气象条件** (辅助分析)
   - 风向、风速、温度、湿度
3. **时间范围**: 通常需要≥1个月数据(至少20-30个样本)

**输出结果**:
1. **源类型识别**:
   - 二次无机气溶胶(硝酸盐、硫酸盐)
   - 燃煤源
   - 机动车尾气
   - 扬尘(建筑扬尘、道路扬尘、土壤尘)
   - 工业排放(冶金、化工等)
   - 生物质燃烧
   - 海盐
2. **源贡献率**: 每个源对总PM2.5/PM10的贡献百分比
3. **时间变化**: 各源贡献的时间序列

### 1.2 OBM/OFP 分析

**定义**:
- **OBM** (Observation-Based Model): 基于观测的光化学模型
- **OFP** (Ozone Formation Potential): 臭氧生成潜势

**原理**:
- 使用观测的VOCs组分浓度和光化学反应速率常数
- 计算每种VOCs物种对O3生成的贡献
- 判断O3生成的限制因子(VOCs控制或NOx控制)

**输入数据**:
1. **VOCs组分浓度** (来自超级站)
   - 烷烃: 乙烷、丙烷、正丁烷、异丁烷等
   - 烯烃: 乙烯、丙烯、1-丁烯等
   - 芳香烃: 苯、甲苯、乙苯、二甲苯等
   - 卤代烃: 二氯甲烷、三氯乙烯等
   - 含氧VOCs: 甲醛、乙醛、丙酮等
2. **NOx浓度** (O3生成的另一前体物)
3. **O3浓度** (实际观测值)
4. **气象条件**: 温度、辐射、湿度等

**输出结果**:
1. **OFP值**: 每种VOCs的O3生成潜势(µg/m³)
2. **敏感性分析**: VOCs敏感型 vs NOx敏感型
3. **关键物种识别**: 对O3生成贡献最大的VOCs物种
4. **控制建议**: 基于敏感性的污染控制策略

---

## 二、工具设计架构

### 2.1 工具类型与职责

| 工具名称 | 类型 | 输入 | 输出 | 区域限制 |
|---------|------|------|------|----------|
| `calculate_pmf` | Analysis Tool | 颗粒物组分数据 + 气象数据 | PMF源解析结果 | 广东省超级站 |
| `calculate_obm_ofp` | Analysis Tool | VOCs组分数据 + NOx + O3 + 气象 | OFP + 敏感性分析 | 广东省超级站 |

### 2.2 技术栈选择

**方案A: 外部API调用** (推荐)
- **优势**:
  - 利用现有成熟算法服务
  - 无需维护复杂计算逻辑
  - 快速集成
- **劣势**:
  - 依赖外部服务可用性
  - 需要确认API是否存在
- **适用条件**: 如果项目已有PMF/OBM计算服务(类似于上风向企业分析API)

**方案B: Python库实现** (备选)
- **PMF**: 使用 `pmfpy` 或 `scikit-learn` 的 NMF (非负矩阵分解)
- **OBM/OFP**: 自行实现基于MIR (Maximum Incremental Reactivity) 系数的计算
- **优势**: 完全自主控制,无外部依赖
- **劣势**:
  - 开发周期较长
  - 需要调试和验证算法准确性
  - PMF需要EPA PMF软件的输出格式适配

**方案C: 简化版计算** (快速原型)
- PMF: 基于经验源谱进行匹配和估算
- OFP: 使用固定的MIR系数表直接计算
- **优势**: 实现简单,快速验证工作流
- **劣势**: 准确性较低,仅作为demo

**推荐策略**:
1. 优先调研是否有现成API (方案A)
2. 若无API,先实现简化版 (方案C) 验证工作流
3. 后续迭代为完整算法实现 (方案B)

### 2.3 工具接口设计

#### 工具1: calculate_pmf

```python
class CalculatePMFTool(LLMTool):
    """
    PMF源解析工具

    适用范围: 广东省超级站
    数据要求: 至少20-30个样本点的颗粒物组分数据
    """

    async def execute(
        self,
        station_name: str,          # 超级站点名称
        pollutant: str,             # "PM2.5" or "PM10"
        start_time: str,            # 起始时间 "YYYY-MM-DD HH:MM:SS"
        end_time: str,              # 结束时间
        factor_number: int = None,  # 源因子数量(None=自动判断,一般4-8个)
        convergence_criteria: float = 0.01,  # 收敛阈值
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行PMF源解析

        Returns:
            {
                "success": True,
                "source_profiles": {
                    "二次无机气溶胶": {"SO4": 0.45, "NO3": 0.35, ...},
                    "燃煤源": {"SO4": 0.25, "OC": 0.15, ...},
                    ...
                },
                "source_contributions": {
                    "二次无机气溶胶": 28.5,  # 贡献率(%)
                    "燃煤源": 18.2,
                    ...
                },
                "timeseries": [
                    {
                        "time": "2025-08-01 00:00:00",
                        "二次无机气溶胶": 12.5,  # µg/m³
                        "燃煤源": 8.3,
                        ...
                    }
                ],
                "model_performance": {
                    "R2": 0.92,
                    "RMSE": 5.3,
                    "convergence_iterations": 45
                },
                "visualization_suggestions": {
                    "source_contribution_pie": {...},
                    "source_timeseries": {...},
                    "source_profiles_heatmap": {...}
                },
                "summary": "✅ PMF源解析完成:识别出6个源,二次无机气溶胶贡献最大(28.5%)"
            }
        """
```

#### 工具2: calculate_obm_ofp

```python
class CalculateOBMOFPTool(LLMTool):
    """
    OBM/OFP分析工具

    适用范围: 广东省超级站
    目标污染物: O3
    """

    async def execute(
        self,
        station_name: str,          # 超级站点名称
        start_time: str,            # 起始时间
        end_time: str,              # 结束时间
        mir_scale: str = "Carter2010",  # MIR系数版本
        sensitivity_method: str = "ratio",  # 敏感性判断方法
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行OBM/OFP分析

        Returns:
            {
                "success": True,
                "ofp_by_species": {
                    "间二甲苯": 45.2,  # µg/m³
                    "甲苯": 38.7,
                    "乙烯": 28.5,
                    ...
                },
                "ofp_by_category": {
                    "芳香烃": 125.3,
                    "烯烃": 89.4,
                    "烷烃": 35.2,
                    ...
                },
                "sensitivity_analysis": {
                    "regime": "VOCs-limited",  # or "NOx-limited" or "transitional"
                    "VOCs_NOx_ratio": 8.5,
                    "confidence": 0.85,
                    "diagnostic_ratios": {
                        "HCHO/NOy": 0.15,
                        "H2O2/HNO3": 0.65
                    }
                },
                "key_species": [
                    {"name": "间二甲苯", "ofp": 45.2, "contribution_pct": 15.2},
                    {"name": "甲苯", "ofp": 38.7, "contribution_pct": 13.1},
                    ...
                ],
                "control_recommendations": {
                    "priority_species": ["芳香烃", "烯烃"],
                    "control_strategy": "重点控制溶剂使用、机动车排放",
                    "expected_effectiveness": "high"
                },
                "visualization_suggestions": {
                    "ofp_species_bar": {...},
                    "ofp_category_pie": {...},
                    "sensitivity_scatter": {...}
                },
                "summary": "✅ OFP分析完成:总OFP=297.3 µg/m³,O3生成为VOCs控制型,关键物种为芳香烃"
            }
        """
```

---

## 三、实施计划

### 3.1 Phase 1: 需求调研与API确认 (0.5天)

**任务清单**:
- [ ] 确认是否有现成的PMF计算API服务
- [ ] 确认是否有现成的OBM/OFP计算API服务
- [ ] 如有API,获取接口文档、测试数据、认证方式
- [ ] 如无API,评估算法实现复杂度

**决策点**:
- 有API → 进入 Phase 2A (API集成)
- 无API → 进入 Phase 2B (简化版实现)

### 3.2 Phase 2A: API集成实现 (2天)

#### PMF工具实现
**文件**: `backend/app/tools/analysis/calculate_pmf/`
```
calculate_pmf/
├── __init__.py          # 导出工具类
├── tool.py              # PMF工具主逻辑
├── api_client.py        # PMF API客户端封装
└── README.md            # 工具使用文档
```

**关键步骤**:
1. 创建API客户端封装 (`api_client.py`)
   - 处理认证
   - 请求/响应格式转换
   - 错误处理与重试
2. 实现LLMTool子类 (`tool.py`)
   - 定义Function Schema
   - 实现 `execute()` 方法
   - 数据验证与预处理
3. 集成到工具注册表 (`app/tools/__init__.py`)

#### OBM/OFP工具实现
**文件**: `backend/app/tools/analysis/calculate_obm_ofp/`
```
calculate_obm_ofp/
├── __init__.py
├── tool.py
├── api_client.py  (或 calculator.py 如果是本地计算)
└── README.md
```

**关键步骤**: (同上)

### 3.2 Phase 2B: 简化版实现 (3天)

#### PMF简化版实现
**策略**: 基于经验源谱库进行匹配
```python
# 经验源谱库 (来自文献或EPA PMF案例)
SOURCE_PROFILES = {
    "二次无机气溶胶": {"SO4": 0.45, "NO3": 0.35, "NH4": 0.20, ...},
    "燃煤源": {"SO4": 0.25, "OC": 0.15, "EC": 0.10, "K": 0.05, ...},
    "机动车": {"EC": 0.30, "OC": 0.25, "NO3": 0.15, ...},
    ...
}

# 简化计算逻辑
1. 读取颗粒物组分数据
2. 标准化为相对浓度
3. 与源谱库进行最小二乘拟合
4. 计算各源贡献率
5. 生成时间序列(简单线性分配)
```

**优势**: 无需复杂的迭代优化算法
**劣势**: 准确性依赖于源谱库的代表性

#### OBM/OFP简化版实现
**策略**: 使用固定MIR系数表直接计算
```python
# MIR系数表 (来自Carter 2010)
MIR_COEFFICIENTS = {
    "乙烷": 0.28,
    "丙烷": 0.49,
    "甲苯": 4.00,
    "间二甲苯": 7.80,
    "乙烯": 9.00,
    ...
}

# 简化计算逻辑
1. 读取VOCs组分浓度 (µg/m³)
2. 转换为ppbC (碳当量)
3. OFP = Σ(VOCi_concentration * MIRi)
4. 敏感性判断: 基于VOCs/NOx比值阈值
   - VOCs/NOx > 8 → VOCs控制
   - VOCs/NOx < 4 → NOx控制
   - 4-8 → 过渡区
```

**优势**: 算法简单,计算快速
**劣势**: 未考虑气象条件和光化学反应动力学

### 3.3 Phase 3: 可视化集成 (1天)

#### PMF可视化
1. **源贡献饼图** (Source Contribution Pie)
   ```json
   {
     "id": "pmf_source_contribution_pie",
     "type": "chart",
     "chart_type": "pie",
     "title": "PM2.5源解析结果",
     "data": [
       {"name": "二次无机气溶胶", "value": 28.5},
       {"name": "燃煤源", "value": 18.2},
       ...
     ]
   }
   ```

2. **源贡献时序图** (Source Timeseries)
   ```json
   {
     "id": "pmf_source_timeseries",
     "type": "chart",
     "chart_type": "line",
     "title": "PM2.5源贡献时间变化",
     "x_axis": ["2025-08-01", "2025-08-02", ...],
     "series": [
       {"name": "二次无机气溶胶", "data": [12.5, 15.3, ...]},
       {"name": "燃煤源", "data": [8.3, 9.1, ...]},
       ...
     ]
   }
   ```

3. **源成分谱热力图** (Source Profile Heatmap)

#### OBM/OFP可视化
1. **OFP物种贡献柱状图**
2. **OFP分类饼图** (烷烃、烯烃、芳香烃等)
3. **敏感性诊断散点图** (VOCs vs NOx)

### 3.4 Phase 4: 测试与验证 (1天)

#### 单元测试
**文件**: `backend/tests/test_pmf_tool.py`, `test_obm_tool.py`

**测试用例**:
1. **正常流程测试**
   - 有效输入 → 正确输出
2. **边界条件测试**
   - 数据不足 (<20样本)
   - 无组分数据
   - 时间范围错误
3. **错误处理测试**
   - API调用失败
   - 数据格式错误
   - 超时处理

#### 集成测试
**文件**: `backend/tests/test_analysis_tools_integration.py`

**测试场景**:
1. ReAct Agent调用PMF工具完整流程
2. ReAct Agent调用OBM工具完整流程
3. 多工具协作场景(先查询组分数据 → 再执行PMF/OBM分析)

#### 端到端测试
**文件**: `backend/tests/test_pmf_obm_e2e.py`

**测试查询**:
```
"对广州天河超级站2025年8月的PM2.5进行源解析"
"分析深圳南山超级站昨日的VOCs对O3生成的贡献"
```

### 3.5 Phase 5: 文档与部署 (0.5天)

#### 文档更新
1. 更新 `backend/docs/ReAct_Agent完整开发总结.md`
   - 新增工具11、12的说明
2. 创建 `backend/docs/PMF_OBM工具使用指南.md`
   - 算法原理
   - 数据要求
   - API调用示例
   - 结果解读

#### 工具注册
更新 `backend/app/tools/__init__.py`:
```python
from app.tools.analysis.calculate_pmf import CalculatePMFTool
from app.tools.analysis.calculate_obm_ofp import CalculateOBMOFPTool

# 注册到全局工具表
global_tool_registry.register(CalculatePMFTool())
global_tool_registry.register(CalculateOBMOFPTool())
```

更新 `backend/app/routers/agent.py`:
- API文档中列出新工具
- 更新健康检查端点工具计数

---

## 四、数据流设计

### 4.1 PMF工具数据流

```
用户查询 → ReAct Agent
    ↓
1. Agent调用 get_component_data(station_name, "particulate", start, end)
   获取颗粒物组分数据
    ↓
2. Agent调用 calculate_pmf(station_name, "PM2.5", start, end)
   输入: 颗粒物组分数据
    ↓
3. PMF工具执行:
   3.1 验证数据完整性(≥20样本)
   3.2 调用PMF算法/API
   3.3 解析源类型与贡献
   3.4 生成可视化配置
    ↓
4. 返回结果给Agent
    ↓
5. Agent调用 generate_chart() 生成图表
    ↓
6. Agent综合分析,生成最终报告
```

### 4.2 OBM工具数据流

```
用户查询 → ReAct Agent
    ↓
1. Agent调用 get_component_data(station_name, "vocs", start, end)
   获取VOCs组分数据
    ↓
2. Agent调用 get_air_quality(station_name, "O3", start, end)
   获取O3和NOx浓度
    ↓
3. Agent调用 calculate_obm_ofp(station_name, start, end)
   输入: VOCs组分 + O3 + NOx
    ↓
4. OBM工具执行:
   4.1 计算每种VOCs的OFP
   4.2 按类别汇总(烷烃、烯烃、芳香烃)
   4.3 敏感性诊断(VOCs vs NOx限制)
   4.4 识别关键控制物种
   4.5 生成控制建议
    ↓
5. 返回结果给Agent
    ↓
6. Agent生成图表和最终报告
```

---

## 五、技术难点与解决方案

### 5.1 PMF算法复杂性

**难点**: PMF是迭代优化算法,需要大量计算

**解决方案**:
- **方案1**: 调用外部API(如EPA PMF服务)
- **方案2**: 使用Python `scikit-learn.decomposition.NMF` (非负矩阵分解)
  ```python
  from sklearn.decomposition import NMF

  model = NMF(n_components=6, init='nndsvd', max_iter=500)
  W = model.fit_transform(X)  # 源贡献矩阵
  H = model.components_       # 源成分谱矩阵
  ```
- **方案3**: 简化版 - 基于源谱库最小二乘拟合

### 5.2 数据质量要求

**难点**:
- PMF需要≥20-30个样本
- 组分数据可能存在缺失值
- 不确定度估计

**解决方案**:
- 数据验证: 检查样本数、缺失值比例
- 缺失值处理:
  - 使用检出限的1/2填充
  - 插值法(仅适用于偶发缺失)
- 不确定度: 使用固定的相对标准偏差(如10%)

### 5.3 源谱解释

**难点**: PMF输出的因子需要人工解释为具体源类型

**解决方案**:
- 建立源谱特征库:
  ```python
  SOURCE_SIGNATURES = {
      "二次无机气溶胶": {"SO4": "high", "NO3": "high", "NH4": "high"},
      "燃煤源": {"SO4": "high", "EC": "moderate", "K": "low"},
      "机动车": {"EC": "high", "OC": "high", "NO3": "moderate"},
      ...
  }
  ```
- 自动匹配算法: 基于特征向量余弦相似度
- 人工审核: 提供源谱可视化供专家确认

### 5.4 OBM敏感性判断

**难点**: 不同文献使用不同的敏感性判断标准

**解决方案**:
- 使用多指标综合判断:
  ```python
  def diagnose_sensitivity(vocs_conc, nox_conc, hcho_conc, h2o2_conc, hno3_conc):
      indicators = {
          "VOCs/NOx": vocs_conc / nox_conc,
          "HCHO/NOy": hcho_conc / nox_conc,
          "H2O2/HNO3": h2o2_conc / hno3_conc
      }

      # 判断逻辑 (根据文献阈值)
      if indicators["VOCs/NOx"] > 8 and indicators["H2O2/HNO3"] > 0.6:
          return "VOCs-limited"
      elif indicators["VOCs/NOx"] < 4 and indicators["H2O2/HNO3"] < 0.3:
          return "NOx-limited"
      else:
          return "transitional"
  ```

---

## 六、验收标准

### 6.1 功能验收

- [ ] PMF工具能成功识别至少4种源类型
- [ ] PMF源贡献率总和=100% (±5%误差)
- [ ] OBM工具能计算所有VOCs物种的OFP
- [ ] OBM能正确判断敏感性类型(VOCs/NOx/transitional)
- [ ] 两个工具都能生成可视化配置

### 6.2 性能验收

- [ ] PMF计算时间 < 30秒 (50个样本)
- [ ] OBM计算时间 < 5秒
- [ ] API超时处理正常(timeout=60s)
- [ ] 并发调用不冲突

### 6.3 质量验收

- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试通过率 = 100%
- [ ] 端到端测试场景全部通过
- [ ] 错误处理完整(无未捕获异常)

### 6.4 文档验收

- [ ] API文档完整(入参、出参、示例)
- [ ] 算法原理文档清晰
- [ ] 工具使用指南包含实际案例
- [ ] 代码注释覆盖率 > 60%

---

## 七、风险评估与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| **无现成API** | 中 | 高 | 采用简化版实现,后续迭代为完整算法 |
| **数据质量差** | 高 | 中 | 增强数据验证,提供明确的数据要求提示 |
| **算法准确性争议** | 中 | 中 | 提供算法来源文献,支持参数可调 |
| **计算时间过长** | 低 | 中 | 异步执行,前端显示进度条 |
| **源谱解释错误** | 中 | 中 | 提供人工审核接口,支持源类型重命名 |

---

## 八、后续优化方向

### 8.1 短期优化 (1个月内)

1. **增强数据验证**
   - 实时检查数据质量
   - 提供数据完整性报告
2. **优化源谱库**
   - 收集本地化源谱数据
   - 支持用户自定义源谱
3. **改进可视化**
   - 增加源谱雷达图
   - 增加敏感性诊断动态图

### 8.2 中期优化 (3个月内)

1. **算法升级**
   - 从简化版升级为完整PMF算法
   - 增加不确定度分析(Bootstrap方法)
2. **增加新功能**
   - CMB (Chemical Mass Balance) 源解析
   - WRF-Chem 区域传输模拟集成
3. **历史数据分析**
   - 支持跨时间段对比
   - 源贡献季节变化分析

### 8.3 长期愿景 (6个月+)

1. **机器学习增强**
   - 使用深度学习自动识别源类型
   - 时间序列预测(未来源贡献)
2. **多站点联合分析**
   - 区域尺度源解析
   - 源贡献空间分布
3. **实时监测**
   - 准实时PMF计算(每小时更新)
   - 源贡献预警系统

---

## 九、参考资料

### 9.1 PMF相关

- **EPA PMF 5.0 User Guide**: https://www.epa.gov/air-research/positive-matrix-factorization-model-environmental-data-analyses
- **PMF理论**: Paatero & Tapper (1994) - *Positive Matrix Factorization: A Non-negative Factor Model with Optimal Utilization of Error Estimates*
- **Python库**: `scikit-learn.decomposition.NMF`

### 9.2 OBM/OFP相关

- **MIR系数**: Carter, W.P.L. (2010) - *Development of the SAPRC-07 Chemical Mechanism*
- **敏感性诊断**: Sillman et al. (1997) - *The Use of NOy, H2O2, and HNO3 as Indicators for Ozone-NOx-Hydrocarbon Sensitivity*
- **OFP计算方法**: GB/T 37863-2019 《臭氧生成潜势计算方法》

### 9.3 项目内部文档

- `backend/docs/ReAct_Agent完整开发总结.md`
- `backend/docs/图表工具优化实施总结.md`
- `backend/app/tools/base/tool_interface.py`

---

**方案制定人**: Claude Code
**审核状态**: 待审核
**下一步**: 需求调研与API确认 (Phase 1)
