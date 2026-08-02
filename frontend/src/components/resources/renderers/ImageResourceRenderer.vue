<template><div class="image"><p v-if="loading">正在加载...</p><div v-else-if="error" class="error"><span>{{ error }}</span><button type="button" @click="retry">重试</button></div><img v-show="!loading && !error" :key="retryVersion" :src="retryUrl" :alt="resource.label" @load="loading = false" @error="handleError" /></div></template>
<script setup>
import { computed, ref, watch } from 'vue'
const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const loading = ref(true)
const error = ref('')
const retryVersion = ref(0)
const retryUrl = computed(() => {
  if (!retryVersion.value) return props.contentUrl
  const separator = props.contentUrl.includes('?') ? '&' : '?'
  return `${props.contentUrl}${separator}retry=${retryVersion.value}`
})
const handleError = () => { loading.value = false; error.value = '图片加载失败' }
const retry = () => { error.value = ''; loading.value = true; retryVersion.value += 1 }
watch(() => props.contentUrl, () => { error.value = ''; loading.value = true; retryVersion.value = 0 })
</script>
<style scoped>.image { display: grid; height: 100%; padding: 16px; overflow: auto; place-items: center; box-sizing: border-box; }.image img { max-width: 100%; max-height: 100%; object-fit: contain; }.error { display: grid; gap: 8px; place-items: center; color: #b42318; }.error button { border: 0; background: transparent; color: #1976d2; cursor: pointer; }</style>
