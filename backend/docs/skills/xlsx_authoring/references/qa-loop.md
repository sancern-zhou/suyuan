# QA 闭环协议（qa-loop）

生成 → 读回校验 → 修复 → 重验收。**没有经过本闭环的 XLSX 不算交付物。**

## 1. 验收调用

```json
validate_office({ "path": "<上次 artifact_path 返回的 file_path>" })
```

xlsx 分支为 openpyxl 读回校验（不做渲染——前端 SheetJS 即预览）。

## 2. 结果解读

- `gate.status`：`passed` / `needs_revision` / `qa_failed`（校验流程异常）。
- `structured_issues[]`：`type/severity/sheet` + 证据（`cells` 错误值坐标、
  `columns` 溢出列号）。
- `sheets[]`：每表行数/列数/错误值/溢出列概览。

## 3. 修复对照表（issue type → 动作）

| type | 动作 |
|---|---|
| xlsx_error_value | 按 `cells` 坐标定位：检查公式引用范围/除零/表名拼写；修正后重生成 |
| xlsx_sheet_name_invalid | 表名压到 ≤31 字符，去掉 `\ / * ? : [ ]` |
| xlsx_empty_sheet | 删除空表，或补上漏写的数据（常见：append 循环没执行） |
| xlsx_column_overflow | 按 `columns` 显式调列宽（中文 2 宽估算，design-rules §3） |
| xlsx_no_freeze_panes | `ws.freeze_panes = "A2"`（>15 行数据的表） |
| xlsx_missing_header | 首行补表头（中文列名 + 单位） |
| validation_error | 文件损坏或路径错误：读回核验能否 load_workbook 打开 |

## 4. 迭代纪律

- 每轮：修改生成代码 → execute_python 重新生成（覆盖同一 artifact_path 文件）→
  重新 validate_office。
- 最多 **3 轮**。error_value 类（high）必须清零才可交付；low 级（冻结窗格类）
  修复成本极低，不应留到第三轮。
- 每轮同时执行读回核验（code-recipes §5）：表名/关键单元格/行列数断言。
