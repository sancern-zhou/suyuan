<template>
  <p v-if="loading" class="state">正在加载预览...</p>
  <p v-else-if="error" class="state error">{{ error }}</p>
  <img v-else-if="as === 'img'" :src="objectUrl" :alt="title" />
  <iframe v-else :src="objectUrl" :title="title" :sandbox="sandbox" />
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'

const props = defineProps({
  contentUrl: { type: String, required: true },
  title: { type: String, default: '资源预览' },
  as: { type: String, default: 'iframe' },
  sandbox: { type: String, default: undefined }
})

const objectUrl = ref('')
const loading = ref(false)
const error = ref('')
let generation = 0

const revoke = () => {
  if (!objectUrl.value) return
  URL.revokeObjectURL(objectUrl.value)
  objectUrl.value = ''
}

watch(() => props.contentUrl, async (url) => {
  const current = ++generation
  revoke()
  error.value = ''
  if (!url) return
  loading.value = true
  try {
    const response = await authFetch(url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const nextUrl = URL.createObjectURL(await response.blob())
    if (current !== generation) {
      URL.revokeObjectURL(nextUrl)
      return
    }
    objectUrl.value = nextUrl
  } catch (failure) {
    if (current === generation) error.value = failure?.message || '预览加载失败'
  } finally {
    if (current === generation) loading.value = false
  }
}, { immediate: true })

onBeforeUnmount(() => {
  generation += 1
  revoke()
})
</script>

<style scoped>
iframe { width: 100%; height: 100%; border: 0; }
img { max-width: 100%; max-height: 100%; object-fit: contain; }
.state { display: grid; height: 100%; margin: 0; place-content: center; color: #64748b; }
.error { color: #b42318; }
</style>
