<template>
  <div v-if="visible" class="task-drawer-overlay" @click="closeDrawer">
    <div class="task-drawer" @click.stop>
      <div class="drawer-header">
        <h2>定时任务管理</h2>
        <div class="header-actions">
          <button
            class="refresh-btn"
            @click="handleRefresh"
            :disabled="refreshing"
            title="刷新任务列表"
          >
            <span :class="{ 'spinning': refreshing }">🔄</span>
          </button>
          <button class="close-btn" @click="closeDrawer">&times;</button>
        </div>
      </div>

      <div class="drawer-content">
        <!-- 统计信息 -->
        <div class="stats-card">
          <div class="stat-item">
            <div class="stat-value">{{ stats.total }}</div>
            <div class="stat-label">总任务</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">{{ stats.running }}</div>
            <div class="stat-label">运行中</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">{{ stats.successRate }}%</div>
            <div class="stat-label">成功率</div>
          </div>
        </div>

        <!-- 任务列表 -->
        <div class="task-list">
          <div v-if="tasks.length === 0" class="empty-state">
            <p>暂无定时任务</p>
          </div>

          <div
            v-for="task in tasks"
            :key="task.task_id"
            class="task-card"
          >
            <!-- 任务头部 -->
            <div class="task-header">
              <div class="task-title">
                <span class="task-name">{{ task.name }}</span>
                <span :class="['task-tag', getScheduleTagClass(task.schedule_type)]">
                  {{ getScheduleLabel(task.schedule_type) }}
                </span>
              </div>

              <!-- 快速开关 -->
              <label class="switch">
                <input
                  type="checkbox"
                  :checked="task.enabled"
                  @change="handleToggle(task)"
                  :disabled="task.toggling"
                />
                <span class="slider"></span>
              </label>
            </div>

            <!-- 任务描述 -->
            <div class="task-description">
              {{ task.description }}
            </div>

            <!-- 任务元信息 -->
            <div class="task-meta">
              <span class="meta-item">⏰ {{ formatNextRun(task.next_run_at) }}</span>
              <span class="meta-item">📋 {{ task.steps?.length || 0 }} 个步骤</span>
              <span class="meta-item">✅ {{ task.success_runs || 0 }}/{{ task.total_runs || 0 }}</span>
            </div>

            <!-- 标签 -->
            <div class="task-tags" v-if="task.tags && task.tags.length > 0">
              <span v-for="tag in task.tags" :key="tag" class="tag">
                {{ tag }}
              </span>
            </div>

            <!-- 操作按钮 -->
            <div class="task-actions">
              <button
                class="btn btn-execute"
                @click="executeTask(task)"
                :disabled="task.executing"
                title="立即执行此任务"
              >
                {{ task.executing ? '执行中...' : '▶️ 立即执行' }}
              </button>
              <button class="btn btn-primary" @click="editTask(task)">
                编辑
              </button>
              <button class="btn btn-secondary" @click="viewExecutions(task)">
                查看记录
              </button>
              <button class="btn btn-danger" @click="deleteTask(task)">
                删除
              </button>
            </div>
          </div>
        </div>

        <!-- 创建任务提示 -->
        <div class="info-alert">
          💡 提示：在对话中说"创建定时任务"即可快速创建
        </div>
      </div>
    </div>
  </div>

  <!-- 执行记录弹窗 -->
  <div v-if="executionDialogVisible" class="modal-overlay" @click="executionDialogVisible = false">
    <div class="modal-dialog modal-large" @click.stop>
      <div class="modal-header">
        <h3>执行记录 - {{ currentTask?.name }}</h3>
        <button class="close-btn" @click="executionDialogVisible = false">&times;</button>
      </div>
      <div class="modal-body">
        <!-- 加载中 -->
        <div v-if="loadingExecutions" class="loading-state">
          <p>加载中...</p>
        </div>

        <!-- 空状态 -->
        <div v-else-if="executions.length === 0" class="empty-state">
          <p>暂无执行记录</p>
        </div>

        <!-- 执行记录列表 -->
        <div v-else class="executions-list">
          <div
            v-for="execution in executions"
            :key="execution.execution_id"
            class="execution-item"
          >
            <!-- 执行头部 -->
            <div class="execution-header">
              <div class="execution-info">
                <span :class="['status-badge', `status-${execution.status}`]">
                  {{ getStatusLabel(execution.status) }}
                </span>
                <span class="execution-time">{{ formatTime(execution.started_at) }}</span>
              </div>
              <div class="execution-duration">
                耗时: {{ formatDuration(execution.started_at, execution.completed_at) }}
              </div>
            </div>

            <!-- 步骤列表 -->
            <div v-if="execution.steps && execution.steps.length > 0" class="steps-timeline">
              <div
                v-for="(step, index) in execution.steps"
                :key="index"
                class="timeline-item"
              >
                <div class="timeline-marker" :class="`marker-${step.status}`"></div>
                <div class="timeline-content">
                  <div class="step-header">
                    <span class="step-name">步骤 {{ index + 1 }} (迭代 {{ step.iterations || 0 }} 次)</span>
                    <span :class="['step-status', `status-${step.status}`]">
                      {{ getStatusLabel(step.status) }}
                    </span>
                  </div>

                  <!-- Agent提示词 -->
                  <div class="step-prompt">
                    <strong>任务：</strong>{{ step.agent_prompt }}
                  </div>

                  <!-- Agent思考过程 -->
                  <div v-if="step.agent_thoughts && step.agent_thoughts.length > 0" class="step-thoughts">
                    <div class="section-title">💭 思考过程</div>
                    <div v-for="(thought, idx) in step.agent_thoughts" :key="idx" class="thought-item">
                      {{ thought }}
                    </div>
                  </div>

                  <!-- 工具调用记录 -->
                  <div v-if="step.tool_calls && step.tool_calls.length > 0" class="step-tools">
                    <div class="section-title">🔧 工具调用</div>
                    <div v-for="(call, idx) in step.tool_calls" :key="idx" class="tool-call-item">
                      <div class="tool-header">
                        <span class="tool-name">{{ call.tool }}</span>
                        <span v-if="call.success !== undefined" :class="['tool-result-badge', call.success ? 'success' : 'failed']">
                          {{ call.success ? '✓ 成功' : '✗ 失败' }}
                        </span>
                      </div>
                      <div v-if="call.args && Object.keys(call.args).length > 0" class="tool-args">
                        <strong>参数：</strong>
                        <pre>{{ JSON.stringify(call.args, null, 2) }}</pre>
                      </div>
                      <div v-if="call.result" class="tool-result">
                        <strong>结果：</strong>{{ call.result }}
                      </div>
                    </div>
                  </div>

                  <!-- Agent响应 -->
                  <div v-if="step.agent_response" class="step-response">
                    <strong>最终结果：</strong>{{ step.agent_response }}
                  </div>

                  <!-- 执行时长 -->
                  <div v-if="step.started_at && step.completed_at" class="step-duration">
                    耗时：{{ formatDuration(step.started_at, step.completed_at) }}
                  </div>

                  <!-- 错误信息 -->
                  <div v-if="step.error_message" class="step-error">
                    ❌ {{ step.error_message }}
                  </div>
                </div>
              </div>
            </div>

            <!-- 错误信息 -->
            <div v-if="execution.error_message" class="execution-error">
              <strong>错误信息：</strong>{{ execution.error_message }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 编辑任务弹窗 -->
  <div v-if="editDialogVisible" class="modal-overlay" @click="editDialogVisible = false">
    <div class="modal-dialog modal-large" @click.stop>
      <div class="modal-header">
        <h3>编辑任务 - {{ editingTask?.name }}</h3>
        <button class="close-btn" @click="editDialogVisible = false">&times;</button>
      </div>
      <div class="modal-body">
        <form @submit.prevent="saveTask" class="edit-form">
          <!-- 任务名称 -->
          <div class="form-group">
            <label>任务名称</label>
            <input
              v-model="editForm.name"
              type="text"
              class="form-control"
              placeholder="例如：每日O3污染分析"
              required
            />
          </div>

          <!-- 任务描述 -->
          <div class="form-group">
            <label>任务描述</label>
            <textarea
              v-model="editForm.description"
              class="form-control"
              rows="2"
              placeholder="详细描述任务目的"
              required
            ></textarea>
          </div>

          <!-- 执行频率 -->
          <div class="form-group">
            <label>执行频率</label>
            <div class="radio-group">
              <label class="radio-label">
                <input type="radio" v-model="editForm.schedule_type" value="once" />
                <span>📅 一次性任务</span>
              </label>
              <label class="radio-label">
                <input type="radio" v-model="editForm.schedule_type" value="interval" />
                <span>⏲️ 自定义间隔</span>
              </label>
              <label class="radio-label">
                <input type="radio" v-model="editForm.schedule_type" value="daily_custom" />
                <span>🕐 每天自定义时间</span>
              </label>
            </div>
          </div>

          <!-- 灵活调度参数 -->
          <div class="form-group" v-if="editForm.schedule_type === 'once'">
            <label>执行时间</label>
            <input
              v-model="editForm.run_at"
              type="datetime-local"
              class="form-control"
              required
            />
          </div>

          <div class="form-group" v-if="editForm.schedule_type === 'interval'">
            <label>间隔时间（分钟）</label>
            <input
              v-model.number="editForm.interval_minutes"
              type="number"
              min="1"
              max="1440"
              class="form-control"
              placeholder="例如：5表示每5分钟"
              required
            />
          </div>

          <div class="form-group" v-if="editForm.schedule_type === 'daily_custom'">
            <label>每天执行时间</label>
            <div style="display: flex; gap: 8px; align-items: center;">
              <input
                v-model.number="editForm.hour"
                type="number"
                min="0"
                max="23"
                class="form-control-small"
                placeholder="时"
                required
                style="width: 80px;"
              />
              <span>:</span>
              <input
                v-model.number="editForm.minute"
                type="number"
                min="0"
                max="59"
                class="form-control-small"
                placeholder="分"
                required
                style="width: 80px;"
              />
            </div>
          </div>

          <!-- 任务步骤 -->
          <div class="form-group">
            <label>任务步骤</label>
            <div class="steps-list">
              <div
                v-for="(step, index) in editForm.steps"
                :key="index"
                class="step-item"
              >
                <div class="step-header">
                  <span class="step-number">步骤 {{ index + 1 }}</span>
                  <button
                    v-if="editForm.steps.length > 1"
                    type="button"
                    class="btn-icon btn-danger-icon"
                    @click="removeStep(index)"
                    title="删除步骤"
                  >
                    ×
                  </button>
                </div>

                <input
                  v-model="step.description"
                  type="text"
                  class="form-control"
                  placeholder="步骤描述"
                  required
                />

                <textarea
                  v-model="step.agent_prompt"
                  class="form-control"
                  rows="2"
                  placeholder="Agent指令（详细、具体）"
                  required
                ></textarea>

                <div class="step-options">
                  <label class="inline-label">
                    超时时间：
                    <input
                      v-model.number="step.timeout_seconds"
                      type="number"
                      min="60"
                      max="3600"
                      step="60"
                      class="form-control-small"
                    /> 秒
                  </label>

                  <label class="checkbox-label">
                    <input type="checkbox" v-model="step.retry_on_failure" />
                    <span>失败时重试</span>
                  </label>
                </div>
              </div>
            </div>

            <button
              type="button"
              class="btn btn-secondary btn-block"
              @click="addStep"
            >
              + 添加步骤
            </button>
          </div>

          <!-- 标签 -->
          <div class="form-group">
            <label>标签</label>
            <div class="tags-input">
              <span
                v-for="(tag, index) in editForm.tags"
                :key="index"
                class="tag-item"
              >
                {{ tag }}
                <button
                  type="button"
                  class="tag-remove"
                  @click="removeTag(index)"
                >
                  ×
                </button>
              </span>
              <input
                v-model="newTag"
                type="text"
                class="tag-input"
                placeholder="输入标签后按回车"
                @keyup.enter="addTag"
              />
            </div>
          </div>

          <!-- 按钮 -->
          <div class="form-actions">
            <button type="button" class="btn btn-secondary" @click="editDialogVisible = false">
              取消
            </button>
            <button type="submit" class="btn btn-primary" :disabled="saving">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useScheduledTasksStore } from '@/stores/scheduledTasks';

const store = useScheduledTasksStore();
const visible = defineModel({ type: Boolean, default: false });

const tasks = computed(() => store.tasks);
const stats = computed(() => store.stats);

const executionDialogVisible = ref(false);
const currentTask = ref(null);
const executions = ref([]);
const loadingExecutions = ref(false);

const editDialogVisible = ref(false);
const editingTask = ref(null);
const saving = ref(false);
const newTag = ref('');
const refreshing = ref(false);  // 刷新状态

const editForm = ref({
  name: '',
  description: '',
  schedule_type: 'daily_8am',
  steps: [],
  tags: [],
  // 灵活调度参数
  run_at: '',
  interval_minutes: null,
  hour: null,
  minute: null
});

const closeDrawer = () => {
  visible.value = false;
};

// 手动刷新任务列表
const handleRefresh = async () => {
  refreshing.value = true;
  try {
    await Promise.all([
      store.fetchTasks(),
      store.fetchStats()
    ]);
  } catch (error) {
    console.error('Failed to refresh tasks:', error);
    showMessage('刷新失败', 'error');
  } finally {
    refreshing.value = false;
  }
};

// 调度类型标签
const getScheduleLabel = (type) => {
  const labels = {
    'daily_8am': '每天8:00',
    'every_2h': '每2小时',
    'every_30min': '每30分钟',
    'once': '一次性',
    'interval': '自定义间隔',
    'daily_custom': '每天自定义'
  };
  return labels[type] || type;
};

const getScheduleTagClass = (type) => {
  const classes = {
    'daily_8am': 'tag-success',
    'every_2h': 'tag-warning',
    'every_30min': 'tag-info'
  };
  return classes[type] || '';
};

// 格式化下次运行时间
const formatNextRun = (time) => {
  if (!time) return '未安排';
  const date = new Date(time);
  const now = new Date();
  const diff = date - now;

  if (diff < 0) return '即将运行';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟后`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时后`;
  return date.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
};

// 快速开关
const handleToggle = async (task) => {
  task.toggling = true;
  try {
    if (task.enabled) {
      await store.disableTask(task.task_id);
      task.enabled = false;
      showMessage(`已禁用：${task.name}`, 'info');
    } else {
      await store.enableTask(task.task_id);
      task.enabled = true;
      showMessage(`已启用：${task.name}`, 'success');
    }
  } catch (error) {
    showMessage('操作失败', 'error');
  } finally {
    task.toggling = false;
  }
};

// 查看执行记录
const viewExecutions = async (task) => {
  currentTask.value = task;
  executionDialogVisible.value = true;
  loadingExecutions.value = true;
  executions.value = [];

  try {
    const response = await fetch(`/api/scheduled-tasks/${task.task_id}/executions?limit=20`);
    if (!response.ok) throw new Error('Failed to fetch executions');
    const data = await response.json();
    executions.value = data.executions || [];
  } catch (error) {
    console.error('Failed to fetch executions:', error);
    showMessage('获取执行记录失败', 'error');
  } finally {
    loadingExecutions.value = false;
  }
};

// 状态标签
const getStatusLabel = (status) => {
  const labels = {
    'pending': '等待中',
    'running': '运行中',
    'completed': '已完成',
    'failed': '失败',
    'timeout': '超时',
    'cancelled': '已取消'
  };
  return labels[status] || status;
};

// 格式化时间
const formatTime = (time) => {
  if (!time) return '-';
  const date = new Date(time);
  return date.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
};

// 格式化持续时间
const formatDuration = (startTime, endTime) => {
  if (!startTime) return '-';
  if (!endTime) return '进行中';

  const start = new Date(startTime);
  const end = new Date(endTime);
  const duration = Math.floor((end - start) / 1000); // 秒

  if (duration < 60) return `${duration}秒`;
  if (duration < 3600) return `${Math.floor(duration / 60)}分${duration % 60}秒`;
  return `${Math.floor(duration / 3600)}小时${Math.floor((duration % 3600) / 60)}分`;
};

// 编辑任务
const editTask = (task) => {
  editingTask.value = task;

  // 处理datetime-local格式（需要"YYYY-MM-DDTHH:mm"格式）
  let run_at = '';
  if (task.run_at) {
    const date = new Date(task.run_at);
    run_at = date.toISOString().slice(0, 16); // 转换为"YYYY-MM-DDTHH:mm"
  }

  editForm.value = {
    name: task.name,
    description: task.description,
    schedule_type: task.schedule_type,
    steps: JSON.parse(JSON.stringify(task.steps || [])),
    tags: [...(task.tags || [])],
    // 灵活调度参数
    run_at: run_at,
    interval_minutes: task.interval_minutes || null,
    hour: task.hour !== undefined ? task.hour : null,
    minute: task.minute !== undefined ? task.minute : null
  };
  editDialogVisible.value = true;
};

// 保存任务
const saveTask = async () => {
  saving.value = true;
  try {
    // 构建提交数据
    const submitData = {
      name: editForm.value.name,
      description: editForm.value.description,
      schedule_type: editForm.value.schedule_type,
      steps: editForm.value.steps,
      tags: editForm.value.tags
    };

    // 根据调度类型添加对应参数
    if (editForm.value.schedule_type === 'once' && editForm.value.run_at) {
      // 转换为后端需要的格式 "YYYY-MM-DD HH:mm:ss"
      const date = new Date(editForm.value.run_at);
      submitData.run_at = date.toISOString().slice(0, 19).replace('T', ' ');
    } else if (editForm.value.schedule_type === 'interval' && editForm.value.interval_minutes) {
      submitData.interval_minutes = editForm.value.interval_minutes;
    } else if (editForm.value.schedule_type === 'daily_custom' &&
               editForm.value.hour !== null && editForm.value.minute !== null) {
      submitData.hour = editForm.value.hour;
      submitData.minute = editForm.value.minute;
    }

    await store.updateTask(editingTask.value.task_id, submitData);
    showMessage('任务已更新', 'success');
    editDialogVisible.value = false;
  } catch (error) {
    showMessage('保存失败', 'error');
  } finally {
    saving.value = false;
  }
};

// 添加步骤
const addStep = () => {
  editForm.value.steps.push({
    step_id: `step_${editForm.value.steps.length + 1}`,
    description: '',
    agent_prompt: '',
    timeout_seconds: 300,
    retry_on_failure: false
  });
};

// 删除步骤
const removeStep = (index) => {
  if (editForm.value.steps.length > 1) {
    editForm.value.steps.splice(index, 1);
  }
};

// 添加标签
const addTag = () => {
  if (newTag.value && !editForm.value.tags.includes(newTag.value)) {
    editForm.value.tags.push(newTag.value);
    newTag.value = '';
  }
};

// 删除标签
const removeTag = (index) => {
  editForm.value.tags.splice(index, 1);
};

// 立即执行任务
const executeTask = async (task) => {
  if (!confirm(`确定立即执行任务"${task.name}"吗？`)) {
    return;
  }

  task.executing = true;
  try {
    const result = await store.executeTaskNow(task.task_id);
    showMessage(`任务已开始执行，执行ID: ${result.execution_id}`, 'success');

    // 刷新任务列表和统计信息
    await store.fetchTasks();
    await store.fetchStats();
  } catch (error) {
    console.error('Failed to execute task:', error);
    showMessage('执行失败', 'error');
  } finally {
    task.executing = false;
  }
};

// 删除任务
const deleteTask = async (task) => {
  if (!confirm(`确定删除任务"${task.name}"吗？此操作不可恢复。`)) {
    return;
  }

  try {
    await store.deleteTask(task.task_id);
    showMessage('任务已删除', 'success');
  } catch (error) {
    showMessage('删除失败', 'error');
  }
};

// 简单的消息提示
const showMessage = (message, type = 'info') => {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('show');
  }, 10);

  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => {
      document.body.removeChild(toast);
    }, 300);
  }, 3000);
};

// 初始化
onMounted(() => {
  store.fetchTasks();
  store.fetchStats();
  // 连接WebSocket实时更新（自动重连）
  store.connectWebSocket();
});

// 清理
onUnmounted(() => {
  store.disconnectWebSocket();
});
</script>

<style scoped>
.task-drawer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.task-drawer {
  width: 450px;
  max-width: 90vw;
  background: white;
  height: 100vh;
  overflow-y: auto;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.15);
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
  position: sticky;
  top: 0;
  background: white;
  z-index: 10;
}

.drawer-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.refresh-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  padding: 4px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: #f0f0f0;
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-btn .spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.close-btn {
  background: none;
  border: none;
  font-size: 28px;
  cursor: pointer;
  color: #666;
  line-height: 1;
  padding: 0;
  width: 32px;
  height: 32px;
}

.close-btn:hover {
  color: #333;
}

.drawer-content {
  padding: 20px;
}

.stats-card {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.stat-item {
  text-align: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #333;
}

.stat-label {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

.task-card {
  padding: 16px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  transition: box-shadow 0.3s;
}

.task-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.task-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.task-name {
  font-weight: 600;
  font-size: 16px;
}

.task-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.tag-success {
  background: #e7f5e7;
  color: #4caf50;
}

.tag-warning {
  background: #fff3e0;
  color: #ff9800;
}

.tag-info {
  background: #e3f2fd;
  color: #2196f3;
}

.switch {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: 0.4s;
  border-radius: 24px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.4s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: #4caf50;
}

input:checked + .slider:before {
  transform: translateX(24px);
}

input:disabled + .slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.task-description {
  color: #666;
  font-size: 14px;
  margin-bottom: 12px;
  line-height: 1.5;
}

.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.meta-item {
  font-size: 13px;
  color: #999;
}

.task-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.tag {
  padding: 2px 8px;
  background: #f0f0f0;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
}

.task-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
  white-space: nowrap;
}

.btn-secondary {
  background: #f0f0f0;
  color: #333;
}

.btn-secondary:hover {
  background: #e0e0e0;
}

.btn-danger {
  background: #f44336;
  color: white;
}

.btn-danger:hover {
  background: #d32f2f;
}

.btn-execute {
  background: #4caf50;
  color: white;
  font-weight: 500;
}

.btn-execute:hover:not(:disabled) {
  background: #45a049;
}

.btn-execute:disabled {
  background: #9e9e9e;
  cursor: not-allowed;
  opacity: 0.7;
}

.info-alert {
  margin-top: 16px;
  padding: 12px;
  background: #e3f2fd;
  border-radius: 4px;
  font-size: 14px;
  color: #1976d2;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-dialog {
  background: white;
  border-radius: 8px;
  width: 700px;
  max-width: 90vw;
  max-height: 80vh;
  overflow: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
}

.modal-body {
  padding: 20px;
}

/* Toast消息 */
:global(.toast) {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 12px 20px;
  border-radius: 4px;
  color: white;
  font-size: 14px;
  z-index: 3000;
  opacity: 0;
  transform: translateX(100%);
  transition: all 0.3s;
}

:global(.toast.show) {
  opacity: 1;
  transform: translateX(0);
}

:global(.toast-success) {
  background: #4caf50;
}

:global(.toast-error) {
  background: #f44336;
}

:global(.toast-info) {
  background: #2196f3;
}

/* 执行记录样式 */
.loading-state {
  text-align: center;
  padding: 40px;
  color: #999;
}

.executions-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.execution-item {
  padding: 16px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: #fafafa;
}

.execution-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e0e0e0;
}

.execution-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.status-completed {
  background: #e7f5e7;
  color: #4caf50;
}

.status-failed {
  background: #ffebee;
  color: #f44336;
}

.status-running {
  background: #e3f2fd;
  color: #2196f3;
}

.status-pending {
  background: #fff3e0;
  color: #ff9800;
}

.status-timeout {
  background: #fce4ec;
  color: #e91e63;
}

.status-cancelled {
  background: #f5f5f5;
  color: #9e9e9e;
}

.execution-time {
  font-size: 13px;
  color: #666;
}

.execution-duration {
  font-size: 13px;
  color: #999;
}

.execution-error {
  margin-top: 12px;
  padding: 12px;
  background: #ffebee;
  border-left: 3px solid #f44336;
  border-radius: 4px;
  font-size: 13px;
  color: #c62828;
}

/* 步骤时间线 */
.steps-timeline {
  margin-top: 12px;
  padding-left: 8px;
}

.timeline-item {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  position: relative;
}

.timeline-item:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 7px;
  top: 24px;
  bottom: -16px;
  width: 2px;
  background: #e0e0e0;
}

.timeline-marker {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
  border: 2px solid #e0e0e0;
  background: white;
}

.marker-completed {
  border-color: #4caf50;
  background: #4caf50;
}

.marker-failed {
  border-color: #f44336;
  background: #f44336;
}

.marker-running {
  border-color: #2196f3;
  background: #2196f3;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.timeline-content {
  flex: 1;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.step-name {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.step-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.step-prompt {
  margin-top: 8px;
  padding: 8px;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 13px;
  color: #333;
  line-height: 1.5;
}

.step-prompt strong {
  color: #666;
  margin-right: 4px;
}

.step-response {
  margin-top: 8px;
  padding: 8px;
  background: #e7f5e7;
  border-radius: 4px;
  font-size: 13px;
  color: #2e7d32;
  line-height: 1.5;
}

.step-response strong {
  color: #1b5e20;
  margin-right: 4px;
}

.step-duration {
  margin-top: 8px;
  font-size: 12px;
  color: #999;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  margin-top: 12px;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #e0e0e0;
}

.step-thoughts {
  margin-top: 12px;
}

.thought-item {
  padding: 8px;
  margin-bottom: 6px;
  background: #f9f9f9;
  border-left: 3px solid #2196f3;
  border-radius: 4px;
  font-size: 13px;
  color: #555;
  line-height: 1.5;
}

.step-tools {
  margin-top: 12px;
}

.tool-call-item {
  padding: 12px;
  margin-bottom: 8px;
  background: #fafafa;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
}

.tool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.tool-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  font-family: 'Courier New', monospace;
}

.tool-result-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.tool-result-badge.success {
  background: #e7f5e7;
  color: #4caf50;
}

.tool-result-badge.failed {
  background: #ffebee;
  color: #f44336;
}

.tool-args {
  margin-top: 8px;
  font-size: 12px;
  color: #666;
}

.tool-args pre {
  margin: 4px 0 0 0;
  padding: 8px;
  background: #f5f5f5;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 11px;
  line-height: 1.4;
}

.tool-result {
  margin-top: 8px;
  padding: 8px;
  background: #e7f5e7;
  border-radius: 4px;
  font-size: 13px;
  color: #2e7d32;
  line-height: 1.5;
}

.tool-result strong {
  color: #1b5e20;
  margin-right: 4px;
}

.step-error {
  margin-top: 8px;
  padding: 8px;
  background: #ffebee;
  border-radius: 4px;
  font-size: 13px;
  color: #c62828;
  line-height: 1.5;
}

.step-result {
  margin-top: 8px;
  padding: 8px;
  background: #e7f5e7;
  border-radius: 4px;
  font-size: 13px;
  color: #2e7d32;
}

/* 编辑表单样式 */
.modal-large {
  width: 700px;
  max-width: 90vw;
}

.edit-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.form-control {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-control:focus {
  outline: none;
  border-color: #1976d2;
}

.form-control-small {
  width: 80px;
  padding: 4px 8px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 13px;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.radio-label:hover {
  background: #f5f5f5;
}

.radio-label input[type="radio"] {
  margin: 0;
  cursor: pointer;
}

.radio-label span {
  font-size: 14px;
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.step-item {
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  background: #f9f9f9;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.step-number {
  font-size: 13px;
  font-weight: 600;
  color: #666;
}

.btn-icon {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-danger-icon {
  color: #f44336;
}

.btn-danger-icon:hover {
  background: #ffebee;
}

.step-options {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-top: 4px;
}

.inline-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #666;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #666;
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  cursor: pointer;
}

.btn-block {
  width: 100%;
}

.tags-input {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  min-height: 40px;
  align-items: center;
}

.tag-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: #e3f2fd;
  color: #1976d2;
  border-radius: 4px;
  font-size: 13px;
}

.tag-remove {
  background: none;
  border: none;
  color: #1976d2;
  font-size: 16px;
  cursor: pointer;
  padding: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 2px;
}

.tag-remove:hover {
  background: rgba(25, 118, 210, 0.1);
}

.tag-input {
  flex: 1;
  min-width: 120px;
  border: none;
  outline: none;
  font-size: 13px;
  padding: 4px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid #e0e0e0;
}

.btn-primary {
  background: #1976d2;
  color: white;
}

.btn-primary:hover {
  background: #1565c0;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}
</style>
