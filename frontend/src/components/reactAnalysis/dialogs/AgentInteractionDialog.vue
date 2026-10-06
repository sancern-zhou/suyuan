<template>
  <div v-if="interaction" class="interaction-strip" :class="{ 'interaction-strip-questions': interaction.kind === 'structured_question' }" role="region" :aria-labelledby="titleId">
    <section class="interaction-content">
      <div class="interaction-copy">
        <h3 :id="titleId">{{ interaction.title || '需要你的确认' }}</h3>
        <p v-if="interaction.kind !== 'structured_question'">{{ interaction.question }}</p>
      </div>
      <div v-if="interaction.kind === 'structured_question'" class="question-list">
        <fieldset v-for="(item, questionIndex) in interaction.questions" :key="questionIndex" class="question-item">
          <legend><span class="question-header">{{ item.header }}</span>{{ item.question }}</legend>
          <label v-for="(option, optionIndex) in item.options" :key="optionIndex" class="question-option">
            <input
              :type="item.multiSelect ? 'checkbox' : 'radio'"
              :name="`${titleId}-${questionIndex}`"
              :checked="selections[questionIndex]?.includes(optionIndex)"
              :disabled="resolving"
              @change="selectOption(questionIndex, optionIndex, item.multiSelect)"
            />
            <span><strong>{{ option.label }}</strong><small>{{ option.description }}</small><pre v-if="option.preview">{{ option.preview }}</pre></span>
          </label>
          <label class="question-option">
            <input
              :type="item.multiSelect ? 'checkbox' : 'radio'"
              :name="`${titleId}-${questionIndex}`"
              :checked="customEnabled[questionIndex] || false"
              :disabled="resolving"
              @change="selectCustom(questionIndex, item.multiSelect)"
            />
            <span><strong>其他</strong></span>
          </label>
          <textarea v-if="customEnabled[questionIndex]" v-model="customAnswers[questionIndex]" rows="2" class="interaction-response" placeholder="请输入你的选择" :disabled="resolving" />
        </fieldset>
      </div>
      <textarea
        v-if="interaction.kind === 'question'"
        v-model="response"
        class="interaction-response"
        rows="2"
        placeholder="请输入回复"
        :disabled="resolving"
      />
    </section>
    <div class="interaction-actions">
      <button class="interaction-secondary" type="button" :disabled="resolving" @click="resolve('reject')">
        {{ interaction.kind === 'structured_question' ? '取消' : '暂不切换' }}
      </button>
      <button class="interaction-primary" type="button" :disabled="resolving || (interaction.kind === 'structured_question' && !canSubmit)" @click="resolve(['question', 'structured_question'].includes(interaction.kind) ? 'answer' : 'approve')">
        {{ resolving ? '处理中…' : (['question', 'structured_question'].includes(interaction.kind) ? '提交回复' : '进入工作空间') }}
      </button>
      <button class="interaction-close" type="button" aria-label="关闭" :disabled="resolving" @click="close">×</button>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'

const props = defineProps({
  interaction: { type: Object, default: null },
  resolving: { type: Boolean, default: false }
})

const emit = defineEmits(['resolve', 'close'])
const response = ref('')
const selections = reactive({})
const customEnabled = reactive({})
const customAnswers = reactive({})
const titleId = `agent-interaction-${Math.random().toString(36).slice(2)}`

watch(() => props.interaction?.interaction_id, () => {
  Object.keys(selections).forEach(key => delete selections[key])
  Object.keys(customEnabled).forEach(key => delete customEnabled[key])
  Object.keys(customAnswers).forEach(key => delete customAnswers[key])
  response.value = ''
})

const selectOption = (questionIndex, optionIndex, multiSelect) => {
  const selected = selections[questionIndex] || []
  selections[questionIndex] = multiSelect
    ? (selected.includes(optionIndex) ? selected.filter(index => index !== optionIndex) : [...selected, optionIndex])
    : [optionIndex]
  if (!multiSelect) customEnabled[questionIndex] = false
}

const selectCustom = (questionIndex, multiSelect) => {
  customEnabled[questionIndex] = !customEnabled[questionIndex]
  if (!multiSelect) selections[questionIndex] = []
}

const canSubmit = computed(() => props.interaction?.questions?.every((_, index) =>
  (selections[index]?.length || 0) > 0 || (customEnabled[index] && customAnswers[index]?.trim())
))

const resolve = (decision) => emit('resolve', {
  decision,
  response: response.value || null,
  answers: props.interaction?.kind === 'structured_question' && decision === 'answer'
    ? props.interaction.questions.map((_, index) => ({
      selected: selections[index] || [],
      custom: customEnabled[index] ? customAnswers[index]?.trim() || null : null
    }))
    : null
})
const close = () => emit('close')
</script>

<style scoped>
.interaction-strip { width: min(1200px, calc(100% - 40px)); box-sizing: border-box; flex-shrink: 0; display: flex; align-items: center; gap: 16px; margin: 0 auto; padding: 12px 14px; border: 1px solid #c8d8ed; border-radius: 7px; background: #f4f8fd; box-shadow: 0 -2px 10px rgba(30, 64, 110, .06); }
.interaction-strip-questions { align-items: stretch; flex-direction: column; }
.interaction-content { flex: 1; min-width: 0; }
.interaction-copy { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.interaction-copy h3 { flex: 0 0 auto; margin: 0; color: #20334d; font-size: 14px; line-height: 1.45; }
.interaction-copy p { min-width: 0; margin: 0; color: #53657c; font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }
.interaction-response { display: block; width: 100%; margin-top: 9px; box-sizing: border-box; resize: vertical; border: 1px solid #b8c8dc; border-radius: 6px; padding: 8px 10px; background: var(--bg-container); color: #26384f; font: inherit; font-size: 13px; }
.interaction-actions { flex: 0 0 auto; display: flex; align-items: center; gap: 8px; }
.interaction-actions button { min-height: 32px; border-radius: 5px; padding: 0 12px; cursor: pointer; white-space: nowrap; }
.interaction-actions button:disabled { cursor: wait; opacity: .65; }
.interaction-secondary { border: 1px solid var(--border, var(--border-2)); background: transparent; color: var(--text-primary, var(--text-1)); }
.interaction-primary { border: 1px solid var(--color-primary); background: var(--color-primary); color: white; }
.interaction-close { width: 30px; padding: 0 !important; border: 0; background: transparent; color: var(--text-2); font-size: 20px; }
.question-list { display: grid; gap: 14px; max-height: min(55vh, 560px); overflow-y: auto; margin-top: 10px; }
.question-item { border: 0; border-bottom: 1px solid var(--border, #ddd); padding: 0 0 12px; margin: 0; min-width: 0; }
.question-item legend { font-size: 14px; font-weight: 600; padding: 0 0 8px; }
.question-header { font-size: 12px; color: var(--color-primary); margin-right: 8px; }
.question-option { display: flex; align-items: flex-start; gap: 8px; padding: 6px 0; cursor: pointer; }
.question-option input { margin-top: 3px; flex: 0 0 auto; }
.question-option span { min-width: 0; }
.question-option strong { font-size: 13px; }
.question-option small { display: block; color: var(--text-2); font-size: 12px; }
.question-option pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; }

@media (max-width: 720px) {
  .interaction-strip { width: calc(100% - 24px); align-items: stretch; flex-direction: column; gap: 10px; }
  .interaction-copy { align-items: flex-start; flex-direction: column; gap: 2px; }
  .interaction-actions { justify-content: flex-end; }
}
</style>
