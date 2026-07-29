# 智能体平台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增默认展示的智能体平台模式选择页，让用户了解并选择六种 Agent 后进入空白对话，同时移除对话区原有模式切换器。

**Architecture:** 使用统一 Agent 元数据配置驱动平台卡片与对话标题；由纯函数决定空闲模式重置或运行模式保护策略；`ReactAnalysisView` 保存非持久化的 `platform/chat` 工作区状态，`MainLayout` 继续承载左侧导航并在主区域切换平台页与现有对话工作区。

**Tech Stack:** Vue 3 Composition API、Pinia、Vite、Node.js test runner、SCSS

---

## 文件结构

- Create: `frontend/src/config/agentModes.js`：六种 Agent 的统一展示元数据与查询函数。
- Create: `frontend/src/config/agentModes.test.js`：验证模式配置的完整性和稳定顺序。
- Create: `frontend/src/components/agentPlatform/workspacePolicy.js`：判断模式是否运行以及选择模式时的动作。
- Create: `frontend/src/components/agentPlatform/workspacePolicy.test.js`：覆盖空闲、运行中及非法模式策略。
- Create: `frontend/src/components/agentPlatform/AgentPlatform.vue`：响应式模式卡片首页。
- Create: `frontend/src/components/agentPlatform/AgentWorkspaceHeader.vue`：对话页当前 Agent 标识。
- Modify: `frontend/src/components/AssistantSidebar.vue`：新增智能体平台一级入口与选中态。
- Modify: `frontend/src/components/reactAnalysis/MainLayout.vue`：在平台首页和原对话工作区之间切换。
- Modify: `frontend/src/views/ReactAnalysisView.vue`：协调默认工作区、模式选择和会话恢复。
- Modify: `frontend/src/components/InputBox.vue`：移除输入框内模式选择器。
- Modify: `frontend/src/components/queryDashboard/QueryDashboardWorkspace.vue`：移除问数大屏悬浮模式选择器。
- Modify: `frontend/package.json`：新增智能体平台 Node 测试脚本。

### Task 1: Agent 元数据与工作区策略

**Files:**
- Create: `frontend/src/config/agentModes.js`
- Create: `frontend/src/config/agentModes.test.js`
- Create: `frontend/src/components/agentPlatform/workspacePolicy.js`
- Create: `frontend/src/components/agentPlatform/workspacePolicy.test.js`
- Modify: `frontend/package.json`

- [ ] **Step 1: 编写失败的元数据测试**

测试断言六个稳定模式值、完整名称与介绍，并验证未知模式返回空值：

```js
test('agent mode catalog exposes the six supported modes in product order', () => {
  assert.deepEqual(AGENT_MODES.map(item => item.id), [
    'assistant', 'expert', 'query', 'report', 'chart', 'ops'
  ])
  assert.ok(AGENT_MODES.every(item => item.name && item.description && item.tags.length))
  assert.equal(getAgentMode('missing'), null)
})
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `cd frontend && node --test src/config/agentModes.test.js`

Expected: FAIL，错误包含 `ERR_MODULE_NOT_FOUND`。

- [ ] **Step 3: 实现最小 Agent 元数据模块**

导出 `AGENT_MODES`、`AGENT_MODE_IDS` 和 `getAgentMode(mode)`；每项包含 `id`、`name`、`shortName`、`description`、`tags`、`accent` 和 SVG 路径数据，文案严格采用设计文档确认内容。

- [ ] **Step 4: 运行元数据测试并确认通过**

Run: `cd frontend && node --test src/config/agentModes.test.js`

Expected: PASS。

- [ ] **Step 5: 编写失败的工作区策略测试**

```js
test('idle mode selection requests a fresh conversation', () => {
  assert.deepEqual(resolveAgentSelection('assistant', state), {
    mode: 'assistant', action: 'reset-and-open'
  })
})

test('running mode selection preserves the active conversation', () => {
  state.modeStates.expert.isAnalyzing = true
  assert.equal(resolveAgentSelection('expert', state).action, 'open-running')
})
```

同时覆盖 `sessionStates` 中运行的会话和非法模式返回 `invalid`。

- [ ] **Step 6: 运行策略测试并确认因模块不存在而失败**

Run: `cd frontend && node --test src/components/agentPlatform/workspacePolicy.test.js`

Expected: FAIL，错误包含 `ERR_MODULE_NOT_FOUND`。

- [ ] **Step 7: 实现最小工作区策略**

```js
export const isAgentModeRunning = (mode, state) =>
  Boolean(state.modeStates?.[mode]?.isAnalyzing) ||
  Object.values(state.sessionStates || {}).some(
    session => session.mode === mode && session.isAnalyzing
  )

export const resolveAgentSelection = (mode, state) => {
  if (!AGENT_MODE_IDS.includes(mode)) return { mode, action: 'invalid' }
  return {
    mode,
    action: isAgentModeRunning(mode, state) ? 'open-running' : 'reset-and-open'
  }
}
```

- [ ] **Step 8: 运行两组测试并确认通过**

Run: `cd frontend && node --test src/config/agentModes.test.js src/components/agentPlatform/workspacePolicy.test.js`

Expected: 全部 PASS。

- [ ] **Step 9: 在 package.json 注册测试命令并提交**

新增 `test:agent-platform`，执行上述两个测试文件。

```bash
git add frontend/package.json frontend/src/config/agentModes.js frontend/src/config/agentModes.test.js frontend/src/components/agentPlatform/workspacePolicy.js frontend/src/components/agentPlatform/workspacePolicy.test.js
git commit -m "test: define agent platform modes and selection policy"
```

### Task 2: 平台首页与对话标题组件

**Files:**
- Create: `frontend/src/components/agentPlatform/AgentPlatform.vue`
- Create: `frontend/src/components/agentPlatform/AgentWorkspaceHeader.vue`

- [ ] **Step 1: 编写组件契约失败测试**

在 `frontend/src/components/agentPlatform/agentPlatformComponents.test.js` 读取组件源码并断言：平台组件遍历 `agents`、按钮发出 `select`、包含运行状态；标题组件通过 `getAgentMode` 显示当前模式。测试先因组件不存在失败。

- [ ] **Step 2: 运行契约测试并确认失败**

Run: `cd frontend && node --test src/components/agentPlatform/agentPlatformComponents.test.js`

Expected: FAIL，错误为组件文件不存在。

- [ ] **Step 3: 实现 AgentPlatform.vue**

组件接口：

```js
const props = defineProps({
  agents: { type: Array, default: () => AGENT_MODES },
  runningModes: { type: Array, default: () => [] },
  selectingMode: { type: String, default: '' },
  error: { type: String, default: '' }
})
const emit = defineEmits(['select'])
```

使用原生 `button` 渲染整张卡片，输出标签、描述、“运行中/开始使用”状态，增加可见 `:focus-visible` 样式和 3/2/1 列响应式断点。

- [ ] **Step 4: 实现 AgentWorkspaceHeader.vue**

接收 `mode`，用 `getAgentMode(mode)` 显示名称、简介及“返回智能体平台”的说明性入口区域；返回动作仍由左侧导航完成，不在标题中复制导航按钮。

- [ ] **Step 5: 运行组件契约测试和生产构建**

Run: `cd frontend && node --test src/components/agentPlatform/agentPlatformComponents.test.js && npm run build`

Expected: 测试 PASS，Vite build 成功。

- [ ] **Step 6: 提交组件**

```bash
git add frontend/src/components/agentPlatform
git commit -m "feat: add agent platform mode cards"
```

### Task 3: 集成左侧导航和工作区切换

**Files:**
- Modify: `frontend/src/components/AssistantSidebar.vue`
- Modify: `frontend/src/components/reactAnalysis/MainLayout.vue`
- Modify: `frontend/src/views/ReactAnalysisView.vue`
- Test: `frontend/src/components/agentPlatform/agentPlatformIntegration.test.js`

- [ ] **Step 1: 编写失败的集成契约测试**

断言：侧栏包含 `agent-platform`；`MainLayout` 接收 `workspace` 并渲染 `AgentPlatform`；页面容器默认 `workspace = ref('platform')`；成功恢复历史会话后切换为 `chat`。

- [ ] **Step 2: 运行测试并确认缺少集成而失败**

Run: `cd frontend && node --test src/components/agentPlatform/agentPlatformIntegration.test.js`

Expected: FAIL，至少一项契约断言不满足。

- [ ] **Step 3: 集成 AssistantSidebar**

新增 `agent-platform` 模块、平台图标和顶部独立入口；`activeModule === 'agent-platform'` 时显示选中态，点击继续通过现有 `action` 事件上报。

- [ ] **Step 4: 集成 MainLayout**

新增 props：

```js
workspace: { type: String, default: 'platform' },
runningAgentModes: { type: Array, default: () => [] },
selectingAgentMode: { type: String, default: '' },
agentPlatformError: { type: String, default: '' }
```

当 `workspace === 'platform'` 时，主区域只渲染 `AgentPlatform`；否则渲染现有问数或普通对话、对话标题及右侧面板。平台组件的选择通过 `select-agent` 事件上传。

- [ ] **Step 5: 集成 ReactAnalysisView 默认状态与选择逻辑**

```js
const workspace = ref('platform')
const selectingAgentMode = ref('')
const agentPlatformError = ref('')

const handleAgentSelect = async (mode) => {
  const decision = resolveAgentSelection(mode, store)
  if (decision.action === 'invalid') return
  selectingAgentMode.value = mode
  try {
    store.switchMode(mode)
    if (decision.action === 'reset-and-open') store.reset()
    hideManagementPanel()
    resetPanelState()
    activeAssistant.value = 'general-agent'
    workspace.value = 'chat'
  } catch (error) {
    agentPlatformError.value = error?.message || '智能体初始化失败，请重试'
  } finally {
    selectingAgentMode.value = ''
  }
}
```

`agent-platform` 侧栏动作只设置平台工作区；所有成功的会话加载/恢复包装函数设置 `workspace = 'chat'`；检测路由名为 `session` 时，初始化保持现有恢复流程并在成功后打开聊天。

- [ ] **Step 6: 运行集成契约测试和前端构建**

Run: `cd frontend && node --test src/components/agentPlatform/agentPlatformIntegration.test.js && npm run build`

Expected: 测试 PASS，Vite build 成功。

- [ ] **Step 7: 提交集成**

```bash
git add frontend/src/components/AssistantSidebar.vue frontend/src/components/reactAnalysis/MainLayout.vue frontend/src/views/ReactAnalysisView.vue frontend/src/components/agentPlatform/agentPlatformIntegration.test.js
git commit -m "feat: make agent platform the default workspace"
```

### Task 4: 移除旧模式切换入口并完成回归验证

**Files:**
- Modify: `frontend/src/components/InputBox.vue`
- Modify: `frontend/src/components/queryDashboard/QueryDashboardWorkspace.vue`
- Modify: `frontend/src/components/reactAnalysis/ChatArea.vue`
- Modify: `frontend/src/components/reactAnalysis/MainLayout.vue`
- Modify: `frontend/src/views/ReactAnalysisView.vue`
- Test: `frontend/src/components/agentPlatform/agentPlatformIntegration.test.js`

- [ ] **Step 1: 扩展失败测试，禁止对话工作区引用 AgentModeSelector**

读取 `InputBox.vue` 和 `QueryDashboardWorkspace.vue`，断言均不包含 `AgentModeSelector`，并断言事件链不再声明 `update:agentMode`。

- [ ] **Step 2: 运行测试并确认旧选择器导致失败**

Run: `cd frontend && node --test src/components/agentPlatform/agentPlatformIntegration.test.js`

Expected: FAIL，指出旧选择器或旧事件仍存在。

- [ ] **Step 3: 删除旧选择器与事件链**

从 `InputBox.vue` 删除组件导入、模板、`showAgentModeSelector` prop、本地 `agentMode` 及更新处理器；从问数大屏删除悬浮选择器；逐层删除 `ChatArea`、`QueryDashboardWorkspace`、`MainLayout` 和 `ReactAnalysisView` 不再使用的 `update:agentMode` 事件。

- [ ] **Step 4: 运行智能体平台测试**

Run: `cd frontend && npm run test:agent-platform`

Expected: 全部 PASS。

- [ ] **Step 5: 运行现有前端测试**

Run: `cd frontend && npm run test:auth && npm run test:event-tasks`

Expected: 全部 PASS。

- [ ] **Step 6: 运行生产构建**

Run: `cd frontend && npm run build`

Expected: Vite build 成功，无 Vue 编译错误。

- [ ] **Step 7: 检查改动范围并提交**

Run: `git diff --check && git status --short`

确认不包含用户已有的后端测试改动与 `NormCraftAI/` 内容。

```bash
git add frontend/src/components/InputBox.vue frontend/src/components/queryDashboard/QueryDashboardWorkspace.vue frontend/src/components/reactAnalysis/ChatArea.vue frontend/src/components/reactAnalysis/MainLayout.vue frontend/src/views/ReactAnalysisView.vue frontend/src/components/agentPlatform/agentPlatformIntegration.test.js
git commit -m "refactor: centralize agent mode selection on platform"
```
