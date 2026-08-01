<template><div class="image"><img :src="contentUrl" :alt="resource.label" /></div></template>
<script setup>
defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
</script>
<style scoped>.image { display: grid; height: 100%; padding: 16px; overflow: auto; place-items: center; box-sizing: border-box; }.image img { max-width: 100%; max-height: 100%; object-fit: contain; }</style>
