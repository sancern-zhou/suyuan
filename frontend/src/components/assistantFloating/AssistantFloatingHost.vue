<template>
  <div v-if="floating.enabled" class="assistant-floating-host">
    <Transition name="assistant-panel">
      <div v-if="floating.open" class="floating-window">
        <AssistantFloatingPanel @close="floating.closePanel()" @open-workspace="openWorkspace" />
      </div>
    </Transition>
    <button
      v-if="!floating.open"
      ref="ballRef"
      type="button"
      class="assistant-ball"
      :class="{ running: floating.state?.isAnalyzing, dragging }"
      :style="ballStyle"
      :title="ballTitle"
      :aria-label="ballTitle"
      @pointerdown="startDrag"
      @click="handleClick"
    >
      <MessageCircle :size="27" aria-hidden="true" />
      <span v-if="floating.unread" class="ball-badge">{{ floating.unread > 99 ? '99+' : floating.unread }}</span>
      <span v-else-if="floating.notificationUnread" class="notification-dot"></span>
      <span class="ball-label">{{ assistantName }}</span>
    </button>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { MessageCircle } from 'lucide-vue-next'
import { useAssistantFloatingStore } from '@/stores/assistantFloating.js'
import AssistantFloatingPanel from './AssistantFloatingPanel.vue'
import { projectConfig } from '@/config/projectConfig.js'

// 助手人设名随项目配置（frontend.assistant_name），缺省「助手」。
const assistantName = projectConfig.assistantName
const ballTitle = `打开${assistantName}（可拖动）`
const floating = useAssistantFloatingStore()
const router = useRouter()
const ballRef = ref(null)
const dragging = ref(false)
let start = null
let moved = false
let suppressClick = false
const ballStyle = computed(() => ({ right: `${floating.position.x}px`, bottom: `${floating.position.y}px` }))
watch(() => floating.visible, value => { if (!value) floating.closePanel() })
function handleClick() {
  if (suppressClick) { suppressClick = false; return }
  floating.openPanel()
}
function startDrag(event) {
  if (event.button !== 0) return
  start = { x: event.clientX, y: event.clientY, right: floating.position.x, bottom: floating.position.y }
  moved = false
  dragging.value = false
  window.addEventListener('pointermove', drag)
  window.addEventListener('pointerup', stopDrag, { once: true })
}
function drag(event) {
  if (!start) return
  const dx = event.clientX - start.x
  const dy = event.clientY - start.y
  if (!moved && Math.hypot(dx, dy) < 5) return
  moved = true
  dragging.value = true
  ballRef.value?.setPointerCapture(event.pointerId)
  const size = ballRef.value?.getBoundingClientRect()
  const width = size?.width || 62
  const height = size?.height || 62
  floating.position = {
    x: Math.max(8, Math.min(window.innerWidth - width - 8, start.right - dx)),
    y: Math.max(8, Math.min(window.innerHeight - height - 8, start.bottom - dy))
  }
}
function stopDrag() {
  if (moved) { floating.savePosition(floating.position); suppressClick = true }
  dragging.value = false
  start = null
  window.removeEventListener('pointermove', drag)
}
async function openWorkspace(sessionId, attachment = null) {
  floating.closePanel()
  if (sessionId) await router.push({ name: 'session', params: { id: sessionId }, query: attachment ? { preview_resource: attachment.resourceId, workspace: 'full' } : { workspace: 'full' } })
  else await router.push({ name: 'analysis', query: { assistant: '1', workspace: 'full' } })
}
function handleKeydown(event) {
  if (event.key === 'Escape' && floating.open) floating.closePanel()
}
onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', keepInView)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('pointermove', drag)
  window.removeEventListener('resize', keepInView)
})
function keepInView() {
  floating.savePosition({
    x: Math.max(8, Math.min(window.innerWidth - 70, floating.position.x)),
    y: Math.max(8, Math.min(window.innerHeight - 70, floating.position.y))
  })
}
</script>

<style scoped>
.assistant-floating-host { position: fixed; inset: 0; z-index: 800; pointer-events: none; }
.floating-window { pointer-events: auto; position: fixed; right: 24px; top: 24px; bottom: 24px; width: min(430px, calc(100vw - 32px)); border: 1px solid var(--border-color, #dfe7ef); border-radius: 14px; box-shadow: 0 16px 50px #18334b2b; overflow: hidden; }
.assistant-ball { pointer-events: auto; position: fixed; width: 62px; height: 62px; border: 0; border-radius: 50%; background: linear-gradient(145deg, #347ecc, #2363a7); color: white; cursor: grab; box-shadow: 0 5px 20px #1a578d45; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 1px; touch-action: none; user-select: none; transition: box-shadow .18s; }
.assistant-ball:hover { box-shadow: 0 7px 25px #1a578d66; } .assistant-ball.dragging { cursor: grabbing; transition: none; } .assistant-ball.running { background: linear-gradient(145deg, #248f9e, #236b96); }
.ball-label { font-size: 11px; line-height: 1; } .ball-badge { position: absolute; top: -4px; right: -5px; min-width: 20px; height: 20px; box-sizing: border-box; border: 2px solid white; background: #e45555; border-radius: 11px; padding: 0 4px; font-size: 10px; line-height: 16px; } .notification-dot { position: absolute; width: 11px; height: 11px; border-radius: 50%; border: 2px solid white; background: #e45555; top: 1px; right: 2px; }
.assistant-panel-enter-active, .assistant-panel-leave-active { transition: opacity .18s, transform .18s; } .assistant-panel-enter-from, .assistant-panel-leave-to { opacity: 0; transform: translateX(18px); }
@media (max-width: 600px) { .floating-window { inset: 8px; width: auto; border-radius: 10px; } }
</style>
