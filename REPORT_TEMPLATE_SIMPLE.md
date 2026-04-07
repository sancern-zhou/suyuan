# 报告模板系统（简洁版）

## 设计理念

**零代码实现，利用Agent自然语言理解能力，复用现有通用工具。**

## 核心组件

### 1. 模板存储
- 位置：`backend_data_registry/report_templates/`
- 格式：纯Markdown文件
- 示例：`广东省空气质量月度通报.md`

### 2. 模板格式
```markdown
# 报告名称

## 报告类型
空气质量通报

## 适用场景
生成广东省某个月的空气质量状况报告

## 数据需求
- 城市：全省21个地级市
- 时间：用户指定月份
- 指标：PM2.5、PM10、O3、NO2、SO2、CO、AQI

## 查询计划
1. 使用 query_new_standard_report 查询指定月份的数据

## 报告结构
1. 总体状况：优良天数比例、PM2.5浓度
2. 城市排名：按PM2.5浓度排序
3. 同比变化：与去年同期对比
4. 统计表格：完整数据表

## DOCX格式要求
- 封面、章节标题、表格格式等
```

## 工作流程

### 使用模板
```
用户需求
  ↓
Agent: grep("关键词", "backend_data_registry/report_templates/")
  ↓
找到模板
  ↓
Agent: read_file("模板路径")
  ↓
Agent理解模板内容
  ↓
Agent: 向用户展示查询计划（根据用户需求调整参数）
  ↓
用户确认
  ↓
执行查询 → 生成报告
```

### 保存新模板
```
报告生成成功
  ↓
Agent询问：是否保存为新模板？
  ↓
用户确认
  ↓
Agent: write_file("模板路径", "模板内容（Markdown格式）")
  ↓
模板已保存
```

## 工具使用

### 搜索模板
```json
{
  "tool": "grep",
  "args": {
    "pattern": "空气质量",
    "path": "backend_data_registry/report_templates/"
  }
}
```

### 读取模板
```json
{
  "tool": "read_file",
  "args": {
    "path": "backend_data_registry/report_templates/广东省空气质量月度通报.md"
  }
}
```

### 保存模板
```json
{
  "tool": "write_file",
  "args": {
    "path": "backend_data_registry/report_templates/新模板名称.md",
    "content": "# 报告名称\n\n## 报告类型\n...\n"
  }
}
```

## 优势

1. **零代码实现**：不需要写任何Python代码
2. **利用Agent能力**：让Agent做它擅长的事（理解自然语言）
3. **易于维护**：模板就是Markdown文件，用户可以直接编辑
4. **灵活性高**：Agent可以根据具体情况调整，不受硬编码限制
5. **可扩展**：未来可以支持更复杂的模板格式

## 对比

| 方面 | 复杂设计 | 简洁设计 |
|------|---------|---------|
| 新增代码 | ~600行 | 0行 |
| 新增工具 | 5个专用工具 | 0个（复用现有工具）|
| 占位符 | 硬编码 `{start_date}` | Agent自然语言理解 |
| 灵活性 | 低（受占位符限制） | 高（Agent自由发挥）|
| 维护成本 | 高（专用工具维护） | 低（Markdown文件）|

## 提示词更新

在 `backend/app/agent/prompts/report_prompt.py` 中添加了：
- 报告模板系统说明
- 推荐工作流程（使用grep、read_file、write_file）
- 场景1：使用报告模板
- 场景6：保存新模板
- 更新工作原则

## 总结

这个设计体现了"简单就是美"的原则：
- 零新代码
- 零新工具
- 利用Agent自然语言理解能力
- 模板即文档（Markdown）
