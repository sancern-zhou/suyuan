# 图表模式提示词更新总结

## 更新日期
2026-04-02

## 更新文件
`backend/app/agent/prompts/chart_prompt.py`

## 更新原因
新增了23个ECharts官方模板，原有提示词只包含9种图表类型和旧的模板检索方式，需要更新以支持新模板。

## 主要变更

### 1. 工作流程优化

#### 原有流程（单一方式）
```
分析数据 → 搜索模板 → 阅读模板 → 展示方案 → 生成代码 → 执行
```

#### 新流程（三种方式）
```
分析数据 → 选择模板来源（三选一） → 阅读/生成 → 展示方案 → 执行
  ├── 方式A（推荐）：直接使用37种内置模板
  ├── 方式B：检索 config/chart_templates/ 自定义模板
  └── 方式C：检索 echarts-examples 官方示例
```

### 2. 新增内容

#### 内置模板库章节
- **原有模板**（14种）：vocs_analysis, pm_analysis, generic_timeseries 等
- **新增模板**（23种）：bar_stack_negative, scatter_clustering, line_area_gradient 等
- **总计**：37种内置模板
- **使用方法**：直接调用 `generate_chart(data, chart_type="模板ID")`

#### ECharts官方示例检索章节
**检索方法**：
1. 按图表类型：`search_files(pattern="bar-*.ts", path="...")`
2. 按元数据：`grep(pattern="category: gauge", type="ts", path="...")`
3. 查看目录：`list_directory(path="...", recursive=false)`
4. 读取示例：`read_file(file_path="...")`

**位置**：`/tmp/echarts-examples-gh-pages/public/examples/ts/`

### 3. 可用工具更新

#### 新增工具
- `search_files` - 检索 echarts-examples 官方示例
- `list_directory` - 查看目录结构

#### 工具分类
- **数据操作**：read_data_registry, execute_python
- **模板检索**：grep, search_files, list_directory, read_file
- **模板管理**：write_file

### 4. 支持的图表类型扩展

#### 原有（9种）
pie, bar, line, timeseries, wind_rose, profile, map, heatmap, radar

#### 新增（28种）
**基础图表**：timeseries, radar
**气象图表**：weather_timeseries
**ECharts变体**（23种）：
- 柱状图：bar_stack_negative, bar_polar_radial, bar_waterfall
- 散点图：scatter_clustering, scatter_matrix, scatter_regression
- 折线图：line_area_gradient, line_step, line_race
- 饼图：pie_rose_type, pie_nest, pie_doughnut
- 仪表盘：gauge_progress, gauge_stage, gauge_ring
- 关系图：graph_force, graph_circular
- 日历图：calendar_heatmap, calendar_pie
- 矩形树图：treemap_simple, treemap_drill_down
- 桑基图：sankey_simple, sankey_vertical

**总计**：37种内置模板

## 测试结果

```
提示词长度: 7973 字符
关键词检查: 11/11 ✓
ECharts模板检查: 10/10 ✓
```

### 验证的关键词
- ✓ 内置模板库
- ✓ ECharts 官方模板
- ✓ bar_stack_negative
- ✓ search_files
- ✓ 37种
- ✓ 方式A/方式B/方式C
- ✓ 官方示例检索
- ✓ scatter_clustering
- ✓ gauge_progress

## 使用示例

### 方式A（推荐）：直接使用内置模板
```
用户：生成一个堆叠柱状图，显示污染源贡献对比

Agent调用：
generate_chart(
    data=[{"category": "源A", "排放": 45, "削减": -10}, ...],
    chart_type="bar_stack_negative"
)
```

### 方式B：检索自定义模板
```
用户：生成一个特殊的渐变柱状图

Agent：
1. grep(pattern="gradient", path="config/chart_templates/")
2. read_file(file_path="config/chart_templates/basic/bar_gradient.json")
3. 基于模板生成代码
```

### 方式C：检索官方示例
```
用户：生成一个环形仪表盘

Agent：
1. search_files(pattern="gauge-*.ts", path="/tmp/echarts-examples-gh-pages/...")
2. read_file(file_path=".../gauge-ring.ts")
3. 提取option配置并生成代码
```

## 设计原则

1. **优先级明确**：方式A（内置模板）> 方式B（自定义）> 方式C（官方示例）
2. **向后兼容**：保留原有的自定义模板检索方式
3. **灵活扩展**：支持三种方式并存，LLM可自由选择
4. **减少检索**：内置模板可直接使用，无需检索，提升效率

## 影响范围

### 正面影响
- ✅ 用户可直接使用23个新模板，无需手动检索
- ✅ 减少LLM检索步骤，提升响应速度
- ✅ 提供更多图表类型选择（从9种→37种）
- ✅ 支持检索echarts-examples官方示例（206个示例）

### 注意事项
- LLM需要学习三种模板使用方式
- 需要在实际对话中观察LLM是否能正确选择方式A

## 后续优化

1. **监控使用情况**：观察LLM是否优先使用方式A（内置模板）
2. **收集反馈**：根据用户需求调整模板优先级
3. **持续扩展**：第二批专业图表（funnel, parallel等）按需添加
4. **前端适配**：确认前端对新图表类型的支持

## 相关文档

- 实施总结：`ECHARTS_TEMPLATES_IMPLEMENTATION_SUMMARY.md`
- 快速指南：`ECHARTS_TEMPLATES_QUICK_START.md`
- 提示词源码：`backend/app/agent/prompts/chart_prompt.py`

---

**更新状态**: ✅ 完成
**测试状态**: ✅ 通过
**提示词长度**: 7973 字符
**支持模板数**: 37种
