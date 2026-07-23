# 可编辑 PPT 诊断上下文与工作流设计

## 背景

当前 `manage_editable_ppt` 已支持源码项目、增量编辑、渲染、严格编译、验证和交付，但一次真实的 10 页材料汇报测试暴露出反馈闭环问题：完整 render/compile 结果直接进入会话历史，单次渲染结果可达到约 8 万字符；Agent 虽然收到编译错误，却无法稳定提取全部受影响页面、判断修改是否改变问题，并反复执行 `edit_sources → compile`。

本设计首先解决“让 Agent 获得准确、完整、可执行的反馈”。第一期只修改 PPT 工具和 PPT 工作流，不修改通用 Agent runtime，不以删除诊断信息换取短上下文，也不依靠强制终止掩盖错误判断。

## 目标

1. 完整保留 PPT 工具产生的原始报告。
2. 默认只把无损的结构化诊断送入 Agent 上下文。
3. 让 Agent 能由诊断直接定位原始报告、页面源码和元素。
4. 让 Agent 比较前后诊断，区分问题消失、变化和未变化。
5. 用明确的 PPT 阶段协议指导材料理解、规划、生成、修复、验证和交付。
6. 保持 Agent 的自由编辑和复杂 PPT 生成上限。

## 非目标

- 不建设通用 Agent 上下文压缩框架。
- 不动态缩减全局工具集合。
- 不设置强制中止或固定重试上限。
- 不把 PPT 工作流改造成不可绕过的通用状态机。
- 不支持任意既有 PPTX 的反向导入。

## 设计原则

- **信息不丢失**：原始结果完整落盘；结构化返回不得遗漏可执行问题。
- **分层反馈**：模型默认消费诊断信封，需要证据时按报告、页面或元素精确回读。
- **先读后改**：诊断用于定位，源码才是修改依据；Agent 修改前必须读取相关源码。
- **批量收敛**：一次诊断中的同类多页问题应整体分析并尽量一次修复。
- **工具辅助判断**：工具提供事实、定位、指纹和建议阶段，不替 Agent 自动修改源码。
- **护栏后置**：先提高反馈质量和行为指导，再考虑强制执行控制。

## 工具层架构

第一期仅在 `manage_editable_ppt` 内加入 PPT 专用报告持久化和诊断提炼层：

```text
Node compiler / validator 原始结果
             │
             ├── 完整写入 .editable-ppt/reports/*.json
             │
             └── PptDiagnosticBuilder
                    ├── 提取全部问题
                    ├── 归一化定位与源码引用
                    ├── 计算稳定指纹
                    ├── 比较前次诊断
                    └── 返回诊断信封给 Agent
```

原始编译器与验证器协议不需要改变。`manage_editable_ppt` 在取得原始结果后负责保存、提炼和返回。现有 `last_compile.json`、`last_validation.json` 可以继续作为最新结果索引，版本化原始报告进入 `reports/`。

### 报告存储

建议目录：

```text
.editable-ppt/
├── reports/
│   ├── render-rev-2-<hash>.json
│   ├── compile-rev-3-<hash>.json
│   └── validate-rev-3-<hash>.json
├── last_render.json
├── last_compile.json
├── last_validation.json
└── last_diagnostic.json
```

`report_ref` 使用相对项目目录的受控路径。工具解析引用时必须确认目标仍位于当前 PPT 项目的 `.editable-ppt/reports/` 中，防止任意文件读取。

### 诊断信封

`render`、`compile`、`validate` 和必要的 `inspect` 返回统一结构：

```json
{
  "success": false,
  "summary": "4 页存在原生图表越界",
  "data": {
    "project_dir": "/absolute/project/path",
    "revision": 21,
    "dirty_slides": ["slide-003", "slide-004", "slide-005", "slide-007"],
    "diagnostic": {
      "fingerprint": "sha256:...",
      "status": "changed",
      "issue_count": 4,
      "groups": [
        {
          "code": "ELEMENT_OVERFLOW",
          "count": 4,
          "pages": [3, 4, 5, 7],
          "likely_cause": "嵌套绝对定位造成坐标重复偏移"
        }
      ],
      "issues": [
        {
          "page": 3,
          "slide_id": "slide-003",
          "element_id": "pollutant-bar-chart",
          "code": "ELEMENT_OVERFLOW",
          "message": "元素超出 1440×810 画布",
          "source_path": "slides/slide-003.js",
          "measured_box": {"x": 200, "y": 280, "width": 1240, "height": 600},
          "expected_bounds": {"width": 1440, "height": 810},
          "evidence_ref": {"report_ref": ".editable-ppt/reports/compile-rev-21-<hash>.json"}
        }
      ]
    },
    "report_ref": ".editable-ppt/reports/compile-rev-21-<hash>.json",
    "recommended_action": {
      "action": "read_sources",
      "source_paths": [
        "slides/slide-003.js",
        "slides/slide-004.js",
        "slides/slide-005.js",
        "slides/slide-007.js"
      ]
    },
    "suggested_stage": "compile_fixing"
  }
}
```

诊断必须包含所有可执行问题。`groups` 只用于帮助 Agent 归纳，不替代 `issues`。体积较大的非诊断数据，如截图清单、DOM 测量树、缓存明细和重复元数据，只保留在原始报告中。

### 问题归一化

每项问题尽量包含：

- `code`、`message`、`severity`
- `page`、`slide_id`
- `element_id` 或其他稳定定位信息
- `source_path`
- `measured_box`、`expected_bounds` 等必要证据
- `likely_cause`（只有规则可以可靠判断时才提供）
- `evidence_ref`

当底层报告缺少元素 ID 时，诊断仍应保留原始页面、错误路径和消息，不能为了满足固定 Schema 丢弃问题。无法确定的字段使用 `null`，不得猜测。

`source_path` 根据 deck 页序和稳定 slide ID 推导；如果无法可靠映射，返回候选路径或项目级文件，并在诊断中标明定位置信度。

### 稳定诊断指纹

指纹仅由问题语义身份构成，例如：

```text
operation + revision-independent code + slide_id + element_id + normalized location/property
```

不应纳入时间戳、报告路径、自然语言顺序、运行耗时等易变字段。问题排序后再计算 SHA-256，确保同一问题集合得到相同指纹。

工具将当前指纹与 `last_diagnostic.json` 比较，返回：

- `new`：没有可比较的历史诊断。
- `changed`：问题集合发生变化。
- `unchanged`：问题集合与上一轮相同。
- `resolved`：上一轮有问题，本轮已清零。

`unchanged` 只提供事实和行动建议，不在第一期强制阻止下一次编译。

### 原始报告回读

给 `manage_editable_ppt` 增加 `read_report` 操作，参数支持：

- `project_dir`
- `report_ref`
- 可选 `pages`
- 可选 `codes`
- 可选 `element_ids`

无筛选条件时可以返回完整报告，但工作流要求优先按诊断定位精确读取。筛选结果必须保留匹配项的完整原始内容和报告元信息；工具不得二次总结成另一个有损摘要。

源码继续通过 `read_source` 或 `read_file` 读取，通过 `edit_source`、`edit_sources` 或直接文档编辑修改。`read_report` 不承担源码读取和修改。

## PPT 标准工作流

PPT 参考文档由原则说明升级为阶段协议。每阶段定义进入条件、允许动作和退出条件，但仍允许 Agent 根据任务复杂度调整批次。

### 1. 材料理解

- 读取用户材料并形成结构化摘要，包括受众、目标、核心结论、事实数据和视觉约束。
- 后续优先使用摘要，不重复读取原始材料；需要核对原文时按需回读。
- 材料不足但不影响方向时允许显式假设，不得虚构事实与数据。

退出条件：已形成足以规划页面的 brief，所有关键数字可追溯到用户材料或工具结果。

### 2. 大纲规划

- 先生成精确页数的大纲。
- 每页至少包含页面目的、核心结论、内容来源和建议版式。
- 检查用户页数要求、章节闭环、目录与正文对应关系。

退出条件：计划页数与用户要求完全一致；不一致时不得进入源码生成。

### 3. 初稿生成

- 创建源码项目后，优先一次批量生成主题、deck 和全部页面源码。
- 简单、约束清晰的任务直接完成全稿；只有视觉方向高度不确定时才先做锚点页。
- 生成后 `inspect`，确认页面数、文件数、资源引用和 revision。

退出条件：源码项目结构完整，实际页面数通过检查。

### 4. 低成本预览

- 对全部页面执行结构检查和预览。
- 默认消费诊断信封，不把完整渲染结果带入历史。
- 存在问题时，根据 `source_paths` 一次读取全部受影响源码；只有诊断证据不足时才读取原始报告片段。

退出条件：Agent 已掌握所有当前问题及其对应源码，或预览问题已经清零。

### 5. 批量修复

- 按错误类型、共同根因和页面分组。
- 同类多页问题尽量在一次 `edit_sources` 中原子修复。
- 修改前记录当前 revision 和诊断指纹。
- 不允许在未读取相关源码的情况下盲目修改。
- 每次重新检查前，Agent 应能说明修改内容及其预计改变的诊断项。

退出条件：修改已提交到新 revision，且受影响源码均被覆盖或明确排除。

### 6. 严格编译

- 预览的结构问题清零后执行 strict compile。
- 编译失败时，先读取诊断对应源码；必要时按 `report_ref` 读取原始证据。
- 比较新旧诊断：
  - `resolved`：进入验证。
  - `changed`：处理新问题或剩余问题。
  - `unchanged`：上次修改没有改变问题，必须重新读取源码和证据、重新判断根因，不得立即重复同一种修改。
- 编译成功后确认实际页数、`forbiddenRasterFallbacks` 和原生对象情况。

退出条件：当前 revision 的 strict compile 成功。

### 7. 验证与交付

- 执行 PPTX 结构验证和视觉检查。
- 验证通过后才能 finalize。
- finalize 成功后才能 present。
- 最终回复报告实际页数、验证结果、交付产物和仍存在的限制。

退出条件：当前 revision、编译产物与验证结果一致，质量门通过。

## 行为约束

- 诊断是定位索引，不是源码；修改前必须读取相关 `source_path`。
- 一次诊断涉及多个页面时，必须整体分析，不得默认只处理第一项。
- 工具返回 `success=true` 不等于视觉质量自动合格。
- 不得交付失败的 PPTX、旧 revision 或未验证文件。
- 不得为单页问题重新生成整套 PPT。
- 原始报告只有在结构化诊断不足时才进入上下文，并优先筛选读取。

## 轻量执行提示

第一期只提供非强制提示：

1. 相同指纹再次出现时返回 `diagnostic.status=unchanged`，提示重新读取源码和证据。
2. 工具根据项目事实返回建议阶段：`outline_missing`、`source_draft`、`preview_fixing`、`compile_fixing`、`validating`、`ready_to_finalize`、`finalized`。
3. 日志记录原始报告字符数、诊断信封字符数、问题数和指纹状态，以评估上下文收益。

工具不自动修改源码，不因 `unchanged` 强制结束运行，也不在第一期改变 Agent 的工具集合。

## 错误处理

- 原始报告写入失败时，工具不得只返回摘要并声称报告可回读；应返回明确的 `REPORT_PERSIST_FAILED`。
- 诊断提取遇到未知问题结构时，必须保留原始问题节点并生成通用诊断项，不能静默忽略。
- `read_report` 的引用越界、报告不存在或筛选参数非法时返回明确错误，不泄露项目外文件。
- 无法映射源码时，诊断返回项目级候选和原始证据引用，由 Agent读取 deck 或报告继续定位。
- 指纹比较状态损坏时不影响本轮诊断返回，状态降级为 `new` 并记录日志。

## 测试策略

### 单元测试

- render、compile、validate 的代表性报告能提取全部问题。
- 未知问题结构不会被丢弃。
- 问题顺序变化不改变指纹；语义问题变化会改变指纹。
- `new`、`changed`、`unchanged`、`resolved` 状态转换正确。
- `source_path` 能按 deck 页序和 slide ID 正确映射。
- `report_ref` 路径约束阻止目录穿越。
- `read_report` 能按页面、错误码和元素 ID 精确回读。
- 原始报告持久化失败时正确失败。

### 集成测试

- 构造多页同类越界，首次 compile 返回全部问题和全部源码引用。
- 只修改一部分页面后，诊断准确反映剩余问题。
- 无效修改后返回 `unchanged`。
- 批量修复后返回 `resolved` 并通过 strict compile。
- validate/finalize 仍遵守当前 revision 和交付门禁。

### 端到端验收

使用本次“根据上传材料制作 10 页汇报 PPT”的同类输入重新测试：

- 最终实际页数必须为 10。
- Agent 根据诊断读取对应源码后再修改。
- 多页同类错误在一轮批量修复中处理。
- render/compile 默认返回诊断信封而非完整大型结果。
- 原始报告可通过 `report_ref` 无损读取。
- 相同诊断再次出现时，Agent 不再立即重复同一种修改。
- strict compile、validate 和 finalize 全部通过后才交付。

诊断信封通常应低于 10 KB，但这是观测目标，不是允许丢弃问题的硬上限；问题数量较多时可以超过该值。

## 实施顺序

1. 新增原始报告持久化、诊断数据模型和提取器。
2. 接入 render、compile、validate，并保留现有交付校验所需完整报告。
3. 增加稳定指纹、历史比较与诊断日志。
4. 增加受控 `read_report` 操作。
5. 更新 PPT prompt 和 workflow 阶段协议。
6. 完成单元、集成和端到端回归测试。

## 成功标准

第一期成功不以“上下文越短越好”为唯一标准，而以以下结果为准：

- Agent 收到的诊断准确且没有遗漏可执行问题。
- 完整证据始终可回读。
- Agent 能从诊断稳定定位源码并采取正确的下一步动作。
- 同一问题的变化状态可被可靠判断。
- 大型 render/compile 原始结果不再在每轮上下文中重复累积。
- 不降低自由源码编辑、复杂布局和多轮完善能力。
