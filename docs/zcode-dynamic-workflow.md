# ZCode 动态工作流（dynamic workflow）源码导读

> 考察对象：[zai-org/ZCode](https://github.com/zai-org/ZCode) `main` 分支（v3.14.3），Agent CLI 源码位于 `apps/zcode-cli/`。本文基于源码（非压缩产物），文件引用均可直接定位。
>
> **对前一篇文档的修正**：[zcode-orchestration-architecture.md](zcode-orchestration-architecture.md) 基于 3.11.2 桌面版压缩包得出"ZCode 没有显式 DAG 引擎"。经源码核实，**该结论只对旧版本成立**——本机已验证 3.11.2 包内无任何 `CreateWorkflow`/`dynamic-workflow` 痕迹（grep 零命中），而当前源码包含一套完整的动态工作流引擎（约 2.7 万行），其依赖图不叫 "DAG" 而叫 **site graph / causality graph / actor graph**，这正是之前按 "DAG" 关键词检索漏掉它的原因。

## 一、总览：ZCode 有两套工作流系统

| | Legacy Expert Workflow | Dynamic Workflow（本文重点） |
|---|---|---|
| 代码 | `apps/zcode-cli/packages/core/src/workflow/`（约 4.7k 行） | `apps/zcode-cli/packages/dynamic-workflow` + `dynamic-workflow-runtime`（约 2.7 万行） |
| 形态 | 固定 8 阶段管线的"长任务"工作流（NL→Code） | **模型编写的 TypeScript 脚本**，任意拓扑 |
| 触发 | `/expert` 命令 | 用户显式要求 workflow → `CreateWorkflow` 工具 |
| DAG 来源 | `arch_decompose` 阶段产出"实现+验证节点的依赖图"，`exec` 阶段按图执行（`scheduled_graph`） | **编译期静态分析脚本数据流恢复依赖图** |
| 状态 | 两系统并存；SKILL.md 明确"legacy `Workflow` 工具和 `/expert` 是共享同一个词的另一个旧功能" | 当前主推 |

## 二、Dynamic Workflow 是什么

一句话：**把工作流写成一段带类型标注的 TypeScript 编排脚本，ZCode 编译它、静态分析出依赖图给用户确认，然后在沙箱子进程里确定性执行，产物与中间结果全程可重放、可修订、可缓存复用。**

```ts
// 脚本示例（节选自官方 SKILL.md）：评审改动文件，每个发现独立确认
phase("逐个评审改动的文件并确认发现");
const confirmed = (
  await Promise.all(
    paths.map(async (p) => {
      const review = await agent(`reviewer-${p}`).ask<Review>(`Review ${p}`);
      return Promise.all(
        review.findings.map((f, i) =>
          agent(`confirmer-${p}-${i}`).ask<Confirmation>(`Reproduce: ${JSON.stringify(f)}`),
        ),
      );
    }),
  )
).flat();
```

四件套工具：`CreateWorkflow`（编译 + 用户确认 + 后台启动）、`AmendWorkflow`（修订运行中/已结束的 run，缓存导入）、`SaveWorkflow`（存为项目可复用工作流，带参数声明）、`EvalWorkflowSnippet`（同步试跑脚本片段，不落盘）。四个工具都拒绝在未加载 `dynamic-workflows` 技能的情况下执行——该技能（`bundled-skills/skills/dynamic-workflows/SKILL.md`，约 1500 行）是完整的编写契约。

## 三、DAG 从哪来：静态分析引擎

这是该设计最核心的决策：**拓扑不写成数据，而是从普通代码的数据流里恢复**。SKILL.md 原话："The harness recovers the dependency graph by reading your code before it runs."

`packages/dynamic-workflow/src/analysis/`（约 1.24 万行）实现了对脚本 TS AST 的抽象解释：

- **site graph**（规范图）：每个 `ask`/`world.run`/世界读是一个"站点"，journal、执行序号、运行期标记全部以站点为键；
- **causality graph**：因果图带三条车道（`WORKSPACE_LANE` 工作区写入、`UNKNOWN_LANE`、`SINK_ID`），节点带 `Certainty`，边是顺序边（order edges），并打上 `Phase/Region/Step` 三层坐标——phase 是用户看到的阶段（脚本里 `phase("...")` 标记声明），loop 回边让循环体聚成一个节点；
- **actor graph**：呈现级投影——**actor 为节点、ask 消息为边**（`actor-graph.ts`），附带 fan-out 基数（`fanout-cardinality.ts`）；`mermaid.ts` 把图渲染成确认对话框里的流程图（所以用户批准的是一个 phase 图，而不是三十张步骤卡）；
- **facade-misuse**：静态拒绝误用（循环内字面重名 actor、运行期拼装 artifact id 等）。

分析器与编译器共享一套诊断（`analyze.ts`：`ok` 表示可提交，任何 diagnostic 都会挡下提交）。可分析性是编写义务："Node 结果流经普通变量、模板插值、解构和小助手函数都会被精确追踪；把结果塞进容器再捞出来，换来的是可分析性诊断。"

## 四、执行模型：确定性状态机 + 沙箱子进程

### 4.1 编译与 lowering

`compiler/compile.ts` 把脚本包进 `async function __workflowScript__()` 后用 TypeScript 真编译检查（facade 的 `dts.ts` 提供环境声明）。一个有意思的工程决策：`strict` 开但 **`noUncheckedIndexedAccess` 刻意关掉**——注释写明"模型写的 TS 都默认这个标志是关的，开着它 TS2532/TS18048 占了本地运行 96% 的 undefined 类编译失败"。禁用 `Date.now`/`Math.random`/`fetch`/`fs` 也是编译期检查——可重放性的前提。`lowering/` 把通过编译的脚本降为可执行函数体。

### 4.2 沙箱与桥接

`dynamic-workflow-runtime/harness.ts`（文件头有完整的中文时序图）：降级后的脚本写进 `<cwd>/.zcode/workflow-runs/<runId>.mjs`，**spawn 一个 node 子进程**执行；子进程内的 `__host.*` 调用经 stdio 上的 **NDJSON 线协议**桥回父进程的引擎（`create-actor` 即发即忘、`request ask/world-read/publish-artifact` 需应答、`event log/report` 单向）。该包刻意只依赖 `@zcode/dynamic-workflow` 和 node 内建，"证明整条管线 app-free 可跑"。

### 4.3 引擎：journal 决定一切的确定性状态机

`engine/engine.ts`（文件头自述）：

- **核心不做任何 I/O、不读时钟、不用随机数**。随时间变化的决策要么进 journal，要么被"站点 id × 每站点执行序号"（`ask#3@n`）+ 每 actor FIFO 的 `actorSeq` 固定——**首次执行与 replay 逐字一致**；
- 每次 host 调用先查 journal 的 `(siteId, ordinal)`：命中即短路（不产生真实调用），并防御性校验 `inputHash`，不一致整个 run 大声失败（绝不静默偏移）；
- 并发由运行时决定（脚本里的 `max_concurrency` 只是用户主动设的上限），引擎暴露 `setMaxConcurrency` 活体控制面；
- 结算三态：`completed`（脚本 return）/ `errored`（脚本自身失败，不可恢复，改脚本走 Amend）/ `stopped`（可 `ResumeWorkflowRun` 原样恢复；stop reason：user/model/interrupted/provider/superseded）。模型侧错误（限流、过载、网络）在 run 内部无上限重试，脚本永远看不见。

### 4.4 修订与缓存导入（AmendWorkflow）

任何 run（哪怕运行中）都可被修订取代：编辑 run 的脚本文件 → `AmendWorkflow` → 停旧起新，**按命名 actor 沿其 ask 序列逐条匹配导入旧 run 的已完成工作，字节一致即命中缓存（零 token）**，直到修订后第一个"活写"（子 agent 写工作区或 `world.run` 真执行）为止——此后缓存全部失效，保证 gate 命令测的是新代码真正产出。旧 run 标记 `superseded`。配套的编写纪律：可调参数放脚本控制流（改它免费），别插值进 ask 文本（改它等于缓存清零）。

## 五、脚本面（facade）速览

| 设施 | 语义 |
|---|---|
| `agent(name?, persona?)` | 创建 actor：新上下文、名字即身份（run 内唯一，重复整个 run 失败）、persona 创建时冻结；同 actor 的并发 ask 排 FIFO（共享上下文 = 串行 = 标定一致） |
| `actor.ask<T>(instructions)` | 派任务；`T` 是脚本内定义的 TS 接口，**JSDoc 字段注释合成运行时 schema 给子 agent**（`schema/synthesize.ts`），控制流要分支就必须带类型 |
| `phase("...")` | 阶段标记（编译期字面量），同名聚为一个图节点；用户确认的是 phase 图 |
| `world.run(cmd, args)` | 确定性门：机器可判定的检查跑真命令、分支在退出码上；命令名必须编译期字面量——**用户批准的是脚本的命令集** |
| `files.glob/grep/read`、`git.changedFiles` | 世界读：超限**拒绝而非截断**（不给静默残缺视图）；可 catch 降级 |
| `report(item, tag?)` | 渐进交付：**run 失败也随完成通知带出**（salvage），条目去重、重放不重复 |
| `artifact.file/markdown/chart/dashboard` | 用户可打开的产物卡；`{ primary: true }` 标记主交付物；发布即版本化 |
| escalation | 子 agent 可升级阻塞性问题（全局唯一 `dwfq-*` id），只挂起该子 agent 的该次调用；`ResolveWorkflowQuestion` 应答；单 ask 限 3 次 |
| 禁止嵌套 | 子 agent 不能调 `CreateWorkflow`；更大的活建模为更多子 agent |

SKILL.md 的方法论部分（fresh eyes、每发现一确认者、确定性门优先、barrier 只留在真正需要全员的地方）本质是把"专家级交付"的评审文化编译进编写契约，并给出了完整的反模式清单。

## 六、与 suyan 显式 DAG 工作流的对比（修订版）

两套系统哲学高度同构——**模型负责编排，引擎负责确定性**——但在三个关键选择上不同：

| 维度 | suyan `run_agent_workflow` | ZCode dynamic workflow |
|---|---|---|
| 拓扑来源 | 模型产出 JSON 节点 + `dependencies` 字段 | 模型写 TypeScript，**编译期从数据流静态恢复**（含循环、分支、fan-out 基数） |
| 控制流 | 无（图固定，重试由引擎按预算自动做） | 脚本即控制流（循环/条件/typed 分支），重试写进脚本 |
| 重放/复用 | 节点结果指纹缓存（依赖闭包完整才复用） | journal 逐站点重放 + 修订按命名 actor 导入（字节级匹配） |
| 确定性保障 | 快照/血缘/结果信封 | 编译期禁随机与时钟 + journal inputHash 防御 |
| 子 agent 通信 | 上游产物清单 + 结论摘要（复用 file_path） | typed 结果跨 schema 边界插值进下游 prompt |
| 人工介入 | 层级不明确时主 agent 先问用户 | 子 agent 运行中升级问题（只挂起该调用） |

最值得借鉴的一点：ZCode 把"依赖图"从**模型要填对的字段**变成了**编译器保证的事实**——模型只写自然的编排代码，图是分析器送的；而 suyan 的模型必须自己正确声明 `dependencies`，靠运行时校验兜底。

## 七、代码地图

| 路径（`apps/zcode-cli/packages/`） | 行数 | 职责 |
|---|---|---|
| `dynamic-workflow/src/analysis/` | 12.4k | 静态分析：site/causality/actor 三图、fanout 基数、facade 误用诊断、mermaid 渲染 |
| `dynamic-workflow/src/engine/` | 5.4k | 确定性执行引擎：journal 重放、per-actor FIFO、结算、导入缓存 |
| `dynamic-workflow/src/compiler|facade|lowering|schema` | ~2.4k | TS 编译检查、facade dts、脚本降级、JSDoc→schema 合成 |
| `dynamic-workflow-runtime/src/` | ~1.1k | 沙箱 harness：子进程编排、NDJSON 线协议、child entry 渲染 |
| `bootstrap/src/app/dynamic-workflow-*.ts` | — | run 服务、提交、journal 持久化、进度回流 |
| `core/src/workflow/`（legacy expert） | 4.7k | 8 阶段管线、依赖图种子化调度器（collections/planner/frontier） |
| `bundled-skills/skills/dynamic-workflows/` | ~1.5k+ | SKILL.md 编写契约 + patterns.md 拓扑目录 + examples.md 完整示例 |

另：`packages/desktop/src/host/index.ts` 是桌面宿主与 CLI 的接驳点；`runtime/methods/background-stop-dynamic-workflow.ts` 等是 core 运行时的暴露方法。
