<template>
  <section class="human-feedback-panel" aria-labelledby="human-feedback-title">
    <header class="feedback-header">
      <div>
        <h3 id="human-feedback-title">{{ feedback?.title || '待确认问题' }}</h3>
        <p>请逐项确认是否列入正式问题清单</p>
      </div>
      <span class="feedback-count">{{ items.length }} 项</span>
    </header>

    <div class="feedback-list">
      <article v-for="item in items" :key="item.item_id" class="feedback-item">
        <div class="item-heading">
          <span class="item-kind">{{ item.kind === 'semantic_review' ? '语义' : '问题' }}</span>
          <strong>{{ item.title }}</strong>
        </div>
        <dl v-if="item.details" class="item-details">
          <template v-for="field in detailFields(item.details)" :key="field.label">
            <dt>{{ field.label }}</dt>
            <dd>{{ field.value }}</dd>
          </template>
        </dl>
        <div class="decision-group" role="group" :aria-label="`确认 ${item.title}`">
          <button
            v-for="option in decisionOptions"
            :key="option.value"
            type="button"
            :class="['decision-button', option.value, { selected: draft[item.item_id]?.decision === option.value }]"
            :aria-pressed="draft[item.item_id]?.decision === option.value"
            @click="setDecision(item.item_id, option.value)"
          >{{ option.label }}</button>
        </div>
        <textarea
          v-model="draft[item.item_id].comment"
          rows="2"
          maxlength="4000"
          placeholder="审核意见（可选）"
          aria-label="审核意见"
        ></textarea>
      </article>
    </div>

    <label class="overall-comment">
      <span>本次审核备注（可选）</span>
      <textarea v-model="overallComment" rows="2" maxlength="4000" placeholder="补充本次审核的共性说明"></textarea>
    </label>

    <p v-if="error" class="feedback-error" role="alert">{{ error }}</p>
    <p v-else-if="!allResolved" class="feedback-hint">仍有条目未选择，完成选择后才能继续生成报告。</p>
    <button class="submit-feedback" type="button" :disabled="submitting || !allResolved" @click="submit">
      {{ submitting ? '提交中...' : '提交审核并继续生成报告' }}
    </button>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  feedback: { type: Object, default: null },
  submitting: { type: Boolean, default: false },
  error: { type: String, default: '' }
})

const emit = defineEmits(['submit'])
const draft = ref({})
const overallComment = ref('')
const decisionOptions = [
  { value: 'include', label: '纳入问题' },
  { value: 'exclude', label: '排除问题' },
  { value: 'pending', label: '暂不决定' }
]
const items = computed(() => Array.isArray(props.feedback?.items) ? props.feedback.items : [])

watch(items, nextItems => {
  const next = {}
  for (const item of nextItems) {
    next[item.item_id] = draft.value[item.item_id] || { decision: 'pending', comment: '' }
  }
  draft.value = next
}, { immediate: true })

const allResolved = computed(() => items.value.length > 0 && items.value.every(item => {
  const decision = draft.value[item.item_id]?.decision
  return decision === 'include' || decision === 'exclude'
}))

const setDecision = (itemId, decision) => {
  draft.value[itemId] = { ...(draft.value[itemId] || {}), decision }
}

const remarkSummary = details => {
  const context = details.remark_context
  if (!context) {
    const text = String(details.original_remark_text || '').trim()
    return text || null
  }
  const parts = []
  for (const entry of context.entries || []) {
    const value = String(entry.value ?? '').trim()
    parts.push(`${entry.field_label || entry.field}：${value || '未填写'}`)
  }
  const text = String(context.text || '').trim()
  if (text && !parts.some(part => part.includes(text))) parts.push(text)
  return parts.length ? parts.join('；') : (context.status_label || null)
}

const detailFields = details => [
  ['工单', details.working_order_code],
  ['站点', details.station_name],
  ['表单', details.rf_form_name],
  ['规则', details.rule_id],
  ['字段', details.field_label || details.field],
  ['备注状态', details.remark_context?.status_label || details.remark_status_label],
  ['备注原文', remarkSummary(details)],
  ['复核结论', details.semantic_conclusion || details.conclusion],
  ['复核范围', Array.isArray(details.semantic_focus) && details.semantic_focus.length
    ? details.semantic_focus.join('、')
    : null]
].filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== '')
  .map(([label, value]) => ({ label, value: String(value) }))

const submit = () => {
  if (!allResolved.value || props.submitting) return
  emit('submit', {
    items: items.value.map(item => ({
      item_id: item.item_id,
      decision: draft.value[item.item_id].decision,
      comment: draft.value[item.item_id].comment || ''
    })),
    comment: overallComment.value
  })
}
</script>

<style scoped>
.human-feedback-panel { height: 100%; display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; padding: 16px; background: #fff; color: #17223b; }
.feedback-header { flex-shrink: 0; display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-bottom: 14px; border-bottom: 1px solid #edf1f7; }
h3 { margin: 0; font-size: 16px; }.feedback-header p { margin: 4px 0 0; color: #64748b; font-size: 12px; }.feedback-count { color: #1b66aa; font-size: 12px; white-space: nowrap; }
.feedback-list { flex: 1; min-height: 0; overflow-y: auto; display: grid; gap: 10px; padding: 14px 0; align-content: start; }.feedback-item { border: 1px solid #dfe6ef; border-radius: 6px; padding: 12px; }.item-heading { display: flex; align-items: flex-start; gap: 8px; line-height: 1.45; }.item-heading strong { min-width: 0; overflow-wrap: anywhere; }.item-kind { flex: 0 0 auto; padding: 2px 5px; border-radius: 3px; background: #eef4fb; color: #1b66aa; font-size: 10px; }
.item-details { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 8px; margin: 8px 0 10px; font-size: 11px; }.item-details dt { color: #7a8798; }.item-details dd { min-width: 0; margin: 0; overflow-wrap: anywhere; color: #42526b; }
.decision-group { display: flex; gap: 6px; margin-bottom: 8px; }.decision-button { flex: 1; min-height: 34px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; color: #42526b; cursor: pointer; font: inherit; font-size: 12px; }.decision-button.selected.include { border-color: #16845b; background: #eaf8f1; color: #106a49; }.decision-button.selected.exclude { border-color: #c2413b; background: #fff0ef; color: #a52e29; }.decision-button.selected.pending { border-color: #bd7b13; background: #fff7e5; color: #8c5c08; }
textarea { width: 100%; box-sizing: border-box; resize: vertical; border: 1px solid #d8e0ea; border-radius: 4px; padding: 7px 8px; color: inherit; font: inherit; font-size: 12px; }.overall-comment { flex-shrink: 0; display: grid; gap: 6px; margin-bottom: 10px; color: #42526b; font-size: 12px; }.feedback-error { flex-shrink: 0; margin: 8px 0; color: #b42318; font-size: 12px; }.feedback-hint { flex-shrink: 0; margin: 8px 0; color: #8c5c08; font-size: 12px; }.submit-feedback { flex-shrink: 0; width: 100%; min-height: 38px; border: 0; border-radius: 4px; background: #1b66aa; color: #fff; cursor: pointer; font: inherit; font-size: 13px; }.submit-feedback:disabled { background: #b7c2cf; cursor: not-allowed; }
</style>
