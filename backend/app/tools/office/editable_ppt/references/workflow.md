# 源码优先 PPT 工作流

## 核心模型

`deck.json` 管理页序，`theme.json` 管理全局视觉变量，`slides/slide-NNN.js` 是每页可直接编辑的文档，`assets/` 保存图片。PPTX 是编译产物。所有文本、基础形状、图片、图表、表格和流程图尽量映射为 PowerPoint 原生对象；`strict` 模式禁止把文字或图表整页截图化。

Agent 不必把每次修改都转换成 Patch。可以用 `read_file` / `edit_file` 直接编辑这些文档，再调用 `manage_editable_ppt(operation="inspect")`；服务会检测哈希变化、创建新 revision，并只把受影响页面标记为 dirty。这样可以从底层多次完善，无需重新生成未修改的页面或丢失人工调整历史。

## 推荐步骤

1. 先完成完整大纲、受众、叙事目标和数据依据。
2. `create` 创建源码项目，选择 government、business 或 data-analysis 主题。
3. 先做封面、一个关键内容页、一个数据页三张锚点页，`render` 检查视觉方向。
4. 方向确定后每批制作 3–5 页。结构调整优先直接编辑源码；单文件修改可用 `edit_source`，同一轮多文件修改用 `edit_sources` 原子提交。
5. 每批 `render`，检查溢出、缺失资源、重复 ID 和关键元素位置。
6. `compile` 使用默认 `editable="strict"`，读取 compile report，确认 forbiddenRasterFallbacks 为 0。
7. `validate` 执行 LibreOffice/PNG/montage/字体/空页检查；修复后重新编译。
8. 只有 strict 编译和验证均通过才 `finalize`。

## 编辑与并发规则

- 调用 `edit_source` 必须携带最近一次 inspect 返回的 `base_revision`；版本过期会拒绝写入。
- 同时修改多页时用一次 `edit_sources`，全部候选源码会先整体校验，然后只增加一个 revision，避免并发调用共享旧版本号造成冲突。
- 普通 `edit_file` 直接编辑后，先 inspect 获取新 revision，再继续托管编辑。
- theme 或模板变化会使全稿 dirty；单页源码变化只影响该页；资源变化只影响引用该资源的页面。
- 每个 `data-pptx-id` / `data-pptx-ref` 必须稳定且页内唯一，图表/表格/流程图通过 nativeElements 表达。
- strict 模式不要使用渐变、`filter`、`transform`、`box-shadow`；装饰元素不能越出 1440×810 画布。每个承载可见文字的叶子节点（包括 `span`）必须有独立的 `data-pptx-id`。
- 可用 `restore` 回到任意已有快照；恢复本身会产生新 revision，不覆写历史。

## 原生对象契约（可直接复制）

原生对象必须同时具备 HTML 占位框和同 ID 的 `nativeElements` 项。占位框负责位置与尺寸，导出时会替换成可编辑的 PowerPoint 对象。不要使用 `type`、`labels`、`values`、`headers` 等简化字段。
占位框应直接放在整页根节点下，并使用相对整页的绝对坐标；不要把整页坐标的占位框嵌入另一个已偏移的容器，否则偏移量会重复叠加并造成越界。

```js
html: `<div class="absolute left-[160px] top-[220px] w-[1120px] h-[420px]" data-pptx-ref="roi-chart"></div>`,
nativeElements: [{
  id: "roi-chart",
  kind: "chart",
  chartType: "column",
  data: {
    categories: ["Q1", "Q2"],
    series: [{ name: "节省工时", values: [120, 260] }]
  }
}]
```

```js
html: `<div class="absolute left-[120px] top-[210px] w-[1200px] h-[430px]" data-pptx-ref="scenario-table"></div>`,
nativeElements: [{
  id: "scenario-table",
  kind: "table",
  data: { rows: [["场景", "价值", "优先级"], ["智能文档", "高", "P0"]] }
}]
```

流程图使用 `kind: "diagram"`，`data.nodes` 的每项包含稳定的 `id` 与 `label`，`data.edges` 的每项包含稳定 `id`、`source`、`target`。若数据并非来自可核验来源，必须在图表或表格附近以可见文字标注“示例数据”，仅写在演讲者备注中不算合格。

## 当前边界

支持 Tailwind/Vite 能稳定测量的 HTML/CSS 子集；复杂滤镜、混合模式和任意脚本不会自动等价转换。用户照片和生成图片可保持为图片对象，但文字、图表、表格不得在 strict 模式中栅格化。任意既有 PPTX 的反向导入编辑属于后续阶段。

## 已验证的性能基线

2026-07-23 在当前开发主机（Node 20、单 Chromium 进程、简单内容页）实测：20 页冷编译 38.1 秒、全缓存热编译 97 毫秒；50 页冷编译 78.8 秒、全缓存热编译 231 毫秒。对应 RSS 约 120–149 MB。基准命令：

`EDITABLE_PPT_PERFORMANCE=1 node --test --test-name-pattern="20/50" test/performance.test.mjs`

缓存键由每页 SlideSpec、主题和固定 viewport 的 SHA-256 共同决定。直接编辑单页后，仅该页重新启动浏览器测量；未变页面复用测量 JSON 与截图。PPTX 仍会完整、确定性地重新打包，避免增量修改 OOXML 包造成关系文件损坏。实际耗时会随图片解码、字体和页面复杂度变化，超过目标会在性能报告中体现，不能因此跳过结构或可编辑性门禁。
