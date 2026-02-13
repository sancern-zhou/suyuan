# 济宁市 ERA5 数据抓取使用说明

## 概述

济宁市 ERA5 Fetcher 是一个专门用于抓取济宁市气象数据的后台服务。支持站点级和市中心点两种数据抓取模式。

## 数据抓取点

### 监测站点（6个）

| 站点ID | 站点名称 | 纬度 | 经度 |
|--------|----------|------|------|
| 11149A | 火炬城 | 35.42884 | 116.6232 |
| 11152A | 北湖区(市污水处理厂) | 35.3767 | 116.5814 |
| 11173A | 任城区站点 | 35.5593 | 116.8249 |
| 11362A | 市第七中学 | 35.4054 | 116.5907 |
| 1352A | 文体南路1号 | 35.3921 | 116.5648 |
| 1353A | 任和路 | 35.4566 | 116.6075 |

### 市中心点（1个）

| 位置名称 | 纬度 | 经度 |
|----------|------|------|
| 济宁市中区(城市预报中心点) | 35.4143 | 116.5871 |

**总计：7个数据抓取点**

## 数据抓取模式

### 1. 站点级数据抓取
- 针对每个监测站点的经纬度
- 自动对齐到 ERA5 标准 0.25° 网格
- 共 6 个站点

### 2. 市中心点数据抓取
- 济宁市中区（城市预报中心点）
- 自动对齐到 ERA5 标准 0.25° 网格
- 1 个中心点

## API 使用

### 1. 获取站点列表和市中心点

**请求**:
```bash
GET /api/fetchers/jining_era5/stations
```

**响应**:
```json
{
  "success": true,
  "station_count": 6,
  "city_center": {
    "station_id": "CITY_CENTER",
    "name": "济宁市中区(城市预报中心点)",
    "lat": 35.4143,
    "lon": 116.5871
  },
  "stations": [
    {
      "station_id": "11149A",
      "name": "火炬城",
      "lat": 35.42884,
      "lon": 116.6232
    },
    ...
  ]
}
```

### 2. 抓取指定站点数据

**请求**:
```bash
POST /api/fetchers/jining_era5/fetch
Content-Type: application/json

{
  "date": "2026-02-01",
  "station_id": "11149A"
}
```

**响应**:
```json
{
  "success": true,
  "message": "Jining station 11149A ERA5 data fetched successfully for 2026-02-01",
  "data": {
    "success": true,
    "station_id": "11149A",
    "station_name": "火炬城",
    "date": "2026-02-01",
    "result": "success",
    "original_coords": "35.42884, 116.6232",
    "grid_coords": "35.5, 116.5"
  }
}
```

### 3. 抓取全市数据（所有站点 + 市中心）

**请求**:
```bash
POST /api/fetchers/jining_era5/fetch
Content-Type: application/json

{
  "date": "2026-02-01"
}
```

**响应**:
```json
{
  "success": true,
  "message": "Jining ERA5 data fetched successfully for 2026-02-01",
  "data": {
    "success": true,
    "date": "2026-02-01",
    "region": "Jining City",
    "station_count": 6,
    "city_center_count": 1,
    "total_count": 7,
    "success_count": 7,
    "failed_count": 0,
    "skipped_count": 0,
    "success_rate": "100.0%"
  }
}
```

## 定时调度

系统每天凌晨 2:00 自动抓取昨天的 ERA5 数据（7个点）。

调度配置：
```python
schedule="0 2 * * *"  # 每天 2:00
```

## 网格对齐说明

ERA5 数据使用 0.25° 网格分辨率，站点坐标会自动对齐到最近的网格点：

**示例1：火炬城站点**
- 原始坐标: (35.42884, 116.6232)
- 网格坐标: (35.5, 116.5)
- 偏移: (0.07116, 0.1232) 度

**示例2：市中心点**
- 原始坐标: (35.4143, 116.5871)
- 网格坐标: (35.5, 116.5)
- 偏移: (0.0857, 0.0871) 度

## 测试

运行测试脚本：
```bash
cd backend
python tests/test_jining_era5_fetcher.py
```

测试内容包括：
1. 站点信息验证（6个站点）
2. 市中心点信息验证
3. 站点数据点生成测试
4. 市中心数据点生成测试
5. 单站点数据抓取测试
6. 批量数据抓取测试（7个点）
7. 网格对齐精度测试

## 错误处理

系统包含完善的错误处理和重试机制：

- **最大重试次数**: 3 次
- **重试延迟**: 指数退避（2秒 × (attempt + 1)）
- **批次大小**: 3 个点/批次
- **批次间延迟**: 3 秒（避免 API 限流）

### 429 限流错误处理
当遇到 API 限流时，系统会：
1. 记录警告日志
2. 等待指定时间后重试
3. 达到最大重试次数后标记为失败

## 日志监控

关键日志事件：

- `starting_jining_era5_fetch`: 开始抓取
- `jining_station_points_generated`: 站点数据点生成完成
- `jining_city_center_point_generated`: 市中心数据点生成完成
- `era5_data_saved`: 单个数据点保存成功
- `rate_limit_hit`: API 限流警告
- `jining_era5_fetch_complete`: 抓取完成

## 数据存储

抓取的数据存储在 PostgreSQL + TimescaleDB 中，表结构与其他 ERA5 数据相同，可通过以下字段查询：

- `lat`: 纬度（网格对齐后的坐标）
- `lon`: 经度（网格对齐后的坐标）
- `time`: 时间戳
- 其他气象要素字段

## 性能指标

- **数据点总数**: 7 个（6个站点 + 1个市中心）
- **预计抓取时间**: 约 21-30 秒（每批次3个点，延迟3秒）
- **API 调用次数**: 7 次/天

## 注意事项

1. **数据可用性**: ERA5 数据通常有 5 天延迟，今天只能获取到 5 天前的数据
2. **API 限流**: Open-Meteo API 有并发限制，系统已配置批次处理和延迟
3. **网格对齐**: 站点坐标会自动对齐到 0.25° 网格，可能导致精度损失约 0.1°
4. **数据去重**: 系统会自动检查数据是否已存在，避免重复抓取
5. **市中心点**: 市中心点不属于监测站点，是城市预报中心点，用于整体气象数据参考

## 扩展站点

如需添加新的监测站点，编辑 `app/fetchers/weather/jining_era5_fetcher.py`:

```python
self.stations = {
    "11149A": {"name": "火炬城", "lat": 35.42884, "lon": 116.6232},
    # 添加新站点
    "NEW_ID": {"name": "新站点名称", "lat": xx.xxxxx, "lon": xxx.xxxx},
}
```

## 与广东省 ERA5 Fetcher 的区别

| 特性 | 广东省 ERA5 Fetcher | 济宁市 ERA5 Fetcher |
|------|-------------------|-------------------|
| 数据点类型 | 网格点 | 站点 + 市中心 |
| 数据点数量 | 约 825 个网格点 | 7 个点（6站+1中心） |
| 覆盖范围 | 广东省全境 | 济宁市关键点位 |
| 抓取时间 | 约 2-3 小时 | 约 21-30 秒 |
| 精度 | 网格级（0.25°） | 站点级（对齐到网格） |
