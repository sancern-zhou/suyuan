# execute_python 数据处理与 Excel 规范

工具 Schema 要求 Agent 在使用 execute_python 进行数据处理、数值计算、Excel/CSV/JSON/Parquet 读写前，通过 read_file 阅读本文件。该要求由 Agent 按任务场景执行，工具运行时代码不检测阅读状态，也不会因此阻断执行。

工具 Schema 已说明所有场景共同遵守的沙箱、input_files、load_data、save_data、artifact_path、返回状态及自动发布规则。本文件只补充数据和表格场景的实施要求。

## 适用场景

- pandas、numpy、scipy 数据清洗、计算、聚合、关联、窗口分析和统计建模。
- Excel、CSV、JSON、Parquet 的读取、修改和生成。
- 跨调用复用的结构化中间结果。
- 专用查询或业务统计工具不能直接完成的自定义计算。

简单查看文件、搜索文本、检查进程或调用已有 CLI 时优先使用对应文件工具或 bash，不要为了调用 Python 而调用 Python。

## 输入与数据访问

- 每次调用都是独立环境，变量和文件挂载不会跨调用保留。
- 读取文件必须在本次调用的 input_files 中声明全部文件；不接受目录。
- input_files 中的路径经权限校验后会以规范化绝对路径注入代码，不要猜测、改写或拼接路径。
- JSON 会话数据优先使用 load_data(file_path)。普通 Excel、CSV 等文件可从 input_files 列表读取。
- 跨调用复用结果必须使用 save_data(data, schema=...)；后续调用原样复用工具返回的 data_file_paths。
- 不得把自行打印、推断或拼接的 sessions/... 路径交给后续工具。

## 数据质量

- 计算前检查字段名称、类型、单位、时间范围、时区、缺失值、重复值和异常值。
- JSON 或数据库中的数字可能是字符串，计算前显式转换并处理转换失败。
- 字典字段可能缺失，使用 get 并明确默认值含义；不得用 0 代替未知或缺失。
- 时间序列先转换为带时区的 datetime，再去重、排序和对齐；不能仅根据首尾样本推断完整性。
- 合并数据必须明确关联键、重复键处理和未匹配记录数量。
- 重要数字应保留可复核的输入范围、单位和计算口径。

## pandas 与 dtype

- 含 None/NaN 的布尔列可能被提升为 object；取反前使用 fillna(False).astype(bool)，或使用 eq(False)。
- 含缺失值的整数列使用可空类型 Int64，不能直接 astype(int)。
- 日期列使用 to_datetime 并显式处理 errors、时区和格式。
- 合并前统一关联字段类型，避免字符串数字与整数数字无法匹配。
- groupby、pivot、窗口计算后核对行数、分组数和总量是否保持合理。
- 不要用全局 fillna(0) 掩盖数据缺失。

## Excel 规则

- 修改现有 Excel 优先使用 openpyxl，避免 pandas.to_excel 覆盖样式、公式、图表、批注和合并区域。
- 创建新文件可使用 pandas 或 openpyxl。
- 修改前检查工作表名称、表头行、冻结窗格、筛选器、隐藏行列、公式和合并单元格。
- 公式优先保留为公式，不要把可计算结果全部硬编码成数值。
- 写入后重新打开文件，核对工作表、关键单元格、公式、行列数和文件可读性。
- 交付 Excel 必须使用 artifact_path(filename.xlsx) 获取输出路径。
- 中间结构化数据使用 save_data，不要把临时 Excel 当作数据交换协议。

Excel 最小示例：

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "结果"
    sheet.append(["指标", "数值"])
    sheet.append(["PM2.5", 30])
    output_path = artifact_path("analysis.xlsx")
    workbook.save(output_path)
    print(output_path)

## 输出与核验

- Excel、CSV、ZIP 等交付文件使用 artifact_path。
- JSON 等跨调用数据使用 save_data。
- 执行后检查 success、error_code、data.data_file_paths、file_path 和 files。
- success=false 时不能声称计算、保存或交付成功。
- 工具已经自动发布交付文件，不要再次调用 publish_session_file。

## 常见失败

- 未声明 input_files：把所有输入路径加入本次调用后重试。
- KeyError：核对真实字段名称，不要凭经验猜字段。
- ValueError/TypeError：检查字符串数字、日期格式、NaN 和混合 dtype。
- Excel 样式丢失：修改已有文件时改用 openpyxl，并避免重建整个工作簿。
- 超时：拆分计算、减少重复扫描，必要时合理提高 timeout。
