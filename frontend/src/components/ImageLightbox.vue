<template>
  <Teleport to="body">
    <Transition name="lightbox">
      <div v-if="visible" class="lightbox-overlay" @click.self="close" @wheel.prevent="handleWheel" @mousedown="startDrag" @mousemove="onDrag" @mouseup="stopDrag" @mouseleave="stopDrag">
        <div class="lightbox-container">
          <!-- 工具栏 -->
          <div class="lightbox-toolbar">
            <button class="toolbar-btn" @click="zoomOut" title="缩小">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19 13H5v-2h14v2z"/>
              </svg>
            </button>
            <span class="zoom-level">{{ Math.round(scale * 100) }}%</span>
            <button class="toolbar-btn" @click="zoomIn" title="放大">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
              </svg>
            </button>
            <button class="toolbar-btn" @click="resetZoom" title="重置">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/>
              </svg>
            </button>
            <div class="toolbar-divider"></div>
            <button class="toolbar-btn" @click="download" title="下载">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
              </svg>
            </button>
            <button class="toolbar-btn close-btn" @click="close" title="关闭 (ESC)">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
              </svg>
            </button>
          </div>

          <!-- 图片容器 -->
          <div class="image-wrapper" :style="{ transform: `translate(${translateX}px, ${translateY}px) scale(${scale})` }">
            <template v-if="currentImage && currentImage.src">
              <img
                :src="currentImage.src"
                :alt="currentImage.alt"
                class="lightbox-image"
                draggable="false"
                @load="onImageLoad"
                @error="onImageError"
              />
            </template>
            <div v-else class="image-error">
              <p>无法加载图片</p>
              <p class="error-detail">图片总数: {{ props.images.length }}</p>
              <p class="error-detail">当前索引: {{ currentIndex.value }}</p>
              <p class="error-detail">当前图片: {{ currentImage?.src || '无' }}</p>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  images: {
    type: Array,
    default: () => []
  },
  startIndex: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['update:visible', 'update:startIndex'])

const currentIndex = ref(0)
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const dragStartTranslateX = ref(0)
const dragStartTranslateY = ref(0)

const currentImage = computed(() => {
  if (props.images.length === 0) {
    console.warn('[ImageLightbox] 没有图片数据')
    return { src: '', alt: '' }
  }
  const img = props.images[currentIndex.value]
  if (!img) {
    console.warn('[ImageLightbox] 当前索引无效', currentIndex.value, props.images.length)
    return props.images[0] || { src: '', alt: '' }
  }
  console.log('[ImageLightbox] 当前图片:', img)
  return img
})

const ZOOM_STEP = 0.1
const MIN_SCALE = 0.5
const MAX_SCALE = 5

const zoomIn = () => {
  scale.value = Math.min(scale.value + ZOOM_STEP, MAX_SCALE)
}

const zoomOut = () => {
  scale.value = Math.max(scale.value - ZOOM_STEP, MIN_SCALE)
}

const resetZoom = () => {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
}

const handleWheel = (e) => {
  const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP
  scale.value = Math.min(Math.max(scale.value + delta, MIN_SCALE), MAX_SCALE)
}

const startDrag = (e) => {
  if (e.target.tagName !== 'IMG') return
  console.log('[ImageLightbox] 开始拖拽')
  isDragging.value = true
  dragStartX.value = e.clientX
  dragStartY.value = e.clientY
  dragStartTranslateX.value = translateX.value
  dragStartTranslateY.value = translateY.value
}

const onDrag = (e) => {
  if (!isDragging.value) return
  const deltaX = e.clientX - dragStartX.value
  const deltaY = e.clientY - dragStartY.value
  translateX.value = dragStartTranslateX.value + deltaX
  translateY.value = dragStartTranslateY.value + deltaY
}

const stopDrag = () => {
  isDragging.value = false
}

const close = () => {
  emit('update:visible', false)
  setTimeout(() => {
    resetZoom()
  }, 300)
}

const download = () => {
  const link = document.createElement('a')
  link.href = currentImage.value.src
  link.download = currentImage.value.alt || 'image.png'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

const onImageLoad = () => {
  console.log('[ImageLightbox] 图片加载成功:', currentImage.value.src)
}

const onImageError = (e) => {
  console.error('[ImageLightbox] 图片加载失败:', currentImage.value.src, e)
}

const handleKeydown = (e) => {
  if (!props.visible) return
  if (e.key === 'Escape') close()
  if (e.key === 'ArrowLeft') navigateImage(-1)
  if (e.key === 'ArrowRight') navigateImage(1)
  if (e.key === '+' || e.key === '=') zoomIn()
  if (e.key === '-' || e.key === '_') zoomOut()
  if (e.key === '0') resetZoom()
}

const navigateImage = (direction) => {
  const newIndex = currentIndex.value + direction
  if (newIndex >= 0 && newIndex < props.images.length) {
    currentIndex.value = newIndex
    emit('update:startIndex', newIndex)
    resetZoom()
  }
}

watch(() => props.startIndex, (newIndex) => {
  currentIndex.value = newIndex
})

watch(() => props.visible, (visible) => {
  if (visible) {
    document.body.style.overflow = 'hidden'
    console.log('[ImageLightbox] 打开灯箱', {
      images: props.images,
      currentIndex: currentIndex.value,
      currentImage: currentImage.value
    })
  } else {
    document.body.style.overflow = ''
  }
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = ''
})
</script>

<style lang="scss" scoped>
.lightbox-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  cursor: grab;
  user-select: none;

  &:active {
    cursor: grabbing;
  }
}

.lightbox-container {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-toolbar {
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 12px;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 10;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.toolbar-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: rgba(255, 255, 255, 0.1);
  color: white;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;

  &:hover {
    background: rgba(255, 255, 255, 0.2);
    transform: scale(1.05);
  }

  &:active {
    transform: scale(0.95);
  }

  &.close-btn {
    background: rgba(239, 68, 68, 0.3);

    &:hover {
      background: rgba(239, 68, 68, 0.5);
    }
  }
}

.toolbar-divider {
  width: 1px;
  height: 24px;
  background: rgba(255, 255, 255, 0.3);
  margin: 0 4px;
}

.zoom-level {
  min-width: 50px;
  text-align: center;
  color: white;
  font-size: 13px;
  font-weight: 500;
}

.image-wrapper {
  transition: transform 0.1s ease-out;
  will-change: transform;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-image {
  max-width: 90vw;
  max-height: 85vh;
  object-fit: contain;
  display: block;
  pointer-events: auto;
}

.image-error {
  color: white;
  text-align: center;
  padding: 40px;

  p {
    margin: 8px 0;
    font-size: 16px;
  }

  .error-detail {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.7);
  }
}

.lightbox-enter-active,
.lightbox-leave-active {
  transition: opacity 0.3s ease;

  .lightbox-image {
    transition: transform 0.3s ease;
  }
}

.lightbox-enter-from,
.lightbox-leave-to {
  opacity: 0;

  .lightbox-image {
    transform: scale(0.9);
  }
}

@media (max-width: 768px) {
  .lightbox-toolbar {
    top: 10px;
    padding: 6px 12px;
    gap: 4px;
  }

  .toolbar-btn {
    width: 32px;
    height: 32px;
  }

  .zoom-level {
    font-size: 12px;
    min-width: 45px;
  }

  .lightbox-image {
    max-width: 95vw;
    max-height: 80vh;
  }
}
</style>
