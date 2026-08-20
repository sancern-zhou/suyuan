<template>
  <section class="work-order-panel">
    <header class="panel-header">
      <div class="heading">
        <span class="eyebrow">FAULT WORK ORDER · 待人工确认</span>
        <strong>{{ draft.order_title || '故障工单草案' }}</strong>
        <div class="station-meta">
          <span>站点：{{ station.station_name || '—' }}（{{ station.station_code || '—' }}）</span>
          <span v-if="station.city_name">{{ station.city_name }}{{ station.district_name || '' }}</span>
          <span>工单类型：故障工单（系统生成）</span>
        </div>
      </div>
      <div class="status-badge" :class="statusTone">{{ statusLabel }}</div>
    </header>

    <div v-if="message" class="banner" :class="messageTone">{{ message }}</div>

    <div v-if="viewState === 'confirmed'" class="result-card">
      <p class="result-title">工单已创建并推送至运维管理平台</p>
      <p class="order-code">{{ draft.result?.work_order_code || '工单号待回查（可稍后在平台按站点/标题检索）' }}</p>
      <p class="result-note" v-if="draft.result?.work_order_code">状态：待分派（ToAssign），请在运维管理平台完成分派与流转。</p>
      <p class="result-note">确认人：{{ draft.confirmed_by?.username || '—' }} · {{ formatTime(draft.confirmed_at) }}</p>
    </div>

    <div v-else-if="viewState === 'dismissed'" class="result-card muted">
      <p class="result-title">草案已放弃，未在运维平台创建工单</p>
      <p class="result-note">操作人：{{ draft.dismissed_by?.username || '—' }} · {{ formatTime(draft.dismissed_at) }}</p>
    </div>

    <form v-else class="panel-body" @submit.prevent="confirm">
      <section class="form-section">
        <h4>系统自动解析 <small>站点、设备与故障现象来自运维平台台账，无需人工填写</small></h4>
        <div class="system-grid">
          <div><span>平台站点编码</span><strong>{{ station.station_code || '—' }}</strong></div>
          <div><span>唯一编码</span><strong>{{ station.unique_code || '—' }}</strong></div>
          <div><span>触发事件</span><strong>{{ draft.event_id || '—' }}</strong></div>
          <div><span>草案生成时间</span><strong>{{ formatTime(draft.created_at) }}</strong></div>
          <div><span>证据包</span><strong>{{ draft.evidence_ref || '—' }}</strong></div>
          <div><span>有效期至</span><strong>{{ formatTime(draft.expires_at) }}</strong></div>
        </div>
      </section>

      <section class="form-section">
        <h4>工单信息 <small>标 * 项由诊断结论预填，可修改</small></h4>
        <label class="field">
          <span>工单标题 *</span>
          <input v-model="form.order_title" maxlength="100" :disabled="!editable" />
        </label>
        <div class="field-row">
          <label class="field">
            <span>紧急程度 *</span>
            <select v-model="form.urgency" :disabled="!editable">
              <option value="Normal">一般</option>
              <option value="Middle">中等</option>
              <option value="Urgent">紧急</option>
            </select>
          </label>
          <label class="field">
            <span>建议完成时间 *</span>
            <input type="datetime-local" v-model="form.plan_finish_local" :disabled="!editable" />
          </label>
        </div>
        <label class="field">
          <span>故障设备 * <em>由平台设备台账解析</em></span>
          <select v-model.number="form.device_id" :disabled="!editable">
            <option v-for="device in draft.devices" :key="device.device_id" :value="device.device_id">
              {{ device.label }}
            </option>
          </select>
        </label>
        <div class="field">
          <span>故障现象 * <em>平台固定选项，可多选</em></span>
          <div class="chips">
            <label v-for="option in faultContentOptions" :key="option.fault_content_id"
                   class="chip" :class="{ checked: form.fault_content_ids.includes(option.fault_content_id) }">
              <input type="checkbox" :value="option.fault_content_id"
                     :checked="form.fault_content_ids.includes(option.fault_content_id)"
                     :disabled="!editable"
                     @change="toggleFaultContent(option.fault_content_id)" />
              {{ option.name }}
            </label>
          </div>
        </div>
        <label class="field">
          <span>故障描述 *</span>
          <textarea v-model="form.fault_description" rows="4" :disabled="!editable"></textarea>
        </label>
        <label class="field">
          <span>处置方案 *</span>
          <textarea v-model="form.remediation_plan" rows="4" :disabled="!editable"></textarea>
        </label>
        <label class="field">
          <span>验证标准 <em>每行一条</em></span>
          <textarea v-model="form.verification_text" rows="3" :disabled="!editable"></textarea>
        </label>
        <label class="field">
          <span>工单内容 <em>系统按固定模板组合，可手工微调</em></span>
          <textarea v-model="form.order_content" rows="8" :disabled="!editable"></textarea>
          <button type="button" class="ghost-button" :disabled="!editable" @click="recomposeContent">按上方内容重新生成</button>
        </label>
      </section>

      <footer class="panel-footer">
        <p class="confirm-hint">确认后将在江苏运维管理平台创建故障工单（状态：待分派），请核对以上信息。</p>
        <div class="actions">
          <button type="button" class="dismiss-button" :disabled="submitting" @click="dismiss">放弃草案</button>
          <button type="submit" class="confirm-button" :disabled="!editable || submitting">
            {{ submitting ? '正在推送…' : '确认推送工单' }}
          </button>
        </div>
      </footer>
    </form>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'

const props = defineProps({ data: { type: Object, required: true } })

const draft = ref(props.data?.data?.draft || {})
const submitting = ref(false)
const message = ref('')
const messageTone = ref('info')

const form = reactive({
  order_title: '',
  order_content: '',
  fault_description: '',
  remediation_plan: '',
  verification_text: '',
  urgency: 'Normal',
  device_id: null,
  fault_content_ids: [],
  plan_finish_local: ''
})

const station = computed(() => draft.value.station || {})
const editable = computed(() => viewState.value === 'pending' && !expired.value)
const expired = computed(() => {
  if (draft.value.status !== 'pending') return false
  const deadline = new Date(draft.value.expires_at || '')
  return !Number.isNaN(deadline.getTime()) && deadline.getTime() < Date.now()
})
const viewState = computed(() => {
  if (draft.value.status === 'confirmed') return 'confirmed'
  if (draft.value.status === 'dismissed') return 'dismissed'
  if (draft.value.status === 'pending' && expired.value) return 'expired'
  return draft.value.status || 'pending'
})
const statusTone = computed(() => ({
  confirmed: 'good', dismissed: 'muted', expired: 'bad', pending: 'pending', failed: 'bad'
}[viewState.value] || 'pending'))
const statusLabel = computed(() => ({
  confirmed: '已创建', dismissed: '已放弃', expired: '已过期', pending: '待确认', failed: '异常'
}[viewState.value] || '待确认'))
const faultContentOptions = computed(() => {
  const options = (draft.value.fault_contents || {})[String(form.device_id)] || []
  const known = options.filter(option => option.fault_content_id !== 'other')
  return [...known, { fault_content_id: 'other', name: '其他' }]
})

const verificationStandards = () => form.verification_text
  .split('\n').map(line => line.trim()).filter(Boolean).slice(0, 8)

const composeContent = () => {
  const lines = [
    `【故障描述】${form.fault_description.trim()}`,
    `【处置方案】${form.remediation_plan.trim()}`
  ]
  const standards = verificationStandards()
  if (standards.length) {
    lines.push('【验证标准】')
    standards.forEach(standard => lines.push(`- ${standard}`))
  }
  const trace = [
    draft.value.event_id ? `事件 ${draft.value.event_id}` : '',
    draft.value.evidence_ref ? `证据包 ${draft.value.evidence_ref}` : ''
  ].filter(Boolean).join('；')
  if (trace) lines.push(`【来源】江苏站点告警自动诊断（${trace}，AI 草案经人工确认后创建）`)
  form.order_content = lines.join('\n')
}

const recomposeContent = () => { composeContent(); }

const toggleFaultContent = (id) => {
  const index = form.fault_content_ids.indexOf(id)
  if (index >= 0) form.fault_content_ids.splice(index, 1)
  else form.fault_content_ids.push(id)
}

watch(() => form.device_id, () => {
  const allowed = new Set(faultContentOptions.value.map(option => option.fault_content_id))
  form.fault_content_ids = form.fault_content_ids.filter(id => allowed.has(id))
  if (!form.fault_content_ids.length) form.fault_content_ids = ['other']
})

const hydrateForm = () => {
  form.order_title = draft.value.order_title || ''
  form.fault_description = draft.value.fault_description || ''
  form.remediation_plan = draft.value.remediation_plan || ''
  form.verification_text = (draft.value.verification_standards || []).join('\n')
  form.order_content = draft.value.order_content || ''
  form.urgency = draft.value.urgency || 'Normal'
  form.device_id = draft.value.selected_device_id || (draft.value.devices?.[0]?.device_id ?? null)
  form.fault_content_ids = [...(draft.value.selected_fault_content_ids || [])]
  const raw = String(draft.value.plan_finish_time || '').replace(' ', 'T')
  form.plan_finish_local = raw.slice(0, 16)
}

const formatTime = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

const notify = (text, tone) => { message.value = text; messageTone.value = tone }

const refreshDraft = async () => {
  const draftId = draft.value.draft_id
  if (!draftId) return
  try {
    const response = await authFetch(`/api/jiangsu/work-order-drafts/${draftId}`, { cache: 'no-store' })
    if (response.ok) {
      const payload = await response.json()
      if (payload?.draft) draft.value = payload.draft
    }
  } catch { /* fall back to the embedded spec */ }
}

const confirm = async () => {
  if (!form.order_title.trim()) return notify('请填写工单标题', 'error')
  if (!form.fault_content_ids.length) return notify('请至少选择一个故障现象', 'error')
  if (!form.plan_finish_local) return notify('请选择建议完成时间', 'error')
  submitting.value = true
  message.value = ''
  try {
    const response = await authFetch(`/api/jiangsu/work-order-drafts/${draft.value.draft_id}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        edits: {
          order_title: form.order_title.trim(),
          order_content: form.order_content.trim() || null,
          fault_description: form.fault_description.trim(),
          remediation_plan: form.remediation_plan.trim(),
          verification_standards: verificationStandards(),
          urgency: form.urgency,
          device_id: form.device_id,
          fault_content_ids: form.fault_content_ids,
          plan_finish_time: form.plan_finish_local.replace('T', ' ') + (form.plan_finish_local.length <= 16 ? ':00' : '')
        }
      })
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = typeof payload?.detail === 'string' ? payload.detail : '推送失败，请稍后重试'
      return notify(detail, 'error')
    }
    draft.value = payload.draft || { ...draft.value, status: 'confirmed', result: { work_order_code: payload.work_order_code } }
    notify('工单已创建并推送至运维管理平台', 'success')
  } catch (failure) {
    notify(failure?.message || '网络异常，推送失败', 'error')
  } finally {
    submitting.value = false
  }
}

const dismiss = async () => {
  submitting.value = true
  message.value = ''
  try {
    const response = await authFetch(`/api/jiangsu/work-order-drafts/${draft.value.draft_id}/dismiss`, { method: 'POST' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = typeof payload?.detail === 'string' ? payload.detail : '操作失败，请稍后重试'
      return notify(detail, 'error')
    }
    draft.value = payload.draft || { ...draft.value, status: 'dismissed' }
  } catch (failure) {
    notify(failure?.message || '网络异常，操作失败', 'error')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await refreshDraft()
  if (['confirmed', 'dismissed'].includes(viewState.value)) return
  hydrateForm()
})
</script>

<style scoped>
.work-order-panel { width: 100%; max-width: 860px; margin: 0 auto; overflow: hidden; border: 1px solid #1768ac; border-radius: 10px; background: #031b37; color: #d9efff; font-family: "Microsoft YaHei", sans-serif; }
.panel-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 22px; border-bottom: 1px solid rgba(69, 178, 255, .68); background: linear-gradient(90deg, #063e76, #075fa8 54%, #073d72); }
.heading { display: grid; gap: 5px; min-width: 0; }
.eyebrow { color: #5bc7ff; font-size: 10px; letter-spacing: 2px; }
.heading strong { color: #fff; font-size: 18px; line-height: 1.35; }
.station-meta { display: flex; flex-wrap: wrap; gap: 4px 16px; color: #a8d7f8; font-size: 11px; }
.status-badge { flex: none; padding: 5px 14px; border: 1px solid; border-radius: 14px; font-size: 12px; font-weight: 700; }
.status-badge.pending { border-color: #ffbd39; color: #ffbd39; }
.status-badge.good { border-color: #37e57b; color: #37e57b; }
.status-badge.bad { border-color: #ff694b; color: #ff694b; }
.status-badge.muted { border-color: #7ca6c1; color: #7ca6c1; }
.banner { margin: 12px 22px 0; padding: 9px 14px; border-radius: 6px; font-size: 12px; }
.banner.info { border: 1px solid rgba(69, 178, 255, .5); background: rgba(11, 62, 105, .6); }
.banner.success { border: 1px solid rgba(55, 229, 123, .5); background: rgba(10, 80, 50, .5); color: #8df0b4; }
.banner.error { border: 1px solid rgba(255, 105, 75, .55); background: rgba(96, 30, 24, .5); color: #ffb3a3; }
.result-card { display: grid; gap: 10px; margin: 18px 22px 24px; padding: 22px; place-items: center; border: 1px solid rgba(55, 229, 123, .4); border-radius: 8px; background: rgba(10, 80, 50, .28); text-align: center; }
.result-card.muted { border-color: rgba(124, 166, 193, .4); background: rgba(20, 40, 64, .4); }
.result-title { color: #fff; font-size: 15px; }
.order-code { color: #44baff; font-size: 22px; font-weight: 800; letter-spacing: 1px; }
.result-note { color: #8ecaf1; font-size: 12px; }
.panel-body { padding: 6px 22px 20px; }
.form-section { margin-top: 14px; }
.form-section h4 { display: flex; align-items: baseline; gap: 10px; margin: 0 0 10px; border-bottom: 1px solid rgba(78, 173, 238, .42); padding-bottom: 7px; color: #e8f7ff; font-size: 13px; }
.form-section h4::before { width: 3px; height: 13px; background: #1ac8ff; box-shadow: 0 0 9px #1ac8ff; content: ""; }
.form-section h4 small { color: #83b5d8; font-size: 10px; font-weight: 400; }
.system-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.system-grid > div { display: grid; gap: 4px; padding: 8px 11px; border: 1px solid rgba(45, 150, 216, .42); border-radius: 4px; background: rgba(4, 48, 85, .78); }
.system-grid span { overflow: hidden; color: #6dc9f5; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.system-grid strong { overflow: hidden; color: #fff; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.field { display: grid; gap: 5px; margin-top: 10px; }
.field > span { color: #a8d7f8; font-size: 11px; }
.field > span em { margin-left: 6px; color: #6f9cba; font-size: 9px; font-style: normal; }
.field input, .field select, .field textarea { width: 100%; padding: 7px 10px; border: 1px solid rgba(69, 178, 255, .38); border-radius: 4px; background: rgba(3, 28, 55, .92); box-sizing: border-box; color: #e8f7ff; font-family: inherit; font-size: 12px; }
.field textarea { resize: vertical; line-height: 1.6; }
.field input:focus, .field select:focus, .field textarea:focus { border-color: #1ac8ff; outline: none; }
.field input:disabled, .field select:disabled, .field textarea:disabled { opacity: .55; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.chips { display: flex; flex-wrap: wrap; gap: 7px; }
.chip { padding: 4px 12px; border: 1px solid rgba(69, 178, 255, .4); border-radius: 13px; background: rgba(3, 28, 55, .92); color: #a8d7f8; cursor: pointer; font-size: 11px; user-select: none; }
.chip input { display: none; }
.chip.checked { border-color: #1ac8ff; background: rgba(26, 200, 255, .16); color: #fff; }
.ghost-button { justify-self: start; margin-top: 6px; padding: 4px 12px; border: 1px solid rgba(69, 178, 255, .5); border-radius: 4px; background: transparent; color: #5bc7ff; cursor: pointer; font-size: 11px; }
.ghost-button:hover { background: rgba(26, 200, 255, .12); }
.panel-footer { display: grid; gap: 10px; margin-top: 18px; padding-top: 14px; border-top: 1px solid rgba(78, 173, 238, .42); }
.confirm-hint { color: #8ecaf1; font-size: 11px; }
.actions { display: flex; justify-content: flex-end; gap: 10px; }
.dismiss-button { padding: 8px 18px; border: 1px solid rgba(124, 166, 193, .5); border-radius: 5px; background: transparent; color: #a8d7f8; cursor: pointer; font-size: 12px; }
.dismiss-button:hover { background: rgba(124, 166, 193, .12); }
.confirm-button { padding: 8px 24px; border: 0; border-radius: 5px; background: linear-gradient(90deg, #0d7fd6, #1ac8ff); color: #fff; cursor: pointer; font-size: 12px; font-weight: 700; }
.confirm-button:disabled, .dismiss-button:disabled { opacity: .5; cursor: not-allowed; }
</style>
