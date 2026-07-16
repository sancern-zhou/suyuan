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
      title="点击放大"
      role="button"
      tabindex="0"
      @load="onLoad"
      @error="onError"
      @click="openLightbox"
      @keydown.enter="openLightbox"
      @keydown.space.prevent="openLightbox"
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

  <ImageLightbox
    v-model:visible="lightboxVisible"
    :images="lightboxImages"
    :start-index="0"
  />
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import ImageLightbox from '@/components/ImageLightbox.vue'
import { createImagePanelLightboxImage } from './imagePanelLightbox.js'
import {
  apiImagePath,
  createLatestImageObjectUrlLoader,
  objectUrlToDataUrl
} from '@/services/apiImageBlob.js'

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
const lightboxVisible = ref(false)
const lightboxImages = ref([])

const apiImageLoader = createLatestImageObjectUrlLoader()
let activeApiLoad = null

const getCaptureImage = async (source) => {
  return source.startsWith('blob:') ? objectUrlToDataUrl(source) : source
}

// 暴露方法给父组件（用于截图捕获）
const getChartImage = async () => {
  // 页面使用Blob URL显示；截图收集仍返回下游需要的data URL。
  if (imageSrc.value && !loadError.value) {
    return getCaptureImage(imageSrc.value)
  }

  // 如果正在加载中，等待加载完成
  if (isLoading.value && activeApiLoad) {
    await activeApiLoad
    return imageSrc.value ? getCaptureImage(imageSrc.value) : null
  }

  // 如果还没开始加载（isLoading为false且imageSrc为空），可能是组件刚创建
  // 主动触发加载并等待
  if (!imageSrc.value && !isLoading.value && !loadError.value) {
    const src = props.src
    if (apiImagePath(src)) {
      await fetchImage(src)
      return imageSrc.value ? getCaptureImage(imageSrc.value) : null
    }
  }

  return null
}

// 暴露方法给父组件
defineExpose({
  getChartImage
})

// 从API获取图片数据
const fetchImage = (source) => {
  apiImageLoader.clear()
  isLoading.value = true
  loadError.value = false
  imageSrc.value = ''

  activeApiLoad = apiImageLoader.start(source, {
    onSuccess: (url) => {
      imageSrc.value = url
    },
    onError: (error) => {
      console.error('图片加载失败:', error)
      loadError.value = true
      imageSrc.value = ''
    },
    onSettled: () => {
      isLoading.value = false
      emit('ready')
    }
  })

  return activeApiLoad
}

// 处理图片源变化
const updateImageSrc = () => {
  const src = props.src

  if (apiImagePath(src)) {
    fetchImage(src)
  } else {
    apiImageLoader.clear()
    activeApiLoad = null
    isLoading.value = false
    loadError.value = false
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
  apiImageLoader.clear()
  imageSrc.value = ''
  loadError.value = true
  emit('ready')
}

const openLightbox = () => {
  const lightboxImage = createImagePanelLightboxImage(imageSrc.value, props.alt)
  if (!lightboxImage) return

  lightboxImages.value = [lightboxImage]
  lightboxVisible.value = true
}

onMounted(() => {
  updateImageSrc()
})

onUnmounted(() => {
  apiImageLoader.clear()
  activeApiLoad = null
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
    cursor: zoom-in;

    &:focus-visible {
      outline: 2px solid #1976D2;
      outline-offset: -2px;
    }
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
