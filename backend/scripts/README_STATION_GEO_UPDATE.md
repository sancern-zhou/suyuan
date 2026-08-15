# 站点地理信息逐城市匹配和更新补充工具

## 概述

本项目提供了一套可靠的工具，用于从 SQL Server 数据库（`BSD_STATION` 表）逐城市匹配和更新补充本地 JSON 文件（`station_district_results_with_type_id.json`）中的站点地理信息。

## 问题背景

- 本地 JSON 文件 `station_district_results_with_type_id.json` 包含 524 个站点，但部分站点的地理信息不全（缺少经度、纬度、区县、详细地址等字段）
- SQL Server 数据库 `180.184.30.94:1433` 的 `AirPollutionAnalysis.BSD_STATION` 表包含完整的站点地理信息
- 需要逐城市匹配，补充缺失的地理信息，确保无遗漏

## 工具列表

### 1. `update_station_geo_info.py` - 主更新脚本

**功能**：
- 从 SQL Server 的 `BSD_STATION` 表获取完整的站点地理信息
- 读取本地的 `station_district_results_with_type_id.json` 文件
- 逐城市对比，找出缺失的地理信息
- 补充缺失的地理信息（经度、纬度、区县、详细地址、行政区划代码等）
- 生成更新后的 JSON 文件

**匹配策略**（三层）：
1. **唯一编码匹配**（最可靠）：通过 `唯一编码` 字段直接匹配
2. **站点名称匹配**：通过 `站点名称` 精确匹配
3. **城市+站点名称组合匹配**：通过 `城市名称` + `站点名称` 组合匹配

**使用方法**：
```bash
cd backend/scripts
python update_station_geo_info.py
```

**输出文件**：
- `station_district_results_with_type_id_updated.json` - 更新后的完整文件
- `station_district_results_with_type_id_updated_unmatched.json` - 未匹配的站点列表（如果有）

### 2. `validate_station_geo_update.py` - 验证脚本

**功能**：
- 验证更新后的 JSON 文件的数据完整性
- 对比更新前后的差异
- 生成详细的验证报告
- 检查是否有遗漏或错误

**使用方法**：
```bash
cd backend/scripts
python validate_station_geo_update.py
```

**输出文件**：
- `station_geo_update_report.txt` - 详细的验证报告

### 3. `test_city_matching.py` - 单城市测试脚本

**功能**：
- 测试指定城市的站点匹配情况
- 显示匹配前后的详细对比
- 用于调试和验证匹配逻辑

**使用方法**：
```bash
cd backend/scripts
python test_city_matching.py 广州
```

**输出**：
- 控制台打印每个站点的匹配对比
- 匹配统计信息

## 工作流程

### 推荐的完整工作流程：

1. **单城市测试**（可选）
   ```bash
   python test_city_matching.py 广州
   ```
   先测试一个城市，确保匹配逻辑正确

2. **执行全量更新**
   ```bash
   python update_station_geo_info.py
   ```
   更新所有城市的站点信息

3. **验证更新结果**
   ```bash
   python validate_station_geo_update.py
   ```
   生成验证报告，检查更新质量

4. **人工审核**
   - 检查未匹配的站点列表（`*_unmatched.json`）
   - 查看验证报告（`station_geo_update_report.txt`）
   - 确认更新后的数据正确性

5. **替换原文件**（确认无误后）
   ```bash
   cp backend/config/station_district_results_with_type_id.json backend/config/station_district_results_with_type_id.json.backup
   cp backend/config/station_district_results_with_type_id_updated.json backend/config/station_district_results_with_type_id.json
   ```

## 数据库连接配置

所有脚本使用相同的 SQL Server 连接配置：

```python
connection_string = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=180.184.30.94,1433;"
    "DATABASE=AirPollutionAnalysis;"
    "UID=sa;"
    "PWD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR;"
    "TrustServerCertificate=yes;"
)
```

如需修改，请编辑各脚本中的 `connection_string` 变量。

## 字段映射

数据库字段 → 本地 JSON 字段：

| 数据库字段 | 本地 JSON 字段 | 说明 |
|-----------|---------------|------|
| StationCode | 唯一编码 | 站点唯一标识 |
| StationName | 站点名称 | 站点名称 |
| CityName | 城市名称 | 城市名称 |
| DistrictName | 区县 | 区县名称 |
| Longitude | 经度 | 经度坐标 |
| Latitude | 纬度 | 纬度坐标 |
| Address | 详细地址 | 详细地址 |
| Province | 省份 | 省份 |
| City | 城市 | 城市（带"市"后缀） |
| Town | 乡镇 | 乡镇 |
| AdminDivisionCode | 行政区划代码 | 行政区划代码 |
| StationTypeID | 站点类型ID | 站点类型标识 |

## 更新策略

- **只补充缺失字段**：如果本地 JSON 中某字段已有值，则保留原值，不覆盖
- **逐城市处理**：按城市分组处理，确保每个城市的站点都被检查
- **详细日志**：记录每个站点的匹配情况和更新内容
- **未匹配追踪**：生成未匹配站点列表，便于后续人工处理

## 依赖项

- Python 3.7+
- pyodbc（SQL Server ODBC 驱动）
- structlog（日志库）

安装依赖：
```bash
pip install pyodbc structlog
```

## 注意事项

1. **备份数据**：更新前务必备份原始 JSON 文件
2. **测试先行**：先使用 `test_city_matching.py` 测试单个城市
3. **人工审核**：更新后务必人工审核验证报告
4. **逐步替换**：确认无误后再替换原文件
5. **数据库连接**：确保能够连接到 SQL Server 数据库

## 故障排除

### 问题1：无法连接到数据库
- 检查网络连接
- 检查 SQL Server 服务是否运行
- 检查用户名和密码是否正确
- 检查 ODBC 驱动是否已安装

### 问题2：匹配率低
- 使用 `test_city_matching.py` 查看具体匹配情况
- 检查数据库和本地 JSON 的站点名称格式是否一致
- 查看未匹配站点列表，分析原因

### 问题3：更新后字段仍然缺失
- 检查数据库中该字段是否为空
- 查看验证报告，了解哪些字段仍然缺失
- 可能需要手动补充或联系数据提供方

## 维护者

如有问题或建议，请联系项目维护者。
