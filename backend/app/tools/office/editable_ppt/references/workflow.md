# 源码优先 PPT 工作流

## 核心模型

`deck.json` 管理页序，`theme.json` 管理全局视觉变量，`slides/slide-NNN.js` 是每页可直接编辑的文档，`assets/` 保存图片。PPTX 是编译产物。所有文本、基础形状、图片、图表、表格和流程图尽量映射为 PowerPoint 原生对象；`strict` 模式禁止把文字或图表整页截图化。

Agent 不必把每次修改都转换成 Patch。可以用 `read_file` / `edit_file` 直接编辑这些文档，再调用 `manage_editable_ppt(operation="inspect")`；服务会检测哈希变化、创建新 revision，并只把受影响页面标记为 dirty。这样可以从底层多次完善，无需重新生成未修改的页面或丢失人工调整历史。

## 1. 材料理解

- 读取用户材料并形成结构化 brief，至少包含受众、汇报目标、核心结论、事实数据、数据来源和视觉约束。
- 后续优先使用 brief，不重复读取整份原始材料；需要核对事实时，只回读对应原文片段。
- 材料不足但不影响方向时可以做显式假设，不得虚构事实、来源或数据。

退出条件：已经具备页面规划所需信息，所有关键数字都能追溯到用户材料或工具结果。

## 2. 大纲规划

- 在生成源码前完成精确页数的大纲。每页至少写明页面目的、核心结论、内容来源和建议版式。
- 检查用户要求页数、章节闭环、目录承诺与正文页是否一致。
- 用户指定页数时，后续 `render` 和 `compile` 必须传 `expected_slide_count`。

退出条件：计划页数与用户要求完全一致；页数不匹配时不得进入源码生成。

## 3. 初稿生成

- 使用 `create` 创建源码项目，根据任务选择 government、business 或 data-analysis 主题。
- 约束清晰的任务优先一次批量生成 theme、deck 和全部页面源码。只有视觉方向高度不确定时，才先做封面、关键内容页和数据页作为锚点。
- 长稿受单次输出规模限制时可以按 3–5 页分批生成，但必须以已确认的完整大纲为准，并在进入交付前补齐全部页面。
- 生成后立即 `inspect`，确认实际页面数、源码文件数、资源引用和 revision。

退出条件：源码项目结构完整，实际页面数通过检查。

## 4. 低成本预览

- 对全部页面执行结构检查和 `render`，默认消费工具返回的结构化 `diagnostic` 与 `report_ref`。
- 诊断是定位索引，不是源码。发现问题后，依据 `diagnostic.issues[*].source_path` 读取全部受影响源码，不能只处理第一项。
- 原始报告只有在结构化诊断不足时才通过 `read_report` 按页面、错误码或元素 ID 回读；不要无条件把完整报告带入上下文。

退出条件：Agent 已掌握全部当前问题及其对应源码，或预览问题已经清零。

## 5. 批量修复

- 按错误类型和共同根因分组；同类多页问题优先在一次 `edit_sources` 中原子提交。
- 修改前记录当前 revision 和 `diagnostic.fingerprint`，并先读取相关源码。不得只根据错误摘要盲目修改。
- 每次重新检查前，明确说明修改了什么，以及为什么预计会改变对应诊断。
- 不得为局部页面问题重新生成整套 PPT。

退出条件：修改已提交到新 revision，所有受影响源码均被处理或有明确排除理由。

## 6. 严格编译

- 预览结构问题清零后执行 `compile(editable="strict")`，确认 forbiddenRasterFallbacks 为 0。
- `diagnostic.status=resolved` 表示上一轮问题已经清零，可以进入验证。
- `diagnostic.status=changed` 表示问题集合已经变化，应处理新问题或剩余问题。
- `diagnostic.status=unchanged` 表示上轮修改没有改变问题；必须重新读取源码和必要的原始证据、重新判断根因，不得立即重复同一种修改。
- 编译成功后再次确认实际页数、原生对象和栅格降级情况。

退出条件：当前 revision 的 strict compile 成功且页数契约成立。

## 7. 验证与交付

- `validate` 执行 LibreOffice、PNG、montage、字体和空页检查；失败时返回对应源码继续修复。
- 只有当前 revision 的 strict compile 和 validate 均通过后才能 `finalize`。
- 只有 `finalize` 成功后才能 `present_artifact`。
- 最终回复说明实际页数、验证结果、产物和仍存在的限制。

退出条件：源码 revision、编译产物和验证结果一致，质量门通过。

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
