# 方案B端到端开发路线图 - 从Mock到生产环境

**当前状态**: ✅ P0-3核心架构完成
**下一步**: 真实API集成 → 生产部署

---

## 阶段1: 真实API集成测试 (Week 1/2)

### 1.1 工具执行器集成

**目标**: 验证 `TemplateDataFetcher` 与真实 `ToolExecutor` 协同工作

**具体步骤**:
```python
# 验证点1: ToolExecutor调用链
ToolExecutor.execute_via_context() → get_air_quality工具 → 返回UDF v2.0数据

# 验证点2: 数据格式验证
response.is_valid() == True
response.data_id != None
response.data.data[0] 包含标准化字段
```

**测试脚本**: `real_integration_test.py`
**验证标准**: 返回真实UDF v2.0数据，field_mapping_applied=True

### 1.2 边界情况处理

```python
# 1. API网络延迟/超时
# 2. 数据库连接失败
# 3. 空数据返回 (return_count=0)
# 4. 字段缺失/格式异常
# 5. 并发请求冲突
```

**处理策略**: Context-Aware V2的错误重试 + 降级数据

---

## 阶段2: 端到端流水线测试 (Week 2/3)

### 2.1 真实历史模板测试

**测试数据**:
```markdown
# 广东省2025年1-6月空气质量分析简报

## 总体概况
全省空气质量持续改善，其中：
- AQI达标率: XX%
- PM2.5浓度: XX μg/m³
- 同比变化: XX%

## 21地市详细数据表

## 城市综合指数排名
```

**预期输出**:
```python
{
    "sections": [{"id": "sec0", "data": [
        {"name": "AQI达标率", "value": 92.3, "unit": "%", "comparison": "同比改善5.2%"}
    ]}],
    "tables": [{"id": "tab0", "rows": [21个城市数据...]}],
    "rankings": [{"id": "rank0", "items": [5个最好城市...]}]
}
```

### 2.2 多时间范围场景验证

- **月度报告**: `1-6月`, `7-12月`
- **季度报告**: `Q1`, `Q2`, `Q3`, `Q4`
- **年度报告**: `1-12月`
- **自定义**: `2025-03-01至2025-03-31`

**验证**: 时间范围正确注入natural language query

---

## 阶段3: 模板管理系统开发 (Week 3/4)

### 3.1 数据库设计

```sql
-- 报告模板表
CREATE TABLE report_templates (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    content TEXT,              -- Markdown模板
    template_type VARCHAR(50), -- 'structural' | 'annotated'
    version VARCHAR(20),
    tags JSON,
    use_count INT DEFAULT 0,
    created_by VARCHAR(100),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 3.2 API接口开发

**REST端点**:
```bash
# 创建模板
POST /api/v1/report-templates
Body: {name, content, type}

# 获取模板列表
GET /api/v1/report-templates?type=structural

# 应用模板生成报告
POST /api/v1/report-templates/{id}/generate
Body: {time_range: {start, end}, options: {}}

# 保存生成的报告
POST /api/v1/reports
Body: {template_id, time_range, content, data_ids: []}
```

---

## 阶段4: 前端集成与UI (Week 4-6)

### 4.1 模板编辑器界面

**Vue 3组件**:
```vue
<ReportTemplateEditor
  :initialContent="templateContent"
  :mode="'structural'"  <!-- or 'annotated' -->
  @parse="handleStructure"
  @error="handleParseError"
/>
```

**功能**:
- ✅ Markdown输入框 + 实时预览
- ✅ 预览LLM解析结构
- ✅ 高亮数据点可选字段
- ✅ 模式选择 (B=C)

### 4.2 报告生成界面

**生成流程**:
1. **模板选择** (列表/搜索)
2. **时间范围** (快速选择/自定义)
3. **进度显示** (事件流可视化)
4. **最终预览** (Markdown渲染)
5. **导出操作** (PDF/Word/Save)

---

## 阶段5: 生产部署准备 (Week 7+)

### 5.1 性能基准测试

| 场景 | 响应时间 | 并发数 | 数据量 |
|------|----------|--------|--------|
| 单模板单时间 | < 5s | 1 | 1000条 |
| 多模板并行 | < 10s | 5 | 5000条 |
| 复杂报告 | < 30s | 1 | 10000条 |

### 5.2 错误监控与恢复

**监控指标**:
- 模板解析成功率
- 工具调用成功率
- 数据生成完整率
- 报告渲染成功率
- 端到端成功率

**告警阈值**: < 90% 触发告警

### 5.3 安全与权限

- **模板访问**: 用户隔离
- **数据权限**: 站点/区域权限控制
- **生成控制**: 频率限制、报告数量限制

---

## 当前待立即执行项

### 🔴 **P0 - 优先执行**
1. **立即**: 运行 `real_integration_test.py`
2. **验证**: 检查 `ToolExecutor` 是否能调通
3. **修复**: 解决 `ModuleNotFoundError` / API连通性

### 🟡 **P1 - 后续跟进**
4. 准备真实历史报告作为测试样本
5. 编写端到端数据流完整性测试
6. 验证UDF v2.0字段映射的准确性

### 🟢 **P2 - 持续优化**
7. 文档最终化 (API文档、用户手册)
8. CLI工具支持快速测试

---

## 风险与应对

| 风险 | 概率 | 应对策略 |
|------|------|----------|
| API网络不可用 | 中 | 本地mock + 降级方案 |
| LLM解析不稳定 | 中 | 硬编码结构绕过 |
| UDF格式不一致 | 低 | 数据标准化钩子 |
| 并发性能差 | 低 | AsyncIO + 数据库优化 |

---

**优先级**: 端到端真实性验证 > 功能完整性 > 性能优化 > 新功能

**支持方式**: 在现有P0-3基础上，直接替换Mock执行器为真实环境，进行最小可行验证。