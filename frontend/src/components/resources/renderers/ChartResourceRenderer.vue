<template>
  <div :class="['chart', { 'stationhouse-chart': isStationhouse, 'work-order-chart': isFaultWorkOrder }]">
    <p v-if="loading">正在加载...</p>
    <div v-else-if="error" class="error">
      <span>{{ error }}</span>
      <button type="button" @click="load">重试</button>
    </div>
    <StationhouseInspectionPanel v-else-if="spec && isStationhouse" :data="spec" />
    <FaultWorkOrderPanel v-else-if="spec && isFaultWorkOrder" :data="spec" />
    <ChartPanel v-else-if="spec" :data="spec" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'
import ChartPanel from '@/components/visualization/ChartPanel.vue'
import FaultWorkOrderPanel from '@/components/visualization/FaultWorkOrderPanel.vue'
import StationhouseInspectionPanel from '@/components/visualization/StationhouseInspectionPanel.vue'

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
const isFaultWorkOrder = computed(() => (
  spec.value?.type === 'fault_work_order' || props.resource?.metadata?.type === 'fault_work_order'
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
.error { display: grid; min-height: 240px; gap: 8px; place-content: center; color: #b42318; text-align: center; }
.error button { border: 0; background: transparent; color: #1976d2; cursor: pointer; }
</style>
