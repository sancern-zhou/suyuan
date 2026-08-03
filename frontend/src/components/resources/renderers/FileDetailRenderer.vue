<template><section class="details"><button type="button" class="back" @click="emit('close')">返回文件列表</button><h3>{{ resource.label }}</h3><p v-if="!(resource.capabilities || []).includes('preview')" class="notice">该资源不支持在线预览，可下载后查看。</p><dl><dt>格式</dt><dd>{{ resource.format }}</dd><dt>状态</dt><dd>{{ resource.status }}</dd><dt>版本</dt><dd>{{ resource.version }}</dd><dt>能力</dt><dd>{{ (resource.capabilities || []).join('、') || '无' }}</dd><dt>组内资源</dt><dd>{{ group?.resources?.length || 1 }}</dd></dl><button v-if="resource.download_url" type="button" :disabled="downloading" @click="download">{{ downloading ? '下载中...' : '下载文件' }}</button><p v-if="error" class="error">{{ error }}</p><span class="content-ref">{{ contentUrl ? '内容已授权' : '无可用内容' }}</span></section></template>
<script setup>
import { ref } from 'vue'
import { downloadResource } from '@/services/resourceDownloads.js'
const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const emit = defineEmits(['close'])
const error = ref('')
const downloading = ref(false)
const download = async () => { if (downloading.value) return; downloading.value = true; error.value = ''; try { await downloadResource(props.resource) } catch (failure) { error.value = failure?.message || '下载失败' } finally { downloading.value = false } }
</script>
<style scoped>.details { padding: 24px; }.details dl { display: grid; grid-template-columns: 90px 1fr; gap: 8px; }.details dt { color: #64748b; }.details dd { margin: 0; }.details button { border: 0; background: transparent; color: #1976d2; cursor: pointer; }.details .back { padding: 0 0 12px; }.notice { color: #64748b; }.error { color: #b42318; }.content-ref { display: none; }</style>
