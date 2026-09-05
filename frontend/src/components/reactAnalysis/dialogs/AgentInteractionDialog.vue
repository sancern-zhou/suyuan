<template>
  <div v-if="interaction" class="interaction-overlay" @click.self="close">
    <section class="interaction-dialog" role="dialog" aria-modal="true" :aria-labelledby="titleId">
      <header class="interaction-header">
        <h3 :id="titleId">{{ interaction.title || '需要你的确认' }}</h3>
        <button class="interaction-close" type="button" aria-label="关闭" @click="close">×</button>
      </header>
      <p class="interaction-question">{{ interaction.question }}</p>
      <textarea
        v-if="interaction.kind === 'question'"
        v-model="response"
        class="interaction-response"
        rows="4"
        placeholder="请输入回复"
      />
      <footer class="interaction-actions">
        <button class="interaction-secondary" type="button" @click="resolve('reject')">暂不切换</button>
        <button class="interaction-primary" type="button" @click="resolve(interaction.kind === 'question' ? 'answer' : 'approve')">
          {{ interaction.kind === 'question' ? '提交回复' : '进入工作空间' }}
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  interaction: { type: Object, default: null }
})

const emit = defineEmits(['resolve', 'close'])
const response = ref('')
const titleId = `agent-interaction-${Math.random().toString(36).slice(2)}`

const resolve = (decision) => emit('resolve', { decision, response: response.value || null })
const close = () => emit('close')
</script>

<style scoped>
.interaction-overlay { position: fixed; inset: 0; z-index: 1200; display: grid; place-items: center; padding: 20px; background: rgba(15, 23, 42, .45); }
.interaction-dialog { width: min(460px, 100%); background: var(--surface, #fff); border: 1px solid var(--border, #dbe2ea); border-radius: 8px; box-shadow: 0 18px 48px rgba(15, 23, 42, .2); }
.interaction-header { display: flex; align-items: center; justify-content: space-between; padding: 18px 20px 12px; }
.interaction-header h3 { margin: 0; color: var(--text-primary, #172033); font-size: 17px; }
.interaction-close { border: 0; background: transparent; color: var(--text-secondary, #64748b); font-size: 22px; cursor: pointer; }
.interaction-question { margin: 0; padding: 0 20px 16px; color: var(--text-secondary, #475569); line-height: 1.6; }
.interaction-response { display: block; width: calc(100% - 40px); margin: 0 20px 16px; box-sizing: border-box; resize: vertical; border: 1px solid var(--border, #cbd5e1); border-radius: 6px; padding: 10px; font: inherit; }
.interaction-actions { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px 18px; border-top: 1px solid var(--border, #e2e8f0); }
.interaction-actions button { min-height: 36px; border-radius: 6px; padding: 0 14px; cursor: pointer; }
.interaction-secondary { border: 1px solid var(--border, #cbd5e1); background: transparent; color: var(--text-primary, #334155); }
.interaction-primary { border: 1px solid #2563eb; background: #2563eb; color: white; }
</style>
