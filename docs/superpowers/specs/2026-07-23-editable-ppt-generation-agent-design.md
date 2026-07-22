# 可编辑 PPT 生成 Agent 设计

## 背景

当前项目的正式 PPT 生成路径以 `create_pptx_with_ppt_master` 为核心。Agent 规划页面和基础形状后，由 `python-pptx` 生成 16:9 PPTX，再通过现有验证、渲染、预览和 Patch 流程修复。该路径稳定且适合兼容既有能力，但公开工具 Schema 与底层渲染能力都偏基础，主要覆盖文本、图片、表格和矩形卡片，难以支撑原生图表、复杂图示、自由布局和高质量长文稿。

本设计新增独立的高质量 PPT 生成 Agent 场景。它面向从零生成 5～50 页的政企汇报、商务方案和数据分析演示文稿，强调视觉质量、稳定性与原生可编辑性之间的平衡。现有 PPT 工具继续保留，不在本项目中被替换。

## 开源方案调研与结论

调研确认没有单个成熟开源项目能够原样满足“HTML 自由布局、高视觉还原、原生图表/表格、严格可编辑、Agent 多轮完善”全部要求。因此采用组合式复用，而不是完整照搬某个产品。

- [Presenton](https://github.com/presenton/presenton) 提供 Apache 2.0 的完整 AI 演示文稿产品、HTML/Tailwind 模板、主题、编辑器和 Puppeteer DOM 抓取流程，适合借鉴 Agent 产品与模板架构。其当前 PPTX 模型主要覆盖文本框、基础形状、连接线和图片，SVG 会转为 PNG，不能直接满足原生图表和原生表格要求。
- [dom-to-pptx](https://github.com/atharva9167j/dom-to-pptx) 采用 Puppeteer、DOM computed style 和 PptxGenJS，将常规 HTML 元素转换为可编辑 PPT 对象，是最接近所需 DOM 编译器的 MIT 项目。它仍较新，复杂 CSS 可能栅格化，且没有完整的原生 PowerPoint Chart 路径，因此只能通过隔离适配层使用，并固定版本或维护受控 fork。
- [PptxGenJS](https://github.com/gitbrent/PptxGenJS) 是最终 PPTX 引擎，负责原生文本、形状、连接线、表格、图表和母版。其官方 HTML 转换仅覆盖表格，不承担整页 HTML 编译。
- [PPTAgent / DeepPresenter](https://github.com/icip-cas/PPTAgent) 的两阶段规划、参考页分析、环境反馈和 Content/Design/Coherence 评价方法适合作为 Agent 工作流参考，不整体引入其 Docker、模型和沙箱运行时。
- [pptx-automizer](https://github.com/singerla/pptx-automizer) 适合二期导入和修改用户已有 PPTX，不作为一期从零生成的核心依赖。

最终技术决策为：Presenton 架构思想、受控的 dom-to-pptx 适配层、PptxGenJS 原生语义扩展、PPTAgent 规划与评价思想，以及 Suyuan 现有文件、预览、验证和交付管线的组合。

## 目标

1. 新增独立的 `PPTGenerationAgent`，专门从零生成 5～50 页 PPT。
2. 同时支持模板布局、自由 HTML/Tailwind 布局和二者混合。
3. 文本、形状、连接线、表格、图表和语义图示尽可能生成 PowerPoint 原生对象。
4. 使用同一份源项目驱动 HTML 预览和 PPTX 交付，防止两套内容漂移。
5. 支持 Agent 直接编辑项目文档并多轮完善，无需重新规划或重新生成整套 PPT。
6. 支持局部预览、局部校验、缓存复用、版本回退和最终确定性重新打包。
7. 将可编辑性、转换降级和视觉一致性变成可检查的工程指标。
8. 复用当前项目的会话资源、产物管理、PPTX 验证、LibreOffice 渲染、截图和蒙太奇能力。

## 非目标

- 一期不编辑用户上传的任意已有 PPTX。
- 一期不建设常驻 Node 微服务；Node 导出器通过 CLI/受控子进程接入 Python 后端。
- 一期不建立页面类型与十种风格的笛卡尔积模板矩阵。
- 一期不追求完整实现所有 CSS；只支持明确定义并经过验证的 CSS 子集。
- 一期不把复杂动画、视频和 PowerPoint 高级交互作为核心验收项。
- 不移除或重写现有 `create_pptx_with_ppt_master` 路径。

## 总体架构

```text
用户需求与资料
    ↓
PPTGenerationAgent（Python，接入现有 Agent Runtime）
    ↓
BriefNormalizer → DeckPlanner → DesignDirector → SlideComposer
    ↓
可持续编辑的 PPT 源项目（Deck IR / SlideSpec）
    ↓
HTML Preview Runtime（Vite + Tailwind）
    ↓
DOM Measurement（Puppeteer）
    ↓
Hybrid PPTX Compiler（Node.js）
    ├── 常规 DOM → dom-to-pptx 适配层
    ├── Chart/Table/Diagram → PptxGenJS 原生对象
    └── 少量必要属性 → 受控 OOXML 后处理
    ↓
Suyuan QA 与产物管线
    ├── validate
    ├── LibreOffice render
    ├── screenshot/montage
    ├── HTML-PPTX visual comparison
    └── Agent repair loop
```

`PPTGenerationAgent` 与编译器之间只通过版本化的源项目格式和结构化报告通信。业务 Agent 不依赖 dom-to-pptx 或 PptxGenJS 的内部实现，后续可以替换编译器而不改变上层工作流。

## 一期范围与兼容策略

新 Agent 只处理从零生成。当前 Python PPT 工具继续作为兼容路径和必要时的显式降级路径，但不是新 Agent 的主渲染器。现有 PPTX 验证、预览、版本和产物能力优先通过适配接入，不复制第二套文件交付系统。

默认页面尺寸为 16:9。Web 画布固定为 1440×810，编译器统一转换为 PowerPoint 坐标。5～10 页可以一次规划后分批生成；10～20 页和 20～50 页均使用 checkpoint 与每批 3～5 页的生成策略。

## Agent 组件

### BriefNormalizer

将用户需求、上传资料和数据转为结构化任务，至少包含受众、场景、汇报目标、页数范围、必含内容、语言、品牌约束、数据来源和允许的素材策略。

### DeckPlanner

生成完整叙事规划，包括章节结构、每页目的、页面标题、页型、内容密度、数据需求、页面依赖和素材需求。全局规划完成后才进入页面绘制，避免长文稿局部漂亮但整体失序。

### DesignDirector

选择或生成主题、字体、颜色、栅格、留白、组件风格和视觉节奏。它先产出封面、标准内容页和数据分析页三个视觉锚点，确认全局设计语言后再扩展到其余页面。

### SlideComposer

将 Deck Plan 分批转换为 `SlideSpec`，可以选择模板、自由布局或混合布局。SlideComposer 可直接编辑源项目文件，也可以通过强类型工具执行简单操作。

### AssetManager

统一处理用户图片、检索图片、图标、SVG、数据文件和生成图片，记录来源、尺寸、哈希、版权说明和引用页面。编译器只消费已登记素材，不在导出阶段临时访问不受控网络资源。

### DeckCritic

从内容准确性、视觉质量、页面内布局和全篇连贯性四个维度检查。它消费预览、编译报告、验证报告和全篇蒙太奇，输出带页面和元素定位的修复建议。

## Agent 工具边界

建议向 Agent 提供以下高层工具：

- `create_deck_project`
- `read_deck_source`
- `edit_deck_source`
- `set_deck_theme`
- `upsert_slide_spec`
- `render_slide_preview`
- `compile_deck`
- `validate_deck`
- `patch_slide_spec`
- `restore_deck_revision`
- `finalize_deck`

直接文档编辑是复杂绘制和重构的主要能力；Patch 是修改标题、数据、坐标、颜色和顺序等常规操作的快捷接口，不是能力边界。所有写操作仅允许作用于当前会话的 PPT 项目目录，并在落盘前执行路径、Schema 和引用校验。

## 生成流程

```text
结构化需求
  → 完整 Deck Plan
  → 三个视觉锚点页
  → 预览和设计校验
  → 每批生成 3～5 页
  → 每批预览、编译、校验和修复
  → 全篇一致性检查
  → 最终编译与交付
```

每个阶段保存 checkpoint。单个元素或页面连续自动修复三次仍未通过时，SlideComposer 必须切换到更简单的原生布局，并记录降级原因，不得无限重试。

## PPT 源项目

每份演示文稿是一个可持续编辑的源项目：

```text
presentation-project/
├── deck.json
├── theme.json
├── slides/
│   ├── slide-001.js
│   ├── slide-002.js
│   └── slide-003.js
├── templates/
├── assets/
├── snapshots/
└── output/
    ├── presentation.pptx
    ├── compile-report.json
    └── validation-report.json
```

`deck.json` 保存元信息、汇报目标、章节、页面顺序、主题引用、素材清单、可编辑策略、Schema 版本及生成记录。`theme.json` 是唯一主题数据源，由预览器映射为 CSS 变量，由导出器直接读取颜色、字体、字号、间距和线条 Token。

每个 `slide-N.js` 注册一个 `SlideSpec`，而不是仅注册 HTML 字符串。例如：

```javascript
window.slideDataMap.set(3, {
  schemaVersion: "1.0",
  id: "market-growth",
  type: "data-analysis",
  intent: "说明近三年业务增长趋势",
  layoutMode: "template",
  templateId: "kpi-chart-right",
  html: `<section>...</section>`,
  nativeElements: [
    {
      id: "revenue-chart",
      kind: "chart",
      chartType: "column",
      data: {
        categories: ["2024", "2025", "2026"],
        series: [{ name: "收入", values: [80, 105, 132] }]
      }
    }
  ],
  speakerNotes: []
});
```

HTML 中通过 `data-pptx-ref` 占位节点确定原生元素的位置。Web 预览器和 PPTX 编译器消费同一份语义数据，避免从 Canvas 或 SVG 外观反推图表数据。

## Preview Runtime 与执行边界

预览运行时是受版本管理的框架依赖，不复制到每页供 Agent 任意修改。它负责自动发现和加载 `slides/`、把 `theme.json` 映射为 CSS 变量、渲染语义组件、处理键盘翻页、支持 `?page=N` 深链接，以及向截图和编译流程暴露页面就绪状态。

Agent 只编辑源项目中的 Deck、Slide、主题、模板、组件和素材，不修改控制器、路由器、编译入口或安全策略。直接编辑 `slide-N.js` 仍必须符合声明式 `SlideSpec` 契约；禁止页面代码访问 Node 文件系统、启动子进程、动态加载远程脚本或绕过素材登记。预览进程使用受限网络策略、加载超时和页面级执行超时，避免一页错误阻塞整套文稿。

生产编译只接受通过 Schema 校验和静态安全检查的源项目。允许自由布局不等于允许任意运行时权限。

## 模板与主题

布局模板与视觉主题解耦：

```text
templates/layouts/
  cover/
  agenda/
  transition/
  content/
  data/
  ending/

themes/
  government/
  business/
  data-analysis/
```

一期建设三套高质量主题和约 15～20 个基础布局。页面支持三种模式：

- `template`：采用模板骨架。
- `freeform`：由 Agent 完全自由编写 HTML/Tailwind。
- `hybrid`：基于模板增删或重排组件。

三种模式都输出相同的 `SlideSpec`，因此共用编译、验证和修复流程。后续增加主题不复制布局文件，增加布局也不复制全部视觉风格。

## Hybrid PPTX Compiler

编译器采用以下确定性流水线：

1. 校验 Deck IR、SlideSpec、主题、素材和语义引用。
2. 启动 Puppeteer，固定 viewport，并等待字体、图片和组件就绪。
3. 获取 DOM computed style、坐标、层级、文本测量和 `data-pptx-ref` 边界。
4. 对元素分类，优先匹配语义原生元素，再处理常规 DOM。
5. 将像素坐标统一转换为 PowerPoint 坐标。
6. 使用 PptxGenJS 生成 PPTX，并在确有必要时执行受控 OOXML 后处理。
7. 生成编译报告并进入 PPTX 结构验证。

转换规则如下：

| 页面元素 | PPTX 输出 |
| --- | --- |
| 文本、富文本、列表 | 原生文本框 |
| 背景、卡片、分割线 | 原生 Shape |
| 流程线、箭头 | 原生 Connector |
| HTML 表格语义组件 | 原生 Table |
| Chart 语义组件 | 原生 Chart，保留数据工作簿 |
| 流程图、时间轴、组织图 | 原生 Shape 与 Connector 组合 |
| 照片、生成图片 | Picture |
| SVG 图标 | 保留 SVG 矢量；简单图标可在后续扩展为原生形状 |
| CSS 模糊、复杂滤镜、伪元素 | 严格模式报错 |

dom-to-pptx 通过内部 Adapter 处理文本、基础形状、图片和经过批准的 CSS 子集。Chart、Table、Connector 和 Diagram Adapter 由项目直接基于 PptxGenJS 实现，不依赖 dom-to-pptx 对这些对象的支持程度。

开源依赖必须固定版本并保留许可证与 NOTICE 信息。dom-to-pptx Adapter 要有独立契约测试和禁用开关；升级其版本时必须重新运行 Golden slide 与 PowerPoint 打开测试，不能自动跟随最新版。

## 可编辑性策略

一期默认 `editable=strict`。允许使用位图的对象只包括用户原始照片、检索图片、AI 生成图片和本身为位图的品牌素材。禁止静默栅格化文本、表格、图表、流程图、数据卡片、CSS 装饰块、整页或局部页面截图。

无法转换的元素返回结构化错误，至少包含错误码、页面 ID、元素 ID、属性和修复建议。例如：

```json
{
  "code": "UNSUPPORTED_CSS_FILTER",
  "slideId": "slide-08",
  "elementId": "risk-card",
  "property": "backdrop-filter",
  "suggestion": "replace-with-solid-or-gradient-fill"
}
```

只有用户明确启用 `allow_visual_fallback` 时，才允许将非核心装饰栅格化。即使允许降级，编译报告也必须记录对象、原因和结果，不能以“fully editable”描述该产物。

`compile-report.json` 至少记录各类原生对象数量、位图来源、SVG 数量、不支持样式、字体替换、溢出、裁剪、修复历史和可编辑性等级。

## 源文档优先的多轮编辑

Agent 可以像编辑一个 HTML/JS 项目一样多次直接编辑 `deck.json`、`theme.json`、`slide-N.js`、模板、组件和素材文件。复杂页面重构、自由布局和特殊视觉实现使用直接文档编辑；简单精确修改可以使用结构化 Patch。

Deck、Slide 和 Element 均使用稳定 ID。系统保存文件内容哈希、依赖图、revision、变更记录、修改前后快照和验证结果。文件变化触发脏数据传播：

- 修改单个 `slide-N.js` 只重新渲染、测量和校验该页。
- 修改素材只使引用该素材的页面失效。
- 修改主题 Token 只使使用相关 Token 的页面失效。
- 修改全局字体或页面尺寸时使所有相关页面失效。

未修改页面复用 DOM 测量、素材缓存、编译中间模型、预览图片和验证结果。最终生成 PPTX 时可以重新写完整 ZIP 包，但该过程只是确定性重新打包：不重新调用模型、不重新规划大纲、不重新生成文案、不重新选图，也不改变未修改页面的源数据。

一期不以直接编辑任意外部 PPTX 的 XML 作为绘制主路径。对于 PptxGenJS 无法表达且有明确测试覆盖的少量属性，可以使用受控 OOXML 后处理。二期再结合 pptx-automizer 或专用 OOXML Patch 支持用户上传 PPTX 的直接修改。

## 并发、版本与回退

直接文件编辑和结构化 Patch 都必须携带或校验当前 revision。基于旧 revision 的修改返回冲突，不覆盖较新的内容。每个成功编辑批次创建 checkpoint，支持撤销、重做和恢复指定版本。

恢复操作只恢复当前 PPT 项目中的源文件和派生状态，不影响会话其他资源。派生输出可以删除后重新生成，源文件和已登记素材不能在没有 checkpoint 的情况下被破坏性覆盖。

## 错误处理与降级

错误按责任归类：

- 内容错误交给 DeckPlanner 或 SlideComposer。
- 页面布局错误交给 SlideComposer。
- 主题与全篇一致性错误交给 DesignDirector。
- DOM/PPTX 转换错误交给对应 Compiler Adapter。
- 素材错误交给 AssetManager。
- 运行时和产物错误交给现有 Suyuan 工具层。

每个错误必须带页面和元素定位，能够被 Agent 转换为局部编辑。单页自动修复最多三轮；仍不通过时切换到更简单的原生布局，并在最终报告中保留降级说明。严格模式下无法生成合规结果时任务失败，不交付伪成功 PPTX。

## 质量校验

### SlideSpec 静态校验

检查 Schema、元素引用、素材路径、字体、图表数据、页面顺序、主题 Token、稳定 ID 和版本兼容性。静态校验失败时不启动浏览器。

### HTML 运行时校验

在 1440×810 固定画布检查内容溢出、安全区、文本截断、图片加载、异常重叠、遮挡、最小字号、对比度及 `data-pptx-ref` 缺失或重复。

### PPTX 结构校验

复用并扩展现有验证能力，检查 PPTX/OOXML 能正常解包、PowerPoint 不提示修复、页数和对象数量与源项目一致、图表包含数据工作簿、关系文件完整、没有被禁止的截图回退，并记录字体替换。

### 视觉一致性校验

将 HTML 预览与 LibreOffice 渲染的 PPTX 页面逐页比较。关键元素几何误差目标不超过约 4px；标题、正文、图表和表格不得缺失；明显换行差异、遮挡和布局漂移必须修复。像素差异作为告警指标，由 DeckCritic 结合元素级结果判断，不因字体渲染器的微小抗锯齿差异直接失败。

### 全篇质量校验

通过蒙太奇检查章节节奏、页面密度、主题一致性、重复布局、标题层级和视觉单调问题。全篇检查只能提出局部源文档修改，不得触发未授权的整套重新生成。

## 测试策略

1. 单元测试覆盖每种 SlideSpec、主题 Token、DOM 属性和 PptxGenJS 对象映射。
2. Schema/Adapter 契约测试确保 Python Agent、Node 编译器和报告格式兼容。
3. Golden slide 测试覆盖中文富文本、卡片、表格、原生图表、流程图、时间轴、图片裁剪、阴影和渐变。
4. 端到端测试从源项目生成 HTML、PPTX、截图、蒙太奇和报告。
5. 增量编辑测试证明修改单页不会重新测量未依赖页面，主题和素材变更按依赖图传播。
6. 回归测试验证同一输入重复编译的页面结构一致，并检测 PowerPoint 修复提示和 OOXML 损坏。
7. 20 页与 50 页压力测试覆盖浏览器生命周期、内存、缓存和超时。
8. 在 Microsoft PowerPoint 与 LibreOffice 中人工抽查原生表格单元格、图表“编辑数据”和图示对象的可选择性。

## 一期验收标准

一期使用 10 页代表性测试集，覆盖封面、目录、政企内容页、KPI、原生表格、柱线组合图、流程图、时间轴、图片页和结尾页，并追加 20 页与 50 页压力测试。

必须满足：

- PPTX 打开无修复提示。
- 文本、表格、图表和语义图示原生可编辑。
- 严格模式下被禁止的栅格回退数量为零。
- 不存在溢出、缺图、空页和关键重叠。
- 中文字体和换行在目标环境稳定。
- 同一输入重复编译的页面结构一致。
- 直接修改单页后只重做必要的预览、测量和校验，未修改内容不重新生成。
- 目标服务器预热后，10 页纯编译目标不超过约 30 秒，50 页不超过约 120 秒；性能测试不包含模型生成、图片检索和外部网络耗时。
- 最终交付 PPTX、HTML 预览、蒙太奇、完整源项目、编译报告和验证报告。

## 实施切片

实施按可独立验证的切片推进：

1. 先完成 10 页技术验证集，对受控 dom-to-pptx 适配层、中文字体、原生图表/表格和 PowerPoint 修复风险做选型验证。
2. 建立 Deck IR、SlideSpec、主题、项目目录、直接文档编辑和增量依赖机制。
3. 建立 HTML Preview Runtime、常规 DOM Adapter 与原生语义 Adapter。
4. 接入现有 Agent Runtime、会话资源和 QA/交付管线。
5. 建设三套主题、基础布局、长文稿 checkpoint 与 DeckCritic 修复闭环。
6. 完成 20 页、50 页压力测试和一期验收。

如果第一步技术验证发现 dom-to-pptx 的常规 DOM 转换不可控，保留 Deck IR、Agent、预览和语义 Adapter 设计，将常规 DOM Adapter 替换为项目自研的受限 CSS 编译器；上层接口不变。

## 后续扩展

- 使用 pptx-automizer 或 OOXML Patch 编辑用户上传的已有 PPTX。
- 从企业母版和既有 PPT 提取主题、布局和组件。
- 将简单 SVG 图标转换为 PowerPoint 原生形状组合。
- 增加地图、桑基图、甘特图等语义组件及相应可编辑策略。
- 在一期验证稳定后扩展更多行业主题和布局，而不是预先铺设低质量模板矩阵。
