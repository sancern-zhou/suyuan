<template>
  <section class="device-control-center">
    <header class="center-header">
      <div class="heading-copy">
        <span class="eyebrow">REMOTE QUALITY CONTROL</span>
        <strong>远程质控工作区</strong>
        <span class="sub">反控全过程留痕：状态核查 → 待确认指令 → 平台下发 → 状态回读 → 审计</span>
      </div>
      <button type="button" class="close-btn" @click="$emit('close')">收起</button>
    </header>

    <div class="process-summary">
      <div class="summary-card">
        <span>目标站点</span>
        <strong>{{ stationLabel }}</strong>
      </div>
      <div class="summary-card">
        <span>当前指令</span>
        <strong>{{ commandLabel }}</strong>
      </div>
      <div class="summary-card">
        <span>过程阶段</span>
        <strong>{{ stageLabel }}</strong>
      </div>
    </div>

    <div class="stage-strip">
      <div
        v-for="stage in stages"
        :key="stage.key"
        :class="['stage', stage.state]"
      >
        <i>{{ stage.index }}</i>
        <span>{{ stage.label }}</span>
        <small>{{ stage.hint }}</small>
      </div>
    </div>

    <div class="history-section">
      <div class="section-title"><span>质控过程记录</span><b>{{ history.length }}</b></div>
      <p v-if="!history.length" class="empty-hint">
        暂无质控过程记录。在对话中读取设备状态或生成反控指令后，过程信息会实时同步到该页面。
      </p>
      <ol v-else class="timeline">
        <li v-for="entry in history" :key="entry.key" :class="`step-${entry.step || 'unknown'}`">
          <div class="node">
            <span class="badge">{{ stepBadge(entry.step) }}</span>
          </div>
          <div class="body">
            <header>
              <strong>{{ stepTitle(entry.step) }}</strong>
              <time>{{ formatTime(entry.command?.occurred_at) }}</time>
            </header>
            <p v-if="entry.command?.station?.station_name || entry.command?.station?.station_id" class="line">
              站点：{{ entry.command.station.station_name || entry.command.station.station_id }}
            </p>
            <p v-if="entry.command?.command" class="line">指令：{{ entry.command.command }}</p>
            <p v-if="entry.command?.expires_at" class="line warning">
              确认截止：{{ formatTime(entry.command.expires_at) }}（超时后需重新生成指令）
            </p>
            <p v-if="entry.step === 'blocked'" class="line warning">{{ entry.command?.reason || '该操作需前端人工确认，尚未生成可执行指令' }}</p>
            <p v-if="entry.step === 'prepare'" class="line">
              状态：<em class="ok">待用户在对话中确认</em>；确认前不会下发任何设备操作
            </p>
            <template v-if="entry.step === 'execute'">
              <p class="line">
                平台受理：<em :class="entry.command?.accepted ? 'ok' : 'fail'">{{ entry.command?.accepted ? '成功' : '失败' }}</em>
                <span v-if="entry.command?.message">（{{ entry.command.message }}）</span>
              </p>
              <p class="line">
                状态回读：{{ entry.command?.readback_available ? '已完成自动复查' : '未获得回读结果，须人工现场核查' }}
              </p>
              <p v-if="entry.command?.audit_log" class="line audit">审计留痕：{{ entry.command.audit_log }}</p>
            </template>
            <p v-if="entry.step === 'state'" class="line">
              {{ entry.command?.success ? '设备状态读取成功，已更新设备状态面板并标注反控前置条件' : `状态读取未成功：${entry.command?.message || '服务未说明原因'}` }}
            </p>
          </div>
        </li>
      </ol>
    </div>

    <footer class="center-footer">
      <p>本页面仅展示质控过程信息：指令下发必须经对话中的用户明确确认；平台受理成功不代表设备已生效，以状态回读与现场核查为准。</p>
    </footer>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, watch } from 'vue'
import {
  DEVICE_CONTROL_WORKSPACE_STEPS,
  applyDeviceControlWorkspaceCommand,
  collectDeviceControlWorkspaceCommands,
  createDeviceControlWorkspaceState,
} from '@/services/jiangsuDeviceControlWorkspace.js'

const props = defineProps({
  workspaceCommand: { type: Object, default: null },
  messages: { type: Array, default: () => [] },
})

const emit = defineEmits(['close'])

const state = reactive(createDeviceControlWorkspaceState())

const rebuildFromMessages = () => {
  const next = createDeviceControlWorkspaceState()
  for (const command of collectDeviceControlWorkspaceCommands(props.messages)) {
    Object.assign(next, applyDeviceControlWorkspaceCommand(next, command))
  }
  Object.assign(state, next)
}

onMounted(rebuildFromMessages)
watch(() => props.messages, rebuildFromMessages)

watch(() => props.workspaceCommand, command => {
  if (!command) return
  Object.assign(state, applyDeviceControlWorkspaceCommand(state, command))
})

const history = computed(() => state.history || [])
const stationLabel = computed(() => (
  state.station?.station_name || state.station?.station_id || '—'
))
const commandLabel = computed(() => state.command || '—')
const stageLabel = computed(() => stepTitle(state.latestStep))

const stages = computed(() => {
  const stepsSeen = new Set(history.value.map(item => item.step))
  const executed = history.value.find(item => item.step === DEVICE_CONTROL_WORKSPACE_STEPS.EXECUTE)?.command
  const definitions = [
    { key: 'state', label: '状态核查', hint: '读取设备状态', done: stepsSeen.has('state') },
    { key: 'prepare', label: '待确认指令', hint: '生成确认卡', done: stepsSeen.has('prepare') },
    { key: 'confirm', label: '用户确认', hint: '对话中确认', done: stepsSeen.has('execute') },
    { key: 'readback', label: '下发与回读', hint: '受理≠生效', done: Boolean(executed?.accepted && executed?.readback_available) },
    { key: 'audit', label: '审计留痕', hint: '操作记录', done: Boolean(executed?.audit_log) },
  ]
  return definitions.map((stage, index) => ({
    ...stage,
    index: index + 1,
    state: stage.done ? 'done' : (stepsSeen.size ? 'pending' : 'idle'),
  }))
})

const stepTitle = step => ({
  state: '设备状态核查',
  prepare: '生成待确认指令',
  blocked: '前置拦截（待前端确认）',
  execute: '平台下发与回读',
}[step] || '质控过程')

const stepBadge = step => ({
  state: '核查',
  prepare: '确认卡',
  blocked: '拦截',
  execute: '下发',
}[step] || '过程')

const formatTime = raw => {
  if (!raw) return '—'
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return String(raw)
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.device-control-center { display: flex; height: 100%; flex-direction: column; gap: 12px; overflow-y: auto; padding: 14px; box-sizing: border-box; background: var(--bg-muted); }
.center-header { display: flex; align-items: flex-start; justify-content: space-between; padding: 14px 16px; border: 1px solid var(--color-primary-bg-hover); border-radius: 10px; background: linear-gradient(120deg, var(--color-primary-bg), var(--bg-muted)); }
.heading-copy { display: grid; gap: 4px; }
.heading-copy .eyebrow { color: #5aa9e6; font-size: 10px; letter-spacing: 2px; }
.heading-copy strong { color: #10365c; font-size: 18px; }
.heading-copy .sub { color: #6b87a3; font-size: 11px; }
.close-btn { padding: 7px 14px; border: 1px solid #d8e9fb; border-radius: 8px; background: var(--bg-container); color: var(--text-2); font-size: 12px; cursor: pointer; }
.close-btn:hover { color: var(--color-primary); border-color: #b9d7f5; }
.process-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.summary-card { display: grid; gap: 5px; padding: 10px 12px; border: 1px solid #e3edf7; border-radius: 8px; background: var(--bg-container); }
.summary-card span { color: #7d93a9; font-size: 10px; }
.summary-card strong { overflow: hidden; color: #17364f; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.stage-strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.stage { display: grid; gap: 3px; padding: 9px 10px; border: 1px dashed #d5e3f0; border-radius: 8px; background: #fbfdff; }
.stage i { width: 18px; height: 18px; border: 1px solid #c3d6e8; border-radius: 50%; color: #7d93a9; font-size: 10px; font-style: normal; line-height: 16px; text-align: center; }
.stage span { color: #33546f; font-size: 12px; font-weight: 600; }
.stage small { color: #8fa6ba; font-size: 9px; }
.stage.done { border: 1px solid #bfe8d2; background: #f2fbf6; }
.stage.done i { border-color: #35b977; background: #35b977; color: var(--bg-container); }
.stage.done span { color: #1d7a4d; }
.stage.pending { border: 1px solid #d8e9fb; }
.history-section { flex: 1 0 auto; padding: 12px 14px; border: 1px solid #e3edf7; border-radius: 10px; background: var(--bg-container); }
.section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; color: #17364f; font-size: 13px; font-weight: 700; }
.section-title b { min-width: 22px; padding: 2px 6px; border-radius: 10px; background: #e8f2fc; color: var(--color-primary); font-size: 11px; text-align: center; }
.empty-hint { margin: 18px 0; color: #8fa6ba; font-size: 12px; text-align: center; }
.timeline { position: relative; margin: 0; padding: 0 0 0 18px; list-style: none; }
.timeline::before { position: absolute; top: 6px; bottom: 6px; left: 8px; width: 2px; background: #e3edf7; content: ""; }
.timeline li { position: relative; display: flex; gap: 12px; padding: 8px 0; }
.timeline .node { flex: none; }
.badge { display: inline-block; min-width: 44px; padding: 3px 8px; border-radius: 999px; background: var(--bg-muted); color: var(--text-2); font-size: 10px; text-align: center; }
.timeline li.step-prepare .badge { background: #e8f2fc; color: var(--color-primary); }
.timeline li.step-blocked .badge { background: #fdf3e0; color: #b97a19; }
.timeline li.step-execute .badge { background: #e6f6ec; color: #1d7a4d; }
.timeline .body { display: grid; flex: 1; gap: 4px; }
.timeline header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.timeline header strong { color: #17364f; font-size: 13px; }
.timeline time { color: #9db1c4; font-size: 10px; }
.timeline .line { margin: 0; color: var(--text-2); font-size: 11px; line-height: 17px; word-break: break-all; }
.timeline .line.warning { color: #b97a19; }
.timeline .line.audit { color: #7d93a9; }
.timeline em { font-style: normal; font-weight: 700; }
.timeline em.ok { color: #1d7a4d; }
.timeline em.fail { color: var(--color-danger); }
.center-footer { padding: 0 4px 2px; }
.center-footer p { margin: 0; color: #9db1c4; font-size: 10px; line-height: 16px; }
</style>
