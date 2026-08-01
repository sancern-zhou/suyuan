<template><div class="board"><p v-if="loading">正在加载...</p><p v-else-if="error" class="error">{{ error }}</p><DrawioBoardPanel v-else :xml="xml" :title="resource.label" /></div></template>
<script setup>
import { onMounted, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'
import DrawioBoardPanel from '@/components/board/DrawioBoardPanel.vue'
const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const xml = ref(''); const loading = ref(false); const error = ref('')
const load = async () => { loading.value = true; error.value = ''; try { const response = await authFetch(props.contentUrl); if (!response.ok) throw new Error(`HTTP ${response.status}`); xml.value = await response.text() } catch (failure) { error.value = failure?.message || '加载失败' } finally { loading.value = false } }
onMounted(load); watch(() => props.contentUrl, load)
</script>
<style scoped>.board { height: 100%; }.error { color: #b42318; }</style>
