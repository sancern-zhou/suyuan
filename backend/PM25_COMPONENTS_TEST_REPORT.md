# PM2.5 组分数据获取工具测试报告

## 测试时间
2026-04-26 15:50

## 测试工具
1. **get_pm25_ionic** - PM2.5 水溶性离子组分查询工具
2. **get_pm25_carbon** - PM2.5 碳组分 (OC/EC) 查询工具

## 测试参数
- 站点名称: 公园前
- 站点编码: 1006b
- 时间范围: 2026-04-12 01:00:00 至 2026-04-15 23:59:59
- 数据质量: 原始数据 (dataType=0)

## 测试结果

### 1. get_pm25_ionic 工具

**状态**: ✓ 成功

**返回结果**:
- 记录数: 4 条（日均值）
- 数据ID: `particulate_unified:v1:85091b697f6740089571c3e59366b31d`
- 数据格式: particulate_unified (UDF v2.0 标准)

**数据质量报告**:
```json
{
  "total_records": 4,
  "ionic_fields": 8,
  "field_names": ["Cl⁻", "NO₃⁻", "SO₄²⁻", "Na⁺", "K⁺", "NH₄⁺", "Mg²⁺", "Ca²⁺"],
  "pmf_components": {
    "SO4": {"field": "SO₄²⁻", "valid_count": 4, "total": 4, "completeness": 1.0},
    "NO3": {"field": "NO₃⁻", "valid_count": 4, "total": 4, "completeness": 1.0},
    "NH4": {"field": "NH₄⁺", "valid_count": 4, "total": 4, "completeness": 1.0}
  }
}
```

**PMF 核心组分完整度**: 100% (SO₄²⁻, NO₃⁻, NH₄⁺)

### 2. get_pm25_carbon 工具

**状态**: ✓ 成功

**返回结果**:
- 记录数: 95 条（小时数据）
- 数据ID: `particulate_unified:v1:008eb7161ab946a496abac24e623349a`
- 数据格式: particulate_unified (UDF v2.0 标准)

**数据质量报告**:
```json
{
  "total_records": 95,
  "carbon_fields": 2,
  "field_names": ["OC（TOT）", "EC（TOT）"],
  "OC": {"field": "OC（TOT）", "valid_count": 76, "total": 95, "completeness": 0.8},
  "EC": {"field": "EC（TOT）", "valid_count": 76, "total": 95, "completeness": 0.8}
}
```

**碳组分完整度**: 80% (OC, EC)

## 数据标准化

两个工具都正确应用了 UDF v2.0 标准化：
- 自动过滤 `_Mark` 字段
- 数据转换为 `particulate_unified` 格式
- 字段映射自动应用
- 生成 data_id 供后续工具使用

## 关键发现

1. **时间粒度差异**:
   - 水溶性离子数据使用 `time_type=2` (日均值)，返回 4 条记录
   - 碳组分数据使用 `time_granularity=1` (小时数据)，返回 95 条记录

2. **数据可用性**:
   - 2026年4月12-15日的数据可用
   - 早期时间范围（2024年1月、2026年1月）无数据

3. **站点映射**:
   - 公园前站点 (1006b) 数据完整
   - particulate_city_mapper.json 中映射的站点名称需要与 geo_matcher 保持一致

4. **数据质量**:
   - PMF 核心离子组分 (SO₄²⁻, NO₃⁻, NH₄⁺) 100% 完整
   - 碳组分 (OC, EC) 80% 完整

## 建议

1. 更新 `particulate_city_station_mapping.json` 中的站点名称，确保与 `geo_matcher` 中的站点名称一致
2. 在文档中说明数据可用的时间范围
3. 对于碳组分数据，建议使用小时粒度 (time_granularity=1) 以获取数值数据
