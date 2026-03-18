# PyBox 集成方案

> 版本: v1.0.0  
> 日期: 2024-12-03  
> 状态: 实施中

## 一、背景与目标

### 1.1 现有OBM工具不足

| 问题 | 现有实现 | 期望目标 |
|------|----------|----------|
| 化学机理 | MIR系数法(43物种) | 完整MCM/RACM2(100+物种, 500+反应) |
| O3生成计算 | 线性OFP累加 | 完整光化学ODE求解 |
| 敏感性诊断 | VOCs/NOx比值法 | 偏导数梯度分析 + EKMA等浓度曲线 |
| 减排模拟 | 文本建议 | 定量5路径模拟 |
| 气象参数 | 不支持 | 温度/光照/压力依赖 |

### 1.2 目标

1. **集成PyBox箱模型引擎** - 支持完整化学机理模拟
2. **实现真正的EKMA分析** - 生成VOCs-NOx-O3等浓度曲面
3. **保留快速模式** - MIR系数法作为快速筛查选项
4. **支持减排情景模拟** - 5种VOCs/NOx减排比例路径

---

## 二、技术选型

### 2.1 PyBox 核心特性

| 特性 | 说明 |
|------|------|
| **GitHub** | https://github.com/loftytopping/PyBox |
| **文档** | https://pybox.readthedocs.io/ |
| **许可证** | GPL-3.0 |
| **化学机理** | MCM (Master Chemical Mechanism) |
| **ODE求解器** | Assimulo (CVode/RodasODE) |
| **加速方式** | Numba JIT / 可选Fortran |

### 2.2 依赖安装

```bash
# Conda环境 (推荐)
conda create -n obm_full python=3.9 -y
conda activate obm_full
conda install -c conda-forge assimulo numba numpy scipy pandas matplotlib -y

# 可选: 气溶胶模拟依赖
conda install -c conda-forge openbabel flask-wtf -y
```

### 2.3 备选方案

| 库名 | 优势 | 劣势 |
|------|------|------|
| **PyCHAM** | 完整气溶胶耦合 | 需要Open Babel |
| **INCHEM-Py** | 文档完善 | 主要针对室内 |
| **AtChem2** | 官方MCM支持 | Fortran核心 |

---

## 三、架构设计

### 3.1 双模式架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        OBM Analysis Tool (v2.0)                         │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐    ┌────────────────────────────────────────┐  │
│  │   Fast Mode (现有)   │    │     Full Chemistry Mode (新增)         │  │
│  │                     │    │                                        │  │
│  │  - MIR系数法        │    │  - PyBox Engine                        │  │
│  │  - VOCs/NOx比值法   │    │  - MCM/RACM2机理                       │  │
│  │  - ~1秒计算         │    │  - 完整ODE求解                         │  │
│  │                     │    │  - ~5-30分钟计算                       │  │
│  │  适用: 快速筛查     │    │  适用: 精确分析/科研                   │  │
│  └─────────────────────┘    └────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 模块结构

```
backend/app/tools/analysis/
├── calculate_obm_ofp/          # 现有模块(保留)
│   ├── calculator.py           # MIR系数法计算器
│   ├── mir_coefficients.py     # MIR系数表
│   └── tool.py                 # 工具接口
│
├── enhanced_obm/               # 现有增强模块(保留)
│   ├── ekma_engine.py          # 简化EKMA
│   ├── po3_engine.py           # 简化PO3
│   └── rir_engine.py           # 简化RIR
│
└── pybox_integration/          # 【新增】PyBox集成模块
    ├── __init__.py             # 模块入口
    ├── config.py               # 配置管理
    ├── pybox_adapter.py        # PyBox引擎适配器
    ├── mechanism_loader.py     # 化学机理加载器
    ├── vocs_mapper.py          # VOCs物种映射
    ├── ekma_full.py            # 完整EKMA分析
    ├── reduction_simulator.py  # 减排情景模拟
    ├── tool.py                 # 工具接口
    └── mechanisms/             # 化学机理文件
        ├── MCM_APINENE.eqn     # Alpha-Pinene机理(示例)
        └── species_mapping.json # 物种映射配置
```

---

## 四、核心模块设计

### 4.1 PyBoxAdapter - 引擎适配器

**职责**: 封装PyBox的ODE求解能力，提供统一API

```python
class PyBoxAdapter:
    def __init__(self, mechanism: str = "MCM_APINENE"):
        """初始化适配器，加载化学机理"""
        
    def simulate_single_point(
        self,
        initial_concentrations: Dict[str, float],
        simulation_time: float = 7200.0,
        temperature: float = 298.15,
        **kwargs
    ) -> Dict[str, Any]:
        """单点模拟，返回O3时序"""
        
    def simulate_ekma_grid(
        self,
        base_vocs: Dict[str, float],
        base_nox: float,
        voc_factors: List[float],
        nox_factors: List[float]
    ) -> Dict[str, Any]:
        """EKMA网格模拟，返回O3响应曲面"""
```

### 4.2 VOCsMapper - 物种映射器

**职责**: 将实测VOC物种映射到MCM/RACM2团簇物种

```python
# 映射示例
VOCS_TO_MCM_MAPPING = {
    "乙烯": "C2H4",
    "丙烯": "C3H6", 
    "甲苯": "TOLUENE",
    "邻二甲苯": "OXYL",
    # ...
}
```

### 4.3 FullEKMAAnalyzer - 完整EKMA分析器

**职责**: 生成VOCs-NOx-O3等浓度曲面，模拟减排路径

```python
class FullEKMAAnalyzer:
    def analyze(
        self,
        vocs_data: List[Dict],
        nox_data: List[Dict],
        o3_data: List[Dict],
        grid_resolution: int = 41
    ) -> Dict[str, Any]:
        """
        返回:
        - o3_surface: 2D O3响应曲面
        - reduction_paths: 5种减排路径
        - sensitivity: 敏感性诊断
        - visuals: 可视化数据
        """
```

### 4.4 ReductionSimulator - 减排模拟器

**职责**: 模拟5种减排情景路径

| 路径 | VOCs:NOx比例 | 适用场景 |
|------|--------------|----------|
| Case 1 | 1:0 | 仅减VOCs |
| Case 2 | 0:1 | 仅减NOx |
| Case 3 | 1:1 | 等比例减排 |
| Case 4 | 2:1 | VOCs优先 |
| Case 5 | 1:2 | NOx优先 |

---

## 五、数据流设计

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  VOCs实测数据 │────▶│  VOCsMapper  │────▶│ MCM团簇浓度  │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  NOx/O3数据  │────▶│ PyBoxAdapter │────▶│  ODE求解     │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  气象参数    │────▶│FullEKMAAnalyzer│───▶│ EKMA等浓度曲面│
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                                 ▼
                                          ┌──────────────┐
                                          │ UDF v2.0输出 │
                                          │ + 可视化数据  │
                                          └──────────────┘
```

---

## 六、API接口设计

### 6.1 工具接口

```python
# 工具注册
TOOL_NAME = "calculate_obm_full_chemistry"
TOOL_DESCRIPTION = "使用完整化学机理进行OBM分析(EKMA/PO3/RIR)"

# 输入参数
INPUT_SCHEMA = {
    "vocs_data_id": "str, VOCs数据ID",
    "nox_data_id": "str, NOx数据ID (可选)",
    "o3_data_id": "str, O3数据ID (可选)",
    "mode": "str, 分析模式 (ekma|po3|rir|all)",
    "mechanism": "str, 化学机理 (MCM|RACM2)",
    "grid_resolution": "int, EKMA网格分辨率 (默认41)"
}

# 输出格式 (UDF v2.0)
OUTPUT_SCHEMA = {
    "status": "success|failed",
    "success": True,
    "data": {
        "ekma": {...},
        "reduction_paths": {...},
        "sensitivity": {...}
    },
    "visuals": [...],
    "metadata": {
        "schema_version": "v2.0",
        "generator": "PyBoxIntegration",
        "mode": "full_chemistry"
    }
}
```

### 6.2 降级策略

```python
# 如果PyBox不可用，自动降级到快速模式
try:
    from .pybox_adapter import PyBoxAdapter
    PYBOX_AVAILABLE = True
except ImportError:
    PYBOX_AVAILABLE = False
    logger.warning("PyBox not available, using fast mode")
```

---

## 七、实施计划

### Phase 1: 基础框架 (当前)

- [x] 设计方案文档
- [ ] 创建模块目录结构
- [ ] 实现配置管理
- [ ] 实现VOCs物种映射器

### Phase 2: 核心引擎

- [ ] 实现PyBoxAdapter适配器
- [ ] 集成Assimulo ODE求解器
- [ ] 实现机理加载器

### Phase 3: EKMA分析

- [ ] 实现FullEKMAAnalyzer
- [ ] 实现减排路径模拟
- [ ] 实现可视化数据生成

### Phase 4: 集成测试

- [ ] 编写单元测试
- [ ] 与现有工具集成
- [ ] 性能优化

---

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Assimulo安装失败 | 无法使用完整模式 | 提供Docker镜像 |
| MCM机理文件缺失 | 无法加载化学反应 | 内置Alpha-Pinene示例机理 |
| 计算时间过长 | 用户体验差 | 提供进度回调 + 异步执行 |
| 内存占用过大 | 系统崩溃 | 限制网格分辨率上限 |

---

## 九、参考资源

1. **PyBox仓库**: https://github.com/loftytopping/PyBox
2. **MCM网站**: http://mcm.york.ac.uk/MCM/
3. **Assimulo文档**: https://jmodelica.org/assimulo/
4. **参考项目**: `D:\溯源\参考\OBM\EKMA.py`
5. **FACSIMILE机理**: `D:\溯源\参考\OBM-deliver_20200901\ekma_v0\ekma.fac`

---
根据对参考项目的分析，以下是现有OBM分析工具与参考项目的主要不足：

   现有OBM工具不足分析

   1. 化学机理差距 (最关键)

   对比项   │ 参考项目                         │ 现有工具
   ------+------------------------------+----------------
   化学机理  │ **RACM2机理** (102种物种, 504个反应) │ 仅MIR系数法 (43种物种)
   反应动力学 │ 完整光化学反应模拟                    │ 无化学反应模拟
   速率常数  │ 温度依赖的Arrhenius方程             │ 无
   光解速率  │ 太阳天顶角计算 (jhono, jhchor)      │ 无

   参考项目使用FACSIMILE引擎求解刚性ODE，模拟完整的大气光化学反应过程；现有工具只是简单的线性OFP累加。

   2. 分析方法差距

   方法       │ 参考项目                       │ 现有工具
   ---------+----------------------------+--------------
   **EKMA** │ ✅ 多参数二次拟合+等浓度曲线模拟         │ ❌ 无
   **PO3**  │ ✅ 臭氧生成速率时序分析              │ ❌ 骨架代码，未完整实现
   **RIR**  │ ✅ 相对增量反应性(扰动法)            │ ❌ 骨架代码，未完整实现
   敏感性诊断    │ 基于化学机理的HCHO/NOy, H2O2/HNO3 │ 仅VOCs/NOx比值法

   3. 物种覆盖差距

   参考项目VOCs物种列表(VOCsList4RACM2.xlsx)包含完整的RACM2团簇物种映射：
   •  烷烃: HC3, HC5, HC8 (按碳链长度分类)
   •  烯烃: OLI, OLT, ISO (内烯、端烯、异戊二烯)
   •  芳香烃: TOL, XYL, CSL (甲苯类、二甲苯类、甲酚)
   •  醛酮: ALD, KET, MACR, MVK
   •  完整自由基: OH, HO2, RO2各类

   现有工具仅支持43种实测物种，缺少中间产物和自由基。

   4. 气象参数处理差距

   参考项目输入：
   •  温度 (T)、气压 (P)、相对湿度 (RH)
   •  太阳天顶角 (计算光解速率)
   •  边界层高度 (混合稀释)

   现有工具完全缺失气象参数的影响。

   5. 减排情景模拟

   参考项目EKMA.py实现：
   •  5种VOCs/NOx减排比例路径 (1:0, 0:1, 1:1, 2:1, 1:2)
   •  等浓度曲线可视化
   •  减排效果预测

   现有工具仅给出控制建议文本，无定量模拟。

   ──────────────────────────────────────────

   建议改进优先级

   1. P0: 集成完整化学机理 (RACM2或MCM)
   2. P1: 实现真正的EKMA等浓度曲线分析
   3. P1: 加入气象参数(温度/光照)对反应速率的影响
   4. P2: 完善PO3/RIR分析引擎
   5. P2: 减排情景定量模拟功能