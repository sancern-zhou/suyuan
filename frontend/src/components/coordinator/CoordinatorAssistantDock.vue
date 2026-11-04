<template>
  <div class="coordinator-assistant-dock">
    <section
      v-if="open"
      class="assistant-float-panel"
      role="dialog"
      aria-label="苏环智管对话浮窗"
      aria-modal="false"
    >
      <header class="float-header">
        <div class="float-heading">
          <span class="float-avatar" aria-hidden="true">
            <svg viewBox="0 0 48 48">
              <path d="M12 16.5 24 9l12 7.5v15L24 39l-12-7.5v-15Z" />
              <path d="M18 24h12M20 29h8" />
              <circle cx="19" cy="20" r="1.5" /><circle cx="29" cy="20" r="1.5" />
            </svg>
          </span>
          <div><strong>{{ coordinator.name || '智能助手' }}</strong><span>{{ isAnalyzing ? '正在响应，可继续查看当前页面' : '随时提问，协同专业能力' }}</span></div>
        </div>
        <div class="float-actions">
          <button type="button" title="打开完整对话" @click="emit('expand')">
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M11.5 3.5h5v5M8.5 16.5h-5v-5M16.5 3.5 11 9M3.5 16.5 9 11" /></svg>
          </button>
          <button type="button" aria-label="收起助手浮窗" title="收起（Esc）" @click="emit('close')">
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7 5 5 5-5" /></svg>
          </button>
        </div>
      </header>

      <ReActMessageList
        class="float-messages"
        :messages="messages"
        :is-analyzing="isAnalyzing"
        :show-reflexion="showReflexion"
        :reflexion-count="reflexionCount"
        :agent-mode="agentMode"
        :hide-welcome="true"
        :session-id="sessionId"
        :on-message-click="() => emit('expand')"
        @preview-message-attachment="emit('expand')"
      />
      <div v-if="!messages.length && !isAnalyzing" class="float-welcome">
        <h2>{{ coordinator.greeting || '今天需要我关注什么？' }}</h2>
        <p>描述目标即可，我会提取意图并切换到合适的专业智能体。</p>
      </div>
      <div v-if="quickPrompts.length && !isAnalyzing" class="float-quick-prompts" aria-label="快捷提问">
        <button v-for="prompt in quickPrompts" :key="prompt.label" type="button" @click="emit('submit', { query: prompt.prompt, mode: prompt.mode })">{{ prompt.label }}</button>
      </div>
      <InputBox
        ref="inputRef"
        v-model="inputValue"
        :pending-steering-inputs="pendingSteeringInputs"
        :background-runs="backgroundRuns"
        :session-id="sessionId"
        :disabled="inputDisabled"
        :is-analyzing="isAnalyzing"
        placeholder="询问运维情况或描述目标"
        :agent-mode="agentMode"
        @send="send"
        @pause="emit('pause')"
      />
    </section>
    <button
      class="assistant-float-ball"
      :class="{ active: open, running: isAnalyzing, unread: hasUnreadReply }"
      type="button"
      :aria-expanded="open"
      aria-label="打开苏环智管助手"
      title="苏环智管 · 随时提问"
      @click="emit('toggle')"
    >
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="M12 16.5 24 9l12 7.5v15L24 39l-12-7.5v-15Z" />
        <path d="M18 24h12M20 29h8" />
        <circle cx="19" cy="20" r="1.5" /><circle cx="29" cy="20" r="1.5" />
      </svg>
      <span v-if="isAnalyzing || hasUnreadReply" class="float-running-dot" :class="{ unread: hasUnreadReply }" aria-hidden="true"></span>
    </button>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { projectConfig } from '@/config/projectConfig.js'
import { getCoordinatorQuickPrompts } from '@/api/coordinatorConfig.js'
import ReActMessageList from '@/components/ReActMessageList.vue'
import InputBox from '@/components/InputBox.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  coordinator: { type: Object, default: () => projectConfig.coordinator || {} },
  messages: { type: Array, default: () => [] },
  pendingSteeringInputs: { type: Array, default: () => [] },
  backgroundRuns: { type: Array, default: () => [] },
  showReflexion: { type: Boolean, default: false },
  reflexionCount: { type: Number, default: 0 },
  isAnalyzing: { type: Boolean, default: false },
  inputDisabled: { type: Boolean, default: false },
  sessionId: { type: String, default: '' },
  agentMode: { type: String, default: 'ops' }
})
const emit = defineEmits(['toggle', 'close', 'submit', 'pause', 'expand'])
const inputRef = ref(null)
const inputValue = ref('')
const runtimeQuickPrompts = ref(null)
const hasUnreadReply = ref(false)
watch(() => props.open, open => { if (open) hasUnreadReply.value = false })
watch(() => props.messages.length, () => {
  if (!props.open && props.messages.at(-1)?.type === 'final' && !props.messages.at(-1)?.streaming) hasUnreadReply.value = true
})
const quickPrompts = computed(() => Array.isArray(runtimeQuickPrompts.value)
  ? runtimeQuickPrompts.value
  : (Array.isArray(props.coordinator?.quickPrompts) ? props.coordinator.quickPrompts : []))

const send = payload => {
  const query = String(payload?.query || '').trim()
  if (!query) return
  emit('submit', { ...payload, query })
  inputValue.value = ''
}

const focusInput = async () => {
  await nextTick()
  const textarea = inputRef.value?.$el?.querySelector('textarea')
  textarea?.focus()
}

const handleKeydown = event => {
  if (event.key === 'Escape' && props.open) emit('close')
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  getCoordinatorQuickPrompts().then(data => {
    const items = Array.isArray(data?.items) ? data.items : []
    runtimeQuickPrompts.value = items.filter(item => item?.label && item?.prompt)
  }).catch(() => { runtimeQuickPrompts.value = null })
})

onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown))
defineExpose({ focusInput })
</script>

<style lang="scss" scoped>
.coordinator-assistant-dock { position: fixed; z-index: 1500; right: 24px; bottom: 24px; display: flex; align-items: flex-end; flex-direction: column; gap: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif; }
.assistant-float-ball { position: relative; display: grid; width: 58px; height: 58px; flex: 0 0 auto; place-items: center; padding: 0; border: 4px solid rgba(255,255,255,.75); border-radius: 50%; background: linear-gradient(145deg, #0d5068, #0b8290); box-shadow: 0 8px 28px rgba(7,41,59,.27), 0 0 0 1px rgba(13,80,104,.1); color: #e9ffff; cursor: pointer; transition: transform .2s, box-shadow .2s; }
.assistant-float-ball:hover { transform: translateY(-3px); box-shadow: 0 12px 30px rgba(7,41,59,.33), 0 0 0 5px rgba(20,160,174,.1); }
.assistant-float-ball:active { transform: scale(.97); }
.assistant-float-ball svg { width: 35px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
.float-running-dot { position: absolute; top: -1px; right: -1px; width: 13px; height: 13px; border: 3px solid #fff; border-radius: 50%; background: #31c987; box-shadow: 0 0 0 3px rgba(49,201,135,.16); }
.float-running-dot.unread { background: #e5a42f; box-shadow: 0 0 0 3px rgba(229,164,47,.16); }
.assistant-float-panel { display: flex; width: min(480px, calc(100vw - 32px)); height: min(660px, calc(100dvh - 116px)); flex-direction: column; overflow: hidden; border: 1px solid #d5e4e7; border-radius: 18px; background: #f9fcfd; box-shadow: 0 18px 60px rgba(7,41,59,.22); animation: float-enter .2s ease-out; }
.float-header { display: flex; align-items: center; justify-content: space-between; flex: 0 0 auto; gap: 12px; padding: 15px 16px; border-bottom: 1px solid #dce8eb; background: #fff; }
.float-heading { display: flex; align-items: center; gap: 10px; min-width: 0; }
.float-heading > div { display: flex; flex-direction: column; gap: 4px; }
.float-heading strong { color: #0a2531; font-size: 15px; }
.float-heading span:not(.float-avatar) { color: #6b828c; font-size: 11px; }
.float-avatar { display: grid; width: 36px; height: 36px; flex: 0 0 auto; place-items: center; border-radius: 11px; background: #e6f5f4; }
.float-avatar svg { width: 25px; fill: none; stroke: #0e8a96; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
.float-actions { display: flex; gap: 3px; }
.float-actions button { display: grid; width: 32px; height: 32px; place-items: center; padding: 0; border: 0; border-radius: 8px; background: transparent; color: #57737e; cursor: pointer; }
.float-actions button:hover { background: #edf5f6; color: #0e8a96; }
.float-actions svg { width: 19px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.6; }
.float-messages { display: flex; min-height: 120px; flex: 1 1 0; overflow: hidden; background: #f8fbfc; }
.float-messages :deep(.message-list-content) { padding: 16px; }
.float-messages :deep(.user-message) { max-width: 90%; font-size: 13px; }
.float-messages :deep(.message-content) { font-size: 13px; }
.float-welcome { flex: 0 0 auto; padding: 18px 20px 13px; }
.float-welcome h2 { margin: 0 0 6px; color: #0a2531; font-size: 19px; }
.float-welcome p { margin: 0; color: #5b7684; font-size: 12px; line-height: 1.7; }
.float-quick-prompts { display: flex; flex: 0 0 auto; flex-wrap: wrap; gap: 6px; padding: 0 16px 10px; }
.float-quick-prompts button { padding: 5px 9px; border: 1px solid #d1e4e6; border-radius: 999px; background: #fff; color: #44717c; font-size: 11px; cursor: pointer; }
.float-quick-prompts button:hover { border-color: #50afb7; color: #0b7884; }
.assistant-float-panel :deep(.input-area) { flex: 0 0 auto; padding: 8px 12px 12px; background: #f9fcfd; }
.assistant-float-panel :deep(.input-field) { max-height: 100px; font-size: 13px; }
.assistant-float-panel :deep(.smart-event-quick-prompts) { display: none; }
button:focus-visible { outline: 3px solid rgba(14,138,150,.28); outline-offset: 2px; }
@keyframes float-enter { from { opacity: 0; transform: translateY(10px) scale(.98); } to { opacity: 1; transform: none; } }
@media (max-width: 700px) {
  .coordinator-assistant-dock { right: 16px; bottom: 16px; }
  .assistant-float-ball { width: 54px; height: 54px; }
  .assistant-float-panel { height: min(680px, calc(100dvh - 94px)); }
}
@media (prefers-reduced-motion: reduce) { .assistant-float-panel { animation: none; } .assistant-float-ball { transition: none; } }
</style>
