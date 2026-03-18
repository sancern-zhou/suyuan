# 污染高值告警快速溯源API文档

## 基本信息

- **服务名称**: 污染高值告警快速溯源
- **部署地址**: `http://219.135.180.51:56041`
- **API版本**: v1.0.0
- **数据格式**: JSON
- **字符编码**: UTF-8

## 目录

1. [快速溯源分析接口](#1-快速溯源分析接口)
2. [健康检查接口](#2-健康检查接口)
3. [支持的城市列表](#3-支持的城市列表)
4. [错误码说明](#4-错误码说明)
5. [调用示例](#5-调用示例)

---

## 1. 快速溯源分析接口

### 接口描述

当监测到污染高值告警时，外部系统调用此接口触发快速溯源分析。系统将自动获取气象数据、空气质量数据、轨迹分析等，生成污染溯源分析报告。

### 请求地址

```
POST http://219.135.180.51:56041/api/quick-trace/alert
```

### 请求方式

```
POST
```

### 请求参数

#### Headers

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| Content-Type | string | 是 | 固定值：`application/json` |

#### Body (JSON)

| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| city | string | 是 | 城市名称 | `"济宁市"` |
| alert_time | string | 是 | 告警时间，格式：`YYYY-MM-DD HH:MM:SS` | `"2026-02-03 00:30:00"` |
| pollutant | string | 是 | 告警污染物类型（支持：PM2.5、PM10、O3、NO2、SO2、CO、AQI） | `"PM2.5"` |
| alert_value | float | 是 | 告警浓度值 | `130.0` |
| unit | string | 否 | 浓度单位，默认：`μg/m³` | `"μg/m³"` |

#### 请求示例

```json
{
  "city": "济宁市",
  "alert_time": "2026-02-03 00:30:00",
  "pollutant": "PM2.5",
  "alert_value": 130.0,
  "unit": "μg/m³"
}
```

### 返回结果

#### 成功响应

**HTTP Status Code**: `200 OK`

```json
{
  "summary_text": "# 济宁市污染高值快速溯源报告\n\n**告警时间**: 2026-02-03 00:30:00\n**告警污染物**: PM2.5\n**告警浓度**: 130.0 μg/m³\n**生成时间**: 2026-02-03 00:48:12\n\n---\n\n## 1. 污染来源轨迹分析\n\n基于后向轨迹分析结果，描述:\n\n- **主要传输方向**: 西北方向\n- **传输距离**: 约300-600公里（基于72小时轨迹推算）\n- **潜在源区**: 河北省南部、河南省北部（如濮阳、安阳、鹤壁等地）\n\n...",
  "visuals": [
    {
      "id": "trajectory_map_001",
      "type": "map",
      "title": "后向轨迹分析图",
      "url": "http://219.135.180.51:56041/api/image/trajectory_xxx"
    }
  ],
  "execution_time_seconds": 85.32,
  "data_ids": [
    "weather:v1:27a52f203a12481e8dd0fb721e9cc6c3",
    "air_quality:v2:xxx"
  ],
  "has_trajectory": true,
  "warning_message": null,
  "city": "济宁市",
  "alert_time": "2026-02-03 00:30:00",
  "pollutant": "PM2.5",
  "alert_value": 130.0
}
```

#### 返回字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| summary_text | string | Markdown格式的分析报告，包含完整的溯源分析内容 |
| visuals | array | 可视化图表列表，包含轨迹图等（如果有） |
| visuals[].id | string | 图表唯一标识 |
| visuals[].type | string | 图表类型（map、chart等） |
| visuals[].title | string | 图表标题 |
| visuals[].url | string | 图表访问URL |
| execution_time_seconds | float | 分析执行耗时（秒） |
| data_ids | array | 生成的数据ID列表（用于数据追溯） |
| has_trajectory | boolean | 是否成功获取轨迹分析数据 |
| warning_message | string/null | 警告信息（如：轨迹分析超时） |
| city | string | 城市名称（请求参数） |
| alert_time | string | 告警时间（请求参数） |
| pollutant | string | 污染物类型（请求参数） |
| alert_value | float | 告警浓度值（请求参数） |

#### 分析报告结构（summary_text）

返回的 `summary_text` 为Markdown格式，包含以下章节：

1. **污染来源轨迹分析**
   - 主要传输方向
   - 传输距离
   - 潜在源区
   - 不同高度层特征

2. **当前气象条件影响**
   - 大气扩散能力（边界层高度、风速风向、垂直扩散）
   - 气象条件对污染的影响（温度、湿度、降水）
   - 不利扩散条件识别

3. **周边城市污染指标趋势分析（传输分析）**
   - 周边城市浓度变化
   - 传输分析
   - 传输贡献评估

4. **未来气象条件及好转窗口**
   - 未来7天气象趋势
   - 污染好转时间窗口
   - 预测依据

5. **应急管控建议**
   - 管控优先级
   - 后续关注重点

6. **数据质量与置信度**
   - 数据完整性
   - 分析置信度
   - 说明

### 执行时间说明

- **正常情况**: 2-3分钟（包含所有工具执行）
- **轨迹分析超时**: 80-90秒（轨迹分析90秒超时，其他工具继续执行）
- **完全失败**: 立即返回（秒级）

---

## 2. 健康检查接口

### 接口描述

检查快速溯源服务是否正常运行。

### 请求地址

```
GET http://219.135.180.51:56041/api/quick-trace/health
```

### 请求方式

```
GET
```

### 请求参数

无

### 返回结果

#### 成功响应

**HTTP Status Code**: `200 OK`

```json
{
  "status": "healthy",
  "service": "quick_trace_alert",
  "version": "1.0.0",
  "supported_cities": [
    "济宁市"
  ]
}
```

#### 返回字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| status | string | 服务状态，`healthy`表示正常 |
| service | string | 服务名称 |
| version | string | 服务版本号 |
| supported_cities | array | 支持的城市列表 |

---

## 3. 支持的城市列表

### 接口描述

获取当前支持分析的城市列表及其坐标信息。

### 请求地址

```
GET http://219.135.180.51:56041/api/quick-trace/supported-cities
```

### 请求方式

```
GET
```

### 请求参数

无

### 返回结果

#### 成功响应

**HTTP Status Code**: `200 OK`

```json
{
  "service": "quick_trace_alert",
  "supported_cities": [
    "济宁市"
  ],
  "city_coordinates": {
    "济宁市": {
      "lat": 35.4154,
      "lon": 116.5875
    }
  },
  "nearby_cities": {
    "济宁市": [
      "菏泽市",
      "枣庄市",
      "临沂市",
      "泰安市",
      "徐州市",
      "商丘市",
      "开封市"
    ]
  }
}
```

#### 返回字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| service | string | 服务名称 |
| supported_cities | array | 支持的城市列表 |
| city_coordinates | object | 城市经纬度映射 |
| city_coordinates.[城市名].lat | float | 纬度 |
| city_coordinates.[城市名].lon | float | 经度 |
| nearby_cities | object | 各城市的周边城市列表（用于区域传输分析） |

---

## 4. 错误码说明

### HTTP状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 422 | 请求数据验证失败 |
| 500 | 服务器内部错误 |

### 错误响应格式

```json
{
  "detail": "错误详细信息"
}
```

### 常见错误示例

#### 1. 城市名称不支持

**HTTP Status Code**: `400`

```json
{
  "detail": "不支持的城市: 北京市"
}
```

#### 2. 告警时间格式错误

**HTTP Status Code**: `422`

```json
{
  "detail": [
    {
      "loc": ["body", "alert_time"],
      "msg": "告警时间格式错误，正确格式为: YYYY-MM-DD HH:MM:SS",
      "type": "value_error"
    }
  ]
}
```

#### 3. 污染物类型不支持

**HTTP Status Code**: `422`

```json
{
  "detail": [
    {
      "loc": ["body", "pollutant"],
      "msg": "不支持的污染物类型: XXX",
      "type": "value_error"
    }
  ]
}
```

#### 4. 服务器内部错误

**HTTP Status Code**: `500`

```json
{
  "detail": "快速溯源分析失败: 详细错误信息"
}
```

---

## 5. 调用示例

### cURL示例

```bash
# 1. 快速溯源分析
curl -X POST "http://219.135.180.51:56041/api/quick-trace/alert" \
  -H "Content-Type: application/json" \
  -d '{
    "city": "济宁市",
    "alert_time": "2026-02-03 00:30:00",
    "pollutant": "PM2.5",
    "alert_value": 130.0
  }'

# 2. 健康检查
curl -X GET "http://219.135.180.51:56041/api/quick-trace/health"

# 3. 获取支持的城市列表
curl -X GET "http://219.135.180.51:56041/api/quick-trace/supported-cities"
```

### Python示例

```python
import requests
import json

# API基础地址
BASE_URL = "http://219.135.180.51:56041"

# 1. 快速溯源分析
def quick_trace_alert(city, alert_time, pollutant, alert_value):
    """触发快速溯源分析"""
    url = f"{BASE_URL}/api/quick-trace/alert"
    payload = {
        "city": city,
        "alert_time": alert_time,
        "pollutant": pollutant,
        "alert_value": alert_value
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=180)
        response.raise_for_status()
        result = response.json()

        print(f"✅ 分析成功")
        print(f"执行耗时: {result['execution_time_seconds']} 秒")
        print(f"包含轨迹分析: {result['has_trajectory']}")
        print(f"警告信息: {result['warning_message']}")

        # 保存报告
        with open("quick_trace_report.md", "w", encoding="utf-8") as f:
            f.write(result["summary_text"])
        print("报告已保存到: quick_trace_report.md")

        return result

    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {e}")
        return None

# 2. 健康检查
def health_check():
    """检查服务健康状态"""
    url = f"{BASE_URL}/api/quick-trace/health"
    try:
        response = requests.get(url)
        response.raise_for_status()
        result = response.json()
        print(f"服务状态: {result['status']}")
        print(f"支持的城市: {result['supported_cities']}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"❌ 健康检查失败: {e}")
        return None

# 3. 获取支持的城市
def get_supported_cities():
    """获取支持的城市列表"""
    url = f"{BASE_URL}/api/quick-trace/supported-cities"
    try:
        response = requests.get(url)
        response.raise_for_status()
        result = response.json()
        print(f"支持的城市: {result['supported_cities']}")
        print(f"城市坐标: {result['city_coordinates']}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"❌ 获取城市列表失败: {e}")
        return None

# 使用示例
if __name__ == "__main__":
    # 先检查服务状态
    health_check()

    # 执行快速溯源分析
    result = quick_trace_alert(
        city="济宁市",
        alert_time="2026-02-03 00:30:00",
        pollutant="PM2.5",
        alert_value=130.0
    )
```

### Java示例

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import com.fasterxml.jackson.databind.ObjectMapper;

public class QuickTraceClient {

    private static final String BASE_URL = "http://219.135.180.51:56041";
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    public QuickTraceClient() {
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();
        this.objectMapper = new ObjectMapper();
    }

    /**
     * 快速溯源分析
     */
    public QuickTraceResult quickTraceAlert(AlertRequest request) throws IOException, InterruptedException {
        String json = objectMapper.writeValueAsString(request);

        HttpRequest httpRequest = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/api/quick-trace/alert"))
            .header("Content-Type", "application/json")
            .timeout(Duration.ofSeconds(180))
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<String> response = httpClient.send(httpRequest,
            HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() == 200) {
            return objectMapper.readValue(response.body(), QuickTraceResult.class);
        } else {
            throw new RuntimeException("请求失败: " + response.statusCode() + ", " + response.body());
        }
    }

    /**
     * 健康检查
     */
    public HealthResult healthCheck() throws IOException, InterruptedException {
        HttpRequest httpRequest = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/api/quick-trace/health"))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<String> response = httpClient.send(httpRequest,
            HttpResponse.BodyHandlers.ofString());

        return objectMapper.readValue(response.body(), HealthResult.class);
    }

    // 请求实体类
    public static class AlertRequest {
        private String city;
        private String alertTime;
        private String pollutant;
        private Double alertValue;
        private String unit = "μg/m³";

        // Getters and Setters
        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
        public String getAlertTime() { return alertTime; }
        public void setAlertTime(String alertTime) { this.alertTime = alertTime; }
        public String getPollutant() { return pollutant; }
        public void setPollutant(String pollutant) { this.pollutant = pollutant; }
        public Double getAlertValue() { return alertValue; }
        public void setAlertValue(Double alertValue) { this.alertValue = alertValue; }
        public String getUnit() { return unit; }
        public void setUnit(String unit) { this.unit = unit; }
    }

    // 响应实体类
    public static class QuickTraceResult {
        private String summaryText;
        private Double executionTimeSeconds;
        private Boolean hasTrajectory;
        private String warningMessage;

        // Getters and Setters
        public String getSummaryText() { return summaryText; }
        public void setSummaryText(String summaryText) { this.summaryText = summaryText; }
        public Double getExecutionTimeSeconds() { return executionTimeSeconds; }
        public void setExecutionTimeSeconds(Double executionTimeSeconds) { this.executionTimeSeconds = executionTimeSeconds; }
        public Boolean getHasTrajectory() { return hasTrajectory; }
        public void setHasTrajectory(Boolean hasTrajectory) { this.hasTrajectory = hasTrajectory; }
        public String getWarningMessage() { return warningMessage; }
        public void setWarningMessage(String warningMessage) { this.warningMessage = warningMessage; }
    }

    public static class HealthResult {
        private String status;
        private String service;
        private String version;
        private java.util.List<String> supportedCities;

        // Getters and Setters
        public String getStatus() { return status; }
        public void setStatus(String status) { this.status = status; }
        public String getService() { return service; }
        public void setService(String service) { this.service = service; }
        public String getVersion() { return version; }
        public void setVersion(String version) { this.version = version; }
        public java.util.List<String> getSupportedCities() { return supportedCities; }
        public void setSupportedCities(java.util.List<String> supportedCities) { this.supportedCities = supportedCities; }
    }

    // 使用示例
    public static void main(String[] args) {
        QuickTraceClient client = new QuickTraceClient();

        try {
            // 健康检查
            HealthResult health = client.healthCheck();
            System.out.println("服务状态: " + health.getStatus());

            // 快速溯源分析
            AlertRequest request = new AlertRequest();
            request.setCity("济宁市");
            request.setAlertTime("2026-02-03 00:30:00");
            request.setPollutant("PM2.5");
            request.setAlertValue(130.0);

            QuickTraceResult result = client.quickTraceAlert(request);
            System.out.println("执行耗时: " + result.getExecutionTimeSeconds() + " 秒");
            System.out.println("包含轨迹分析: " + result.getHasTrajectory());
            System.out.println("报告: " + result.getSummaryText().substring(0, 200) + "...");

        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
```

### JavaScript/Node.js示例

```javascript
const axios = require('axios');

// API基础地址
const BASE_URL = 'http://219.135.180.51:56041';

/**
 * 快速溯源分析
 */
async function quickTraceAlert(city, alertTime, pollutant, alertValue) {
  try {
    const response = await axios.post(`${BASE_URL}/api/quick-trace/alert`, {
      city: city,
      alert_time: alertTime,
      pollutant: pollutant,
      alert_value: alertValue
    }, {
      headers: { 'Content-Type': 'application/json' },
      timeout: 180000 // 3分钟超时
    });

    console.log('✅ 分析成功');
    console.log('执行耗时:', response.data.execution_time_seconds, '秒');
    console.log('包含轨迹分析:', response.data.has_trajectory);
    console.log('警告信息:', response.data.warning_message);

    // 保存报告
    const fs = require('fs');
    fs.writeFileSync('quick_trace_report.md', response.data.summary_text);
    console.log('报告已保存到: quick_trace_report.md');

    return response.data;

  } catch (error) {
    console.error('❌ 请求失败:', error.response?.data || error.message);
    throw error;
  }
}

/**
 * 健康检查
 */
async function healthCheck() {
  try {
    const response = await axios.get(`${BASE_URL}/api/quick-trace/health`);
    console.log('服务状态:', response.data.status);
    console.log('支持的城市:', response.data.supported_cities);
    return response.data;
  } catch (error) {
    console.error('❌ 健康检查失败:', error.message);
    throw error;
  }
}

/**
 * 获取支持的城市列表
 */
async function getSupportedCities() {
  try {
    const response = await axios.get(`${BASE_URL}/api/quick-trace/supported-cities`);
    console.log('支持的城市:', response.data.supported_cities);
    console.log('城市坐标:', response.data.city_coordinates);
    return response.data;
  } catch (error) {
    console.error('❌ 获取城市列表失败:', error.message);
    throw error;
  }
}

// 使用示例
(async () => {
  try {
    // 先检查服务状态
    await healthCheck();

    // 执行快速溯源分析
    const result = await quickTraceAlert(
      '济宁市',
      '2026-02-03 00:30:00',
      'PM2.5',
      130.0
    );

  } catch (error) {
    console.error('执行失败:', error.message);
  }
})();
```

---

## 附录

### 支持的污染物类型

| 污染物 | 说明 | 单位 |
|--------|------|------|
| PM2.5 | 细颗粒物 | μg/m³ |
| PM10 | 可吸入颗粒物 | μg/m³ |
| O3 | 臭氧 | μg/m³ |
| NO2 | 二氧化氮 | μg/m³ |
| SO2 | 二氧化硫 | μg/m³ |
| CO | 一氧化碳 | mg/m³ |
| AQI | 空气质量指数 | - |

### 周边城市说明

对于每个城市，系统会自动分析其周边城市的污染情况，用于区域传输分析。例如：

- **济宁市**的周边城市：菏泽市、枣庄市、临沂市、泰安市、徐州市、商丘市、开封市

### 数据获取说明

系统会自动获取以下数据（无需外部提供）：

1. **当天气象数据** - 温度、湿度、风速、气压等
2. **历史气象数据** - 告警时间前3天的ERA5数据
3. **未来7天天气预报** - 边界层高度、风场、降水等
4. **周边城市空气质量数据** - 前12小时小时数据
5. **72小时后向轨迹** - 100m、500m、1000m三个高度层

### 注意事项

1. **执行时间**: 正常情况下2-3分钟，建议设置超时时间为3分钟
2. **轨迹分析超时**: 轨迹分析可能超时（90秒），不影响其他分析结果
3. **数据缺失**: 部分数据可能缺失（如周边城市空气质量数据），报告中会说明
4. **报告格式**: 返回的 `summary_text` 为Markdown格式，前端需要使用Markdown渲染器显示
5. **图表URL**: `visuals` 数组中的图表URL可直接在 `<img>` 标签中使用

### 联系方式

如有问题，请联系系统管理员。

---

**文档版本**: v1.0.0
**最后更新**: 2026-02-03
