<template><section class="details"><h3>{{ resource.label }}</h3><dl><dt>格式</dt><dd>{{ resource.format }}</dd><dt>状态</dt><dd>{{ resource.status }}</dd><dt>版本</dt><dd>{{ resource.version }}</dd><dt>能力</dt><dd>{{ (resource.capabilities || []).join('、') || '无' }}</dd><dt>组内资源</dt><dd>{{ group?.resources?.length || 1 }}</dd></dl><button v-if="resource.download_url" type="button" :disabled="downloading" @click="download">{{ downloading ? '下载中...' : '下载文件' }}</button><p v-if="error" class="error">{{ error }}</p><span class="content-ref">{{ contentUrl ? '内容已授权' : '无可用内容' }}</span></section></template>
<script setup>
import { ref } from 'vue'
import { downloadResource } from '@/services/resourceDownloads.js'
const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const error = ref('')
const downloading = ref(false)
const download = async () => { if (downloading.value) return; downloading.value = true; error.value = ''; try { await downloadResource(props.resource) } catch (failure) { error.value = failure?.message || '下载失败' } finally { downloading.value = false } }
</script>
<style scoped>.details { padding: 24px; }.details dl { display: grid; grid-template-columns: 90px 1fr; gap: 8px; }.details dt { color: #64748b; }.details dd { margin: 0; }.details button { border: 0; background: transparent; color: #1976d2; cursor: pointer; }.error { color: #b42318; }.content-ref { display: none; }</style>
