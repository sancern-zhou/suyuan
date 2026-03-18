# PMF源解析工具工作手册

## 1. 概述

本项目包含两个PMF源解析工具，基于**NIMFA无监督因子分解**实现：

| 工具 | 文件 | 适用污染物 | 主要功能 |
|------|------|-----------|---------|
| PM_PMF | calculate_pm_pmf/tool.py | PM2.5/PM10 | 颗粒物源解析（水溶性离子+碳组分） |
| VOC_PMF | calculate_vocs_pmf/tool.py | VOCs | 臭氧前体物溯源 |

**核心特点**：
- 无监督学习：无需预定义源谱库
- 专家解读：返回因子载荷矩阵，由LLM根据化学特征判断污染源
- 自动因子数分析：规范6.1.3
- 数据驱动权重配置：规范6.1.2

---

## 2. 数据流

```
输入数据 → 数据验证 → 预处理(构建浓度矩阵) → 质量控制(KMO/Bartlett)
                                                      ↓
因子数分析 ← 权重配置 ← 关键组分识别 ← 数据质量分析
    ↓
NIMFA因子分解/SVD+NNLS简化算法
    ↓
结果转换(W/H矩阵 → 贡献率/载荷矩阵)
    ↓
输出(因子载荷、贡献率、时间序列、性能指标)
```

---

## 3. 方法实现细节

### 3.1 因子分解算法

#### NIMFA库（首选）

代码位置：`quality_control.py:NIMFAWrapper`

```python
# 核心调用流程
V = np.asarray(X_matrix)                    # 浓度矩阵
fm = nimfa.Nmf(V, rank=rank, max_iter=max_iter)
fit_result = fm()

W = fit_result.basis()                      # 源贡献矩阵 (n_samples × p)
H = fit_result.coef()                       # 因子载荷矩阵 (p × m)
```

**返回指标**：
| 指标 | 计算方法 |
|-----|---------|
| Q值 | `sum((X - WH)^2)` 残差平方和 |
| R² | `1 - SSres/SStot` 解释方差比例 |
| 稀疏度 | `sqrt(n) - norm_1/norm_2` |
| 迭代次数 | 收敛所需迭代数 |

#### SVD+NNLS（降级方案）

代码位置：`calculator.py:_simplified_factorization`

当NIMFA不可用时，使用SVD分解+非负最小二乘求解：

```python
U, S, Vt = svd(X_matrix, full_matrices=False)  # SVD分解
W_matrix = U[:, :rank] * S[:rank]               # 初始W矩阵
H_matrix = Vt[:rank, :]                         # 初始H矩阵

# NNLS优化W矩阵
for i in range(n_samples):
    G_matrix[i, :], _ = nnls(H_matrix.T, X_matrix[i, :])
```

### 3.2 权重配置（规范6.1.2）

代码位置：`pmf_weights.py:PMFWeightCalculator`

#### 基础权重设置

```python
# 关键标识组分权重 = 1.0
if comp in key_components:
    base_weights[comp] = 1.0
# 非关键组分权重 = 0.5
elif comp in secondary_components:
    base_weights[comp] = 0.5
else:
    base_weights[comp] = 0.5
```

#### PM2.5关键组分

| 类别 | 组分 | 中文名 |
|-----|------|-------|
| 水溶性离子 | SO4, NO3, NH4 | 硫酸盐、硝酸盐、铵盐 |
| | Cl | 氯离子 |
| 碳组分 | OC, EC | 有机碳、元素碳 |
| 地壳元素 | Al, Si, Ca, K, Fe, Ti | 铝、硅、钙、钾、铁、钛 |

#### VOCs关键物种

| 类别 | 物种 | 中文名 |
|-----|------|-------|
| 烯烃 | C2H4, C3H6 | 乙烯、丙烯 |
| 烷烃 | C2H6, C3H8 | 乙烷、丙烷 |
| 芳烃 | C6H6, C7H8, C8H10 | 苯、甲苯、二甲苯/乙苯 |
| 生物源 | C5H8 | 异戊二烯 |

#### 质量调整因子

```python
# 基于变异系数(CV)调整
if cv < 0.3:
    qf = 1.0           # 数据稳定
elif cv < 0.5:
    qf = 0.8           # 中等变异
else:
    qf = 0.5           # 高变异

# 最终权重
final_weight = base_weight * quality_factor

# 缺失率>20%排除
if stats.missing_rate > 0.2:
    excluded.append(comp)
```

### 3.3 因子数确定（规范6.1.3）

代码位置：`factor_analyzer.py:FactorAnalyzer`

#### 分析范围

```python
# 因子数范围：3-8
max_possible_rank = min(min(20, n_samples // 10), n_components)
max_rank = min(max_rank, max_possible_rank)
```

#### Q值变化曲线分析（主方法）

```python
# 计算下降率
for i in range(1, len(Q_curve)):
    drop_rate = (prev_Q - curr_Q) / prev_Q
    Q_curve[i]["drop_rate"] = drop_rate

# 拐点判定：下降率 < 5%
for i in range(1, len(Q_curve)):
    if Q_curve[i].get("drop_rate", 0) < 0.05:
        return Q_curve[i-1]["rank"]  # 返回拐点前一个因子数
```

#### 残差分析（验证）

```python
# 计算加权残差
uncertainty = np.abs(X_matrix) * 0.1 + 0.01
weighted_residuals = residuals / (uncertainty + 1e-10)

# 关键组分残差 <= 3
key_passed = np.all(np.abs(key_residuals) <= 3)

# 整体通过率 >= 80%
all_pass_rate = np.sum(all_in_range) / len(all_in_residuals)
passed = key_passed and all_pass_rate >= 0.8
```

#### 回归诊断（验证）

```python
# 检查系数非负
coefficients_non_negative = np.all(contributions >= 0)

# 计算相关性
correlation = np.corrcoef(obs_valid, pred_valid)[0, 1]

# 综合判断
passed = coefficients_non_negative and correlation > 0.8
```

#### 综合置信度

```python
score = 0.0
# Q值合理性 (0-0.3): Q_ratio在0.85-1.15之间得满分
if 0.85 <= q_ratio <= 1.15:
    score += 0.3
# 残差验证通过 (0-0.3)
if optimal_rank in pass_residual:
    score += 0.3
# 回归验证通过 (0-0.3)
if optimal_rank in pass_regression:
    score += 0.3
# Q值稳定性 (0-0.1)
if prev_drop > 0.05:
    score += 0.1
```

### 3.4 质量控制

代码位置：`quality_control.py:PMFQualityController`

#### KMO检验

```python
# KMO值计算
sum_sq_corr = np.sum(corr_matrix ** 2) - np.sum(np.diag(corr_matrix) ** 2)
sum_sq_partial = np.sum(partial_corr ** 2)
kmo = sum_sq_corr / (sum_sq_corr + sum_sq_partial)

# KMO等级
kmo >= 0.9: "极佳"
kmo >= 0.8: "很好"
kmo >= 0.7: "良好"
kmo >= 0.6: "一般"
kmo < 0.6: "不适合"
```

#### Bartlett球形度检验

```python
# Bartlett统计量
bartlett_stat = -(n - 1 - (2p + 5)/6) * log(det_corr)

# p值 < 0.05 通过检验
passed = p_value < 0.05
```

#### 算法推荐

```python
quality_score = 0
quality_score += 40 if kmo_passed else 20
quality_score += 40 if bartlett_passed else 20
quality_score += preprocessing_score * 20

# 推荐结果
quality_score >= 80: 推荐nimfa，置信度"高"
quality_score >= 60: 推荐nimfa，置信度"中"
quality_score < 60:  推荐simplified，置信度"低"
```

---

## 4. 工具使用说明

### 4.1 PM_PMF工具

代码位置：`calculate_pm_pmf/tool.py:CalculatePMFTool`

#### 输入参数

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| station_name | string | 是 | 超级站点名称 |
| data_id | string | 是 | 水溶性离子数据ID（particulate_unified格式） |
| gas_data_id | string | 否 | 碳组分数据ID（role=carbon） |
| pollutant_type | string | 否 | PM2.5（默认）或PM10 |
| nimfa_rank | int | 否 | 因子数（默认自动分析） |

#### 使用示例

```python
# 步骤1：获取水溶性离子数据
ion_data = get_particulate_data(
    "深圳市2024年12月的PM2.5水溶性离子数据",
    role="water-soluble"
)

# 步骤2：获取碳组分数据（推荐）
carbon_data = get_particulate_data(
    "深圳市2024年12月的PM2.5碳组分数据",
    role="carbon"
)

# 步骤3：执行PMF
pmf_result = calculate_pm_pmf(
    station_name="深圳南山",
    data_id="particulate_unified:xxx",
    gas_data_id="particulate_unified:yyy"
)
```

#### 数据要求

- 水溶性离子数据：有效样本 >= 10
- 碳组分数据：有效样本 >= 10
- 组分数：>= 3

### 4.2 VOC_PMF工具

代码位置：`calculate_vocs_pmf/tool.py:CalculateVOCSPMFTool`

#### 输入参数

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| station_name | string | 是 | 超级站点名称 |
| data_id | string | 是 | VOCs数据ID（vocs_unified格式） |
| nimfa_rank | int | 否 | 因子数（默认自动分析） |

#### 使用示例

```python
# 获取VOCs数据
vocs_data = get_vocs_data(
    "广州市2024年8月的VOCs小时数据",
    species="乙烯、丙烯、苯、甲苯、二甲苯"
)

# 执行PMF
voc_pmf = calculate_vocs_pmf(
    station_name="广州天河",
    data_id="vocs_unified:yyy"
)
```

### 4.3 输出结果格式

```json
{
    "status": "success",
    "data": {
        "sources": [
            {"source_name": "因子1", "contribution_pct": 32.5, "concentration": 15.2},
            {"source_name": "因子2", "contribution_pct": 28.3, "concentration": 13.2}
        ],
        "source_contributions": {"因子1": 32.5, "因子2": 28.3},
        "source_concentrations": {"因子1": 15.2, "因子2": 13.2},
        "factor_loadings": {
            "因子1": {"SO4": 0.85, "NO3": 0.72, "NH4": 0.91},
            "因子2": {"OC": 0.88, "EC": 0.82}
        },
        "performance": {
            "R2": 0.89,
            "q_value": 1250.5,
            "convergence_iterations": 85
        }
    },
    "weights_config": {
        "key_components": ["SO4", "NO3", "NH4", "OC", "EC"],
        "component_count": 8
    },
    "factor_analysis": {
        "optimal_rank": 5,
        "confidence": 0.85,
        "pass_residual": [4, 5, 6],
        "pass_regression": [4, 5, 6]
    }
}
```

---

## 5. 数据合并（PM_PMF）

代码位置：`calculator.py:_merge_gas_data`

当同时提供水溶性离子数据和碳组分数据时，系统会自动合并：

```python
# 按时间戳匹配
gas_dict = {timestamp: record for record in gas_records}

# 合并到主数据
for record in component_data:
    timestamp = record.get("timestamp", "")
    if timestamp in gas_dict:
        # 提取OC/EC
        for key in ("OC", "EC"):
            if key in gas_record:
                merged_record["components"][key] = gas_record[key]
```

---

## 6. 质量评估指标

### 6.1 模型性能

| 指标 | 良好 | 一般 | 较差 |
|-----|------|------|------|
| R² | > 0.85 | 0.7-0.85 | < 0.7 |
| Q_ratio | 0.85-1.15 | 0.7-1.3 | 其他 |
| 置信度 | > 80% | 60-80% | < 60% |

### 6.2 数据质量

| 检验 | 阈值 | 说明 |
|-----|------|------|
| KMO | >= 0.6 | 数据适合因子分析 |
| Bartlett p | < 0.05 | 变量间显著相关 |
| 缺失率 | < 20% | 数据完整性 |
| 变异系数 | 无固定阈值 | 影响权重配置 |

---

## 7. 专家解读指南

### 7.1 因子载荷解读

| 载荷特征 | 可能污染源 | 典型组分 |
|---------|-----------|---------|
| SO4/NO3/NH4高载荷 | 二次生成 | 硫酸盐、硝酸盐、铵盐 |
| OC/EC高载荷 | 机动车/燃煤 | 有机碳、元素碳 |
| Ca/Si/Al高载荷 | 土壤扬尘 | 钙、硅、铝 |
| C2H4/C3H6高载荷 | 机动车尾气 | 乙烯、丙烯 |
| C6H6/C7H8高载荷 | 工业溶剂 | 苯、甲苯 |

### 7.2 解读流程

1. 检查因子载荷矩阵，识别各因子主要载荷物种
2. 对照源特征表判断污染源类型
3. 验证时间序列是否符合源排放规律
4. 综合气象条件、区域传输等因素

---

*文档基于代码v3.1.0生成*
