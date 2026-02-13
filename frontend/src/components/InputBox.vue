<template>
  <div class="input-area">
    <div class="input-container">
      <div class="input-wrapper">
        <textarea
          ref="textareaRef"
          v-model="localValue"
          class="input-field"
          :placeholder="placeholder"
          :disabled="disabled"
          @keydown="handleKeydown"
          @input="autoResize"
          @focus="handleFocus"
          @blur="handleBlur"
          rows="1"
        />

        <div class="action-group">
          <button
            class="kb-toggle-button"
            :class="{ 'kb-active': showKnowledgeBaseSelector }"
            @click="toggleKnowledgeBase"
            title="选择知识库"
          >
            <svg viewBox="0 0 24 24" class="kb-icon">
              <path d="M4 4h16v4H4V4zm0 6h16v10H4V10zm4 2v6h8v-6H8z" fill="currentColor"/>
            </svg>
          </button>

          <label class="upload-label" title="文件上传功能即将开放">
            <input type="file" disabled />
            <span class="upload-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path
                  d="M8.5 13.5 17 5a3.5 3.5 0 0 1 5 5l-10 10a5.5 5.5 0 0 1-7.8-7.8l9-9"
                  fill="none"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </span>
          </label>

          <button
            class="action-button"
            :class="{ 'pause-button': isAnalyzing, 'send-button': !isAnalyzing }"
            @click="isAnalyzing ? handlePause() : handleSend()"
            :disabled="(!localValue.trim() && !isAnalyzing) || disabled"
            :title="isAnalyzing ? '暂停分析 (Esc)' : '发送 (Enter)'"
          >
            <svg v-if="!isAnalyzing" viewBox="0 0 24 24" class="send-icon">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" fill="currentColor"/>
            </svg>
            <span v-else>暂停</span>
          </button>
        </div>
      </div>

      <!-- 知识库选择器 -->
      <KnowledgeBaseSelector v-if="showKnowledgeBaseSelector" />

      <div class="feature-buttons">
        <!-- 极速模式切换：仅在快速/深度溯源场景显示，通用Agent模式隐藏 -->
        <button
          type="button"
          v-if="assistantMode === 'quick-tracing-expert' || assistantMode === 'deep-tracing-expert'"
          class="feature-button"
          :class="{ 'feature-button-active': precision === 'fast' }"
          @click="toggleFastMode"
          title="切换到极速模式（快速筛查，约18秒）"
        >
          {{ precision === 'fast' ? '✓ 极速模式' : '切换到极速模式（快速筛查）' }}
        </button>
        <button
          type="button"
          v-if="assistantMode === 'general-agent'"
          class="feature-button"
          :class="{ 'feature-button-active': enableReasoning }"
          @click="toggleReasoning"
          :title="enableReasoning ? '已启用深度思考模式（显示LLM推理过程）' : '启用深度思考模式（显示LLM推理过程）'"
        >
          {{ enableReasoning ? '✓ 深度思考' : '深度思考' }}
        </button>
        <button class="feature-button" disabled title="敬请期待">联网搜索</button>
        <!-- 精准检索开关：仅在知识问答模式显示 -->
        <button
          type="button"
          v-if="assistantMode === 'knowledge-qa'"
          class="feature-button"
          :class="{ 'feature-button-active': useReranker }"
          @click="toggleReranker"
          title="启用精准检索模式（提升检索精度，但响应稍慢）"
        >
          {{ useReranker ? '✓ 精准检索' : '精准检索' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import KnowledgeBaseSelector from '@/components/knowledge/KnowledgeBaseSelector.vue'

const kbStore = useKnowledgeBaseStore()

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '输入您的问题...'
  },
  disabled: {
    type: Boolean,
    default: false
  },
  isAnalyzing: {
    type: Boolean,
    default: false
  },
  assistantMode: {
    type: String,
    default: 'general-agent'
  },
  useReranker: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'send', 'pause', 'update:precision', 'update:enableReasoning', 'update:useReranker'])

const textareaRef = ref(null)
const localValue = ref(props.modelValue)
const precision = ref('standard')  // 默认standard模式，点击按钮切换为fast
const showKnowledgeBaseSelector = ref(false)
const enableReasoning = ref(false)  // 默认禁用思考模式（不显示推理过程）
const useReranker = ref(props.useReranker)  // 精准检索开关状态

const toggleKnowledgeBase = () => {
  showKnowledgeBaseSelector.value = !showKnowledgeBaseSelector.value
}

const toggleFastMode = () => {
  // ✅ 安全检查：仅在支持的模式下允许切换
  if (props.assistantMode === 'quick-tracing-expert' || props.assistantMode === 'deep-tracing-expert') {
    // 在standard和fast之间切换
    precision.value = precision.value === 'fast' ? 'standard' : 'fast'
    emit('update:precision', precision.value)
  }
}

const toggleReasoning = () => {
  // ✅ 仅在通用Agent模式下允许切换
  if (props.assistantMode === 'general-agent') {
    enableReasoning.value = !enableReasoning.value
    emit('update:enableReasoning', enableReasoning.value)
  }
}

const toggleReranker = () => {
  // 精准检索开关：仅在知识问答模式下允许切换
  if (props.assistantMode === 'knowledge-qa') {
    useReranker.value = !useReranker.value
    emit('update:useReranker', useReranker.value)
  }
}

const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`
  }
}

watch(() => props.modelValue, (newValue) => {
  localValue.value = newValue
})

watch(
  () => props.assistantMode,
  (newMode, oldMode) => {
    // ✅ 快速溯源专家：保持当前状态（默认standard，点击按钮切换为fast）
    if (newMode === 'quick-tracing-expert') {
      // 不强制设置，让用户手动选择
      return
    }

    // ✅ 深度溯源专家：保持当前状态
    if (newMode === 'deep-tracing-expert') {
      return
    }

    // ✅ 通用Agent/气象专家/数据可视化专家：重置为默认模式
    if (precision.value !== 'standard') {
      precision.value = 'standard'
      emit('update:precision', 'standard')
    }

    // ✅ 通用Agent模式：重置思考模式状态
    if (newMode === 'general-agent') {
      return
    } else {
      // 其他模式：禁用思考模式
      if (enableReasoning.value) {
        enableReasoning.value = false
        emit('update:enableReasoning', false)
      }
    }
  },
  { immediate: true }
)

watch(localValue, async (newValue) => {
  emit('update:modelValue', newValue)
  await nextTick()
  autoResize()
})

const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !props.isAnalyzing) {
    e.preventDefault()
    handleSend()
  } else if (e.key === 'Escape' && props.isAnalyzing) {
    e.preventDefault()
    handlePause()
  }
}

const handleFocus = () => {
  // 输入框获得焦点时的处理
}

const handleBlur = () => {
  // 输入框失去焦点时的处理
}

const handleSend = () => {
  if (!localValue.value.trim() || props.disabled || props.isAnalyzing) return

  // 获取选中的知识库ID列表
  const knowledgeBaseIds = kbStore.selectedIds

  // 将查询、知识库ID、精度模式、思考模式一起发送
  emit('send', {
    query: localValue.value,
    knowledgeBaseIds: knowledgeBaseIds,
    precision: precision.value,
    enableReasoning: enableReasoning.value
  })

  localValue.value = ''

  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  })
}

const handlePause = () => {
  if (!props.isAnalyzing) return

  emit('pause')
}
</script>

<style lang="scss" scoped>
.input-area {
  padding: 16px 20px;
  background: #fff;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.input-container {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.input-wrapper {
  display: flex;
  align-items: stretch;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;

  &:focus-within {
    border-color: #1976D2;
    box-shadow: 0 0 0 3px rgba(25, 118, 210, 0.1);
  }
}

.input-field {
  flex: 1;
  min-height: 44px;
  max-height: 120px;
  padding: 10px 16px;
  border: none;
  border-radius: 8px 0 0 8px;
  font-size: 15px;
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  overflow-y: hidden;

  &:focus {
    outline: none;
  }

  &:disabled {
    background: #f5f5f5;
    cursor: not-allowed;
    color: #999;
  }
}

.action-group {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
}

.upload-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  color: #7c8db5;
  background: transparent;
  cursor: not-allowed;
  user-select: none;
  transition: background 0.2s;

  &:hover {
    background: #f5f5f5;
  }
}

.upload-label input {
  display: none;
}

.upload-icon svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
}

.kb-toggle-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  color: #7c8db5;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.kb-toggle-button:hover {
  background: #f5f5f5;
  color: #1976D2;
}

.kb-toggle-button.kb-active {
  background: #e3f2fd;
  color: #1976D2;
}

.kb-icon {
  width: 18px;
  height: 18px;
}

.action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;

  &:disabled {
    cursor: not-allowed;
  }
}

.send-icon {
  width: 18px;
  height: 18px;
}

.send-button {
  background: #1976D2;
  color: white;

  &:hover:not(:disabled) {
    background: #1565C0;
  }

  &:disabled {
    background: #e0e0e0;
    color: #999;
  }
}

.pause-button {
  width: auto;
  padding: 0 12px;
  background: #FF5722;
  color: white;

  &:hover:not(:disabled) {
    background: #E64A19;
  }

  &:disabled {
    background: #e0e0e0;
    color: #999;
  }
}

.feature-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding-left: 4px;
}

.feature-button {
  padding: 6px 16px;
  border-radius: 999px;
  border: 1px solid #d4dbe8;
  background: #fff;
  color: #6b7a99;
  font-size: 13px;
  cursor: pointer;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.5);
  transition: all 0.2s;

  &:hover:not(:disabled) {
    border-color: #1976D2;
    color: #1976D2;
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
}

.feature-button-active {
  background: #e3f2fd;
  border-color: #1976D2;
  color: #1976D2;
  font-weight: 500;
}

.feature-hint {
  padding: 6px 16px;
  border-radius: 999px;
  border: 1px solid #4CAF50;
  background: #E8F5E9;
  color: #2E7D32;
  font-size: 13px;
  font-weight: 500;
}

.grid-resolution-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border: 1px solid #d4dbe8;
  border-radius: 999px;
  background: #fff;
  font-size: 13px;
  color: #6b7a99;

  label {
    font-weight: 500;
    white-space: nowrap;
  }
}

.grid-resolution-select {
  border: none;
  background: transparent;
  font-size: 13px;
  color: #1976D2;
  cursor: pointer;
  outline: none;

  &:focus {
    outline: none;
  }

  option {
    padding: 4px;
  }
}

@media (max-width: 768px) {
  .action-group {
    padding: 4px;
  }
}
</style>
