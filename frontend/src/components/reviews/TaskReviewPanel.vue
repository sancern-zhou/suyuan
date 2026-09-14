<template>
  <section class="task-review-panel" aria-label="任务结果人工审核">
    <p v-if="loading">正在读取审核结果…</p>
    <p v-if="error" role="alert">{{ error }} <button @click="load">刷新</button></p>
    <template v-if="review">
      <header class="review-header"><div class="review-eyebrow"><span>{{ review.category }}</span><span class="status-pill">{{ (jiangsuReviewStatus(review) || statuses[review.status]) }}</span></div><h2>{{ review.title }}</h2><p>{{ review.summary }}</p></header>
      <p class="review-reference">业务编号：{{ review.subject_id }} <span aria-hidden="true">·</span> {{ review.task_name }}</p>
      <section class="review-section conclusion"><h3>AI 结论 <span>{{ decisions[review.decision] }}</span></h3><p class="text">{{ review.comment }}</p></section>
      <section v-if="review.review_basis.length" class="review-section"><h3>审核依据</h3><ul><li v-for="basis in review.review_basis" :key="basis">{{ basis }}</li></ul></section>
      <section v-if="!compact" class="review-section"><h3>检查项</h3><article v-for="(check, index) in review.checks" :key="index"><strong>{{ check.name }} · {{ checkStatuses[check.status] }}</strong><p>{{ check.basis }}</p><p v-if="check.missing_evidence.length">缺少证据：{{ check.missing_evidence.join('、') }}</p></article></section>
      <section v-for="(section, index) in review.sections" :key="index" class="review-section"><h3>{{ section.title }}</h3><dl><template v-for="(field, n) in section.fields" :key="n"><dt>{{ field.label }}</dt><dd class="text">{{ field.value }}</dd></template></dl></section>
      <section v-if="review.actions.length" class="review-section"><h3>处置建议</h3><ol><li v-for="(action, index) in review.actions" :key="index">{{ action }}</li></ol></section>
      <section v-if="!compact && review.evidence.length" class="review-section"><h3>证据材料</h3><button class="evidence-button" v-for="(item, index) in review.evidence" :key="index" @click="download(index)">{{ item.label }}</button></section>
      <!-- 紧凑模式不展示数据影响与时间区间明细：结论文字已包含该说明；涉及剔除时的核验勾选仍保留。 -->
      <section v-if="!compact && form.data_impact.length"><h3>数据影响与时间区间</h3><fieldset v-for="(impact, index) in form.data_impact" :key="index" :disabled="!editable || submitting">
        <legend>{{ impact.pollutant }} · {{ impact.station_code }} · {{ impact.granularity }}</legend>
        <label>数据结论<select v-model="impact.decision"><option v-for="(label, value) in impactDecisions" :key="value" :value="value">{{ label }}</option></select></label>
        <label v-if="impact.start">开始时间（含时区）<input v-model="impact.start" /></label><label v-if="impact.end">结束时间（含时区）<input v-model="impact.end" /></label>
        <p>{{ impact.basis }}</p><p v-if="impact.boundary_sources.length">边界来源：{{ impact.boundary_sources.join('、') }}</p>
        <template v-if="impact.reasonableness_status"><label>合理性<select v-model="impact.reasonableness_status"><option value="pass">合理</option><option value="uncertain">不确定</option><option value="fail">不合理</option></select></label><label>合理性说明<textarea v-model="impact.reasonableness_basis" /></label></template>
      </fieldset></section>
      <form v-if="editable" @submit.prevent>
        <h3>人工处理</h3><label>最终结论<select v-model="form.decision" :disabled="submitting"><option v-for="(label, value) in decisions" :key="value" :value="value">{{ label }}</option></select></label>
        <label>审核意见<textarea v-model="form.comment" :disabled="submitting" required maxlength="4000" /></label>
        <label v-if="requiresConfirmation"><input v-model="form.intervals_confirmed" type="checkbox" :disabled="submitting" />已核验结论中涉及的数据剔除区间及合理性</label>
        <footer><template v-if="review.status === 'pending_review'"><button :disabled="submitting" @click="submit('confirm')">确认归档</button><button :disabled="submitting" @click="submit('start_disposal')">转入处置</button></template><button v-else :disabled="submitting" @click="submit('complete')">处置完成</button><button :disabled="submitting" @click="submit('reject')">退回修改</button></footer>
      </form>
      <section v-if="review.human_decision" class="review-section human-record"><h3>人工处理记录</h3><p>{{ review.human_decision.actor.username }} · {{ review.human_decision.occurred_at }}</p><p>{{ review.human_decision.comment }}</p></section>
    </template>
  </section>
</template>
<script setup>
import { jiangsuReviewStatus } from '../management/jiangsuJudgmentPresentation.js'
import { computed, ref, watch } from 'vue'
import { getTaskReview, decideTaskReview, downloadReviewEvidence } from '@/services/taskReviewsApi.js'
const props = defineProps({ reviewId: { type: String, required: true }, compact: { type: Boolean, default: false } })
const emit = defineEmits(['updated'])
const review = ref(null), loading = ref(false), submitting = ref(false), error = ref('')
const form = ref({ decision: 'approve', comment: '', data_impact: [], intervals_confirmed: false })
const statuses = { pending_review: '待人工确认', in_disposal: '待处置', archived: '已归档', rejected: '已退回' }
const decisions = { approve: '建议通过', reject: '建议退回', needs_evidence: '需要补证', needs_action: '需要处置' }
const checkStatuses = { pass: '通过', fail: '未通过', uncertain: '不确定', not_applicable: '不适用' }
const impactDecisions = { keep: '保留', partial_exclude: '部分剔除', exclude: '剔除', missing_no_delete: '缺失无需剔除', not_applicable: '不适用', needs_evidence: '需要补证' }
const editable = computed(() => ['pending_review', 'in_disposal'].includes(review.value?.status))
const requiresConfirmation = computed(() => [...(review.value?.data_impact || []), ...form.value.data_impact].some(item => ['exclude', 'partial_exclude'].includes(item.decision)))
function populate(value) {
  review.value = value
  const human = value.human_decision
  form.value = { decision: human?.decision || value.decision, comment: human?.comment || '', data_impact: structuredClone(human?.data_impact || value.data_impact), intervals_confirmed: false }
}
async function load() {
  loading.value = true; error.value = ''; review.value = null
  try { populate((await getTaskReview(props.reviewId)).review) } catch (e) { error.value = e.message } finally { loading.value = false }
}
async function submit(action) {
  if (!form.value.comment.trim()) { error.value = '请填写审核意见'; return }
  submitting.value = true; error.value = ''
  try { populate((await decideTaskReview(props.reviewId, { ...form.value, version: review.value.version, action })).review); emit('updated', review.value) }
  catch (e) { error.value = e.message } finally { submitting.value = false }
}
async function download(index) { try { await downloadReviewEvidence(props.reviewId, index) } catch (e) { error.value = e.message } }
watch(() => props.reviewId, load, { immediate: true })
</script>
<style scoped>
.task-review-panel { height:100%; overflow:auto; box-sizing:border-box; padding:clamp(18px, 3vw, 32px); color:#1f2937; background:#f8fafc; font-size:14px; line-height:1.6; }
.review-header { border-bottom:1px solid #e5e7eb; padding-bottom:20px; }
.review-eyebrow { display:flex; align-items:center; gap:10px; color:#64748b; font-size:12px; font-weight:600; letter-spacing:.04em; }
.status-pill { padding:3px 9px; border:1px solid #bfdbfe; border-radius:999px; background:#eff6ff; color:#1d4ed8; letter-spacing:0; }
h2 { margin:10px 0 6px; color:#0f172a; font-size:clamp(20px, 2vw, 26px); line-height:1.3; }
.review-header p { margin:0; color:#64748b; }
.review-reference { margin:14px 0 22px; color:#64748b; font-size:12px; }
.review-section { margin:22px 0; padding-top:2px; }
h3 { display:flex; align-items:center; gap:8px; margin:0 0 11px; color:#334155; font-size:14px; font-weight:700; }
h3::before { width:3px; height:15px; border-radius:2px; background:#2563eb; content:""; }
.conclusion { padding:16px 18px; border:1px solid #dbeafe; border-radius:8px; background:#eff6ff; }
.conclusion h3 span { color:#1d4ed8; font-weight:600; }
article, fieldset { margin:10px 0; padding:14px 16px; border:1px solid #e5e7eb; border-radius:7px; background:#fff; }
article strong { color:#334155; } article p, .human-record p { margin:5px 0 0; color:#64748b; }
label { display:block; margin:13px 0; color:#475569; font-weight:600; }
input:not([type=checkbox]), textarea, select { display:block; box-sizing:border-box; width:100%; padding:9px 11px; margin-top:6px; border:1px solid #cbd5e1; border-radius:6px; background:#fff; color:#0f172a; font:inherit; transition:border-color .15s, box-shadow .15s; }
input:not([type=checkbox]):focus, textarea:focus, select:focus { outline:0; border-color:#2563eb; box-shadow:0 0 0 3px #dbeafe; }
textarea { min-height:88px; resize:vertical; }
dl { display:grid; grid-template-columns:minmax(100px, 25%) 1fr; gap:10px 18px; margin:0; padding:14px 16px; border:1px solid #e5e7eb; border-radius:7px; background:#fff; }
dt { color:#64748b; font-weight:600; } dd { margin:0; color:#1f2937; }
ul, ol { margin:0; padding-left:20px; color:#475569; } li + li { margin-top:5px; }
.evidence-button, footer button { cursor:pointer; padding:9px 14px; margin:4px 6px 4px 0; border:1px solid #cbd5e1; border-radius:6px; background:#fff; color:#1d4ed8; font:inherit; }
form { margin-top:28px; padding:18px; border:1px solid #dbeafe; border-radius:8px; background:#fff; } form h3 { margin-bottom:14px; }
footer { display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; padding-top:14px; border-top:1px solid #e5e7eb; }
footer button:first-child { border-color:#2563eb; background:#2563eb; color:#fff; } footer button:nth-child(2) { border-color:#cbd5e1; background:#f8fafc; color:#334155; }
button:disabled { opacity:.5; cursor:wait; } [role=alert] { padding:10px 12px; border:1px solid #fecaca; border-radius:6px; background:#fef2f2; color:#b91c1c; }
@media (max-width:560px) { .task-review-panel { padding:16px; } dl { grid-template-columns:1fr; gap:3px; } dd { margin-bottom:8px; } form { padding:14px; } }
</style>
