# DataAnalysisExpert工具名称修复方案

**问题**: DataAnalysisExpert使用的工具名称与实际注册的工具不匹配
**状态**: ⚠️ 阻塞性问题 - 必须立即修复
**影响**: PMF和OBM工具无法被Agent调用

---

## 问题诊断

### 1. 实际注册的工具 (backend/app/tools/__init__.py)

```python
✅ get_component_data        # 统一的组分数据查询工具(VOCs + 颗粒物)
✅ calculate_pmf             # PMF源解析工具
✅ calculate_obm_ofp         # OBM/OFP分析工具
```

### 2. DataExpert当前使用的工具名称 (backend/app/agent/experts/expert_agents.py:154-162)

```python
❌ get_vocs_components       # 不存在！应该是 get_component_data
❌ get_particulate_components # 不存在！应该是 get_component_data
❌ 缺少 calculate_pmf         # 未添加到工具列表
❌ 缺少 calculate_obm_ofp     # 未添加到工具列表
```

### 3. 影响

- Agent启动时会打印warning: `expert_missing_tools`
- 调用组分数据查询时返回None
- PMF/OBM工具即使存在也无法被调用
- 源解析流程彻底中断

---

## 修复方案

### Step 1: 更新工具列表

**文件**: `backend/app/agent/experts/expert_agents.py`
**位置**: 第150-163行

**原代码**:
```python
def __init__(self):
    super().__init__(
        name="data_analysis_expert",
        description="负责数据获取、清洗和初步分析",
        tool_names=[
            "get_weather_data",
            "get_weather_forecast",
            "get_air_quality",
            "get_vocs_components",          # ❌ 错误
            "get_particulate_components",   # ❌ 错误
            "analyze_upwind_enterprises",
            "get_nearby_stations"
        ]
    )
```

**修改后**:
```python
def __init__(self):
    super().__init__(
        name="data_analysis_expert",
        description="负责数据获取、清洗和初步分析（含源解析）",
        tool_names=[
            "get_weather_data",
            "get_weather_forecast",
            "get_air_quality",
            "get_component_data",           # ✅ 正确：统一工具
            "analyze_upwind_enterprises",
            "calculate_pmf",                # ✅ 新增：PMF源解析
            "calculate_obm_ofp"             # ✅ 新增：OBM/OFP分析
        ]
    )
```

---

### Step 2: 删除旧的组分数据获取方法

**删除以下两个方法** (行422-490):
- `_fetch_vocs_components`
- `_fetch_particulate_components`

---

### Step 3: 添加新的统一组分数据获取方法

**位置**: 在 `_analyze_enterprises` 方法之后

```python
async def _fetch_component_data(
    self,
    params: Dict[str, Any],
    component_type: str  # "vocs" or "particulate"
) -> Any:
    """
    获取组分数据（VOCs或颗粒物）

    Args:
        params: 提取的参数
        component_type: 组分类型 ("vocs" 或 "particulate")

    Returns:
        组分数据 或 None
    """
    # 检查工具是否可用
    if "get_component_data" not in self.tools:
        logger.warning(
            "tool_unavailable_skipping",
            tool="get_component_data",
            expert=self.name
        )
        return None

    try:
        station_name = params.get("station_name") or params.get("location")
        start_time = params.get("start_time")
        end_time = params.get("end_time") or start_time

        logger.info(
            "fetching_component_data",
            station_name=station_name,
            component_type=component_type,
            start_time=start_time,
            end_time=end_time
        )

        result = await self._execute_tool(
            "get_component_data",
            station_name=station_name,
            component_type=component_type,
            start_time=start_time,
            end_time=end_time
        )

        if result and result.get("success"):
            logger.info(
                "component_data_fetched",
                component_type=component_type,
                count=result.get("count", 0)
            )
        else:
            logger.warning(
                "component_data_empty",
                component_type=component_type,
                station_name=station_name
            )

        return result

    except Exception as e:
        logger.warning(
            "component_data_fetch_failed",
            component_type=component_type,
            error=str(e)
        )
        return None
```

---

### Step 4: 更新Phase 3调用逻辑

**文件**: `backend/app/agent/experts/expert_agents.py`
**位置**: 第213-234行 (execute方法中的Phase 3)

**原代码**:
```python
# Phase 3: 获取组分数据（基于污染物类型）
pollutant = extracted_params.get("pollutant", "").upper()
if pollutant in ["O3", "OZONE"]:
    logger.info("data_expert_phase_start", phase="VOCs组分数据获取", phase_num=3)
    组分数据 = await self._fetch_vocs_components(extracted_params)
    result_data["vocs_components"] = 组分数据
    logger.info(
        "data_expert_phase_complete",
        phase="VOCs组分数据获取",
        phase_num=3,
        has_result=组分数据 is not None
    )
elif pollutant in ["PM2.5", "PM10"]:
    logger.info("data_expert_phase_start", phase="颗粒物组分数据获取", phase_num=3)
    组分数据 = await self._fetch_particulate_components(extracted_params)
    result_data["particulate_components"] = 组分数据
    logger.info(
        "data_expert_phase_complete",
        phase="颗粒物组分数据获取",
        phase_num=3,
        has_result=组分数据 is not None
    )
```

**修改后**:
```python
# Phase 3: 获取组分数据（基于污染物类型）
pollutant = extracted_params.get("pollutant", "").upper()
if pollutant in ["O3", "OZONE"]:
    logger.info("data_expert_phase_start", phase="VOCs组分数据获取", phase_num=3)
    组分数据 = await self._fetch_component_data(extracted_params, "vocs")
    result_data["vocs_components"] = 组分数据
    logger.info(
        "data_expert_phase_complete",
        phase="VOCs组分数据获取",
        phase_num=3,
        has_result=组分数据 is not None
    )
elif pollutant in ["PM2.5", "PM10"]:
    logger.info("data_expert_phase_start", phase="颗粒物组分数据获取", phase_num=3)
    组分数据 = await self._fetch_component_data(extracted_params, "particulate")
    result_data["particulate_components"] = 组分数据
    logger.info(
        "data_expert_phase_complete",
        phase="颗粒物组分数据获取",
        phase_num=3,
        has_result=组分数据 is not None
    )
```

---

### Step 5 (可选但强烈建议): 添加源解析调用

**在Phase 3之后添加Phase 4**:

```python
# Phase 4: 源解析（基于组分数据）
if result_data.get("vocs_components"):
    # 检查是否成功获取数据
    vocs_data = result_data["vocs_components"]
    if vocs_data and vocs_data.get("success") and vocs_data.get("count", 0) > 0:
        logger.info("data_expert_phase_start", phase="OBM/OFP分析", phase_num=4)

        # 准备NOx数据
        nox_data = None
        if result_data.get("air_quality"):
            # 从空气质量数据中提取NOx (如果有)
            nox_data = result_data["air_quality"].get("data")

        # 调用OBM/OFP工具
        ofp_result = await self._execute_tool(
            "calculate_obm_ofp",
            station_name=extracted_params.get("station_name") or extracted_params.get("location"),
            vocs_data=vocs_data["data"],
            nox_data=nox_data
        )

        result_data["ofp_analysis"] = ofp_result

        logger.info(
            "data_expert_phase_complete",
            phase="OBM/OFP分析",
            phase_num=4,
            has_result=ofp_result is not None,
            total_ofp=ofp_result.get("total_ofp") if ofp_result else None
        )

if result_data.get("particulate_components"):
    # 检查是否成功获取数据
    particulate_data = result_data["particulate_components"]
    if particulate_data and particulate_data.get("success") and particulate_data.get("count", 0) > 0:
        logger.info("data_expert_phase_start", phase="PMF源解析", phase_num=4)

        # 调用PMF工具
        pmf_result = await self._execute_tool(
            "calculate_pmf",
            station_name=extracted_params.get("station_name") or extracted_params.get("location"),
            component_data=particulate_data["data"],
            pollutant=extracted_params.get("pollutant", "PM2.5")
        )

        result_data["pmf_analysis"] = pmf_result

        logger.info(
            "data_expert_phase_complete",
            phase="PMF源解析",
            phase_num=4,
            has_result=pmf_result is not None,
            source_count=len(pmf_result.get("source_contributions", {})) if pmf_result else 0
        )
```

---

## 验证步骤

### 1. 启动后端服务

```bash
cd backend
python -m uvicorn app.main:app --reload
```

### 2. 检查日志

**正常情况**:
```
tool_loaded tool=get_component_data
tool_loaded tool=calculate_pmf
tool_loaded tool=calculate_obm_ofp
expert_initialized expert=data_analysis_expert tools=["get_weather_data", "get_air_quality", "get_component_data", "calculate_pmf", "calculate_obm_ofp", ...]
```

**异常情况** (修复前):
```
expert_missing_tools expert=data_analysis_expert missing=["get_vocs_components", "get_particulate_components"] available=[...]
```

### 3. API测试

```bash
curl http://localhost:8000/api/agent/stats
```

**预期输出**:
```json
{
  "experts": [
    {
      "name": "data_analysis_expert",
      "available_tools": [
        "get_weather_data",
        "get_air_quality",
        "get_component_data",
        "calculate_pmf",
        "calculate_obm_ofp",
        "analyze_upwind_enterprises"
      ]
    }
  ]
}
```

### 4. 功能测试

**测试查询**:
```
"对广州天河超级站2025年8月的PM2.5进行源解析"
```

**预期Agent行为**:
1. ✅ 调用 `get_component_data(component_type="particulate")`
2. ✅ 调用 `calculate_pmf(component_data=[...])`
3. ✅ 返回源解析结果

---

## 风险评估

### 风险1: 现有功能中断
**可能性**: 低
**原因**: 只是重命名工具调用，不影响其他逻辑
**缓解**: 保留旧方法作为备份，待测试通过后再删除

### 风险2: 数据格式不兼容
**可能性**: 中
**原因**: `get_component_data` 返回格式可能与PMF/OBM期望不一致
**缓解**: 已在设计时对齐格式，测试时重点验证

---

## 回滚方案

如果修复后出现问题，可以快速回滚:

```bash
# 1. 使用Git恢复
git checkout backend/app/agent/experts/expert_agents.py

# 2. 或手动还原工具列表
tool_names=[
    "get_weather_data",
    "get_weather_forecast",
    "get_air_quality",
    "analyze_upwind_enterprises"
]
# 不调用组分数据和源解析工具
```

---

## 总结

**修复内容**:
1. ✅ 更正工具名称: `get_vocs_components`, `get_particulate_components` → `get_component_data`
2. ✅ 新增工具: `calculate_pmf`, `calculate_obm_ofp`
3. ✅ 统一组分数据获取方法
4. ✅ 可选: 自动调用源解析工具

**预计工作量**: 30-60分钟
**测试时间**: 30分钟
**优先级**: P0 - 必须立即修复

**完成后效果**:
- Agent能够正确识别和调用PMF/OBM工具
- 源解析流程完整可用
- 为前后端集成测试扫清障碍
