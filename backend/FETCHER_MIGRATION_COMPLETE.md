# 数据质量监控和污染事件监控迁移完成

## 迁移概述

已将两个组件从**工具（Tools）**迁移到**数据抓取器（Fetchers）**：

### 1. 空气质量数据质量监控
- **旧位置**: `backend/app/tools/analysis/air_quality_data_quality_monitor/`
- **新位置**: `backend/app/fetchers/air_quality_data_quality_monitor/`
- **调度**: 每小时整点运行（`0 * * * *`）
- **功能**: 巡检城市站点小时数据质量，识别疑似问题

### 2. 城市污染事件监控
- **旧位置**: `backend/app/tools/analysis/city_pollution_event_monitor/`
- **新位置**: `backend/app/fetchers/city_pollution_event_monitor/`
- **调度**: 每30分钟运行（`*/30 * * * *`）
- **功能**: 识别污染过程事件，收集证据包

## 目录结构

```
backend/app/
├── fetchers/
│   ├── air_quality_data_quality_monitor/
│   │   ├── __init__.py
│   │   └── air_quality_data_quality_fetcher.py  (新增)
│   └── city_pollution_event_monitor/
│       ├── __init__.py
│       └── city_pollution_event_fetcher.py  (新增)
└── services/
    ├── air_quality_data_quality_monitor.py  (保留，被 fetcher 调用)
    └── pollution_event_monitor.py  (保留，被 fetcher 调用)
```

## 已完成的修改

### 1. 创建新的 Fetcher 类
- `AirQualityDataQualityFetcher` - 继承 `DataFetcher`
- `CityPollutionEventFetcher` - 继承 `DataFetcher`

### 2. 更新注册文件
- ✅ `backend/app/fetchers/__init__.py` - 添加两个新 fetcher 到调度器
- ✅ `backend/app/tools/__init__.py` - 移除旧工具的注册

### 3. 测试验证
- ✅ 创建测试脚本 `backend/test_fetchers.py`
- ✅ 所有测试通过

## 使用方式

### 方式1: 作为定时任务运行（推荐）

通过 FetcherScheduler 自动调度运行：

```python
from app.fetchers import create_scheduler

scheduler = create_scheduler()
await scheduler.run()  # 会按 cron 表达式自动运行
```

### 方式2: 手动运行（测试或临时执行）

```python
from app.fetchers.air_quality_data_quality_monitor import AirQualityDataQualityFetcher

fetcher = AirQualityDataQualityFetcher(cities=["广州"], hours=24)
result = await fetcher.fetch_and_store()
```

### 方式3: 通过 Agent 调用（仍然支持）

虽然已迁移到 fetchers，但用户仍可以通过 Agent 对话调用：

```
用户: "检查广州的数据质量"
Agent: 调用服务层代码执行检查
```

## 配置参数

### AirQualityDataQualityFetcher
- `cities`: 监控城市列表，默认 `["广州", "深圳", "佛山", "东莞"]`
- `hours`: 回看小时数，默认 24
- `station_type`: 站点类型，默认 "国控"
- `output_root`: 输出目录，默认 `backend_data_registry/data_quality_issues/`

### CityPollutionEventFetcher
- `cities`: 监控城市列表，默认 `["广州", "深圳", "佛山", "东莞"]`
- `hours`: 回看小时数，默认 24
- `station_type`: 站点类型，默认 "国控"
- `output_root`: 输出目录，默认 `backend_data_registry/pollution_process_events/`
- `force_collect`: 是否强制收集数据，默认 False
- `include_components`: 是否包含组分数据，默认 True

## 输出位置

### 数据质量巡检
```
backend_data_registry/data_quality_issues/{city}/{date}/{time}/
├── quality_package.json
└── data_quality_analysis.md  (Agent 生成)
```

### 污染事件监控
```
backend_data_registry/pollution_process_events/{city}/{date}/{time}/
├── evidence_pack.json
└── reasoning_analysis.md  (Agent 生成)
```

## 清理工作（可选）

可以删除旧的工具目录：

```bash
# 删除旧的工具目录
rm -rf backend/app/tools/analysis/air_quality_data_quality_monitor/
rm -rf backend/app/tools/analysis/city_pollution_event_monitor/

# 删除旧的 CLI 脚本（如果不再需要）
rm backend/scripts/air_quality_data_quality_monitor.py
rm backend/scripts/city_pollution_event_monitor.py
```

注意：保留以下文件，它们仍然被使用：
- ✅ `backend/app/services/air_quality_data_quality_monitor.py`
- ✅ `backend/app/services/pollution_event_monitor.py`
- ✅ `backend/scripts/install_air_quality_data_quality_task.py`
- ✅ `backend/scripts/install_city_pollution_event_task.py`
- ✅ `backend/docs/skills/*.md` (技能文档)

## 下一步

1. **重启后端服务**以使更改生效
2. **验证定时任务**是否正常运行
3. **监控日志**确认 fetcher 正常工作
4. **检查输出目录**确认证据包正确生成

## 验证命令

```bash
# 测试 fetcher 是否正常工作
cd backend && python3 test_fetchers.py

# 查看已注册的 fetcher
cd backend && python3 -c "from app.fetchers import create_scheduler; s = create_scheduler(); print([n for n in s.fetchers.keys()])"
```
