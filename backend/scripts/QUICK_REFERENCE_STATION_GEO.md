# 站点地理信息更新工具 - 快速参考

## 快速开始

### 方式1：使用启动脚本（推荐）

```bash
cd backend/scripts
./run_station_geo_update.sh
```

按照提示选择操作：
1. 测试单个城市
2. 执行全量更新
3. 验证更新结果
4. 完整流程（推荐）

### 方式2：直接执行脚本

```bash
cd backend/scripts

# 1. 测试单个城市（可选）
python3 test_city_matching.py 广州

# 2. 执行全量更新
python3 update_station_geo_info.py

# 3. 验证更新结果
python3 validate_station_geo_update.py
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `station_district_results_with_type_id_updated.json` | 更新后的完整文件 |
| `station_district_results_with_type_id_updated_unmatched.json` | 未匹配的站点列表 |
| `station_geo_update_report.txt` | 详细的验证报告 |

## 验证替换

更新完成后，请务必：

1. **查看验证报告**
   ```bash
   cat backend/config/station_geo_update_report.txt
   ```

2. **检查未匹配站点**（如果有）
   ```bash
   cat backend/config/station_district_results_with_type_id_updated_unmatched.json
   ```

3. **确认无误后替换原文件**
   ```bash
   cp backend/config/station_district_results_with_type_id.json backend/config/station_district_results_with_type_id.json.backup
   cp backend/config/station_district_results_with_type_id_updated.json backend/config/station_district_results_with_type_id.json
   ```

## 匹配策略

1. **唯一编码匹配**（最可靠）
2. **站点名称精确匹配**
3. **城市+站点名称组合匹配**

## 更新策略

- 只补充缺失字段
- 不覆盖已有数据
- 逐城市处理
- 详细日志记录

## 常见问题

**Q: 匹配率低怎么办？**
A: 使用 `test_city_matching.py` 查看具体匹配情况，分析原因

**Q: 如何回滚？**
A: 使用备份文件恢复：`cp backend/config/station_district_results_with_type_id.json.backup backend/config/station_district_results_with_type_id.json`

**Q: 数据库连接失败？**
A: 检查网络连接和数据库配置，确认 ODBC 驱动已安装

## 详细文档

查看完整文档：`README_STATION_GEO_UPDATE.md`
