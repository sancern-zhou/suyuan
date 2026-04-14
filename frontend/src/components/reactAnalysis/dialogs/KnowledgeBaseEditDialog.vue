<template>
  <div v-if="visible" class="dialog-overlay" @click.self="handleClose">
    <div class="dialog">
      <div class="dialog-header">
        <h3>编辑知识库</h3>
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
          <label>
            <input type="checkbox" v-model="formData.is_default" />
            设为默认知识库
          </label>
          <p class="form-hint">默认知识库会在新建会话时自动选中</p>
        </div>
      </div>

      <div class="dialog-footer">
        <button class="btn-secondary" @click="handleClose">取消</button>
        <button
          class="btn-primary"
          @click="handleConfirm"
          :disabled="!formData.name || isSubmitting"
        >
          {{ isSubmitting ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { validateKbName, validateKbDescription } from '@/utils/validators'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  knowledgeBase: {
    type: Object,
    default: null
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
  is_default: false
})

const errors = reactive({})
const isSubmitting = ref(false)

// 初始化表单数据
watch(() => props.visible, (visible) => {
  if (visible && props.knowledgeBase) {
    // 从知识库数据初始化表单
    formData.name = props.knowledgeBase.name || ''
    formData.description = props.knowledgeBase.description || ''
    formData.is_default = props.knowledgeBase.is_default || false

    // 清空错误
    Object.keys(errors).forEach(key => delete errors[key])
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
  }
}

// 验证整个表单
const validateForm = () => {
  validateField('name')
  validateField('description')

  return Object.keys(errors).length === 0
}

// 处理确认
const handleConfirm = async () => {
  // 验证表单
  if (!validateForm()) {
    return
  }

  isSubmitting.value = true

  try {
    // 发送确认事件
    emit('confirm', {
      ...formData,
      id: props.knowledgeBase?.id
    })

    handleClose()
  } catch (error) {
    console.error('更新知识库失败:', error)
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
  loadKnowledgeBase: (kb) => {
    formData.name = kb.name || ''
    formData.description = kb.description || ''
    formData.is_default = kb.is_default || false
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
  max-width: 500px;
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
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  transition: all 0.2s;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.1);
}

.form-group input.input-error {
  border-color: #ff4d4f;
}

.form-group textarea {
  resize: vertical;
  min-height: 80px;
}

.form-group input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  margin-right: 8px;
}

.form-hint {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: #999;
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
