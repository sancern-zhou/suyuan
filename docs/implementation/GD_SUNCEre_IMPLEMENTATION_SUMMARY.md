# 广东省 Suncere API 实现总结

## 项目概述

基于 Vanna 项目的 API 架构，为溯源系统实现了广东省生态环境厅官方 Suncere API 的完整客户端，包括 token 认证、数据查询和自动标准化功能。

## 核心成果

### 1. API 客户端 (`gd_suncere_api_client.py`)

**功能特性**:
- ✅ **Token 认证**: Basic Auth 获取访问令牌
- ✅ **自动刷新**: Token 缓存 30 分钟，过期自动重新获取
- ✅ **错误重试**: 401 错误自动刷新 token 并重试
- ✅ **超时控制**: 可配置的请求超时时间

**主要方法**:
```python
get_token()                    # 获取访问令牌
query_city_day_data()          # 查询城市日报
query_station_hour_data()      # 查询站点小时数据
query_report_data()            # 查询统计报表
```

### 2. 查询工具 (`query_gd_suncere/tool.py`)

**功能特性**:
- ✅ **多查询模式**: 城市日报、站点小时、区域对比
- ✅ **批量查询**: 一次查询多个城市
- ✅ **自动标准化**: 转换为 UDF v2.0 格式
- ✅ **错误处理**: 优雅处理部分失败

**导出函数**:
```python
execute_query_gd_suncere_city_day()              # 城市日报查询
execute_query_gd_suncere_station_hour()         # 站点小时查询
execute_query_gd_suncere_regional_comparison()  # 区域对比查询
```

### 3. 配置文件 (`gd_suncere_api_config.yaml`)

**配置项**:
- API 基础 URL 和认证凭据
- 查询端点映射
- 城市代码映射表
- 污染物代码列表
- 超时和分页配置

### 4. 完整文档

- **使用指南**: `docs/api/GD_SUNCEre_API_GUIDE.md`
- **集成指南**: `docs/implementation/GD_SUNCEre_INTEGRATION.md`
- **测试脚本**: `tests/test_gd_suncere_api.py`

## 技术架构

### 数据流程

```
┌─────────────────────────────────────────────────────────────┐
│                     用户/Agent 请求                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            query_gd_suncere_station_hour()                   │
│              (广东省站点小时数据查询工具)                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              GDSuncereAPIClient.get_token()                  │
│         (自动获取/刷新访问令牌，缓存30分钟)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           api_client.query_station_hour_data()              │
│         (调用 Suncere API，自动重试和错误处理)                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              DataStandardizer.standardize()                 │
│         (字段映射、单位转换、UDF v2.0 转换)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           context.data_manager.save_data()                  │
│         (保存到 DataContext，自动添加元数据)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    返回结果给用户                             │
│         (包含 data_id、measurements、metadata)               │
└─────────────────────────────────────────────────────────────┘
```

### 数据格式对比

**API 原始格式**:
```json
{
  "stationName": "广雅中学",
  "PM2.5": 35.2,
  "SO2": 8.3
}
```

**标准化后 (UDF v2.0)**:
```json
{
  "station_name": "广雅中学",
  "measurements": {
    "PM2_5": 35.2,
    "SO2": 45.6
  },
  "metadata": {
    "schema_version": "v2.0",
    "field_mapping_applied": true
  }
}
```

## 与现有工具的对比

| 特性 | get_guangdong_regular_stations | query_gd_suncere |
|-----|-------------------------------|------------------|
| 数据源 | UQP 查询接口 (9091) | 官方 Suncere API |
| 认证 | 无需认证 | Token 认证 |
| 查询方式 | 自然语言 question | 结构化参数 |
| 数据质量 | 可能返回缺失值 | 质量检查 |
| 标准化 | 手动处理 | 自动 UDF v2.0 |
| 可靠性 | 中等 | 高 |

## 推荐使用场景

### 使用 query_gd_suncere (新工具)

✅ **生产环境部署**
- 可靠的数据质量
- 完善的错误处理
- 自动 token 管理

✅ **区域对比分析**
- 结构化的多城市查询
- 一致的数据格式
- 自动标准化

✅ **大规模查询**
- 批量查询优化
- 自动重试机制
- 性能监控

### 使用 get_guangdong_regular_stations (现有工具)

✅ **快速原型**
- 灵活的自然语言查询
- 无需配置认证
- 快速验证

## 集成步骤

### 步骤1: 测试 API 连接

```bash
cd backend
python tests/test_gd_suncere_api.py
```

### 步骤2: 在 Expert Plan Generator 中配置

修改 `expert_plan_generator.py`:

```python
# 生成区域对比计划时使用新 API
def generate_regional_plan(self, task, pollutants):
    return {
        "tool": "execute_query_gd_suncere_regional_comparison",
        "params": {
            "target_city": "韶关",
            "nearby_cities": ["广州", "深圳", "佛山", "东莞"],
            "start_time": start_time,
            "end_time": end_time
        }
    }
```

### 步骤3: 验证数据质量

```python
# 检查返回数据
result = execute_query_gd_suncere_station_hour(...)

# 确认包含 measurements 字段
assert "measurements" in result["data"][0]

# 确认有实际数值（非 None）
measurements = result["data"][0]["measurements"]
assert any(v is not None for v in measurements.values())
```

## 关键优势

### 1. 数据可靠性

- ✅ 官方 API，数据质量有保障
- ✅ 经过质量检查，避免无效数据
- ✅ 自动错误处理和重试

### 2. 开发效率

- ✅ 结构化参数，无需解析自然语言
- ✅ 自动标准化，直接符合 UDF v2.0
- ✅ 统一错误处理，减少异常代码

### 3. 运维友好

- ✅ Token 自动管理，无需手动干预
- ✅ 完善的日志记录
- ✅ 性能监控和告警

## 文件清单

### 核心代码

1. `backend/app/services/gd_suncere_api_client.py` - API 客户端
2. `backend/app/tools/query/query_gd_suncere/tool.py` - 查询工具
3. `backend/app/tools/query/query_gd_suncere/__init__.py` - 模块导出
4. `backend/config/gd_suncere_api_config.yaml` - 配置文件

### 文档和测试

5. `docs/api/GD_SUNCEre_API_GUIDE.md` - 使用指南
6. `docs/implementation/GD_SUNCEre_INTEGRATION.md` - 集成指南
7. `backend/tests/test_gd_suncere_api.py` - 测试脚本

## 总结

通过参考 Vanna 项目的 API 架构，我们实现了：

1. ✅ **完整的 Token 认证机制**
   - Basic Auth 获取 token
   - 自动缓存和刷新
   - 401 错误自动重试

2. ✅ **多种数据查询方式**
   - 城市日报数据
   - 站点小时数据
   - 区域对比数据
   - 综合统计报表

3. ✅ **自动化数据处理**
   - 字段标准化映射
   - UDF v2.0 格式转换
   - 元数据自动添加

4. ✅ **完善的错误处理**
   - 网络超时处理
   - 部分失败优雅降级
   - 详细的日志记录

5. ✅ **易于集成**
   - 清晰的 API 接口
   - 完整的使用文档
   - 可运行的测试脚本

建议在生产环境中优先使用新的 Suncere API 工具，确保数据查询的稳定性和可靠性。
