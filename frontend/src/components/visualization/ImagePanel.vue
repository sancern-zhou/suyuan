<template>
  <div class="image-panel">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="image-loading">
      <div class="loading-spinner"></div>
      <p>加载图片中...</p>
    </div>
    <!-- 图片显示 -->
    <img
      v-else-if="imageSrc && !loadError"
      :src="imageSrc"
      :alt="alt"
      @load="onLoad"
      @error="onError"
    />
    <!-- 加载失败 -->
    <div v-else-if="loadError" class="image-error">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
      <p>图片加载失败</p>
    </div>
    <!-- 空占位符 -->
    <div v-else class="image-placeholder">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
        <circle cx="8.5" cy="8.5" r="1.5"></circle>
        <path d="M21 15l-5-5L5 21"></path>
      </svg>
      <p>图片展示</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed } from 'vue'

const props = defineProps({
  src: {
    type: String,
    default: ''
  },
  alt: {
    type: String,
    default: '分析图片'
  }
})

const emit = defineEmits(['ready'])

// 图片源 - 支持两种格式：
// 1. 完整 data URL: "data:image/png;base64,..."
// 2. 占位符格式: "[IMAGE:image_id]"
const imageSrc = ref('')
const isLoading = ref(false)
const loadError = ref(false)

// 用于等待图片加载完成的 Promise
let imageLoadPromise = null

// 暴露方法给父组件（用于截图捕获）
const getChartImage = async () => {
  // 如果图片已加载且没有错误，直接返回数据URL
  if (imageSrc.value && !loadError.value) {
    return imageSrc.value
  }

  // 如果正在加载中，等待加载完成
  if (isLoading.value) {
    return new Promise((resolve) => {
      const unwatch = watch(isLoading, (loading) => {
        if (!loading) {
          unwatch()
          resolve(imageSrc.value || null)
        }
      })
    })
  }

  // 如果还没开始加载（isLoading为false且imageSrc为空），可能是组件刚创建
  // 主动触发加载并等待
  if (!imageSrc.value && !isLoading.value && !loadError.value) {
    const src = props.src
    if (isImagePlaceholder(src)) {
      const imageId = src.slice(7, -1)
      // 重新触发加载
      await fetchImage(imageId)
      return imageSrc.value || null
    }
  }

  return null
}

// 暴露方法给父组件
defineExpose({
  getChartImage
})

// 检测是否是 [IMAGE:xxx] 格式的占位符
const isImagePlaceholder = (src) => {
  return typeof src === 'string' && src.startsWith('[IMAGE:') && src.endsWith(']')
}

// 检测是否是 /api/image/xxx 格式的URL
const isApiImageUrl = (src) => {
  return typeof src === 'string' && src.startsWith('/api/image/')
}

// 获取完整的后端API基础URL
const getBaseUrl = () => {
  return import.meta.env.PROD
    ? window.location.origin
    : 'http://localhost:8000'
}

// 补充URL基础地址（处理相对路径）
const resolveImageUrl = (src) => {
  if (src.startsWith('http')) {
    return src  // 已是完整URL
  }
  if (src.startsWith('/api/image/')) {
    return `${getBaseUrl()}${src}`  // 补充后端基础URL
  }
  return src  // 其他情况（如data URL）
}

// 从API获取图片数据
const fetchImage = async (imageId) => {
  try {
    isLoading.value = true
    loadError.value = false
    const response = await fetch(`/api/image/${imageId}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const data = await response.json()
    if (data.data) {
      imageSrc.value = data.data
    } else {
      throw new Error('Invalid response format')
    }
  } catch (error) {
    console.error('图片加载失败:', error)
    loadError.value = true
    imageSrc.value = ''
  } finally {
    isLoading.value = false
    emit('ready')
  }
}

// 处理图片源变化
const updateImageSrc = () => {
  const src = props.src

  // 如果是 [IMAGE:xxx] 格式，从API获取base64数据
  if (isImagePlaceholder(src)) {
    const imageId = src.slice(7, -1) // 提取 "[IMAGE:xxx]" 中的 xxx
    fetchImage(imageId)
  }
  // 如果是 /api/image/xxx 格式，补充基础URL后作为图片URL
  else if (isApiImageUrl(src)) {
    imageSrc.value = resolveImageUrl(src)
    emit('ready')
  }
  // 否则，直接使用完整 data URL 或其他格式
  else {
    imageSrc.value = src
    emit('ready')
  }
}

// 使用computed保证响应式更新
const computedSrc = computed(() => props.src)

// 监听src变化
watch(computedSrc, () => {
  updateImageSrc()
})

const onLoad = () => {
  emit('ready')
}

const onError = () => {
  console.error('图片加载失败:', imageSrc.value)
  loadError.value = true
  emit('ready')
}

onMounted(() => {
  updateImageSrc()
})
</script>

<style lang="scss" scoped>
.image-panel {
  width: 100%;
  background: #fafafa;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);

  img {
    width: 100%;
    height: auto;
    display: block;
  }
}

.image-placeholder,
.image-loading,
.image-error {
  width: 100%;
  height: 300px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #999;

  svg {
    margin-bottom: 16px;
  }

  p {
    margin: 0;
    font-size: 16px;
  }
}

.image-loading {
  background: #f5f5f5;
}

.image-error {
  color: #e74c3c;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e0e0e0;
  border-top-color: #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
