<template><div class="sheet"><p v-if="loading">正在加载...</p><p v-else-if="error" class="error">{{ error }}</p><table v-else><tbody><tr v-for="(row, rowIndex) in rows" :key="rowIndex"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody></table></div></template>
<script setup>
import { onMounted, ref, watch } from 'vue'
import * as XLSX from 'xlsx'
import { authFetch } from '@/auth/http.js'
const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const rows = ref([]); const loading = ref(false); const error = ref('')
const load = async () => { loading.value = true; error.value = ''; try { const response = await authFetch(props.contentUrl); if (!response.ok) throw new Error(`HTTP ${response.status}`); const workbook = XLSX.read(await response.arrayBuffer(), { type: 'array' }); rows.value = XLSX.utils.sheet_to_json(workbook.Sheets[workbook.SheetNames[0]], { header: 1 }) } catch (failure) { error.value = failure?.message || '加载失败' } finally { loading.value = false } }
onMounted(load); watch(() => props.contentUrl, load)
</script>
<style scoped>.sheet { height: 100%; padding: 12px; overflow: auto; box-sizing: border-box; }table { border-collapse: collapse; }td { min-width: 90px; padding: 6px 8px; border: 1px solid #dfe5ec; }.error { color: #b42318; }</style>
