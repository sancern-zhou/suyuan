<template>
  <div :class="['chart', {
    'stationhouse-chart': isStationhouse,
    'work-order-chart': isFaultWorkOrder,
    'task-review-chart': isTaskReview,
    'qc-detail-chart': isQcTaskDetail,
    'review-evidence-chart': isReviewEvidence
  }]">
    <p v-if="loading">正在加载...</p>
    <div v-else-if="error" class="error">
      <span>{{ error }}</span>
      <button type="button" @click="load">重试</button>
    </div>
    <StationhouseInspectionPanel v-else-if="spec && isStationhouse" :data="spec" />
    <DeviceControlStatePanel v-else-if="spec && isDeviceControlState" :data="spec" />
    <FaultWorkOrderPanel v-else-if="spec && isFaultWorkOrder" :data="spec" />
    <TaskReviewPanel v-else-if="spec?.type === 'task_review'" :review-id="spec.data.review_id" compact />
    <QcTaskDetailPanel v-else-if="spec && isQcTaskDetail" :data="spec" />
    <WorkOrderReviewEvidencePanel v-else-if="spec && isReviewEvidence" :data="spec" />
    <ChartPanel v-else-if="spec" :data="spec" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'
import TaskReviewPanel from '@/components/reviews/TaskReviewPanel.vue'
import ChartPanel from '@/components/visualization/ChartPanel.vue'
import DeviceControlStatePanel from '@/components/visualization/DeviceControlStatePanel.vue'
import FaultWorkOrderPanel from '@/components/visualization/FaultWorkOrderPanel.vue'
import QcTaskDetailPanel from '@/components/visualization/QcTaskDetailPanel.vue'
import StationhouseInspectionPanel from '@/components/visualization/StationhouseInspectionPanel.vue'
import WorkOrderReviewEvidencePanel from '@/components/visualization/WorkOrderReviewEvidencePanel.vue'
import { isTaskReviewVisual } from '@/services/visualizationTypes.js'

const props = defineProps({
  resource: { type: Object, required: true },
  group: { type: Object, default: null },
  contentUrl: { type: String, required: true }
})

const spec = ref(null)
const loading = ref(false)
const error = ref('')
const isStationhouse = computed(() => (
  spec.value?.type === 'stationhouse' || props.resource?.metadata?.type === 'stationhouse'
))
const isDeviceControlState = computed(() => (
  spec.value?.type === 'device_control_state' || props.resource?.metadata?.type === 'device_control_state'
))
const isFaultWorkOrder = computed(() => (
  spec.value?.type === 'fault_work_order' || props.resource?.metadata?.type === 'fault_work_order'
))
const isTaskReview = computed(() => (
  isTaskReviewVisual(spec.value) || isTaskReviewVisual(props.resource)
))
const isQcTaskDetail = computed(() => (
  spec.value?.type === 'qc_task_detail' || props.resource?.metadata?.type === 'qc_task_detail'
))
const isReviewEvidence = computed(() => (
  spec.value?.type === 'work_order_review_evidence' || props.resource?.metadata?.type === 'work_order_review_evidence'
))

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await authFetch(props.contentUrl, { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    spec.value = await response.json()
  } catch (failure) {
    error.value = failure?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.contentUrl, load)
</script>

<style scoped>
.chart { height: 100%; padding: 12px; overflow: auto; box-sizing: border-box; }
.chart.stationhouse-chart { height: auto; min-height: 724px; flex: 0 0 724px; overflow-x: auto; overflow-y: visible; }
.chart.work-order-chart { height: auto; min-height: 560px; overflow: visible; }
.chart.qc-detail-chart { height: auto; min-height: 720px; flex: 0 0 auto; overflow-x: auto; overflow-y: visible; }
.chart.review-evidence-chart { height: auto; overflow-x: auto; }
.chart.task-review-chart { display: flex; height: 100%; min-height: 0; padding: 0; overflow: hidden; }
.chart.task-review-chart :deep(.task-review-panel) { flex: 1 1 auto; min-width: 0; min-height: 0; }
.error { display: grid; min-height: 240px; gap: 8px; place-content: center; color: var(--color-danger); text-align: center; }
.error button { border: 0; background: transparent; color: var(--color-primary); cursor: pointer; }
</style>
