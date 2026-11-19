<template><iframe class="frame" :src="frameSrc" :title="resource.label || 'PDF 预览'" /></template>
<script setup>
import { computed } from 'vue'
import { browserResourceUrl } from '@/services/resourceUrls.js'
const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const frameSrc = computed(() => browserResourceUrl(props.contentUrl))
</script>
<style scoped>.frame { width: 100%; height: 100%; border: 0; }</style>
