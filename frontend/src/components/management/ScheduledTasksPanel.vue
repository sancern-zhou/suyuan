<template>
  <div class="management-panel scheduled-tasks-panel">
    <div class="panel-header">
      <h3>{{ selectedHistoryTask ? `${selectedHistoryTask.name} · 执行记录` : '任务管理' }}</h3>
      <button v-if="!selectedHistoryTask" class="panel-btn small primary" @click="openCreateDialog">
        新建任务
      </button>
      <div v-else class="panel-actions">
        <button class="panel-btn small" @click="closeExecutionHistory">返回任务列表</button>
        <button class="panel-btn small primary" :disabled="executionHistoryLoading" @click="refreshExecutionHistory">
          {{ executionHistoryLoading ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div v-if="!selectedHistoryTask" class="scheduled-tasks-content">
      <!-- 任务列表 -->
      <div class="scheduled-tasks-list">
        <div v-if="tasks.length === 0" class="scheduled-empty-state">
          <p>暂无定时任务</p>
          <p class="scheduled-hint">在对话中说"创建定时任务"即可快速创建</p>
        </div>

        <div
          v-for="task in tasks"
          :key="task.task_id"
          class="scheduled-task-card"
        >
          <!-- 任务头部 -->
          <div class="scheduled-task-header">
            <div class="scheduled-task-title">
              <span class="scheduled-task-name">{{ task.name }}</span>
              <span :class="['scheduled-task-tag', getTaskTriggerClass(task)]">
                {{ getTaskTriggerLabel(task) }}
              </span>
            </div>

            <!-- 快速开关 -->
            <label class="scheduled-switch">
              <input
                type="checkbox"
                :checked="task.enabled"
                @change="$emit('toggle-task', task)"
                :disabled="task.toggling"
              />
              <span class="scheduled-slider"></span>
            </label>
          </div>

          <!-- 任务描述 -->
          <div class="scheduled-task-description">
            {{ task.description }}
          </div>

          <!-- 任务元信息 -->
          <div class="scheduled-task-meta">
            <span v-if="task.trigger_type !== 'event'" class="scheduled-meta-item">⏰ {{ formatScheduledNextRun(task.next_run_at) }}</span>
            <span v-else class="scheduled-meta-item">事件：{{ getEventLabel(task.event_type) }}</span>
            <span class="scheduled-meta-item">⏱ {{ task.timeout_seconds || 1800 }} 秒超时</span>
            <span class="scheduled-meta-item">✅ {{ task.success_runs || 0 }}/{{ task.total_runs || 0 }}</span>
            <span class="scheduled-meta-item">🧠 {{ getExecutionModeLabel(task.execution_mode) }}</span>
            <span v-if="task.skill_id" class="scheduled-meta-item">📘 Skill：{{ task.skill_id }}</span>
            <span v-if="task.broadcast_enabled" class="scheduled-meta-item">接收人：{{ task.target_user_ids?.length || 0 }}</span>
          </div>

          <!-- 标签 -->
          <div class="scheduled-task-tags" v-if="task.tags && task.tags.length > 0">
            <span v-for="tag in task.tags" :key="tag" class="scheduled-tag">
              {{ tag }}
            </span>
          </div>

          <!-- 操作按钮 -->
          <div class="scheduled-task-actions">
            <button
              v-if="task.trigger_type !== 'event'"
              class="scheduled-btn scheduled-btn-execute"
              @click="$emit('execute-task', task)"
              :disabled="task.executing"
              title="立即执行此任务"
            >
              {{ task.executing ? '执行中...' : '▶️ 立即执行' }}
            </button>
            <button class="scheduled-btn scheduled-btn-secondary" @click="openExecutionHistory(task)">
              执行记录
            </button>
            <button class="scheduled-btn scheduled-btn-secondary" @click="openHistoryDialog(task)">
              历史记忆
            </button>
            <button class="scheduled-btn scheduled-btn-secondary" @click="openEditDialog(task)">
              编辑
            </button>
            <button class="scheduled-btn scheduled-btn-danger" @click="$emit('delete-task', task)">
              删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="execution-history-view">
      <div v-if="executionHistoryLoading" class="execution-history-state">
        <span class="execution-history-spinner">⏳</span>
        <p>加载执行记录...</p>
      </div>

      <div v-else-if="executionHistoryError" class="execution-history-state error">
        <p>{{ executionHistoryError }}</p>
        <button class="panel-btn small" @click="refreshExecutionHistory">重试</button>
      </div>

      <div v-else-if="executionHistory.length === 0" class="execution-history-state">
        <span class="execution-history-empty-icon">📭</span>
        <p>暂无执行记录</p>
      </div>

      <div v-else class="execution-history-list">
        <button
          v-for="execution in executionHistory"
          :key="execution.execution_id"
          type="button"
          class="execution-history-item"
          :class="{ disabled: !canRestoreExecution(execution) }"
          :disabled="!canRestoreExecution(execution)"
          :title="canRestoreExecution(execution) ? '查看执行对话' : '该记录未生成会话'"
          @click="restoreExecutionSession(execution)"
        >
          <span class="execution-history-main">
            <span :class="['execution-status', `status-${executionStatusMeta(execution.status).key}`]">
              {{ executionStatusMeta(execution.status).label }}
            </span>
            <span class="execution-time">{{ formatExecutionTime(execution.started_at) }}</span>
            <span class="execution-duration">{{ formatExecutionDuration(execution.duration_seconds) }}</span>
          </span>
          <span class="execution-history-meta">
            <span>{{ execution.status || 'pending' }}</span>
            <span>{{ execution.trigger_type === 'event' ? '事件触发' : '定时触发' }}</span>
            <span v-if="execution.session_id">会话 {{ shortSessionId(execution.session_id) }}</span>
            <span v-else>未生成会话</span>
          </span>
          <span v-if="execution.error_message" class="execution-error-summary">
            {{ execution.error_message }}
          </span>
        </button>
      </div>
      <nav
        v-if="!executionHistoryLoading && executionHistoryPagination.totalPages > 1"
        class="execution-history-pagination"
        aria-label="执行记录分页"
      >
        <button
          type="button"
          class="panel-btn small"
          :disabled="executionHistoryPagination.page <= 1"
          @click="changeExecutionHistoryPage(executionHistoryPagination.page - 1)"
        >上一页</button>
        <span>
          第 {{ executionHistoryPagination.page }} / {{ executionHistoryPagination.totalPages }} 页，
          共 {{ executionHistoryPagination.total }} 条
        </span>
        <button
          type="button"
          class="panel-btn small"
          :disabled="executionHistoryPagination.page >= executionHistoryPagination.totalPages"
          @click="changeExecutionHistoryPage(executionHistoryPagination.page + 1)"
        >下一页</button>
      </nav>
    </div>

    <!-- 新建/编辑任务弹窗 -->
    <div v-if="showCreateDialog" class="modal-backdrop" @click.self="closeDialog">
      <div class="modal-panel">
        <div class="modal-header">
          <h4>{{ editingTaskId ? '编辑任务' : '新建任务' }}</h4>
          <button class="panel-btn small" @click="closeDialog">关闭</button>
        </div>

        <div class="modal-body">
          <div class="form-grid">
            <label class="form-field">
              <span>任务名称</span>
              <input v-model="createForm.name" type="text" placeholder="例如：运城市告警推送" />
            </label>

            <div class="form-field">
              <span>触发方式</span>
              <div class="trigger-segment" role="group" aria-label="触发方式">
                <button
                  type="button"
                  :class="{ active: createForm.trigger_type === 'schedule' }"
                  @click="setTriggerType('schedule')"
                >定时触发</button>
                <button
                  type="button"
                  :class="{ active: createForm.trigger_type === 'event' }"
                  @click="setTriggerType('event')"
                >事件触发</button>
              </div>
            </div>

            <label class="form-field">
              <span>执行模式</span>
              <select v-model="createForm.execution_mode" @change="handleExecutionModeChange">
                <option value="assistant">assistant</option>
                <option value="expert">expert</option>
                <option value="query">query</option>
                <option value="social">social</option>
                <option value="custom">custom（自选工具）</option>
              </select>
            </label>

            <div v-if="createForm.execution_mode === 'custom'" class="form-field form-wide">
              <span>Agent 工具（本次任务所有步骤固定共享）</span>
              <input v-model="createForm.toolSearch" type="search" placeholder="搜索工具名称或说明" />
              <div class="tool-picker">
                <label v-for="tool in filteredTools" :key="tool.name" class="tool-option">
                  <input
                    v-model="createForm.tool_names"
                    type="checkbox"
                    :value="tool.name"
                    :disabled="tool.status !== 'enabled'"
                  />
                  <span class="tool-option-main">
                    <strong>{{ tool.name }}</strong>
                    <small>{{ tool.description || '暂无说明' }}</small>
                  </span>
                  <span v-if="tool.status !== 'enabled'" class="tool-disabled">已禁用</span>
                </label>
                <div v-if="filteredTools.length === 0" class="recipient-empty">没有匹配的工具</div>
              </div>
              <small class="form-hint">仅加载所选工具，不继承其他模式能力；系统不会自动补充依赖工具。</small>
            </div>

            <label class="form-field form-wide">
              <span>上下文 Skill（可选）</span>
              <select v-model="createForm.skill_id" :disabled="scheduledTasksStore.skillsLoading">
                <option value="">不注入 Skill</option>
                <option
                  v-if="createForm.skill_id && !selectedSkill"
                  :value="createForm.skill_id"
                >
                  {{ createForm.skill_id }}（当前不可用）
                </option>
                <option v-for="skill in availableSkills" :key="skill.id" :value="skill.id">
                  {{ skill.name || skill.id }}
                </option>
              </select>
              <small v-if="scheduledTasksStore.skillsLoading" class="form-hint">正在加载项目 Skill...</small>
              <small v-else-if="selectedSkill" class="form-hint">
                任务执行时会将“{{ selectedSkill.name || selectedSkill.id }}”完整注入 Agent 上下文。工具是否满足 Skill 要求由配置人自行确认。
              </small>
              <small v-else class="form-hint">事件任务和定时任务均可选择一个已发布 Skill，用于稳定约束 Agent 的分析流程和输出。</small>
            </label>

            <label class="form-field form-wide">
              <span>任务描述</span>
              <textarea v-model="createForm.description" rows="4" placeholder="描述广播主题、语气、目标人群"></textarea>
            </label>

            <label class="form-field form-wide">
              <span>Agent 执行指令</span>
              <textarea
                v-model="createForm.agent_prompt"
                rows="5"
                placeholder="描述事件发生后 Agent 要执行的具体步骤、技能和产物要求"
              ></textarea>
            </label>

            <label v-if="createForm.trigger_type === 'schedule'" class="form-field">
              <span>调度类型</span>
              <select v-model="createForm.schedule_type">
                <option value="daily_8am">每天 8 点</option>
                <option value="every_2h">每 2 小时</option>
                <option value="every_30min">每 30 分钟</option>
                <option value="once">一次性</option>
                <option value="interval">自定义间隔</option>
                <option value="daily_custom">每天自定义时间</option>
              </select>
            </label>

            <label class="form-field" v-if="createForm.trigger_type === 'schedule' && createForm.schedule_type === 'once'">
              <span>执行时间</span>
              <input v-model="createForm.run_at" type="datetime-local" />
            </label>

            <label class="form-field" v-if="createForm.trigger_type === 'schedule' && createForm.schedule_type === 'interval'">
              <span>间隔分钟</span>
              <input v-model.number="createForm.interval_minutes" type="number" min="1" />
            </label>

            <label class="form-field" v-if="createForm.trigger_type === 'schedule' && createForm.schedule_type === 'daily_custom'">
              <span>小时</span>
              <input v-model.number="createForm.hour" type="number" min="0" max="23" />
            </label>

            <label class="form-field" v-if="createForm.trigger_type === 'schedule' && createForm.schedule_type === 'daily_custom'">
              <span>分钟</span>
              <input v-model.number="createForm.minute" type="number" min="0" max="59" />
            </label>

            <label v-if="createForm.trigger_type === 'event'" class="form-field">
              <span>事件类型</span>
              <select v-model="createForm.event_type">
                <option value="" disabled>请选择事件</option>
                <option v-for="eventType in eventTypes" :key="eventType.event_type" :value="eventType.event_type">
                  {{ eventType.label }}
                </option>
              </select>
            </label>

            <label v-if="createForm.trigger_type === 'event'" class="form-field">
              <span>城市过滤</span>
              <input v-model="createForm.filterCity" type="text" placeholder="留空表示不过滤" />
            </label>

            <div v-if="createForm.trigger_type === 'event'" class="form-field form-wide">
              <span>告警级别</span>
              <div class="channel-checks">
                <label v-for="level in alertLevelOptions" :key="level.value" class="channel-check">
                  <input v-model="createForm.filterAlertLevels" type="checkbox" :value="level.value" />
                  <span>{{ level.label }}</span>
                </label>
              </div>
            </div>

            <div v-if="createForm.trigger_type === 'schedule'" class="form-field form-wide">
              <span>目标渠道</span>
              <div class="channel-checks">
                <label v-for="channel in channelOptions" :key="channel.value" class="channel-check">
                  <input v-model="createForm.channels" type="checkbox" :value="channel.value" />
                  <span>{{ channel.label }}</span>
                </label>
              </div>
            </div>

            <div class="form-field form-wide">
              <label class="switch-field inline-switch">
                <input v-model="createForm.broadcast_enabled" type="checkbox" />
                <span>执行成功后广播</span>
              </label>
            </div>

            <div v-if="createForm.broadcast_enabled" class="form-field form-wide">
              <span>接收人（微信 / App，可多选）</span>
              <div class="recipient-list">
                <label v-for="user in socialUsers" :key="user.id" class="recipient-option">
                  <input v-model="createForm.target_user_ids" type="checkbox" :value="user.channel === 'app' ? user.social_user_id : user.id" />
                  <span class="recipient-name">{{ user.name }}</span>
                  <span class="recipient-channel">{{ user.channel }}</span>
                </label>
                <div v-if="socialUsers.length === 0" class="recipient-empty">暂无已启用的微信或 App 用户</div>
              </div>
            </div>

            <label class="form-field form-wide">
              <span>标签</span>
              <input v-model="createForm.tagsText" type="text" placeholder="广播,提醒,日报" />
            </label>

            <div class="form-field form-wide">
              <label class="switch-field inline-switch">
                <input v-model="createForm.workspaceEntryEnabled" type="checkbox" />
                <span>在左侧显示业务入口</span>
              </label>
              <input v-if="createForm.workspaceEntryEnabled" v-model="createForm.workspaceEntryTitle" type="text" placeholder="例如：告警溯源" />
            </div>

            <div class="form-field form-wide">
              <label class="switch-field inline-switch">
                <input v-model="createForm.historyLearningEnabled" type="checkbox" />
                <span>历史执行记忆（任务专属案例库 + 长期记忆）</span>
              </label>
              <div v-if="createForm.historyLearningEnabled" class="history-learning-fields">
                <label class="form-field">
                  <span>注入最近案例数</span>
                  <input v-model.number="createForm.historyMaxRecentCases" type="number" min="0" max="20" />
                </label>
                <label class="form-field">
                  <span>记忆字符预算</span>
                  <input v-model.number="createForm.historyMemoryCharBudget" type="number" min="200" step="100" />
                </label>
                <small class="form-hint">
                  每次执行后自动沉淀本次案例并更新长期记忆；下次执行注入以上配置的历史记忆，帮助任务感知历史、持续优化输出。
                </small>
              </div>
            </div>
          </div>

          <div class="task-preview">
            <div class="task-preview-title">执行步骤预览</div>
            <div class="task-preview-body">
              <p v-if="createForm.trigger_type === 'event'">事件匹配后只运行一次 Agent，结果由后台广播给所选微信或 App 用户并写入各自会话。</p>
              <p v-else>任务将在设定时间运行，并按配置处理广播。</p>
            </div>
          </div>
          <div v-if="formError" class="form-error" role="alert">{{ formError }}</div>
        </div>

        <div class="modal-actions">
          <label class="switch-field">
            <input v-model="createForm.enabled" type="checkbox" />
            <span>启用任务</span>
          </label>
          <button class="panel-btn" @click="closeDialog">取消</button>
          <button class="panel-btn primary" :disabled="creatingTask" @click="saveTask">
            {{ creatingTask ? '保存中...' : (editingTaskId ? '保存修改' : '创建任务') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 历史执行记忆弹窗 -->
    <div v-if="showHistoryDialog" class="modal-backdrop" @click.self="closeHistoryDialog">
      <div class="modal-panel history-modal">
        <div class="modal-header">
          <h4>{{ historyTask?.name }} · 历史执行记忆</h4>
          <button class="panel-btn small" @click="closeHistoryDialog">关闭</button>
        </div>

        <div class="modal-body">
          <div class="history-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              :class="{ active: historyTab === 'cases' }"
              @click="historyTab = 'cases'"
            >案例库（{{ historyCasesTotal }}）</button>
            <button
              type="button"
              role="tab"
              :class="{ active: historyTab === 'memory' }"
              @click="historyTab = 'memory'"
            >长期记忆</button>
          </div>

          <div v-if="historyLoading" class="history-state">加载历史执行记忆...</div>
          <div v-else-if="historyError" class="history-state error">
            <p>{{ historyError }}</p>
            <button class="panel-btn small" @click="loadHistoryData">重试</button>
          </div>

          <!-- 案例库页签 -->
          <div v-else-if="historyTab === 'cases'" class="history-cases">
            <div v-if="historyCases.length === 0" class="history-state">
              暂无历史案例，任务每次执行后会自动累积。
            </div>
            <div v-for="caseItem in historyCases" :key="caseItem.execution_id" class="history-case-card">
              <div class="history-case-header">
                <span :class="['execution-status', `status-${caseStatusKey(caseItem.status)}`]">
                  {{ caseStatusLabel(caseItem.status) }}
                </span>
                <span class="history-case-time">{{ formatHistoryTime(caseItem.started_at) }}</span>
                <span v-if="caseItem.duration_seconds != null" class="history-case-duration">
                  {{ formatExecutionDuration(caseItem.duration_seconds) }}
                </span>
                <span v-if="caseItem.trigger?.type === 'event'" class="history-case-trigger">事件触发</span>
              </div>
              <p v-if="caseItem.trigger?.context_digest" class="history-case-digest">
                {{ caseItem.trigger.context_digest }}
              </p>
              <p class="history-case-brief">
                {{ caseItem.distilled?.case_brief || caseItem.summary || '（无摘要）' }}
              </p>
              <ul v-if="caseItem.distilled?.findings?.length" class="history-case-findings">
                <li v-for="(finding, index) in caseItem.distilled.findings" :key="index">{{ finding }}</li>
              </ul>
              <div v-if="caseItem.outputs?.length" class="history-case-outputs">
                <span v-for="output in caseItem.outputs" :key="`${output.kind}:${output.ref}`" class="history-case-ref">
                  {{ output.kind }}:{{ output.ref }}
                </span>
              </div>
              <div v-if="caseItem.errors?.length" class="history-case-errors">
                <p v-for="(error, index) in caseItem.errors" :key="index">{{ error }}</p>
              </div>
            </div>
            <p v-if="historyCasesTotal > historyCases.length" class="history-cases-more">
              仅显示最近 {{ historyCases.length }} 条，共 {{ historyCasesTotal }} 条
            </p>
          </div>

          <!-- 长期记忆页签 -->
          <div v-else class="history-memory">
            <div v-if="memoryEditing" class="history-memory-editor">
              <textarea v-model="memoryDraft" rows="14" placeholder="编辑任务专属长期记忆（Markdown）"></textarea>
              <div v-if="memoryEditError" class="form-error" role="alert">{{ memoryEditError }}</div>
              <div class="history-memory-editor-actions">
                <button class="panel-btn small" @click="cancelMemoryEdit">取消</button>
                <button class="panel-btn small primary" :disabled="memorySaving" @click="saveMemoryEdit">
                  {{ memorySaving ? '保存中...' : '保存记忆' }}
                </button>
              </div>
            </div>
            <template v-else>
              <div class="history-memory-meta">
                <span>版本 v{{ historyMemory?.meta?.version ?? 0 }}</span>
                <span>巩固：{{ consolidationStatusLabel(historyMemory?.meta?.last_consolidation_status) }}</span>
                <span v-if="historyMemory?.meta?.consolidation_failures > 0" class="history-memory-warn">
                  巩固失败 {{ historyMemory.meta.consolidation_failures }} 次
                </span>
                <span v-if="historyMemory?.meta?.updated_at">更新于 {{ formatHistoryTime(historyMemory.meta.updated_at) }}</span>
                <button class="panel-btn small" @click="startMemoryEdit">编辑</button>
              </div>
              <div v-if="historyMemory?.memory" class="history-memory-content markdown-body" v-html="renderedMemory"></div>
              <div v-else class="history-state">
                暂无长期记忆，任务完成首次执行并巩固后会自动生成。
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'
import {
  applyExecutionMode,
  applyTriggerDefaults,
  buildTaskPayload,
  selectableSocialUsers
} from './scheduledTaskForm.js'
import {
  canRestoreExecution,
  executionStatusMeta,
  loadScheduledTaskExecutions,
  sortExecutionsNewestFirst
} from './scheduledTaskActions.js'

// Props
defineProps({
  tasks: {
    type: Array,
    default: () => []
  },
  stats: {
    type: Object,
    default: () => ({
      total: 0,
      running: 0,
      successRate: 0
    })
  },
  scheduledTasksRefreshing: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'close',
  'refresh-tasks',
  'toggle-task',
  'execute-task',
  'edit-task',
  'delete-task',
  'restore-execution-session'
])

const scheduledTasksStore = useScheduledTasksStore()
const showCreateDialog = ref(false)
const creatingTask = ref(false)
const editingTaskId = ref(null)
const formError = ref('')
const selectedHistoryTask = ref(null)
const executionHistory = ref([])
const executionHistoryLoading = ref(false)
const executionHistoryError = ref('')
const executionHistoryPagination = ref({ page: 1, pageSize: 10, total: 0, totalPages: 0 })

const eventTypes = computed(() => scheduledTasksStore.eventTypes)
const socialUsers = computed(() => selectableSocialUsers(scheduledTasksStore.socialUsers))
const availableSkills = computed(() => scheduledTasksStore.availableSkills)
const selectedSkill = computed(() => availableSkills.value.find(
  skill => skill.id === createForm.value.skill_id
) || null)
const filteredTools = computed(() => {
  const query = createForm.value.toolSearch.trim().toLowerCase()
  return scheduledTasksStore.availableTools.filter(tool => !query || [
    tool.name,
    tool.description,
    tool.category
  ].some(value => String(value || '').toLowerCase().includes(query)))
})

const channelOptions = [
  { label: '微信', value: 'weixin' },
  { label: 'App', value: 'app' },
  { label: 'QQ', value: 'qq' },
  { label: '钉钉', value: 'dingtalk' }
]

const alertLevelOptions = [
  { label: '低', value: 'low' },
  { label: '中', value: 'medium' },
  { label: '高', value: 'high' }
]

const defaultForm = () => ({
  name: '',
  description: '',
  agent_prompt: '',
  execution_mode: 'assistant',
  skill_id: '',
  tool_names: [],
  toolSearch: '',
  trigger_type: 'schedule',
  schedule_type: 'daily_custom',
  event_type: '',
  event_filters: {},
  filterCity: '',
  filterAlertLevels: [],
  broadcast_enabled: false,
  target_user_ids: [],
  enabled: true,
  hour: 9,
  minute: 0,
  interval_minutes: 30,
  run_at: '',
  channels: ['weixin'],
  tagsText: ''
  ,workspaceEntryEnabled: false
  ,workspaceEntryTitle: ''
  ,historyLearningEnabled: true
  ,historyMaxRecentCases: 3
  ,historyMemoryCharBudget: 4000
  ,historyLearningBase: null
})

const createForm = ref(defaultForm())

const setTriggerType = (triggerType) => {
  applyTriggerDefaults(createForm.value, triggerType, eventTypes.value)
}

const handleExecutionModeChange = async () => {
  applyExecutionMode(createForm.value, createForm.value.execution_mode)
  if (createForm.value.execution_mode === 'custom') {
    await loadAvailableTools()
  }
}

const refreshExecutionHistory = async (requestedPage = executionHistoryPagination.value.page) => {
  if (!selectedHistoryTask.value) return
  const page = Number.isInteger(requestedPage)
    ? requestedPage
    : executionHistoryPagination.value.page
  executionHistoryLoading.value = true
  executionHistoryError.value = ''
  try {
    const result = await loadScheduledTaskExecutions(
      scheduledTasksStore,
      selectedHistoryTask.value,
      { page, pageSize: executionHistoryPagination.value.pageSize }
    )
    executionHistory.value = sortExecutionsNewestFirst(result.executions)
    executionHistoryPagination.value = {
      page: result.page,
      pageSize: result.pageSize,
      total: result.total,
      totalPages: result.totalPages
    }
  } catch (error) {
    console.error('Failed to fetch task executions:', error)
    executionHistoryError.value = '执行记录加载失败，请重试'
  } finally {
    executionHistoryLoading.value = false
  }
}

const openExecutionHistory = async (task) => {
  selectedHistoryTask.value = task
  executionHistory.value = []
  executionHistoryPagination.value = { page: 1, pageSize: 10, total: 0, totalPages: 0 }
  await refreshExecutionHistory(1)
}

const closeExecutionHistory = () => {
  selectedHistoryTask.value = null
  executionHistory.value = []
  executionHistoryError.value = ''
  executionHistoryPagination.value = { page: 1, pageSize: 10, total: 0, totalPages: 0 }
}

const changeExecutionHistoryPage = page => {
  if (page < 1 || page > executionHistoryPagination.value.totalPages) return
  refreshExecutionHistory(page)
}

const restoreExecutionSession = (execution) => {
  if (!canRestoreExecution(execution)) return
  emit('restore-execution-session', execution.session_id)
}

// ===== 历史执行记忆弹窗 =====
const showHistoryDialog = ref(false)
const historyTask = ref(null)
const historyTab = ref('cases')
const historyLoading = ref(false)
const historyError = ref('')
const historyCases = ref([])
const historyCasesTotal = ref(0)
const historyMemory = ref(null)
const memoryEditing = ref(false)
const memoryDraft = ref('')
const memorySaving = ref(false)
const memoryEditError = ref('')
let historyRequestToken = 0

const md = new MarkdownIt({ breaks: true })
const renderedMemory = computed(() => {
  const content = historyMemory.value?.memory
  return content ? md.render(content) : ''
})

const caseStatusKey = (status) => ({ succeeded: 'success', timeout: 'timeout' }[status] || 'failed')
const caseStatusLabel = (status) => ({ succeeded: '成功', failed: '失败', timeout: '超时' }[status] || status || '未知')
const consolidationStatusLabel = (status) => ({
  success: '成功',
  failed: '失败',
  manual: '人工编辑'
}[status] || '未巩固')

const formatHistoryTime = (timestamp) => {
  if (!timestamp) return '时间未知'
  return String(timestamp).slice(0, 19).replace('T', ' ')
}

const loadHistoryData = async () => {
  if (!historyTask.value) return
  const requestToken = ++historyRequestToken
  const taskId = historyTask.value.task_id
  historyLoading.value = true
  historyError.value = ''
  const [casesResult, memoryResult] = await Promise.allSettled([
    scheduledTasksStore.fetchTaskHistoryCases(taskId, { limit: 50 }),
    scheduledTasksStore.fetchTaskMemory(taskId)
  ])
  if (requestToken !== historyRequestToken || historyTask.value?.task_id !== taskId) return
  if (casesResult.status === 'fulfilled') {
    historyCases.value = casesResult.value.cases
    historyCasesTotal.value = casesResult.value.total
  } else {
    historyCases.value = []
    historyCasesTotal.value = 0
  }
  if (memoryResult.status === 'fulfilled') {
    historyMemory.value = memoryResult.value
  } else {
    historyMemory.value = null
  }
  if (casesResult.status === 'rejected' && memoryResult.status === 'rejected') {
    historyError.value = '历史执行记忆加载失败，请重试'
  }
  historyLoading.value = false
}

const openHistoryDialog = async (task) => {
  historyTask.value = task
  historyTab.value = 'cases'
  historyCases.value = []
  historyCasesTotal.value = 0
  historyMemory.value = null
  memoryEditing.value = false
  memoryEditError.value = ''
  showHistoryDialog.value = true
  await loadHistoryData()
}

const closeHistoryDialog = () => {
  historyRequestToken += 1
  showHistoryDialog.value = false
  historyTask.value = null
  historyCases.value = []
  historyCasesTotal.value = 0
  historyMemory.value = null
  historyError.value = ''
  memoryEditing.value = false
  memoryEditError.value = ''
}

const startMemoryEdit = () => {
  memoryDraft.value = historyMemory.value?.memory || ''
  memoryEditError.value = ''
  memoryEditing.value = true
}

const cancelMemoryEdit = () => {
  memoryEditing.value = false
  memoryEditError.value = ''
}

const saveMemoryEdit = async () => {
  if (!historyTask.value) return
  const content = memoryDraft.value.trim()
  if (!content) {
    memoryEditError.value = '记忆内容不能为空'
    return
  }
  memorySaving.value = true
  memoryEditError.value = ''
  try {
    historyMemory.value = await scheduledTasksStore.updateTaskMemory(
      historyTask.value.task_id,
      content,
      historyMemory.value?.meta?.version ?? 0
    )
    memoryEditing.value = false
  } catch (error) {
    console.error('Failed to save task memory:', error)
    memoryEditError.value = error.status === 409
      ? '记忆已被其他操作更新，请重新加载后再编辑'
      : '保存失败：' + (error.message || '未知错误')
  } finally {
    memorySaving.value = false
  }
}

const formatExecutionTime = (timestamp) => {
  if (!timestamp) return '时间未知'
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '时间无效'
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const formatExecutionDuration = (seconds) => {
  if (seconds == null) return '耗时计算中'
  const value = Number(seconds)
  if (!Number.isFinite(value) || value < 0) return '耗时未知'
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)} 秒`
  const minutes = Math.floor(value / 60)
  const remainingSeconds = Math.round(value % 60)
  return `${minutes} 分 ${remainingSeconds} 秒`
}

const shortSessionId = (sessionId) => sessionId.slice(0, 8)

// Methods
const getScheduledTaskLabel = (type) => {
  const labels = {
    daily_8am: '每天 8 点',
    every_2h: '每 2 小时',
    every_30min: '每 30 分钟',
    daily_custom: '每天自定义',
    interval: '自定义间隔',
    once: '一次性',
    daily: '每天',
    weekly: '每周',
    monthly: '每月',
    cron: '自定义'
  }
  return labels[type] || type
}

const getTaskTriggerClass = (task) => task.trigger_type === 'event' ? 'event' : 'schedule'

const getTaskTriggerLabel = (task) => task.trigger_type === 'event'
  ? '事件触发'
  : getScheduledTaskLabel(task.schedule_type)

const getEventLabel = (eventType) => eventTypes.value.find(
  item => item.event_type === eventType
)?.label || eventType || '未配置'

const getExecutionModeLabel = (mode) => {
  const labels = {
    assistant: '助手模式',
    expert: '专家模式',
    query: '问数模式',
    social: '社交模式',
    custom: '自定义工具模式'
  }
  return labels[mode] || mode || '默认'
}

const formatScheduledNextRun = (time) => {
  if (!time) return '未设置'
  try {
    const date = new Date(time)
    const now = new Date()
    const diff = date - now

    if (diff < 0) return '已过期'

    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 60) return `${minutes}分钟后`
    if (hours < 24) return `${hours}小时后`
    return `${days}天后`
  } catch {
    return '无效时间'
  }
}

const loadConfigurationOptions = async () => {
  const results = await Promise.allSettled([
    scheduledTasksStore.fetchEventTypes(),
    scheduledTasksStore.fetchSocialUsers(),
    scheduledTasksStore.fetchAvailableSkills()
  ])
  if (results.some(result => result.status === 'rejected')) {
    formError.value = '部分配置项加载失败，请关闭后重试'
  }
  if (
    createForm.value.trigger_type === 'event' &&
    !createForm.value.event_type &&
    eventTypes.value.length > 0
  ) {
    createForm.value.event_type = eventTypes.value[0].event_type
  }
}

const loadAvailableTools = async () => {
  try {
    await scheduledTasksStore.fetchAvailableTools()
  } catch (error) {
    console.error('Failed to fetch custom task tools:', error)
    formError.value = '自定义工具列表加载失败，请重新登录后重试'
  }
}

const openCreateDialog = async () => {
  editingTaskId.value = null
  createForm.value = defaultForm()
  formError.value = ''
  showCreateDialog.value = true
  await loadConfigurationOptions()
}

const openEditDialog = async (task) => {
  editingTaskId.value = task.task_id
  formError.value = ''
  createForm.value = {
    ...defaultForm(),
    name: task.name || '',
    description: task.description || '',
      agent_prompt: task.prompt || task.description || '',
    execution_mode: task.execution_mode || 'assistant',
    skill_id: task.skill_id || '',
    tool_names: [...(task.tool_names || [])],
    trigger_type: task.trigger_type || 'schedule',
    schedule_type: task.schedule_type || 'daily_custom',
    event_type: task.event_type || '',
    event_filters: task.event_filters || {},
    filterCity: task.event_filters?.city || '',
    filterAlertLevels: Array.isArray(task.event_filters?.alert_level)
      ? [...task.event_filters.alert_level]
      : (task.event_filters?.alert_level ? [task.event_filters.alert_level] : []),
    broadcast_enabled: Boolean(task.broadcast_enabled),
    target_user_ids: [...(task.target_user_ids || [])],
    enabled: Boolean(task.enabled),
    hour: task.hour ?? 9,
    minute: task.minute ?? 0,
    interval_minutes: task.interval_minutes ?? 30,
    run_at: task.run_at || '',
    tagsText: (task.tags || []).join(',')
    ,workspaceEntryEnabled: Boolean(task.workspace_entry?.enabled)
    ,workspaceEntryTitle: task.workspace_entry?.title || ''
    ,historyLearningEnabled: task.history_learning?.enabled !== false
    ,historyMaxRecentCases: task.history_learning?.max_recent_cases ?? 3
    ,historyMemoryCharBudget: task.history_learning?.memory_char_budget ?? 4000
    ,historyLearningBase: task.history_learning || null
  }
  showCreateDialog.value = true
  await loadConfigurationOptions()
  if (createForm.value.execution_mode === 'custom') {
    await loadAvailableTools()
  }
}

const closeDialog = () => {
  showCreateDialog.value = false
  editingTaskId.value = null
  formError.value = ''
}

const saveTask = async () => {
  formError.value = ''
  if (!createForm.value.name.trim()) {
    formError.value = '请填写任务名称'
    return
  }
  if (!createForm.value.description.trim()) {
    formError.value = '请填写任务描述'
    return
  }
  if (createForm.value.trigger_type === 'event' && !createForm.value.event_type) {
    formError.value = '请选择事件类型'
    return
  }
  if (createForm.value.broadcast_enabled && createForm.value.target_user_ids.length === 0) {
    formError.value = '请至少选择一名微信或 App 接收人'
    return
  }
  if (createForm.value.execution_mode === 'custom' && createForm.value.tool_names.length === 0) {
    formError.value = '请至少选择一个 Agent 工具'
    return
  }

  creatingTask.value = true
  try {
    const eventFilters = {}
    if (createForm.value.filterCity.trim()) {
      eventFilters.city = createForm.value.filterCity.trim()
    }
    if (createForm.value.filterAlertLevels.length > 0) {
      eventFilters.alert_level = [...createForm.value.filterAlertLevels]
    }
    const payload = buildTaskPayload({
      ...createForm.value,
      event_filters: eventFilters,
      agent_prompt: createForm.value.agent_prompt || createForm.value.description
    })

    if (editingTaskId.value) {
      await scheduledTasksStore.updateTask(editingTaskId.value, payload)
    } else {
      await scheduledTasksStore.createTask(payload)
    }
    closeDialog()
    emit('refresh-tasks')
  } catch (error) {
    console.error('Failed to save task:', error)
    formError.value = '保存失败：' + (error.message || '未知错误')
  } finally {
    creatingTask.value = false
  }
}

</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow-y: auto;
  padding: 20px;
  background: white;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e0e0e0;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.panel-actions {
  display: flex;
  gap: 8px;
}

.panel-btn {
  padding: 6px 12px;
  border: 1px solid #1976d2;
  background: white;
  color: #1976d2;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.panel-btn:hover:not(:disabled) {
  background: #1976d2;
  color: white;
}

.panel-btn.primary {
  background: #1976d2;
  color: white;
}

.panel-btn.primary:hover:not(:disabled) {
  background: #1565c0;
  color: white;
}

.panel-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.panel-btn.small {
  padding: 4px 8px;
  font-size: 12px;
}

.scheduled-tasks-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.scheduled-tasks-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.scheduled-empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #6c757d;
}

.scheduled-empty-state p {
  margin: 8px 0;
}

.scheduled-hint {
  font-size: 12px;
  font-style: italic;
}

.scheduled-task-card {
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 15px;
  transition: all 0.2s;
}

.scheduled-task-card:hover {
  border-color: #1976d2;
  box-shadow: 0 2px 8px rgba(25, 118, 210, 0.15);
}

.scheduled-task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.scheduled-task-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.scheduled-task-name {
  font-weight: 600;
  color: #212529;
  font-size: 14px;
}

.scheduled-task-tag {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.scheduled-task-tag.once {
  background: #e3f2fd;
  color: #1976d2;
}

.scheduled-task-tag.daily {
  background: #f3e5f5;
  color: #7b1fa2;
}

.scheduled-task-tag.weekly {
  background: #e8f5e9;
  color: #388e3c;
}

.scheduled-task-tag.monthly {
  background: #fff3e0;
  color: #f57c00;
}

.scheduled-task-tag.cron {
  background: #fce4ec;
  color: #c2185b;
}

.scheduled-task-tag.default {
  background: #e2e3e5;
  color: #383d41;
}

.scheduled-task-tag.event {
  background: #e8f5e9;
  color: #237a3b;
}

.scheduled-task-tag.schedule {
  background: #e3f2fd;
  color: #1565c0;
}

.scheduled-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}

.scheduled-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.scheduled-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: .4s;
  border-radius: 24px;
}

.scheduled-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .4s;
  border-radius: 50%;
}

.scheduled-switch input:checked + .scheduled-slider {
  background-color: #1976d2;
}

.scheduled-switch input:checked + .scheduled-slider:before {
  transform: translateX(20px);
}

.scheduled-switch input:disabled + .scheduled-slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.scheduled-task-description {
  color: #495057;
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 10px;
}

.scheduled-task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
}

.scheduled-meta-item {
  font-size: 12px;
  color: #6c757d;
}

.scheduled-task-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.scheduled-tag {
  padding: 2px 8px;
  background: #e9ecef;
  border-radius: 12px;
  font-size: 11px;
  color: #495057;
}

.scheduled-task-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.scheduled-btn {
  padding: 4px 10px;
  border: 1px solid #dee2e6;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.scheduled-btn:hover:not(:disabled) {
  background: #f8f9fa;
}

.scheduled-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.scheduled-btn-execute {
  background: #1976d2;
  color: white;
  border-color: #1976d2;
}

.scheduled-btn-execute:hover:not(:disabled) {
  background: #1565c0;
}

.scheduled-btn-secondary {
  color: #1976d2;
  border-color: #1976d2;
}

.scheduled-btn-secondary:hover:not(:disabled) {
  background: #e3f2fd;
}

.scheduled-btn-danger {
  color: #dc3545;
  border-color: #dc3545;
}

.scheduled-btn-danger:hover:not(:disabled) {
  background: #f8d7da;
}

.execution-history-view {
  min-height: 240px;
}

.execution-history-state {
  display: flex;
  min-height: 240px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #64748b;
  text-align: center;
}

.execution-history-state.error {
  color: #b42318;
}

.execution-history-state p {
  margin: 0;
}

.execution-history-spinner,
.execution-history-empty-icon {
  font-size: 30px;
}

.execution-history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.execution-history-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
  color: #64748b;
  font-size: 12px;
}

.execution-history-item {
  width: 100%;
  padding: 14px 16px;
  border: 1px solid #dbe3ea;
  border-radius: 8px;
  background: #fff;
  color: #334155;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.execution-history-item:hover:not(:disabled) {
  border-color: #1976d2;
  box-shadow: 0 2px 8px rgba(25, 118, 210, 0.14);
}

.execution-history-item.disabled {
  cursor: not-allowed;
  opacity: 0.68;
}

.execution-history-main,
.execution-history-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.execution-history-main {
  margin-bottom: 8px;
}

.execution-history-meta {
  color: #64748b;
  font-size: 12px;
}

.execution-status {
  display: inline-flex;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.status-success {
  background: #dcfce7;
  color: #166534;
}

.status-running,
.status-pending {
  background: #dbeafe;
  color: #1d4ed8;
}

.status-failed,
.status-timeout {
  background: #fee2e2;
  color: #b91c1c;
}

.status-cancelled,
.status-unknown {
  background: #e2e8f0;
  color: #475569;
}

.execution-time {
  font-weight: 500;
  color: #1f2937;
}

.execution-duration {
  color: #64748b;
  font-size: 12px;
}

.execution-error-summary {
  display: block;
  margin-top: 9px;
  padding: 8px 10px;
  border-left: 3px solid #dc2626;
  background: #fff5f5;
  color: #b42318;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-panel {
  width: min(840px, calc(100vw - 32px));
  max-height: min(90vh, 860px);
  overflow: auto;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #dbe3ea;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.2);
  padding: 18px;
}

.modal-header,
.modal-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.modal-header {
  margin-bottom: 14px;
}

.modal-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-field span {
  font-size: 12px;
  color: #475569;
}

.form-field input,
.form-field select,
.form-field textarea {
  width: 100%;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 9px 10px;
  font-size: 13px;
  color: #0f172a;
  background: white;
}

.form-field textarea {
  resize: vertical;
}

.form-wide {
  grid-column: 1 / -1;
}

.tool-picker {
  max-height: 260px;
  overflow-y: auto;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}

.tool-option {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
}

.tool-option:last-child { border-bottom: 0; }
.tool-option input { width: auto; }
.tool-option-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.tool-option-main strong { font-size: 13px; color: #0f172a; overflow-wrap: anywhere; }
.tool-option-main small, .form-hint { font-size: 12px; color: #64748b; }
.tool-disabled { font-size: 12px; color: #b42318; }

.channel-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.channel-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #334155;
}

.channel-check input,
.recipient-option input,
.switch-field input {
  width: auto;
  flex: 0 0 auto;
}

.trigger-segment {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  min-height: 36px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  overflow: hidden;
}

.trigger-segment button {
  border: 0;
  border-right: 1px solid #cbd5e1;
  background: #fff;
  color: #475569;
  cursor: pointer;
  font-size: 13px;
}

.trigger-segment button:last-child {
  border-right: 0;
}

.trigger-segment button.active {
  background: #1976d2;
  color: #fff;
}

.inline-switch {
  min-height: 34px;
}

.recipient-list {
  max-height: 190px;
  overflow-y: auto;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}

.recipient-option {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) minmax(110px, auto);
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 7px 10px;
  border-bottom: 1px solid #e2e8f0;
  cursor: pointer;
}

.recipient-option:last-child {
  border-bottom: 0;
}

.recipient-name,
.recipient-channel {
  overflow-wrap: anywhere;
}

.recipient-channel {
  color: #64748b;
  text-align: right;
}

.recipient-empty {
  padding: 14px;
  color: #64748b;
  font-size: 13px;
}

.form-error {
  border-left: 3px solid #dc3545;
  padding: 9px 12px;
  background: #fff5f5;
  color: #b42318;
  font-size: 13px;
}

.task-preview {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 14px;
  background: #f8fafc;
}

.task-preview-title {
  font-size: 12px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 6px;
}

.task-preview-body {
  font-size: 13px;
  color: #475569;
  line-height: 1.6;
}

.switch-field {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #334155;
}

.modal-actions {
  margin-top: 16px;
}

@media (max-width: 640px) {
  .management-panel {
    padding: 14px;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-wide {
    grid-column: 1;
  }

  .recipient-option {
    grid-template-columns: 20px minmax(0, 1fr);
  }

  .recipient-channel {
    grid-column: 2;
    text-align: left;
  }

  .modal-actions {
    flex-wrap: wrap;
  }
}

/* ===== 历史执行记忆弹窗 ===== */
.history-modal {
  max-width: 720px;
}

.history-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 8px;
}

.history-tabs button {
  padding: 6px 14px;
  border: none;
  background: transparent;
  color: #6c757d;
  font-size: 13px;
  cursor: pointer;
  border-radius: 4px;
}

.history-tabs button.active {
  background: #1976d2;
  color: white;
}

.history-state {
  text-align: center;
  color: #6c757d;
  padding: 24px 12px;
  font-size: 13px;
}

.history-state.error {
  color: #c2413b;
}

.history-cases {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.history-case-card {
  border: 1px solid #e3e6ea;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fafbfc;
}

.history-case-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #64748b;
}

.history-case-time,
.history-case-duration,
.history-case-trigger {
  white-space: nowrap;
}

.history-case-digest {
  margin: 6px 0 0;
  font-size: 12px;
  color: #856404;
  word-break: break-all;
}

.history-case-brief {
  margin: 6px 0 0;
  font-size: 13px;
  color: #333;
}

.history-case-findings {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: #4b5563;
}

.history-case-findings li {
  margin: 2px 0;
}

.history-case-outputs {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.history-case-ref {
  font-size: 11px;
  font-family: monospace;
  background: #eef2f7;
  border: 1px solid #d7dee8;
  border-radius: 3px;
  padding: 2px 6px;
  color: #33517a;
  word-break: break-all;
}

.history-case-errors {
  margin-top: 8px;
  font-size: 12px;
  color: #c2413b;
}

.history-case-errors p {
  margin: 2px 0;
  word-break: break-all;
}

.history-cases-more {
  text-align: center;
  font-size: 12px;
  color: #6c757d;
  margin: 8px 0 0;
}

.history-memory-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 10px;
}

.history-memory-meta .panel-btn {
  margin-left: auto;
}

.history-memory-warn {
  color: #b45309;
}

.history-memory-content {
  border: 1px solid #e3e6ea;
  border-radius: 6px;
  background: #fafbfc;
  padding: 14px;
  font-size: 13px;
  line-height: 1.6;
  max-height: 55vh;
  overflow-y: auto;
}

.history-memory-content :deep(h1) {
  font-size: 15px;
  margin: 0 0 8px;
}

.history-memory-content :deep(h2) {
  font-size: 13px;
  margin: 10px 0 6px;
}

.history-memory-content :deep(ul) {
  padding-left: 18px;
  margin: 4px 0;
}

.history-memory-editor textarea {
  width: 100%;
  box-sizing: border-box;
  font-family: monospace;
  font-size: 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  padding: 10px;
  resize: vertical;
}

.history-memory-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.history-learning-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 8px;
}

.history-learning-fields .form-hint {
  grid-column: 1 / -1;
}
</style>
