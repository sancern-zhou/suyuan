#!/bin/bash
# 更新图表模式长期记忆文件

MEMORY_FILE="/home/xckj/suyuan/backend_data_registry/memory/chart/MEMORY.md"

sudo tee "$MEMORY_FILE" > /dev/null << 'EOF'
## 用户偏好
- 用户关注站点级5分钟粒度数据查询。
- 用户需要绘制污染物风玫瑰图，需风向数据支持。

## 领域知识
- **5分钟数据查询工具**：get_5min_data（⭐ 新增）- 查询站点5分钟污染物浓度和气象数据（SQL Server air_quality_db数据库，表名格式Air_5m_{年份}_{站点代码}_Src）。支持站点名称或代码，返回宽表格式数据（包含PM2.5、PM10、SO2、NO2、O3、CO、风速WS、风向WD、温度TEMP、湿度RH、气压PRESSURE），支持生成污染风玫瑰图、高精度时序图。
- **小时数据查询工具**：query_gd_suncere_city_hour（城市级别小时数据）、query_gd_suncere_station_hour_new（站点级别小时数据，新标准HJ 633-2026）。
- **日报数据查询工具**：query_gd_suncere_city_day_new（城市级别日报数据，新标准HJ 633-2026）。
- **污染风玫瑰图**：使用 get_5min_data 查询5分钟数据（包含WD风向、WS风速、污染物浓度），通过极坐标散点图 + visualMap 颜色映射展示不同风向下的污染物浓度分布。
- **自定义模板库**：config/chart_templates/meteorology/pollution_rose.json（污染风玫瑰图模板）、config/chart_templates/meteorology/wind_rose.json（风向玫瑰图模板）。

## 历史结论
- 5分钟粒度数据查询工具（get_5min_data）已可用，支持高精度时序图和污染风玫瑰图生成。
- 污染风玫瑰图需要风向（WD）、风速（WS）和污染物浓度数据，get_5min_data 工具返回的数据包含这些字段。
EOF

echo "图表模式长期记忆文件已更新"
echo "文件位置: $MEMORY_FILE"
