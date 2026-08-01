<template><div class="slides"><img v-for="page in pages" :key="page.resource_id" :src="page.content_url" :alt="page.label" /><p v-if="!pages.length">{{ resource.label }} 暂无页面预览</p></div></template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const pages = computed(() => (props.group?.resources || []).filter(item => item.status === 'active' && item.renderer === 'image'))
</script>
<style scoped>.slides { height: 100%; padding: 16px; overflow: auto; box-sizing: border-box; }.slides :deep(img) { display: block; width: min(100%, 1100px); margin: 0 auto 16px; box-shadow: 0 2px 12px #0002; }</style>
