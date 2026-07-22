# 源码优先 PPT 工作流

## 核心模型

`deck.json` 管理页序，`theme.json` 管理全局视觉变量，`slides/slide-NNN.js` 是每页可直接编辑的文档，`assets/` 保存图片。PPTX 是编译产物。所有文本、基础形状、图片、图表、表格和流程图尽量映射为 PowerPoint 原生对象；`strict` 模式禁止把文字或图表整页截图化。

Agent 不必把每次修改都转换成 Patch。可以用 `read_file` / `edit_file` 直接编辑这些文档，再调用 `manage_editable_ppt(operation="inspect")`；服务会检测哈希变化、创建新 revision，并只把受影响页面标记为 dirty。这样可以从底层多次完善，无需重新生成未修改的页面或丢失人工调整历史。

## 推荐步骤

1. 先完成完整大纲、受众、叙事目标和数据依据。
2. `create` 创建源码项目，选择 government、business 或 data-analysis 主题。
3. 先做封面、一个关键内容页、一个数据页三张锚点页，`render` 检查视觉方向。
4. 方向确定后每批制作 3–5 页。结构调整优先直接编辑源码；极小文本修改可用 `edit_source`。
5. 每批 `render`，检查溢出、缺失资源、重复 ID 和关键元素位置。
6. `compile` 使用默认 `editable="strict"`，读取 compile report，确认 forbiddenRasterFallbacks 为 0。
7. `validate` 执行 LibreOffice/PNG/montage/字体/空页检查；修复后重新编译。
8. 只有 strict 编译和验证均通过才 `finalize`。

## 编辑与并发规则

- 调用 `edit_source` 必须携带最近一次 inspect 返回的 `base_revision`；版本过期会拒绝写入。
- 普通 `edit_file` 直接编辑后，先 inspect 获取新 revision，再继续托管编辑。
- theme 或模板变化会使全稿 dirty；单页源码变化只影响该页；资源变化只影响引用该资源的页面。
- 每个 `data-pptx-id` / `data-pptx-ref` 必须稳定且页内唯一，图表/表格/流程图通过 nativeElements 表达。
- 可用 `restore` 回到任意已有快照；恢复本身会产生新 revision，不覆写历史。

## 当前边界

支持 Tailwind/Vite 能稳定测量的 HTML/CSS 子集；复杂滤镜、混合模式和任意脚本不会自动等价转换。用户照片和生成图片可保持为图片对象，但文字、图表、表格不得在 strict 模式中栅格化。任意既有 PPTX 的反向导入编辑属于后续阶段。
