<template>
  <div v-if="interaction" class="interaction-strip" role="region" :aria-labelledby="titleId">
    <section class="interaction-content">
      <div class="interaction-copy">
        <h3 :id="titleId">{{ interaction.title || '需要你的确认' }}</h3>
        <p>{{ interaction.question }}</p>
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
        暂不切换
      </button>
      <button class="interaction-primary" type="button" :disabled="resolving" @click="resolve(interaction.kind === 'question' ? 'answer' : 'approve')">
        {{ resolving ? '处理中…' : (interaction.kind === 'question' ? '提交回复' : '进入工作空间') }}
      </button>
      <button class="interaction-close" type="button" aria-label="关闭" :disabled="resolving" @click="close">×</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  interaction: { type: Object, default: null },
  resolving: { type: Boolean, default: false }
})

const emit = defineEmits(['resolve', 'close'])
const response = ref('')
const titleId = `agent-interaction-${Math.random().toString(36).slice(2)}`

const resolve = (decision) => emit('resolve', { decision, response: response.value || null })
const close = () => emit('close')
</script>

<style scoped>
.interaction-strip { width: min(1200px, calc(100% - 40px)); box-sizing: border-box; flex-shrink: 0; display: flex; align-items: center; gap: 16px; margin: 0 auto; padding: 12px 14px; border: 1px solid #c8d8ed; border-radius: 7px; background: #f4f8fd; box-shadow: 0 -2px 10px rgba(30, 64, 110, .06); }
.interaction-content { flex: 1; min-width: 0; }
.interaction-copy { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.interaction-copy h3 { flex: 0 0 auto; margin: 0; color: #20334d; font-size: 14px; line-height: 1.45; }
.interaction-copy p { min-width: 0; margin: 0; color: #53657c; font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }
.interaction-response { display: block; width: 100%; margin-top: 9px; box-sizing: border-box; resize: vertical; border: 1px solid #b8c8dc; border-radius: 6px; padding: 8px 10px; background: #fff; color: #26384f; font: inherit; font-size: 13px; }
.interaction-actions { flex: 0 0 auto; display: flex; align-items: center; gap: 8px; }
.interaction-actions button { min-height: 32px; border-radius: 5px; padding: 0 12px; cursor: pointer; white-space: nowrap; }
.interaction-actions button:disabled { cursor: wait; opacity: .65; }
.interaction-secondary { border: 1px solid var(--border, #cbd5e1); background: transparent; color: var(--text-primary, #334155); }
.interaction-primary { border: 1px solid #2563eb; background: #2563eb; color: white; }
.interaction-close { width: 30px; padding: 0 !important; border: 0; background: transparent; color: #64748b; font-size: 20px; }

@media (max-width: 720px) {
  .interaction-strip { width: calc(100% - 24px); align-items: stretch; flex-direction: column; gap: 10px; }
  .interaction-copy { align-items: flex-start; flex-direction: column; gap: 2px; }
  .interaction-actions { justify-content: flex-end; }
}
</style>
