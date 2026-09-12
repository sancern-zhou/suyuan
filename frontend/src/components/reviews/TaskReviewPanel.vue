<template>
  <section class="task-review-panel" aria-label="任务结果人工审核">
    <p v-if="loading">正在读取审核结果…</p>
    <p v-if="error" role="alert">{{ error }} <button @click="load">刷新</button></p>
    <template v-if="review">
      <header><span>{{ review.category }} · {{ (jiangsuReviewStatus(review) || statuses[review.status]) }}</span><h2>{{ review.title }}</h2><p>{{ review.summary }}</p></header>
      <p>业务编号：{{ review.subject_id }} · {{ review.task_name }}</p>
      <section><h3>AI 结论：{{ decisions[review.decision] }}</h3><p class="text">{{ review.comment }}</p></section>
      <section v-if="review.review_basis.length"><h3>审核依据</h3><ul><li v-for="basis in review.review_basis" :key="basis">{{ basis }}</li></ul></section>
      <section><h3>检查项</h3><article v-for="(check, index) in review.checks" :key="index"><strong>{{ check.name }} · {{ checkStatuses[check.status] }}</strong><p>{{ check.basis }}</p><p v-if="check.missing_evidence.length">缺少证据：{{ check.missing_evidence.join('、') }}</p></article></section>
      <section v-for="(section, index) in review.sections" :key="index"><h3>{{ section.title }}</h3><dl><template v-for="(field, n) in section.fields" :key="n"><dt>{{ field.label }}</dt><dd class="text">{{ field.value }}</dd></template></dl></section>
      <section v-if="review.actions.length"><h3>处置建议</h3><ol><li v-for="(action, index) in review.actions" :key="index">{{ action }}</li></ol></section>
      <section v-if="review.evidence.length"><h3>证据材料</h3><button v-for="(item, index) in review.evidence" :key="index" @click="download(index)">{{ item.label }}</button></section>
      <section v-if="form.data_impact.length"><h3>数据影响与时间区间</h3><fieldset v-for="(impact, index) in form.data_impact" :key="index" :disabled="!editable || submitting">
        <legend>{{ impact.pollutant }} · {{ impact.station_code }} · {{ impact.granularity }}</legend>
        <label>数据结论<select v-model="impact.decision"><option v-for="(label, value) in impactDecisions" :key="value" :value="value">{{ label }}</option></select></label>
        <label v-if="impact.start">开始时间（含时区）<input v-model="impact.start" /></label><label v-if="impact.end">结束时间（含时区）<input v-model="impact.end" /></label>
        <p>{{ impact.basis }}</p><p v-if="impact.boundary_sources.length">边界来源：{{ impact.boundary_sources.join('、') }}</p>
        <template v-if="impact.reasonableness_status"><label>合理性<select v-model="impact.reasonableness_status"><option value="pass">合理</option><option value="uncertain">不确定</option><option value="fail">不合理</option></select></label><label>合理性说明<textarea v-model="impact.reasonableness_basis" /></label></template>
      </fieldset></section>
      <form v-if="editable" @submit.prevent>
        <h3>人工处理</h3><label>最终结论<select v-model="form.decision" :disabled="submitting"><option v-for="(label, value) in decisions" :key="value" :value="value">{{ label }}</option></select></label>
        <label>审核意见<textarea v-model="form.comment" :disabled="submitting" required maxlength="4000" /></label>
        <label v-if="requiresConfirmation"><input v-model="form.intervals_confirmed" type="checkbox" :disabled="submitting" />已核验数据剔除区间及合理性</label>
        <footer><template v-if="review.status === 'pending_review'"><button :disabled="submitting" @click="submit('confirm')">确认归档</button><button :disabled="submitting" @click="submit('start_disposal')">转入处置</button></template><button v-else :disabled="submitting" @click="submit('complete')">处置完成</button><button :disabled="submitting" @click="submit('reject')">退回修改</button></footer>
      </form>
      <section v-if="review.human_decision"><h3>人工处理记录</h3><p>{{ review.human_decision.actor.username }} · {{ review.human_decision.occurred_at }}</p><p>{{ review.human_decision.comment }}</p></section>
    </template>
  </section>
</template>
<script setup>
import { jiangsuReviewStatus } from '../management/jiangsuJudgmentPresentation.js'
import { computed, ref, watch } from 'vue'
import { getTaskReview, decideTaskReview, downloadReviewEvidence } from '@/services/taskReviewsApi.js'
const props = defineProps({ reviewId: { type: String, required: true } })
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
.task-review-panel { height:100%; overflow:auto; box-sizing:border-box; padding:24px; color:#183340; background:#fff; }
header { border-bottom:1px solid #dbe6eb; padding-bottom:16px; } h2 { font-size:22px; } h3 { font-size:16px; margin:18px 0 10px; }
section, article, fieldset { margin:14px 0; } article, fieldset { padding:14px; border:1px solid #dbe6eb; border-radius:8px; } label { display:block; margin:10px 0; }
input:not([type=checkbox]), textarea, select { display:block; box-sizing:border-box; width:100%; padding:8px; margin-top:5px; border:1px solid #b8cbd3; border-radius:5px; } textarea { min-height:80px; } button { cursor:pointer; padding:8px 14px; margin:4px; border:1px solid #adc7d0; border-radius:6px; background:#eef7fa; color:#164d66; } button:disabled { opacity:.5; cursor:wait; }
dl { display:grid; grid-template-columns:minmax(100px, 25%) 1fr; gap:10px; } dd { margin:0; } .text { white-space:pre-wrap; overflow-wrap:anywhere; } [role=alert] { color:#a42620; }
</style>
