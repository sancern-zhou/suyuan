# Office 文档工具

当前工具不依赖 Microsoft Office COM。Agent 文件路径以项目根目录为基准，后端路径显式包含 `backend/`。

| 任务 | 当前入口 |
|---|---|
| 读取 Word | `read_file` / `read_docx` |
| 生成或修改 Word | `execute_python`，配合 python-docx；报告模式按当前报告资源规范交付 |
| Excel 创建、修改、重算 | `execute_python`，配合 openpyxl、pandas、xlsxwriter |
| 读取 PPTX | `read_pptx` |
| 新建高质量、原生可编辑 PPT | `manage_editable_ppt` |
| 继续维护 PPT Master 项目 | `create_pptx_with_ppt_master` |
| PPT 渲染与质量检查 | `validate_pptx` |
| 企业微信操作 | `wecom-cli` 工具包装 |

具体能力与调用参数以当前工具 Schema 为准。

- 能力选择：[Office 技能指南](office_skills_guide.md)
- Excel 操作：[Excel 操作指南](Excel操作指南.md)
- PPT Master 兼容流程：[PPT 操作指南](PPT操作指南.md)
- 可编辑 PPT 项目：[项目入口规范](editable_ppt/references/index.md)
- 跨平台转换：`soffice.py` 提供 LibreOffice 适配；实际转换仍需部署环境安装相应程序。

历史 Win32 工具实现及对应交互式手工测试已经退役，不再提供相关导入与安装步骤。
