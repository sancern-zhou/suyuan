<template><iframe ref="frame" class="frame" :src="contentUrl" :title="resource.label || 'HTML 预览'" sandbox="allow-scripts allow-forms" @load="focusFrame" /></template>
<script setup>
import { ref } from 'vue'
defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const frame = ref(null)
const focusFrame = () => { try { frame.value?.contentWindow?.focus?.() } catch { /* cross-origin focus is best-effort */ } }
</script>
<style scoped>.frame { width: 100%; height: 100%; border: 0; }</style>
