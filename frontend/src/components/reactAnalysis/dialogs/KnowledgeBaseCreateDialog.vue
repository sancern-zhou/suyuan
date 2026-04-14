<template>
  <div v-if="visible" class="dialog-overlay" @click.self="handleClose">
    <div class="dialog">
      <div class="dialog-header">
        <h3>新建知识库</h3>
        <button class="btn-close" @click="handleClose">×</button>
      </div>

      <div class="dialog-body">
        <div class="form-group">
          <label>名称 *</label>
          <input
            v-model="formData.name"
            type="text"
            placeholder="输入知识库名称"
            :class="{ 'input-error': errors.name }"
            @blur="validateField('name')"
          />
          <span v-if="errors.name" class="error-text">{{ errors.name }}</span>
        </div>

        <div class="form-group">
          <label>描述</label>
          <textarea
            v-model="formData.description"
            placeholder="输入知识库描述"
            rows="3"
          ></textarea>
        </div>

        <div class="form-group">
          <label>类型</label>
          <select v-model="formData.kb_type">
            <option value="private">个人知识库</option>
            <option value="public">公共知识库</option>
          </select>
        </div>

        <div class="form-group" v-if="formData.kb_type === 'public'">
          <label>公共知识库权限</label>
          <label class="checkbox-inline">
            <input type="checkbox" v-model="adminConfirm" />
            以管理员身份创建（自动携带 X-Is-Admin: true）
          </label>
          <p class="form-hint danger">提醒：公共知识库必须以管理员身份创建，否则会返回 403。</p>
        </div>

        <div class="form-group">
          <label>分块策略</label>
          <select v-model="formData.chunking_strategy">
            <option value="llm">LLM智能分块（推荐）</option>
            <option value="sentence">句子分块</option>
            <option value="semantic">语义分块</option>
            <option value="markdown">Markdown分块</option>
            <option value="hybrid">混合分块</option>
          </select>
          <p class="form-hint">{{ getStrategyDescription(formData.chunking_strategy) }}</p>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>分块大小</label>
            <input
              v-model.number="formData.chunk_size"
              type="number"
              min="64"
              max="2048"
              :class="{ 'input-error': errors.chunk_size }"
              @blur="validateField('chunk_size')"
            />
            <span v-if="errors.chunk_size" class="error-text">{{ errors.chunk_size }}</span>
          </div>

          <div class="form-group">
            <label>分块重叠</label>
            <input
              v-model.number="formData.chunk_overlap"
              type="number"
              min="0"
              max="512"
              :class="{ 'input-error': errors.chunk_overlap }"
              @blur="validateField('chunk_overlap')"
            />
            <span v-if="errors.chunk_overlap" class="error-text">{{ errors.chunk_overlap }}</span>
          </div>
        </div>
      </div>

      <div class="dialog-footer">
        <button class="btn-secondary" @click="handleClose">取消</button>
        <button
          class="btn-primary"
          @click="handleConfirm"
          :disabled="!formData.name || isSubmitting"
        >
          {{ isSubmitting ? '创建中...' : '创建' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { validateKbName, validateKbDescription, validateChunkSize, validateChunkOverlap } from '@/utils/validators'
import { KB_DEFAULTS } from '@/utils/constants'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  initialData: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits([
  'confirm',
  'close',
  'update:visible'
])

// 表单数据
const formData = reactive({
  name: '',
  description: '',
  kb_type: 'private',
  chunking_strategy: 'llm',
  chunk_size: KB_DEFAULTS.CHUNK_SIZE,
  chunk_overlap: KB_DEFAULTS.CHUNK_OVERLAP
})

const adminConfirm = ref(localStorage.getItem('isAdmin') === 'true')
const errors = reactive({})
const isSubmitting = ref(false)

// 初始化表单数据
watch(() => props.visible, (visible) => {
  if (visible) {
    // 重置表单
    Object.assign(formData, {
      name: '',
      description: '',
      kb_type: 'private',
      chunking_strategy: 'llm',
      chunk_size: KB_DEFAULTS.CHUNK_SIZE,
      chunk_overlap: KB_DEFAULTS.CHUNK_OVERLAP
    })
    adminConfirm.value = localStorage.getItem('isAdmin') === 'true'
    Object.keys(errors).forEach(key => delete errors[key])

    // 应用初始数据
    if (props.initialData && Object.keys(props.initialData).length > 0) {
      Object.assign(formData, props.initialData)
    }
  }
})

// 验证单个字段
const validateField = (field) => {
  delete errors[field]

  switch (field) {
    case 'name':
      const nameResult = validateKbName(formData.name)
      if (!nameResult.valid) {
        errors.name = nameResult.message
      }
      break

    case 'description':
      const descResult = validateKbDescription(formData.description)
      if (!descResult.valid) {
        errors.description = descResult.message
      }
      break

    case 'chunk_size':
      const sizeResult = validateChunkSize(formData.chunk_size)
      if (!sizeResult.valid) {
        errors.chunk_size = sizeResult.message
      }
      break

    case 'chunk_overlap':
      const overlapResult = validateChunkOverlap(
        formData.chunk_overlap,
        formData.chunk_size
      )
      if (!overlapResult.valid) {
        errors.chunk_overlap = overlapResult.message
      }
      break
  }
}

// 验证整个表单
const validateForm = () => {
  validateField('name')
  validateField('description')
  validateField('chunk_size')
  validateField('chunk_overlap')

  return Object.keys(errors).length === 0
}

// 获取策略描述
const getStrategyDescription = (strategy) => {
  const descriptions = {
    llm: '使用LLM智能识别文档结构，适合复杂文档（较慢）',
    sentence: '按句子分块，保持语义完整，适合通用文本',
    semantic: '基于语义相似度分块，保持主题连贯',
    markdown: '按Markdown结构分块，保留标题层级',
    hybrid: '混合策略，结合多种方法优势'
  }
  return descriptions[strategy] || ''
}

// 处理确认
const handleConfirm = async () => {
  // 公共知识库需要管理员确认
  if (formData.kb_type === 'public' && !adminConfirm.value) {
    alert('创建公共知识库需要管理员权限，请勾选确认。')
    return
  }

  // 验证表单
  if (!validateForm()) {
    return
  }

  isSubmitting.value = true

  try {
    // 同步管理员标识到 localStorage
    if (formData.kb_type === 'public' && adminConfirm.value) {
      localStorage.setItem('isAdmin', 'true')
    } else if (!adminConfirm.value) {
      localStorage.removeItem('isAdmin')
    }

    // 发送确认事件
    emit('confirm', {
      ...formData,
      adminConfirm: adminConfirm.value
    })

    handleClose()
  } catch (error) {
    console.error('创建知识库失败:', error)
  } finally {
    isSubmitting.value = false
  }
}

// 处理关闭
const handleClose = () => {
  emit('close')
  emit('update:visible', false)
}

// 暴露方法
defineExpose({
  validateForm,
  resetForm: () => {
    Object.assign(formData, {
      name: '',
      description: '',
      kb_type: 'private',
      chunking_strategy: 'llm',
      chunk_size: KB_DEFAULTS.CHUNK_SIZE,
      chunk_overlap: KB_DEFAULTS.CHUNK_OVERLAP
    })
    Object.keys(errors).forEach(key => delete errors[key])
  }
})
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
}

.dialog-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.btn-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-close:hover {
  background: #f5f5f5;
  color: #333;
}

.dialog-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.form-group input[type="text"],
.form-group input[type="number"],
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  transition: all 0.2s;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.1);
}

.form-group input.input-error,
.form-group select.input-error {
  border-color: #ff4d4f;
}

.form-group textarea {
  resize: vertical;
  min-height: 80px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-row .form-group {
  flex: 1;
}

.checkbox-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  cursor: pointer;
}

.checkbox-inline input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.form-hint {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: #999;
}

.form-hint.danger {
  color: #ff4d4f;
}

.error-text {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #ff4d4f;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #e8e8e8;
}

.btn-secondary,
.btn-primary {
  padding: 8px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.btn-secondary {
  background: white;
  border-color: #d9d9d9;
  color: #333;
}

.btn-secondary:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.btn-primary {
  background: #1890ff;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #40a9ff;
}

.btn-primary:disabled {
  background: #d9d9d9;
  color: #999;
  cursor: not-allowed;
}
</style>
