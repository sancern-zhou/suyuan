# Office 文档工具

当前工具不依赖 Microsoft Office COM。Agent 文件路径以项目根目录为基准，后端路径显式包含 `backend/`。

| 任务 | 当前入口 |
|---|---|
| 读取 Word | `read_file` / `read_docx` |
| 生成或修改 Word | `execute_python`，配合 python-docx；报告模式按当前报告资源规范交付 |
| Excel 创建、修改、重算 | `execute_python`，配合 openpyxl、pandas、xlsxwriter |
| 读取 PPTX | `read_pptx` |
| 生成/修改 PPT（全场景） | `execute_python` + python-pptx，走技能 `pptx_authoring` |
| PPT 渲染与质量检查 | `validate_pptx` |
| 企业微信操作 | `wecom-cli` 工具包装 |

具体能力与调用参数以当前工具 Schema 为准。

- 三格式创作规范：共享技能 `pptx_authoring` / `docx_authoring` / `xlsx_authoring`
  （view_skill 按需读取；PPT 管线 manage_editable_ppt / create_pptx_with_ppt_master 已于 2026-11 退役）
- 跨平台转换：`soffice.py` 提供 LibreOffice 适配；实际转换仍需部署环境安装相应程序。

历史 Win32 工具实现及对应交互式手工测试已经退役，不再提供相关导入与安装步骤。
