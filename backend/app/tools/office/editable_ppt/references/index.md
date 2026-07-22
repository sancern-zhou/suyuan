# 可编辑 PPT Agent 指南

这是新建高质量 PPT 的源码优先工作流。它保留一个长期存在的源码项目，并从源码确定性编译 PPTX；不要把导出的 PPTX 当作下一轮修改的输入。

按需阅读：

- [workflow.md](workflow.md)：生成、直接文件编辑、增量预览、严格编译和交付流程。

工具路由：新建且要求高质量、原生对象可编辑、多轮完善时用 `manage_editable_ppt`；兼容旧项目时继续用 `create_pptx_with_ppt_master`。当前阶段不承诺导入和编辑任意既有 PPTX。
