<template><div class="scroll"><p v-if="loading">正在加载...</p><p v-else-if="error" class="error">{{ error }}</p><MarkdownRenderer v-else :content="content" /></div></template>
<script setup>
import { onMounted, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const content = ref(''); const loading = ref(false); const error = ref('')
const load = async () => { loading.value = true; error.value = ''; try { const response = await authFetch(props.contentUrl); if (!response.ok) throw new Error(`HTTP ${response.status}`); content.value = await response.text() } catch (failure) { error.value = failure?.message || '加载失败' } finally { loading.value = false } }
onMounted(load); watch(() => props.contentUrl, load)
</script>
<style scoped>.scroll { height: 100%; padding: 18px; overflow: auto; box-sizing: border-box; }.error { color: #b42318; }</style>
