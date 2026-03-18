# 前端地图和图表展示修复方案

## 🔍 问题诊断

### 当前问题
前端没有任何图表被展示，原因是**后端生成的payload格式与前端期望的格式不匹配**。

### 格式不匹配详情

#### 1. **Bar Chart (柱状图)**
- ❌ 后端生成:
```python
{
    "title": "OFP贡献前十物种",
    "categories": ["乙烯", "丙烯", ...],
    "series": [{"name": "OFP贡献前十物种", "data": [10.5, 8.3, ...]}]
}
```

- ✅ 前端期望:
```typescript
{
    "x": ["乙烯", "丙烯", ...],
    "y": [10.5, 8.3, ...]
}
```

#### 2. **Pie Chart (饼图)**
- ❌ 后端生成:
```python
{
    "title": "VOCs浓度前十物种",
    "data": [{"name": "乙烯", "value": 10.5}, ...]
}
```

- ✅ 前端期望:
```typescript
[
    {"name": "乙烯", "value": 10.5},
    {"name": "丙烯", "value": 8.3},
    ...
]
```

#### 3. **Timeseries (时序图)**
- ✅ 格式基本匹配，但需要确认字段名

#### 4. **Map (地图)**
- ✅ 格式基本匹配

---

## 🛠️ 解决方案

### 方案 A: 修改后端生成器（推荐）✅

**优点**: 
- 一次修改，所有分析模块受益
- 保持前端代码稳定
- 符合前端已有的渲染逻辑

**修改文件**: `backend/app/utils/visualization.py`

#### 修改内容:

```python
def generate_bar_payload(
    data: List[Dict[str, Any]],
    title: str = "柱状图",
    category_key: str = "category",
    value_key: str = "value",
) -> Dict[str, Any]:
    """Generate ECharts bar chart payload."""
    categories = []
    values = []

    for item in data:
        if not isinstance(item, dict):
            continue
        cat = item.get(category_key)
        val = item.get(value_key)
        if cat is not None and val is not None:
            categories.append(str(cat))
            values.append(val)

    # ✅ 修改为前端期望的格式
    return {
        "x": categories,  # 改为 x
        "y": values,      # 改为 y
    }


def generate_pie_payload(
    data: List[Dict[str, Any]],
    title: str = "饼图",
    name_key: str = "name",
    value_key: str = "value",
) -> Dict[str, Any]:
    """Generate ECharts pie chart payload."""
    pie_data = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get(name_key)
        value = item.get(value_key)
        if name is not None and value is not None:
            pie_data.append({"name": str(name), "value": value})

    # ✅ 直接返回数组，不包装
    return pie_data  # 不是 {"title": ..., "data": ...}
```

---

### 方案 B: 修改前端渲染器

**优点**: 
- 后端格式更语义化
- 可以保留title等元数据

**缺点**: 
- 需要修改多个前端组件
- 增加前端复杂度

**修改文件**: `frontend/src/components/ChartsPanel.tsx`

---

## 📋 实施步骤

### Step 1: 修复 Bar Chart 生成器

```python
# backend/app/utils/visualization.py

def generate_bar_payload(...) -> Dict[str, Any]:
    # ... 现有逻辑 ...
    
    return {
        "x": categories,  # 改名
        "y": values,      # 改名
    }
```

### Step 2: 修复 Pie Chart 生成器

```python
# backend/app/utils/visualization.py

def generate_pie_payload(...) -> List[Dict[str, Any]]:  # 返回类型改为List
    pie_data = []
    # ... 现有逻辑 ...
    
    return pie_data  # 直接返回数组
```

### Step 3: 验证 Timeseries 格式

确认返回格式为:
```python
{
    "x": ["2025-08-09T00:00:00Z", ...],
    "series": [
        {"name": "站点A", "data": [150.5, 180.2, ...]},
        {"name": "站点B", "data": [145.3, 175.8, ...]}
    ]
}
```

### Step 4: 验证 Map 格式

确认返回格式为:
```python
{
    "map_center": {"lng": 113.3, "lat": 23.1},
    "station": {"lng": 113.3, "lat": 23.1, "name": "目标站点"},
    "enterprises": [
        {"lng": 113.2, "lat": 23.0, "name": "企业A", "industry": "化工"},
        ...
    ],
    "upwind_paths": [...],  # 可选
    "sectors": [...]         # 可选
}
```

---

## 🧪 测试清单

### 1. VOCs分析模块
- [ ] VOCs浓度前十物种（饼图）
- [ ] OFP贡献前十物种（柱状图）
- [ ] 行业VOCs排放贡献（饼图）

### 2. 颗粒物分析模块
- [ ] 颗粒物主要组分（饼图）
- [ ] 行业颗粒物排放贡献（柱状图）

### 3. 区域对比分析模块
- [ ] 站点浓度时序对比（时序图）

### 4. 气象分析模块
- [ ] 上风向企业地图（高德地图）

---

## 🔧 前端ChartsPanel期望格式总结

### Bar Chart
```typescript
payload: {
    x: string[],      // 类别数组
    y: number[]       // 数值数组
}
```

### Pie Chart
```typescript
payload: Array<{
    name: string,     // 切片名称
    value: number     // 切片数值
}>
```

### Timeseries
```typescript
payload: {
    x: string[],      // 时间点数组
    series: Array<{
        name: string,   // 系列名称
        data: number[]  // 数据数组
    }>
}
```

### Map
```typescript
payload: {
    map_center: { lng: number, lat: number },
    station: { lng: number, lat: number, name: string },
    enterprises: Array<{
        lng: number,
        lat: number,
        name: string,
        industry: string,
        distance?: number,
        score?: number
    }>,
    upwind_paths?: any[],
    sectors?: any[]
}
```

---

## 📝 注意事项

1. **不要修改title**: title应该在Visual对象的顶层，不在payload中
2. **保持meta独立**: unit、thresholds等元数据在meta字段，不在payload中
3. **测试所有污染物**: O3、PM2.5、PM10、SO2、NO2、CO
4. **验证空数据**: 确保没有数据时不会崩溃

---

## 🚀 部署步骤

1. 修改 `backend/app/utils/visualization.py`
2. 重启后端服务: `python main.py`
3. 清除浏览器缓存
4. 测试查询: "分析2025年8月9日东湖站臭氧超标原因"
5. 验证所有图表正常显示

---

## ✅ 预期结果

修复后，前端应该能够正常显示:
- ✅ VOCs浓度饼图
- ✅ OFP贡献柱状图
- ✅ 行业排放饼图/柱状图
- ✅ 站点对比时序图
- ✅ 上风向企业地图


