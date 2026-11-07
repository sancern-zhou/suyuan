# 交付契约（output-contract）

## 1. 输出路径与命名

- 交付文件必须 `out = artifact_path("主题_YYYYMMDD.xlsx")`；禁止自拼路径。
- 命名：`{中文主题}_{YYYYMMDD}.xlsx`；同一主题迭代**复用首次 file_path 覆盖保存**。

## 2. 规模约束

- 单 sheet ≤5 万行（前端 SheetJS 解析限制）；超限分 sheet 或改 CSV 附件并汇报说明。
- 修改现有大文件（>10 万行）优先就地改单元格，不整表重写。

## 3. 预览与发布

- execute_python 检测到 openpyxl/xlsx 关键字会自动注入 Excel 辅助函数并触发
  预览（EXCEL_SAVED 协议）；保存 .xlsx 后自动生成 PDF 预览。
- validate_office 通过后 xlsx 主文件 + report.json 作为同一资源组自动发布，
  `gate.status == "passed"` 即完成交付。
- 前端在线预览（SheetJS）不保真样式/条件格式/图表：关键信息必须有文字列
  承载，不能只靠颜色传达；交付说明中提示完整样式请下载后用 Excel 打开。

## 4. 数据纪律（data_manual 继承）

- 中间结构化数据用 `save_data(...)`，禁止把临时 Excel 当工具间交换协议。
- 交付表中的数据必须可追溯：来源与时间范围写入"说明"sheet 或表注。
