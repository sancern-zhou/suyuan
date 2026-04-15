# 臭氧垂直报告批量处理 - 快速使用指南

## 1. 准备工作（5分钟）

### 步骤1：组织报告文件

创建一个文件夹存放所有待处理的报告：

```bash
mkdir -p /home/xckj/suyuan/ozone_reports
```

将所有臭氧垂直报告文件复制到该文件夹：

```
/home/xckj/suyuan/ozone_reports/
├── 2022年1月1日臭氧垂直.docx
├── 2022年1月2日臭氧垂直.docx
├── 2022年1月3日臭氧垂直.docx
└── ...
```

### 步骤2：配置API密钥

```bash
# 设置环境变量（必须）
export QWEN_VL_API_KEY="your-api-key-here"

# 验证环境变量已设置
echo $QWEN_VL_API_KEY
```

**重要**：
- API密钥必须通过环境变量设置
- 脚本会自动从环境变量读取
- 无需修改配置文件

### 步骤3：修改配置文件

```bash
cd /home/xckj/suyuan/backend/scripts
vim batch_ozone_config.json
```

确认以下配置正确：

```json
{
  "reports_dir": "/home/xckj/suyuan/ozone_reports",
  "output_dir": "/home/xckj/suyuan/ozone_reports_processed",
  "concurrent_tasks": 1,
  "api_request_interval": 2
}
```

**配置说明**：
- `concurrent_tasks`: 1（顺序执行，避免API限流）
- `api_request_interval`: 2（每次请求间隔2秒）

## 2. 测试处理（推荐先测试）

### 测试单份报告

```bash
cd /home/xckj/suyuan/backend/scripts

# 使用启动脚本
./run_test.sh "/home/xckj/suyuan/ozone_reports/2022年1月1日臭氧垂直.docx"

# 或直接使用Python
python3 test_single_report.py --file "/home/xckj/suyuan/ozone_reports/2022年1月1日臭氧垂直.docx"
```

### 查看测试结果

```bash
# 查看处理报告
cat test_report.json | jq

# 查看输出文件
ls -la test_output/

# 检查处理后的报告
vim test_output/2022年1月1日臭氧垂直.docx
```

## 3. 批量处理

### 启动批量处理

```bash
cd /home/xckj/suyuan/backend/scripts

# 使用启动脚本（推荐）
./run_batch_processor.sh

# 或直接使用Python
python3 batch_ozone_report_processor.py
```

### 监控处理进度

**方式1：查看进度文件**

```bash
# 实时查看进度
watch -n 5 'cat batch_ozone_report_processor_progress.json | jq'
```

**方式2：查看日志输出**

```bash
# 保存日志到文件
python3 batch_ozone_report_processor.py 2>&1 | tee processing.log

# 实时查看日志
tail -f processing.log
```

### 查看处理结果

```bash
# 查看最终报告
cat batch_ozone_report_processor_report.json | jq

# 查看处理后的报告
ls -la /home/xckj/suyuan/ozone_reports_processed/

# 统计成功/失败数量
jq '.statistics' batch_ozone_report_processor_report.json
```

## 4. 常见问题

### Q1：如何暂停和恢复处理？

```bash
# 暂停：Ctrl+C 停止脚本

# 恢复：重新运行脚本，会自动跳过已完成的报告
./run_batch_processor.sh
```

### Q2：如何只处理部分报告？

```bash
# 方法1：创建子文件夹，只放入要处理的报告
mkdir /home/xckj/suyuan/ozone_reports_batch1
cp /home/xckj/suyuan/ozone_reports/2022年1月*.docx /home/xckj/suyuan/ozone_reports_batch1/

# 修改配置文件指向新文件夹
vim batch_ozone_config.json
# "reports_dir": "/home/xckj/suyuan/ozone_reports_batch1"

# 运行处理
./run_batch_processor.sh
```

### Q3：处理失败怎么办？

```bash
# 查看失败报告列表
jq '.progress.failed' batch_ozone_report_processor_progress.json

# 单独处理失败的报告
./run_test.sh "/home/xckj/suyuan/ozone_reports/失败的报告.docx"

# 查看详细错误日志
cat processing.log | grep "ERROR"
```

### Q4：如何调整处理速度？

```bash
# 查看当前配置
cat batch_ozone_config.json | jq '.concurrent_tasks'

# 保持默认配置（推荐）
# "concurrent_tasks": 1  - 顺序执行，最稳定
# "api_request_interval": 2  - 每次请求间隔2秒
```

**重要**：
- 默认配置已经是最佳配置（顺序执行）
- 不建议修改为并发执行，可能触发API限流
- 处理速度主要受API响应时间影响

### Q5：遇到API限流怎么办？

```bash
# 查看日志中的限流警告
grep "api_rate_limit" processing.log

# 脚本会自动处理：
# 1. 检测到429错误自动重试
# 2. 使用指数退避策略（5秒→10秒→15秒）
# 3. 最多重试3次

# 如果仍然频繁限流：
# - 确认 concurrent_tasks=1（顺序执行）
# - 增加 api_request_interval 到3或5
# - 检查API密钥的并发限制
```

## 5. 处理流程说明

每份报告会依次执行以下5个步骤：

1. **数据特征分析**：读取表格数据，生成分析结论
2. **NO2、O3污染特征分析**：分析图片1和2，生成污染特征
3. **O3空间分布特征**：分析图片3，生成空间分布特征
4. **臭氧垂直分布分析**：分析图片4和5，生成垂直分布特征
5. **生成总结**：综合以上分析，生成总结

每个步骤都会自动替换文档中的对应文本。

## 6. 文件说明

```
backend/scripts/
├── batch_ozone_report_processor.py      # 主处理脚本
├── batch_ozone_config.json              # 配置文件
├── test_single_report.py                # 测试脚本
├── run_batch_processor.sh               # 批量处理启动脚本
├── run_test.sh                          # 测试启动脚本
├── BATCH_OZONE_PROCESSOR_README.md      # 详细说明文档
└── QUICK_START.md                       # 本快速指南
```

## 7. 下一步

1. **完成测试**：先处理1-2份报告，确认结果符合预期
2. **批量处理**：启动批量处理，等待完成
3. **质量检查**：随机抽查处理后的报告，确认质量
4. **归档原始报告**：备份原始报告到安全位置

## 8. 获取帮助

- 详细文档：`BATCH_OZONE_PROCESSOR_README.md`
- 查看日志：`processing.log`
- 检查配置：`batch_ozone_config.json`

---

**预计处理时间**：
- 单份报告：约3-6分钟（取决于图片数量和API响应速度）
- 100份报告（顺序执行）：约5-10小时
- 处理速度：约10-20份/小时

**执行模式**：
- 顺序执行（concurrent_tasks=1）：推荐，最稳定
- API请求间隔：2秒（避免触发限流）
- 自动重试：3次（遇到错误自动恢复）

**注意事项**：
- 必须设置 `QWEN_VL_API_KEY` 环境变量
- 处理过程中请保持网络连接
- 建议在非高峰时段运行批量处理
- 定期检查处理进度和结果
- API费用：根据报告数量和图片数量计费
