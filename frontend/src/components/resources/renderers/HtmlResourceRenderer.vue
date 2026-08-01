<template><AuthenticatedMedia class="frame" :content-url="contentUrl" :title="resource.label || 'HTML 预览'" sandbox="allow-scripts allow-forms" /></template>
<script setup>
import AuthenticatedMedia from './AuthenticatedMedia.vue'
defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
</script>
<style scoped>.frame { width: 100%; height: 100%; border: 0; }</style>
