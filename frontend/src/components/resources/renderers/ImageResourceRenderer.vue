<template>
  <div class="image">
    <p v-if="loading">正在加载...</p>
    <div v-else-if="error" class="error">
      <span>{{ error }}</span>
      <button type="button" @click="retry">重试</button>
    </div>
    <button
      v-show="!loading && !error"
      type="button"
      class="image-preview-trigger"
      title="点击放大"
      :aria-label="`放大查看：${resource.label || '图片'}`"
      @click="previewVisible = true"
    >
      <img
        :key="`${resource.resource_id}:${resource.version}:${retryVersion}`"
        :src="retryUrl"
        :alt="resource.label"
        @load="loading = false"
        @error="handleError"
      />
    </button>
    <ImageLightbox v-model:visible="previewVisible" :images="previewImages" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import ImageLightbox from '@/components/ImageLightbox.vue'

const props = defineProps({ resource: { type: Object, required: true }, group: { type: Object, default: null }, contentUrl: { type: String, required: true } })
const loading = ref(true)
const error = ref('')
const retryVersion = ref(0)
const previewVisible = ref(false)
const retryUrl = computed(() => {
  if (!retryVersion.value) return props.contentUrl
  const separator = props.contentUrl.includes('?') ? '&' : '?'
  return `${props.contentUrl}${separator}retry=${retryVersion.value}`
})
const previewImages = computed(() => [{ src: retryUrl.value, alt: props.resource.label || '图片' }])
const handleError = () => { loading.value = false; error.value = '图片加载失败'; previewVisible.value = false }
const retry = () => { error.value = ''; loading.value = true; retryVersion.value += 1 }
watch(() => [props.contentUrl, props.resource.resource_id, props.resource.version], () => {
  previewVisible.value = false
  error.value = ''
  loading.value = true
  retryVersion.value = 0
})
</script>

<style scoped>
.image { display: grid; height: 100%; padding: 16px; overflow: auto; place-items: center; box-sizing: border-box; }
.image-preview-trigger { display: grid; width: 100%; height: 100%; min-height: 0; padding: 0; border: 0; background: transparent; place-items: center; cursor: zoom-in; }
.image-preview-trigger:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.image img { max-width: 100%; max-height: 100%; object-fit: contain; }
.error { display: grid; gap: 8px; place-items: center; color: var(--color-danger); }
.error button { border: 0; background: transparent; color: var(--color-primary); cursor: pointer; }
</style>
