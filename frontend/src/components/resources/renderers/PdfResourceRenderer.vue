<template><iframe class="frame" :src="contentUrl" :title="resource.label || 'PDF 预览'" /></template>
<script setup>
defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
</script>
<style scoped>.frame { width: 100%; height: 100%; border: 0; }</style>
