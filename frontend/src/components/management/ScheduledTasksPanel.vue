<template>
  <div class="management-panel scheduled-tasks-panel">
    <div class="panel-header">
      <h3>定时任务管理</h3>
      <button class="panel-btn small primary" @click="showCreateDialog = true">
        新建广播任务
      </button>
      <button class="panel-btn small" @click="$emit('refresh-tasks')" :disabled="scheduledTasksRefreshing">
        {{ scheduledTasksRefreshing ? '刷新中...' : '刷新' }}
      </button>
      <button class="panel-btn close-btn" @click="$emit('close')">关闭</button>
    </div>

    <div class="scheduled-tasks-content">
      <!-- 统计信息 -->
      <div class="scheduled-stats-card">
        <div class="scheduled-stat-item">
          <div class="scheduled-stat-value">{{ stats.total }}</div>
          <div class="scheduled-stat-label">总任务</div>
        </div>
        <div class="scheduled-stat-item">
          <div class="scheduled-stat-value">{{ stats.running }}</div>
          <div class="scheduled-stat-label">运行中</div>
        </div>
        <div class="scheduled-stat-item">
          <div class="scheduled-stat-value">{{ stats.successRate }}%</div>
          <div class="scheduled-stat-label">成功率</div>
        </div>
      </div>

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
              <span :class="['scheduled-task-tag', getScheduledTaskTagClass(task.schedule_type)]">
                {{ getScheduledTaskLabel(task.schedule_type) }}
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
            <span class="scheduled-meta-item">⏰ {{ formatScheduledNextRun(task.next_run_at) }}</span>
            <span class="scheduled-meta-item">📋 {{ task.steps?.length || 0 }} 个步骤</span>
            <span class="scheduled-meta-item">✅ {{ task.success_runs || 0 }}/{{ task.total_runs || 0 }}</span>
            <span class="scheduled-meta-item">🧠 {{ getExecutionModeLabel(task.execution_mode) }}</span>
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
              class="scheduled-btn scheduled-btn-execute"
              @click="$emit('execute-task', task)"
              :disabled="task.executing"
              title="立即执行此任务"
            >
              {{ task.executing ? '执行中...' : '▶️ 立即执行' }}
            </button>
            <button class="scheduled-btn scheduled-btn-secondary" @click="$emit('edit-task', task)">
              编辑
            </button>
            <button class="scheduled-btn scheduled-btn-danger" @click="$emit('delete-task', task)">
              删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 新建广播任务弹窗 -->
    <div v-if="showCreateDialog" class="modal-backdrop" @click.self="showCreateDialog = false">
      <div class="modal-panel">
        <div class="modal-header">
          <h4>新建广播任务</h4>
          <button class="panel-btn small" @click="showCreateDialog = false">关闭</button>
        </div>

        <div class="modal-body">
          <div class="form-grid">
            <label class="form-field">
              <span>任务名称</span>
              <input v-model="createForm.name" type="text" placeholder="例如：每日广播提醒" />
            </label>

            <label class="form-field">
              <span>执行模式</span>
              <select v-model="createForm.execution_mode">
                <option value="assistant">assistant</option>
                <option value="expert">expert</option>
              </select>
            </label>

            <label class="form-field form-wide">
              <span>任务描述</span>
              <textarea v-model="createForm.description" rows="4" placeholder="描述广播主题、语气、目标人群"></textarea>
            </label>

            <label class="form-field">
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

            <label class="form-field" v-if="createForm.schedule_type === 'once'">
              <span>执行时间</span>
              <input v-model="createForm.run_at" type="datetime-local" />
            </label>

            <label class="form-field" v-if="createForm.schedule_type === 'interval'">
              <span>间隔分钟</span>
              <input v-model.number="createForm.interval_minutes" type="number" min="1" />
            </label>

            <label class="form-field" v-if="createForm.schedule_type === 'daily_custom'">
              <span>小时</span>
              <input v-model.number="createForm.hour" type="number" min="0" max="23" />
            </label>

            <label class="form-field" v-if="createForm.schedule_type === 'daily_custom'">
              <span>分钟</span>
              <input v-model.number="createForm.minute" type="number" min="0" max="59" />
            </label>

            <div class="form-field form-wide">
              <span>目标渠道</span>
              <div class="channel-checks">
                <label v-for="channel in channelOptions" :key="channel.value" class="channel-check">
                  <input v-model="createForm.channels" type="checkbox" :value="channel.value" />
                  <span>{{ channel.label }}</span>
                </label>
              </div>
            </div>

            <label class="form-field form-wide">
              <span>标签</span>
              <input v-model="createForm.tagsText" type="text" placeholder="广播,提醒,日报" />
            </label>
          </div>

          <div class="task-preview">
            <div class="task-preview-title">执行步骤预览</div>
            <div class="task-preview-body">
              <p>助手将先根据任务描述生成广播内容，再调用广播工具发送给选中的社交渠道。</p>
            </div>
          </div>
        </div>

        <div class="modal-actions">
          <label class="switch-field">
            <input v-model="createForm.enabled" type="checkbox" />
            <span>启用任务</span>
          </label>
          <button class="panel-btn" @click="showCreateDialog = false">取消</button>
          <button class="panel-btn primary" :disabled="creatingTask" @click="createBroadcastTask">
            {{ creatingTask ? '创建中...' : '创建任务' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'

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

const emit = defineEmits(['close', 'refresh-tasks', 'toggle-task', 'execute-task', 'edit-task', 'delete-task'])

const scheduledTasksStore = useScheduledTasksStore()
const showCreateDialog = ref(false)
const creatingTask = ref(false)

const channelOptions = [
  { label: '微信', value: 'weixin' },
  { label: 'QQ', value: 'qq' },
  { label: '钉钉', value: 'dingtalk' }
]

const createForm = ref({
  name: '广播任务',
  description: '根据任务描述生成广播内容并发送给社交用户',
  execution_mode: 'assistant',
  schedule_type: 'daily_custom',
  enabled: true,
  hour: 9,
  minute: 0,
  interval_minutes: 30,
  run_at: '',
  channels: ['weixin'],
  tagsText: 'broadcast'
})

// Methods
const getScheduledTaskLabel = (type) => {
  const labels = {
    once: '一次性',
    daily: '每天',
    weekly: '每周',
    monthly: '每月',
    cron: '自定义'
  }
  return labels[type] || type
}

const getScheduledTaskTagClass = (type) => {
  const classMap = {
    once: 'once',
    daily: 'daily',
    weekly: 'weekly',
    monthly: 'monthly',
    cron: 'cron'
  }
  return classMap[type] || 'default'
}

const getExecutionModeLabel = (mode) => {
  const labels = {
    assistant: '助手模式',
    expert: '专家模式',
    query: '问数模式',
    social: '社交模式'
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

const buildBroadcastPrompt = () => {
  const channelsText = createForm.value.channels.length > 0
    ? createForm.value.channels.join('、')
    : '所有已知社交用户'

  return [
    `你正在执行一个广播定时任务。`,
    `任务名称：${createForm.value.name}`,
    `任务描述：${createForm.value.description}`,
    `目标渠道：${channelsText}`,
    `请先根据任务描述生成一段适合广播给社交用户的内容，然后调用 broadcast_social_users 工具发送。`,
    `要求内容简洁、明确、避免提及内部实现过程。`
  ].join('\n')
}

const createBroadcastTask = async () => {
  if (!createForm.value.name.trim()) {
    alert('请填写任务名称')
    return
  }
  if (!createForm.value.description.trim()) {
    alert('请填写任务描述')
    return
  }

  creatingTask.value = true
  try {
    const payload = {
      name: createForm.value.name.trim(),
      description: createForm.value.description.trim(),
      execution_mode: createForm.value.execution_mode,
      schedule_type: createForm.value.schedule_type,
      enabled: createForm.value.enabled,
      steps: [
        {
          step_id: 'step_1',
          description: '生成并广播消息',
          agent_prompt: buildBroadcastPrompt(),
          timeout_seconds: 600,
          retry_on_failure: false
        }
      ],
      tags: createForm.value.tagsText
        .split(',')
        .map(tag => tag.trim())
        .filter(Boolean),
    }

    if (payload.schedule_type === 'once') {
      payload.run_at = createForm.value.run_at
    } else if (payload.schedule_type === 'interval') {
      payload.interval_minutes = Number(createForm.value.interval_minutes) || 30
    } else if (payload.schedule_type === 'daily_custom') {
      payload.hour = Number(createForm.value.hour) || 9
      payload.minute = Number(createForm.value.minute) || 0
    }

    await scheduledTasksStore.createTask(payload)
    showCreateDialog.value = false
    emit('refresh-tasks')
  } catch (error) {
    console.error('Failed to create broadcast task:', error)
    alert('创建失败: ' + (error.message || '未知错误'))
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

.scheduled-stats-card {
  display: flex;
  gap: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
}

.scheduled-stat-item {
  flex: 1;
  text-align: center;
  padding: 12px;
  background: white;
  border-radius: 6px;
}

.scheduled-stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #1976d2;
  margin-bottom: 4px;
}

.scheduled-stat-label {
  font-size: 12px;
  color: #6c757d;
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
</style>
