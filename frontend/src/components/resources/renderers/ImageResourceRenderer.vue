<template><div class="image"><AuthenticatedMedia as="img" :content-url="contentUrl" :title="resource.label" /></div></template>
<script setup>
import AuthenticatedMedia from './AuthenticatedMedia.vue'
defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
</script>
<style scoped>.image { display: grid; height: 100%; padding: 16px; overflow: auto; place-items: center; box-sizing: border-box; }.image img { max-width: 100%; max-height: 100%; object-fit: contain; }</style>
