# API配置说明文档

**文档更新时间**: 2025-10-19

---

## 📋 API端口配置总览

| API类型 | 端口 | 完整URL | 配置项名称 | 用途 |
|---------|------|---------|-----------|------|
| **站点查询API** | 9095 | `http://180.184.91.74:9095` | `station_api_base_url` | 查询站点信息和附近站点 |
| **监测数据API** | 9091 | `http://180.184.91.74:9091` | `monitoring_data_api_url` | 查询污染物浓度数据（SO2, CO, O3, PM2.5, PM10, NOX） |
| **VOCs数据API** | 9092 | `http://180.184.91.74:9092` | `vocs_data_api_url` | 查询VOCs组分和OFP数据 |
| **颗粒物数据API** | 9093 | `http://180.184.91.74:9093` | `particulate_data_api_url` | 查询颗粒物组分数据 |
| **气象数据API** | - | `http://180.184.30.94/api/...` | `meteorological_api_url` | 查询风速风向等气象数据 |
| **上风向分析API** | 9092 | `http://192.168.20.2:9092` | `upwind_analysis_api_url` | 上风向企业分析 |

---

## 🔧 配置文件位置

**主配置文件**: `backend/config/settings.py`

```python
class Settings(BaseSettings):
    # External API Endpoints
    station_api_base_url: str = Field(
        default="http://180.184.91.74:9095",
        description="Station and district query API base URL"
    )
    monitoring_data_api_url: str = Field(
        default="http://180.184.91.74:9091",
        description="Monitoring data API URL"
    )
    vocs_data_api_url: str = Field(
        default="http://180.184.91.74:9092",
        description="VOCs component data API URL"
    )
    particulate_data_api_url: str = Field(
        default="http://180.184.91.74:9093",
        description="Particulate component data API URL"
    )
    meteorological_api_url: str = Field(
        default="http://180.184.30.94/api/AiDataService/ReportApplication/UserReportDataQuery/Query",
        description="Meteorological data API URL"
    )
    upwind_analysis_api_url: str = Field(
        default="http://192.168.20.2:9092",
        description="Upwind analysis API base URL"
    )
```

---

## 🌍 环境变量覆盖

可以通过环境变量或 `.env` 文件覆盖默认配置：

```bash
# .env 文件示例
STATION_API_BASE_URL=http://180.184.91.74:9095
MONITORING_DATA_API_URL=http://180.184.91.74:9091
VOCS_DATA_API_URL=http://180.184.91.74:9092
PARTICULATE_DATA_API_URL=http://180.184.91.74:9093
METEOROLOGICAL_API_URL=http://180.184.30.94/api/AiDataService/ReportApplication/UserReportDataQuery/Query
UPWIND_ANALYSIS_API_URL=http://192.168.20.2:9092
```

**注意**: 环境变量会覆盖配置文件中的默认值。

---

## 📡 API详细说明

### 1. 站点查询API (端口 9095)

**基础URL**: `http://180.184.91.74:9095`

**端点**:
- `GET /api/station-district/by-station-name` - 根据站点名称查询站点信息
  - 参数: `station_name` (站点名称), `top_k` (返回结果数量)
  - 返回: 站点的城市、区县、经纬度等信息

- `GET /api/nearest-stations/by-station-name` - 查询附近站点
  - 参数: `station_name` (参考站点), `max_distance` (最大距离km), `max_results` (最大结果数)
  - 返回: 附近站点列表及距离信息

**代码位置**: `backend/app/services/external_apis.py` - `StationAPIClient`

---

### 2. 监测数据API (端口 9091)

**基础URL**: `http://180.184.91.74:9091`

**端点**:
- `POST /api/uqp/query` - 自然语言查询污染物数据
  - 请求体: `{"question": "站点名称站点的小时污染物浓度，时间为开始时间至结束时间"}`
  - 支持污染物: SO2, CO, O3, PM2.5, PM10, NOX
  - 返回: 时序监测数据列表

**请求示例**:
```json
{
  "question": "广雅中学站点的小时O3污染物浓度，时间为2024-08-09 00:00:00至2024-08-09 23:59:59"
}
```

**代码位置**: `backend/app/services/external_apis.py` - `MonitoringDataAPIClient.get_station_pollutant_data()`

---

### 3. VOCs数据API (端口 9092) ✅

**基础URL**: `http://180.184.91.74:9092`

**端点**:
- `POST /api/uqp/query` - 自然语言查询VOCs组分数据
  - 请求体: `{"question": "查询城市所有站点的OFP前十数据，时间周期为开始时间至结束时间，时间精度为小时"}`
  - 返回: VOCs组分和OFP（臭氧生成潜势）数据

**请求示例**:
```json
{
  "question": "查询广州所有站点的OFP前十数据，时间周期为2024-08-09 00:00:00至2024-08-09 23:59:59，时间精度为小时"
}
```

**代码位置**: `backend/app/services/external_apis.py` - `MonitoringDataAPIClient.get_vocs_component_data()`

---

### 4. 颗粒物数据API (端口 9093)

**基础URL**: `http://180.184.91.74:9093`

**端点**:
- `POST /api/uqp/query` - 自然语言查询颗粒物组分数据
  - 请求体: `{"question": "查询城市所有站点的PM2.5组分数据，时间周期为开始时间至结束时间，时间精度为小时"}`
  - 返回: 颗粒物组分数据

**请求示例**:
```json
{
  "question": "查询广州所有站点的PM2.5组分数据，时间周期为2024-08-09 00:00:00至2024-08-09 23:59:59，时间精度为小时"
}
```

**代码位置**: `backend/app/services/external_apis.py` - `MonitoringDataAPIClient.get_particulate_component_data()`

---

### 5. 气象数据API

**完整URL**: `http://180.184.30.94/api/AiDataService/ReportApplication/UserReportDataQuery/Query`

**端点**:
- `GET /api/AiDataService/ReportApplication/UserReportDataQuery/Query` - 查询气象数据
  - 参数: 
    - `beginTime`: 开始日期 (YYYY-MM-DD)
    - `endTime`: 结束日期 (YYYY-MM-DD)
    - `cityName`: 城市名称
    - `directName`: 区县名称
  - 请求头: `Authorization: Basic <API_KEY>`
  - 返回: 风速、风向、温度等气象数据

**请求示例**:
```
GET http://180.184.30.94/api/AiDataService/ReportApplication/UserReportDataQuery/Query?beginTime=2024-08-09&endTime=2024-08-09&cityName=广州&directName=荔湾区
Headers: Authorization: Basic 1882bb80-16a0-419a-ae3e-f442471909d3
```

**注意事项**:
- ⚠️ 此API可能只提供当前/最近的数据，不支持历史数据查询
- ⚠️ 对于历史日期，返回空数组是正常现象
- ⚠️ 需要API Key认证

**代码位置**: `backend/app/services/external_apis.py` - `MeteorologicalAPIClient.get_weather_data()`

---

### 6. 上风向分析API (端口 9092)

**基础URL**: `http://192.168.20.2:9092`

**端点**:
- `POST /api/upwind/analyze` - 分析上风向企业
  - 请求体: 包含站点位置、风向、搜索范围等参数
  - 返回: 上风向企业列表及相关信息

**代码位置**: `backend/app/services/external_apis.py` - `UpwindAnalysisAPIClient`

---

## 🔍 验证配置

运行以下命令验证当前配置：

```bash
cd backend
python -c "from config.settings import settings; print('站点API:', settings.station_api_base_url); print('监测数据API:', settings.monitoring_data_api_url); print('VOCs数据API:', settings.vocs_data_api_url); print('颗粒物数据API:', settings.particulate_data_api_url); print('气象数据API:', settings.meteorological_api_url)"
```

**预期输出**:
```
站点API: http://180.184.91.74:9095
监测数据API: http://180.184.91.74:9091
VOCs数据API: http://180.184.91.74:9092
颗粒物数据API: http://180.184.91.74:9093
气象数据API: http://180.184.30.94/api/AiDataService/ReportApplication/UserReportDataQuery/Query
```

---

## 🐛 常见问题

### Q1: 为什么运行时的配置与代码中的默认值不同？

**A**: 可能是环境变量覆盖了默认配置。检查：
1. 系统环境变量
2. `.env` 文件（如果存在）
3. Docker容器的环境变量配置

### Q2: VOCs API应该使用哪个端口？

**A**: VOCs API使用 **9092端口**，配置已正确设置为 `http://180.184.91.74:9092`

### Q3: 气象数据API为什么返回空数组？

**A**: 气象数据API可能只支持当前/最近的数据，对于历史日期返回空数组是正常的。建议使用最近的日期进行测试。

### Q4: 如何修改API配置？

**A**: 有两种方式：
1. **修改默认值**: 编辑 `backend/config/settings.py` 中的 `Field(default=...)`
2. **使用环境变量**: 创建 `.env` 文件或设置系统环境变量

---

## 📝 更新日志

- **2025-10-19**: 创建文档，确认VOCs API端口为9092
- **2025-10-19**: 添加所有API的详细说明和示例

---

**维护者**: 开发团队  
**最后更新**: 2025-10-19

