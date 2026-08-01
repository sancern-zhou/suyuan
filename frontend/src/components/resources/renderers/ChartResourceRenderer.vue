<template><div class="chart"><p v-if="loading">正在加载...</p><p v-else-if="error" class="error">{{ error }}</p><ChartPanel v-else-if="spec" :data="spec" /></div></template>
<script setup>
import { onMounted, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'
import ChartPanel from '@/components/visualization/ChartPanel.vue'
const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const spec = ref(null); const loading = ref(false); const error = ref('')
const load = async () => { loading.value = true; error.value = ''; try { const response = await authFetch(props.contentUrl); if (!response.ok) throw new Error(`HTTP ${response.status}`); spec.value = await response.json() } catch (failure) { error.value = failure?.message || '加载失败' } finally { loading.value = false } }
onMounted(load); watch(() => props.contentUrl, load)
</script>
<style scoped>.chart { height: 100%; padding: 12px; overflow: auto; box-sizing: border-box; }.error { color: #b42318; }</style>
