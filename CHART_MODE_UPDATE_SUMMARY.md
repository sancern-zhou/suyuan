# 图表模式更新总结

## 更新时间
2026-03-29

## 更新内容

### 1. 后端工具注册表更新

**文件**: `backend/app/agent/prompts/tool_registry.py`

#### 新增工具到 CHART_TOOLS：
- ✅ **数据查询工具**（5个）：
  - `query_gd_suncere_city_hour` - 查询广东省城市小时空气质量数据
  - `query_gd_suncere_city_day_new` - 查询广东省城市日空气质量数据（新标准）
  - `query_new_standard_report` - 查询HJ 633-2024新标准空气质量统计报表
  - `query_old_standard_report` - 查询HJ 633-2011旧标准空气质量统计报表
  - `compare_standard_reports` - 新标准报表对比分析

- ✅ **文件操作工具**（3个）：
  - `read_file` - 读取文件内容
  - `write_file` - 写入文件内容
  - `list_directory` - 列出目录内容

#### 更新 CHART_TOOL_ORDER：
```
1. query_gd_suncere_city_hour
2. query_gd_suncere_city_day_new
3. query_new_standard_report
4. query_old_standard_report
5. compare_standard_reports
6. read_data_registry
7. read_file
8. write_file
9. list_directory
10. execute_python
11. TodoWrite
12. call_sub_agent
```

### 2. 图表模式系统提示词更新

**文件**: `backend/app/agent/prompts/chart_prompt.py`

#### 更新工作流程：
- ✅ 支持两种场景：
  - **场景1**：基于已保存数据生成图表（data_id → 分析 → 设计 → 生成）
  - **场景2**：基于查询数据生成图表（查询 → 设计 → 生成）

#### 新增典型工作流程示例：
- ✅ 场景5：基于查询数据生成图表（查询 → 设计 → 生成）
- ✅ 场景6：展示设计并等待确认（查询数据场景）

#### 更新工作原则：
- ✅ 区分两种场景的工作原则
- ✅ 添加查询工具的重复检查规则
- ✅ 更新检查清单，包含数据查询工具

## 功能特性

### 场景1：基于已保存数据
```
用户: 生成广州O3浓度时序图，数据ID是 vocs_unified:v1:xxx

Agent: 
1. read_data_registry(list_fields=true) - 分析数据
2. FINAL_ANSWER - 展示设计方案并等待确认
3. 用户确认后 read_data_registry - 加载完整数据
4. execute_python - 生成并执行Matplotlib代码
```

### 场景2：基于查询数据（新增）
```
用户: 生成广州2024年1月的O3浓度时序图

Agent:
1. query_gd_suncere_city_day_new - 查询数据
2. FINAL_ANSWER - 展示设计方案并等待确认
3. 用户确认后 execute_python - 生成并执行Matplotlib代码
```

## 工具数量对比

| 类别 | 更新前 | 更新后 | 增加 |
|------|--------|--------|------|
| 数据查询工具 | 0 | 5 | +5 |
| 数据读取工具 | 1 | 1 | 0 |
| 文件操作工具 | 0 | 3 | +3 |
| 代码执行工具 | 1 | 1 | 0 |
| 任务管理工具 | 1 | 1 | 0 |
| 模式互调工具 | 1 | 1 | 0 |
| **总计** | **4** | **12** | **+8** |

## 优势

1. **更强大的数据获取能力**
   - 不再局限于已保存的数据
   - 可以直接查询广东省空气质量数据
   - 支持多种数据格式和时间粒度

2. **更灵活的工作流程**
   - 支持两种数据来源（已保存数据 + 实时查询）
   - 自动选择最优工作流程
   - 智能避免重复操作

3. **更好的用户体验**
   - 无需手动查询数据再保存
   - 一次请求完成数据查询和图表生成
   - 依然保持用户确认环节

## 使用示例

### 示例1：查询数据生成图表
```
用户: 生成广州2024年3月的PM2.5浓度柱状图

Agent:
[查询] query_gd_suncere_city_day_new(cities=["广州"], start_date="2024-03-01", end_date="2024-03-31")
[分析] 获取到31天数据，包含PM2.5、PM10、O3等字段
[设计] 📊 图表设计方案（待确认）
      【数据信息】城市: 广州，时间: 2024-03-01~2024-03-31，字段: timestamp, PM2_5, PM10...
      【图表设计】类型: bar，X轴: 日期，Y轴: PM2.5
      请确认或提出修改建议。
[生成] 用户确认后生成Matplotlib代码并执行
[完成] 返回图表图片URL
```

### 示例2：基于已保存数据生成图表
```
用户: 生成O3浓度时序图，数据ID是 vocs_unified:v1:xxx

Agent:
[分析] read_data_registry(data_id="vocs_unified:v1:xxx", list_fields=true)
[设计] 📊 图表设计方案（待确认）
[加载] 用户确认后 read_data_registry(time_range="2024-01-01,2024-01-31")
[生成] execute_python(生成的Matplotlib代码)
[完成] 返回图表图片URL
```

## 兼容性

✅ 向后兼容：原有的基于已保存数据的工作流程完全保留
✅ 工具增强：新增工具不影响现有功能
✅ 前端支持：前端已更新，支持图表模式切换
✅ 后端支持：后端API已更新，支持图表模式

## 验证清单

- ✅ CHART_TOOLS 已更新（12个工具）
- ✅ CHART_TOOL_ORDER 已更新
- ✅ 图表模式系统提示词已更新
- ✅ 工作流程示例已添加
- ✅ 工作原则已更新
- ✅ 检查清单已更新

## 下一步

图表模式现已完全集成，可以：
1. 查询广东省空气质量数据
2. 读取和分析已保存数据
3. 生成各种类型的Matplotlib图表
4. 支持文件读写操作
5. 与其他模式互调

建议测试场景：
- 生成广州市PM2.5月度变化柱状图
- 生成多城市O3浓度对比图
- 生成空气质量指标时序图
