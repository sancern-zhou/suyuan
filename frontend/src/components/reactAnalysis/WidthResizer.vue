<template>
  <div
    v-if="visible"
    class="resize-handle"
    :class="{ dragging: isDragging }"
    @mousedown="handleMouseDown"
    @dblclick.stop="handleDoubleClick"
    :title="title"
  >
    <div class="resize-line"></div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /**
   * 是否显示调整器
   */
  visible: {
    type: Boolean,
    default: true
  },
  /**
   * 是否正在拖动
   */
  isDragging: {
    type: Boolean,
    default: false
  },
  /**
   * 提示文本
   */
  title: {
    type: String,
    default: '拖拽调整面板宽度，双击恢复默认'
  }
})

const emit = defineEmits([
  'start-drag',
  'stop-drag',
  'reset'
])

/**
 * 处理鼠标按下事件
 */
const handleMouseDown = (event) => {
  event.preventDefault()
  emit('start-drag', event)
}

/**
 * 处理双击事件
 */
const handleDoubleClick = () => {
  emit('reset')
}
</script>

<style scoped>
.resize-handle {
  position: relative;
  width: 4px;
  height: 100%;
  cursor: col-resize;
  background: #e8e8e8;
  transition: background-color 0.2s;
  user-select: none;
  flex-shrink: 0;
  align-self: stretch;
}

.resize-handle:hover,
.resize-handle.dragging {
  background: #1890ff;
}

.resize-line {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 40px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 1px;
}

.resize-handle:hover .resize-line,
.resize-handle.dragging .resize-line {
  background: rgba(255, 255, 255, 0.8);
}
</style>
