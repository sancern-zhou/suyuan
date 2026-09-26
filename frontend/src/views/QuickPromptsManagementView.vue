<template>
  <div class="quick-prompts-management-view">
    <header class="page-header">
      <div class="header-copy">
        <div>
          <h2>常用问题管理</h2>
          <p>维护首页“快捷提问”与对话输入框上方的常用问题按钮，保存后用户下次进入即生效</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="ghost-button" type="button" :disabled="loading" @click="load">刷新</button>
        <button class="primary-button" type="button" :disabled="loading" @click="openCreateFor(activeSurface)">
          + 新增{{ activeSurface === 'home' ? '' : '（当前模式）' }}
        </button>
      </div>
    </header>

    <nav class="surface-tabs" role="tablist" aria-label="常用问题位置">
      <button
        type="button"
        role="tab"
        :aria-selected="activeSurface === 'home'"
        :class="{ active: activeSurface === 'home' }"
        @click="activeSurface = 'home'"
      >首页快捷提问（{{ homeItems.length }}）</button>
      <button
        type="button"
        role="tab"
        :aria-selected="activeSurface === 'input'"
        :class="{ active: activeSurface === 'input' }"
        @click="activeSurface = 'input'"
      >输入框常用问题（{{ inputItems.length }}）</button>
    </nav>

    <section v-if="error" class="state-panel error" role="alert">{{ error }}</section>
    <section v-if="loading" class="state-panel"><strong>加载中...</strong></section>

    <!-- 首页快捷提问：扁平列表 -->
    <template v-else-if="activeSurface === 'home'">
      <section v-if="homeItems.length === 0" class="state-panel empty">
        <strong>暂无首页快捷提问</strong>
        <span>点击“新增”创建第一个快捷提问。</span>
      </section>
      <section v-else class="prompt-list">
        <article
          v-for="(item, index) in homeItems"
          :key="item.id"
          class="prompt-card"
          :class="{ disabled: !item.enabled }"
        >
          <div class="order-tools" aria-label="排序">
            <button type="button" title="上移" :disabled="index === 0 || saving" @click="move(item, index, -1)">↑</button>
            <button type="button" title="下移" :disabled="index === homeItems.length - 1 || saving" @click="move(item, index, 1)">↓</button>
          </div>
          <div class="prompt-main">
            <div class="prompt-title-line">
              <span class="prompt-label">{{ item.label }}</span>
              <span class="prompt-mode">{{ modeLabel(item.mode) }}</span>
              <span v-if="!item.enabled" class="prompt-disabled-badge">已停用</span>
            </div>
            <p class="prompt-text" :title="item.prompt">{{ item.prompt }}</p>
            <span class="prompt-meta"><template v-if="item.updatedBy">更新人 {{ item.updatedBy }}</template><template v-if="item.updatedBy && item.updatedAt"> · </template><template v-if="item.updatedAt">{{ formatTime(item.updatedAt) }}</template></span>
          </div>
          <div class="prompt-actions">
            <label class="switch" :title="item.enabled ? '点击停用' : '点击启用'">
              <input type="checkbox" :checked="item.enabled" :disabled="saving" @change="toggleEnabled(item, $event)">
              <span class="slider" aria-hidden="true"></span>
            </label>
            <button class="ghost-button" type="button" :disabled="saving" @click="openEdit(item)">编辑</button>
            <button class="danger-button" type="button" :disabled="saving" @click="remove(item)">删除</button>
          </div>
        </article>
      </section>
    </template>

    <!-- 输入框常用问题：按智能体模式分组 -->
    <template v-else>
      <section v-if="inputGroups.length === 0" class="state-panel empty">
        <strong>暂无输入框常用问题</strong>
        <span>选择右上角“新增”为当前智能体模式添加建议问题。</span>
      </section>
      <section v-else class="mode-groups">
        <article v-for="group in inputGroups" :key="group.mode" class="mode-group">
          <header class="mode-group-header">
            <span class="prompt-mode">{{ modeLabel(group.mode) }}</span>
            <span class="mode-group-count">{{ group.items.length }} 条</span>
            <button class="ghost-button small" type="button" :disabled="saving || group.items.length >= MAX_INPUT_PER_MODE" @click="openCreateFor('input', group.mode)">+ 新增</button>
          </header>
          <div class="mode-group-body">
            <div
              v-for="(item, index) in group.items"
              :key="item.id"
              class="input-row"
              :class="{ disabled: !item.enabled }"
            >
              <div class="order-tools horizontal" aria-label="排序">
                <button type="button" title="前移" :disabled="index === 0 || saving" @click="move(item, index, -1, group)">←</button>
                <button type="button" title="后移" :disabled="index === group.items.length - 1 || saving" @click="move(item, index, 1, group)">→</button>
              </div>
              <span class="input-row-label" :title="item.prompt">{{ item.label }}</span>
              <span v-if="!item.enabled" class="prompt-disabled-badge">已停用</span>
              <span class="input-row-meta">{{ item.updatedBy || '' }}</span>
              <div class="prompt-actions">
                <label class="switch" :title="item.enabled ? '点击停用' : '点击启用'">
                  <input type="checkbox" :checked="item.enabled" :disabled="saving" @change="toggleEnabled(item, $event)">
                  <span class="slider" aria-hidden="true"></span>
                </label>
                <button class="ghost-button" type="button" :disabled="saving" @click="openEdit(item)">编辑</button>
                <button class="danger-button" type="button" :disabled="saving" @click="remove(item)">删除</button>
              </div>
            </div>
          </div>
        </article>
      </section>
    </template>

    <div v-if="dialogVisible" class="dialog-mask" @click.self="closeDialog">
      <div class="dialog" role="dialog" aria-modal="true" aria-label="编辑常用问题">
        <h3>{{ editing ? '编辑常用问题' : (form.surface === 'input' ? '新增输入框常用问题' : '新增首页快捷提问') }}</h3>
        <div class="dialog-error" v-if="dialogError" role="alert">{{ dialogError }}</div>
        <label class="field">
          <span>按钮标题（{{ form.label.length }}/{{ MAX_LABEL }}）</span>
          <input v-model="form.label" type="text" maxlength="30" placeholder="例如：今日运维态势">
        </label>
        <label class="field">
          <span v-if="form.surface === 'input'">填入输入框的内容（{{ form.prompt.length }}/{{ MAX_PROMPT }}，留空则与标题相同）</span>
          <span v-else>发送内容（{{ form.prompt.length }}/{{ MAX_PROMPT }}）</span>
          <textarea
            v-model="form.prompt"
            rows="4"
            maxlength="500"
            :placeholder="form.surface === 'input' ? '点击按钮后填入对话输入框的文字' : '点击按钮后发送给智能体的完整问题'"
          ></textarea>
        </label>
        <label class="field">
          <span>{{ form.surface === 'input' ? '所属智能体模式（必选）' : '智能体模式' }}</span>
          <select v-model="form.mode">
            <option v-if="form.surface !== 'input'" :value="null">自动路由（按内容切换）</option>
            <option v-for="mode in modes" :key="mode.id" :value="mode.id">
              {{ mode.shortName }}（{{ mode.id }}）
            </option>
          </select>
        </label>
        <div class="dialog-actions">
          <button class="ghost-button" type="button" :disabled="saving" @click="closeDialog">取消</button>
          <button class="primary-button" type="button" :disabled="saving || !formValid" @click="submitDialog">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  adminCreateQuickPrompt,
  adminDeleteQuickPrompt,
  adminListQuickPrompts,
  adminReorderQuickPrompts,
  adminUpdateQuickPrompt
} from '@/api/coordinatorConfig.js'

const MAX_HOME = 10
const MAX_INPUT_PER_MODE = 8
const MAX_LABEL = 30
const MAX_PROMPT = 500

const items = ref([])
const modes = ref([])
const activeSurface = ref('home')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const dialogVisible = ref(false)
const dialogError = ref('')
const editing = ref(null)
const form = ref({ surface: 'home', label: '', prompt: '', mode: null })

const homeItems = computed(() => items.value.filter(item => item.surface === 'home'))
const inputItems = computed(() => items.value.filter(item => item.surface === 'input'))

const inputGroups = computed(() => {
  const byMode = new Map()
  for (const item of inputItems.value) {
    if (!byMode.has(item.mode)) byMode.set(item.mode, [])
    byMode.get(item.mode).push(item)
  }
  return Array.from(byMode.entries()).map(([mode, groupItems]) => ({
    mode,
    items: groupItems
  }))
})

const formValid = computed(() => {
  if (form.value.label.trim().length === 0) return false
  if (form.value.surface === 'input' && !form.value.mode) return false
  return true
})

const modeLabel = modeId => {
  if (!modeId) return '自动路由'
  const mode = modes.value.find(item => item.id === modeId)
  // 无中文名配置的模式只显示 id，避免 "id（id）" 重复
  if (!mode || mode.shortName === mode.id) return modeId
  return `${mode.shortName}（${mode.id}）`
}

const formatTime = value => (value ? String(value).replace('T', ' ') : '')

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await adminListQuickPrompts()
    items.value = Array.isArray(data?.items) ? data.items : []
    modes.value = Array.isArray(data?.modes) ? data.modes : []
  } catch (err) {
    error.value = err.message || '加载常用问题失败'
  } finally {
    loading.value = false
  }
}

const openCreateFor = (surface, mode = null) => {
  editing.value = null
  form.value = { surface, label: '', prompt: '', mode: surface === 'input' ? mode : null }
  dialogError.value = ''
  dialogVisible.value = true
}

const openEdit = item => {
  editing.value = item
  form.value = {
    surface: item.surface,
    label: item.label,
    prompt: item.prompt,
    mode: item.mode || null
  }
  dialogError.value = ''
  dialogVisible.value = true
}

const closeDialog = () => {
  dialogVisible.value = false
  dialogError.value = ''
}

const submitDialog = async () => {
  if (!formValid.value || saving.value) return
  saving.value = true
  dialogError.value = ''
  const payload = {
    label: form.value.label.trim(),
    prompt: (form.value.prompt.trim() || form.value.label.trim()),
    mode: form.value.mode || null,
    surface: form.value.surface
  }
  try {
    if (editing.value) {
      await adminUpdateQuickPrompt(editing.value.id, payload)
    } else {
      await adminCreateQuickPrompt(payload)
    }
    dialogVisible.value = false
    await load()
  } catch (err) {
    dialogError.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}

const toggleEnabled = async (item, event) => {
  saving.value = true
  error.value = ''
  try {
    await adminUpdateQuickPrompt(item.id, { enabled: event.target.checked })
    await load()
  } catch (err) {
    error.value = err.message || '更新失败'
    await load()
  } finally {
    saving.value = false
  }
}

const move = async (item, index, offset, group = null) => {
  const siblings = group ? group.items : homeItems.value
  const next = [...siblings]
  const [moved] = next.splice(index, 1)
  next.splice(index + offset, 0, moved)
  saving.value = true
  error.value = ''
  try {
    await adminReorderQuickPrompts(next.map(row => row.id), {
      surface: item.surface,
      mode: group ? group.mode : null
    })
    await load()
  } catch (err) {
    error.value = err.message || '排序失败'
  } finally {
    saving.value = false
  }
}

const remove = async item => {
  if (!window.confirm(`确定删除常用问题“${item.label}”吗？`)) return
  saving.value = true
  error.value = ''
  try {
    await adminDeleteQuickPrompt(item.id)
    await load()
  } catch (err) {
    error.value = err.message || '删除失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style lang="scss" scoped>
.quick-prompts-management-view {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  height: 100%;
  padding: 20px 24px 32px;
  overflow-y: auto;
  background: #f5f7fa;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
}

.header-copy h2 {
  margin: 0 0 4px;
  font-size: 20px;
  color: #1f2d3d;
}

.header-copy p {
  margin: 0;
  color: #7f8fa4;
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: 10px;
  margin-left: auto;
}

.surface-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;

  button {
    padding: 8px 18px;
    border: 1px solid #d3dce6;
    border-radius: 999px;
    background: #fff;
    color: #46586e;
    font: inherit;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      border-color: #116086;
      color: #116086;
    }

    &.active {
      background: #116086;
      border-color: #116086;
      color: #fff;
      font-weight: 600;
    }
  }
}

.primary-button,
.ghost-button,
.danger-button {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid transparent;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }
}

.ghost-button.small {
  padding: 4px 10px;
  font-size: 12px;
}

.primary-button {
  background: #116086;
  color: #fff;

  &:hover:not(:disabled) {
    background: #0d4c6b;
  }
}

.ghost-button {
  background: #fff;
  border-color: #d3dce6;
  color: #46586e;

  &:hover:not(:disabled) {
    border-color: #116086;
    color: #116086;
  }
}

.danger-button {
  background: #fff;
  border-color: #efc4bd;
  color: #b44738;

  &:hover:not(:disabled) {
    background: #fff6f4;
  }
}

.state-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
  border: 1px solid #e3e9f0;
  border-radius: 12px;
  background: #fff;
  color: #7f8fa4;
  font-size: 14px;

  &.error {
    border-color: #efb7af;
    background: #fff6f4;
    color: #b44738;
    align-items: flex-start;
  }

  &.empty strong {
    color: #46586e;
  }
}

.prompt-list,
.mode-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mode-group {
  border: 1px solid #e3e9f0;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}

.mode-group-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid #eef2f6;
  background: #fafcfd;
}

.mode-group-count {
  color: #9aa7b8;
  font-size: 12px;
  margin-right: auto;
}

.mode-group-body {
  display: flex;
  flex-direction: column;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 14px;

  & + .input-row {
    border-top: 1px solid #f1f5f8;
  }

  &.disabled {
    opacity: 0.6;
  }
}

.order-tools {
  display: flex;
  flex-direction: column;
  gap: 4px;

  &.horizontal {
    flex-direction: row;
  }

  button {
    width: 26px;
    height: 24px;
    border: 1px solid #d3dce6;
    border-radius: 6px;
    background: #fff;
    color: #46586e;
    font-size: 13px;
    line-height: 1;
    cursor: pointer;

    &:hover:not(:disabled) {
      border-color: #116086;
      color: #116086;
    }

    &:disabled {
      cursor: not-allowed;
      opacity: 0.35;
    }
  }
}

.input-row-label {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #1f2d3d;
  font-size: 13px;
}

.input-row-meta {
  color: #b3bdcb;
  font-size: 11px;
  white-space: nowrap;
}

.prompt-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid #e3e9f0;
  border-radius: 12px;
  background: #fff;
  transition: opacity 0.2s;

  &.disabled {
    opacity: 0.62;
    background: #fafbfc;
  }
}

.prompt-main {
  flex: 1;
  min-width: 0;
}

.prompt-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.prompt-label {
  font-size: 15px;
  font-weight: 600;
  color: #1f2d3d;
}

.prompt-mode {
  padding: 1px 8px;
  border: 1px solid #cfe0ee;
  border-radius: 999px;
  background: #f2f8fd;
  color: #256080;
  font-size: 11px;
}

.prompt-disabled-badge {
  padding: 1px 8px;
  border: 1px solid #efc4bd;
  border-radius: 999px;
  background: #fff6f4;
  color: #b44738;
  font-size: 11px;
}

.prompt-text {
  margin: 6px 0 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #46586e;
  font-size: 13px;
}

.prompt-meta {
  color: #9aa7b8;
  font-size: 12px;
}

.prompt-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.switch {
  position: relative;
  display: inline-block;
  width: 38px;
  height: 21px;

  input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .slider {
    position: absolute;
    inset: 0;
    border-radius: 999px;
    background: #cfd8e3;
    cursor: pointer;
    transition: background 0.2s;

    &::before {
      content: '';
      position: absolute;
      width: 15px;
      height: 15px;
      left: 3px;
      top: 3px;
      border-radius: 50%;
      background: #fff;
      transition: transform 0.2s;
    }
  }

  input:checked + .slider {
    background: #116086;
  }

  input:checked + .slider::before {
    transform: translateX(17px);
  }

  input:disabled + .slider {
    cursor: not-allowed;
    opacity: 0.6;
  }
}

.dialog-mask {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 34, 51, 0.42);
}

.dialog {
  width: min(520px, 100%);
  max-height: calc(100vh - 80px);
  overflow-y: auto;
  padding: 22px 24px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 18px 44px rgba(10, 42, 58, 0.24);

  h3 {
    margin: 0 0 14px;
    font-size: 17px;
    color: #1f2d3d;
  }
}

.dialog-error {
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid #efb7af;
  border-radius: 8px;
  background: #fff6f4;
  color: #b44738;
  font-size: 13px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;

  span {
    color: #5b6b80;
    font-size: 12px;
  }

  input,
  textarea,
  select {
    width: 100%;
    padding: 9px 12px;
    border: 1px solid #d3dce6;
    border-radius: 8px;
    font: inherit;
    font-size: 13px;
    color: #1f2d3d;
    box-sizing: border-box;

    &:focus {
      outline: none;
      border-color: #116086;
      box-shadow: 0 0 0 3px rgba(17, 96, 134, 0.12);
    }
  }

  textarea {
    resize: vertical;
    min-height: 84px;
  }
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 6px;
}

@media (max-width: 720px) {
  .prompt-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .order-tools {
    flex-direction: row;
  }

  .prompt-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
