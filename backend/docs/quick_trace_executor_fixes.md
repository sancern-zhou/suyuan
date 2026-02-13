# QuickTraceExecutor 修复总结

## 修复日期
2026-02-04

## 问题描述

### 问题1：边界层数据缺失
**现象**：LLM上下文中边界层高度全部显示为 `Nonem`（应该是 `无数据` 或实际数值）

**根本原因**：
1. `get_current_weather` 工具使用的 Open-Meteo Current Weather API 不返回 `boundary_layer_height` 字段
2. 格式化逻辑未处理 `None` 值，导致 `f"{None}m"` 生成字符串 `"Nonem"`

### 问题2：今天数据不完整
**现象**：Prompt 要求分析"今天00:00~当前时刻"的完整小时数据，但实际只提供3个采样时点

**根本原因**：
- `_format_forecast_data` 方法对所有天都采样3个时点（00时, 12时, 23时）
- 没有针对告警当天传递完整小时数据

### 问题3：日期标注混乱
**现象**：`2026-02-03` 被标注为"昨天及以前"，但实际可能是告警当天

**根本原因**：
- 使用 `datetime.now()` 判断"今天"，而非基于 `alert_time`
- 导致在告警时间与系统时间不同时产生标注错误

---

## 修复方案

### 修复1：移除 `get_current_weather` 工具

**理由**：
1. 当前天气数据已包含在 `get_weather_forecast` 的返回中（`past_days=1` 时包含今天00:00~当前时刻）
2. Forecast API 包含 `boundary_layer_height` 字段
3. 避免重复API调用，统一数据来源

**修改位置**：
- `quick_trace_executor.py:72-98` - 移除工具加载
- `quick_trace_executor.py:163-192` - 移除任务调用
- `quick_trace_executor.py:550-568` - 移除数据摘要提取
- `quick_trace_executor.py:722-746` - 更新 Prompt 数据说明

**修改内容**：
```python
# 移除前
tasks = {
    "current_weather": self.tools["current_weather"].execute(...),
    "historical_weather": ...,
    "forecast": ...,
}

# 移除后
tasks = {
    "historical_weather": ...,
    "forecast": self.tools["weather_forecast"].execute(
        past_days=1,  # 包含昨天+今天00:00~当前时刻完整数据（包含边界层高度）
        ...
    ),
}
```

---

### 修复2：今天数据完整传递

**目标**：告警当天传递从 00:00 到告警时刻的完整小时数据

**修改位置**：
- `quick_trace_executor.py:550-554` - 添加 `alert_time` 参数
- `quick_trace_executor.py:516` - 传递 `alert_time`
- `quick_trace_executor.py:925-1050` - 修改 `_format_forecast_data` 方法

**修改内容**：
```python
def _format_forecast_data(self, forecast_result: Dict, alert_time: str = None) -> str:
    # 解析告警时间
    if alert_time:
        alert_dt = datetime.strptime(alert_time, "%Y-%m-%d %H:%M:%S")
        alert_date_str = alert_dt.strftime("%Y-%m-%d")
        alert_hour = alert_dt.hour
    
    # 对每条记录
    for date in sorted(daily_data.keys()):
        if alert_date_str and date == alert_date_str and alert_hour is not None:
            # ✅ 告警当天：选择从00:00到告警时刻的完整小时数据
            selected_points = []
            for rec in day_records:
                hour = int(str(rec["timestamp"])[11:13])
                if hour <= alert_hour:
                    selected_points.append(rec)
        else:
            # 其他天：采样3个时点控制数据量
            selected_points = [day_records[0], day_records[len(day_records)//2], day_records[-1]]
```

**效果**：
- 告警时刻 `2026-02-03 16:00` → 提供 00:00, 01:00, ..., 16:00 共17条数据
- 其他日期 → 提供 00:00, 12:00, 23:00 共3条数据（控制数据量）

---

### 修复3：边界层 None 值格式化

**目标**：将 `boundary_layer_height=None` 格式化为 `无数据` 而非 `Nonem`

**修改位置**：
- `quick_trace_executor.py:920-921` - `_format_weather_data` 方法
- `quick_trace_executor.py:1038-1039` - `_format_forecast_data` 方法

**修改内容**：
```python
# 修改前
pblh = meas.get("boundary_layer_height")
lines.append(f"...边界层{pblh}m...")  # None -> "Nonem"

# 修改后
pblh = meas.get("boundary_layer_height")
pblh_str = f"{pblh}m" if pblh is not None else "无数据"
lines.append(f"...边界层{pblh_str}...")  # None -> "无数据"
```

**效果**：
- `boundary_layer_height=100` → `边界层100m`
- `boundary_layer_height=None` → `边界层无数据`
- `boundary_layer_height=0` → `边界层0m`

---

### 修复4：日期标注逻辑（基于 alert_time）

**目标**：基于告警时间判断"今天"而非系统时间

**修改位置**：
- `quick_trace_executor.py:980-996` - `_format_forecast_data` 方法

**修改内容**：
```python
# 解析告警时间
if alert_time:
    alert_dt = datetime.strptime(alert_time, "%Y-%m-%d %H:%M:%S")
    alert_date_str = alert_dt.strftime("%Y-%m-%d")
    alert_hour = alert_dt.hour

# 识别日期类型
if alert_date_str:
    if date < alert_date_str:
        date_label = f"{date} (告警前，历史分析场数据)"
    elif date == alert_date_str:
        alert_time_str = f"{alert_hour:02d}:00" if alert_hour is not None else "当前"
        date_label = f"{date} (告警当天，从00:00到{alert_time_str}，分析场数据)"
    else:
        date_label = f"{date} (未来，预报数据)"
else:
    # 降级：使用datetime.now()判断
    today = datetime.now().strftime("%Y-%m-%d")
    ...
```

**效果**：
- 告警时间 `2026-02-03 16:00`：
  - `2026-02-01` → `2026-02-01 (告警前，历史分析场数据)`
  - `2026-02-03` → `2026-02-03 (告警当天，从00:00到16:00，分析场数据)`
  - `2026-02-04` → `2026-02-04 (未来，预报数据)`

---

## 测试验证

### 测试1：边界层格式化
```python
输入: {'boundary_layer_height': 100}
输出: 边界层100m

输入: {'boundary_layer_height': None}
输出: 边界层无数据

输入: {'boundary_layer_height': 0}
输出: 边界层0m
```

### 测试2：今天数据选择
```python
告警时刻: 2026-02-03 16:00:00
所有小时: [0, 4, 8, 12, 16, 20, 23]
选择小时: [0, 4, 8, 12, 16]  # ≤ 16
数据点数: 5
```

### 测试3：日期标注
```
告警时间: 2026-02-03 16:00

2026-02-01 (告警前，历史分析场数据)
2026-02-02 (告警前，历史分析场数据)
2026-02-03 (告警当天，从00:00到16:00，分析场数据)
2026-02-04 (未来，预报数据)
2026-02-05 (未来，预报数据)
```

---

## 影响评估

### 正面影响
1. ✅ **边界层数据可用**：从 Forecast API 获取完整的边界层高度数据
2. ✅ **今天数据完整**：LLM 可以分析告警当天 00:00~当前时刻的完整趋势
3. ✅ **日期标注准确**：基于告警时间判断，避免时区问题
4. ✅ **格式化正确**：`None` 值显示为 `无数据` 而非 `Nonem`
5. ✅ **减少API调用**：移除 `get_current_weather` 节省 1 次API调用

### 无负面影响
- 不影响其他功能
- 向后兼容（`alert_time` 为 `None` 时降级到 `datetime.now()`）

---

## 文件变更清单

| 文件 | 修改行数 | 说明 |
|------|---------|------|
| `quick_trace_executor.py` | ~150 行 | 移除工具、修复格式化、修复数据选择逻辑 |

---

## 验证命令

```bash
# 语法检查
cd D:\溯源\backend
python -m py_compile app/agent/executors/quick_trace_executor.py

# 运行测试（如果有）
pytest tests/test_quick_trace_executor.py -v
```

---

## 后续优化建议

1. **监控日志**：关注 `selected_today_data_points` 日志，验证数据点数量符合预期
2. **性能优化**：如果今天数据量过大（如告警时刻23:00），可以考虑采样策略（如每2小时1个点）
3. **错误处理**：增强 `alert_time` 解析失败的错误提示

---

## 相关文档

- `backend/docs/weather_expert_workflow.md` - 气象专家分析工作流程
- `backend/app/external_apis/openmeteo_client.py` - Open-Meteo API 客户端
- `backend/app/tools/query/get_weather_forecast/tool.py` - 天气预报工具
