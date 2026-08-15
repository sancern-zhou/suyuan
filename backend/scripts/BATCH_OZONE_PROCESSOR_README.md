# 臭氧垂直报告批量处理脚本 - 使用说明

## 功能概述

自动批量处理臭氧垂直分析报告，依次执行5个分析和替换步骤：

1. **第1步**：查看文档表格内容并进行数据特征分析
2. **第2步**：导出图片并分析NO2、O3污染特征
3. **第3步**：查看分析第3张图片并给出O3空间分布特征
4. **第4步**：读取第4张和第5张图片并分析臭氧垂直分布
5. **第5步**：生成总结并替换

**执行模式**：顺序执行（逐份报告处理），避免API并发限制

## 文件结构

```
backend/scripts/
├── batch_ozone_report_processor.py      # 主处理脚本
├── batch_ozone_config.json              # 配置文件
├── test_single_report.py                # 单份报告测试脚本
└── BATCH_OZONE_PROCESSOR_README.md      # 本说明文档
```

## 快速开始

### 1. 准备报告文件

将所有待处理的臭氧垂直报告放到一个文件夹中，例如：

```
/home/xckj/suyuan/ozone_reports/
├── 2022年1月1日臭氧垂直.docx
├── 2022年1月2日臭氧垂直.docx
├── 2022年1月3日臭氧垂直.docx
└── ...
```

### 2. 配置参数

编辑 `batch_ozone_config.json` 文件：

```json
{
  "reports_dir": "/home/xckj/suyuan/ozone_reports",
  "output_dir": "/home/xckj/suyuan/ozone_reports_processed",
  "concurrent_tasks": 1,
  "api_request_interval": 2,
  "max_retries": 3,
  "retry_delay": 5
}
```

**重要配置说明**：
- `reports_dir`: 存放待处理报告的文件夹路径
- `output_dir`: 处理后报告的输出文件夹（自动创建）
- `concurrent_tasks`: 并发处理数（默认1，即顺序执行）
- `api_request_interval`: API请求间隔（秒），避免触发限流
- `max_retries`: API失败最大重试次数
- `retry_delay`: 重试延迟（秒）

**API密钥配置**：
- API密钥从环境变量 `QWEN_VL_API_KEY` 自动读取
- 无需在配置文件中设置
- 确保环境变量已正确设置

### 3. 运行脚本

#### 运行脚本

```bash
cd /home/xckj/suyuan/backend/scripts

# 1. 设置API密钥环境变量（必须）
export QWEN_VL_API_KEY="your-api-key-here"

# 2. 运行脚本
python batch_ozone_report_processor.py
```

**注意**：API密钥必须通过环境变量设置，脚本会自动读取

### 4. 查看处理结果

处理完成后，查看以下文件：

- **处理报告**: `batch_ozone_report_processor_report.json`
- **进度文件**: `batch_ozone_report_processor_progress.json`
- **处理后的报告**: `output_dir` 配置的文件夹

## 测试模式

在批量处理之前，建议先测试单份报告：

```bash
# 使用测试脚本
python test_single_report.py --file "/path/to/2022年1月1日臭氧垂直.docx"
```

测试脚本会：
1. 只处理指定的单份报告
2. 输出详细的处理日志
3. 生成测试报告

## 进度和恢复

脚本支持断点续传：

- 已处理的报告会记录在 `progress_file` 中
- 如果脚本中断，重新运行会跳过已完成的报告
- 查看进度：`cat batch_ozone_report_processor_progress.json`

## API限流和重试

脚本内置API限流保护：

- **顺序执行**：默认逐份报告处理，避免并发限流
- **请求间隔**：每次API请求间隔2秒（可配置）
- **自动重试**：API失败自动重试3次（可配置）
- **指数退避**：遇到429错误时，重试延迟逐步增加

**通义千问API限制**：
- 免费版：2次/秒并发限制
- 付费版：根据套餐不同，并发限制更高
- 建议：保持 `concurrent_tasks=1`，顺序执行最稳定

## 性能优化

### 执行模式选择

**推荐配置（稳定优先）**：
```json
{
  "concurrent_tasks": 1,
  "api_request_interval": 2
}
```
- 顺序执行，最稳定
- 适合长时间批量处理
- 不会触发API限流

**性能配置（速度优先，需谨慎）**：
```json
{
  "concurrent_tasks": 2,
  "api_request_interval": 1
}
```
- 2份报告同时处理
- 请求间隔缩短为1秒
- 仅在API并发限制较高时使用

### API调用优化

- 图片分析：同一报告内的图片分析仍然并发执行
- 请求间隔：每个报告之间有间隔，避免连续请求
- 自动重试：网络错误或API限流时自动重试
- 指数退避：重试延迟逐步增加（5秒 → 10秒 → 15秒）

## 错误处理

### 常见错误

1. **API密钥未设置**
   ```
   错误：未配置 LLM_API_KEY 环境变量
   解决：export QWEN_VL_API_KEY="your-api-key-here"
   ```

2. **API限流（429错误）**
   ```
   警告：api_rate_limit retry=1/3
   说明：触发了API并发限制，脚本会自动重试
   解决：等待自动重试，或降低 concurrent_tasks
   ```

3. **报告目录不存在**
   ```
   错误：报告目录不存在：/path/to/reports
   解决：修改配置文件中的 reports_dir 路径
   ```

4. **图片分析失败**
   ```
   警告：not_enough_images count=2
   说明：报告中的图片数量不足5张，跳过相应步骤
   ```

5. **网络超时**
   ```
   错误：图片分析超时（120秒）
   解决：检查网络连接，脚本会自动重试
   ```

## 日志和监控

### 查看实时日志

```bash
# 运行时输出详细日志
python batch_ozone_report_processor.py --verbose
```

### 查看处理报告

```bash
# 查看JSON格式的处理报告
cat batch_ozone_report_processor_report.json | jq
```

### 监控进度

```bash
# 实时查看进度文件
watch -n 5 'cat batch_ozone_report_processor_progress.json | jq'
```

## 高级用法

### 自定义提示词

编辑脚本中的 `_step1_data_analysis` 等方法，修改 `prompt` 变量来自定义分析提示词。

### 批量处理特定日期范围

```python
# 在脚本中添加日期过滤
def get_reports(self) -> List[Path]:
    reports = list(self.reports_dir.glob("*.docx"))
    # 添加日期过滤逻辑
    return [r for r in reports if self._is_in_date_range(r)]
```

### 导出处理日志

```bash
# 保存处理日志到文件
python batch_ozone_report_processor.py 2>&1 | tee processing.log
```

## 注意事项

1. **API密钥**: 必须设置 `QWEN_VL_API_KEY` 环境变量
2. **API费用**: 大量处理会产生API调用费用，建议先测试小批量
3. **API限流**: 通义千问API有并发限制，建议保持顺序执行（concurrent_tasks=1）
4. **文件备份**: 处理前建议备份原始报告
5. **网络稳定**: 确保网络连接稳定，避免处理中断
6. **磁盘空间**: 确保有足够的磁盘空间存储处理后的报告
7. **处理时间**: 单份报告约2-5分钟，100份报告约8-16小时（顺序执行）

## 技术支持

如遇问题，请检查：
1. 配置文件是否正确
2. API密钥是否有效
3. 报告文件格式是否正确
4. 网络连接是否正常
5. 日志文件中的错误信息

## 版本历史

- **v1.1** (2026-04-14): 优化版本
  - ✅ 改为顺序执行（避免API并发限制）
  - ✅ 添加API请求间隔（默认2秒）
  - ✅ 添加自动重试机制（最多3次）
  - ✅ API密钥从环境变量自动获取
  - ✅ 添加指数退避策略
  - ✅ 改进错误日志

- **v1.0** (2026-04-14): 初始版本
  - 支持5个步骤的自动处理
  - 进度跟踪和断点续传
  - 并发处理和错误恢复
