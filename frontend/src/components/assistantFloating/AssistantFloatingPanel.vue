<template>
  <section class="assistant-floating-panel" aria-label="助手">
    <header class="floating-header">
      <div class="assistant-title"><span class="status-dot" :class="{ running: state.isAnalyzing }"></span><strong>助手</strong></div>
      <div class="header-actions">
        <button type="button" class="items-toggle" :class="{ 'has-unread': floating.notificationUnread }" title="事项与建议" aria-label="事项与建议" @click="itemsOpen = true"><ListChecks :size="17" /></button>
        <button type="button" title="新建对话" aria-label="新建对话" @click="newConversation"><Plus :size="18" /></button>
        <button type="button" title="展开主工作区" aria-label="展开主工作区" @click="openWorkspace"><Maximize2 :size="17" /></button>
        <button type="button" title="收起（Esc）" aria-label="收起助手" @click="close"><ChevronDown :size="19" /></button>
      </div>
    </header>
    <div v-if="error" class="floating-error" role="alert">{{ error }}<button type="button" @click="error = ''">知道了</button></div>
    <div v-if="state.backgroundDelegation" class="delegation-banner" :class="state.backgroundDelegation.phase">
      {{ state.backgroundDelegation.phase === 'completed' ? '后台任务已完成' : '后台任务运行中，可直接追问进展' }}
    </div>
    <ReActMessageList
      :messages="state.messages || []"
      :is-analyzing="!!state.isAnalyzing"
      :show-reflexion="!!state.showReflexion"
      :reflexion-count="state.reflexionCount || 0"
      :use-markdown="true"
      agent-mode="assistant"
      :session-id="state.sessionId || ''"
      :has-more-messages="!!state.pagination?.hasMoreMessages"
      :total-message-count="state.pagination?.totalMessageCount || 0"
      :loading-more="!!state.pagination?.loadingMore"
      @load-more="store.loadMoreMessages()"
      @preview-message-attachment="preview"
    />
    <div v-if="!policy.readOnly && quickPrompts.length && !state.isAnalyzing" class="floating-quick-prompts" aria-label="快捷提问">
      <button v-for="prompt in quickPrompts" :key="prompt.label" type="button" :title="prompt.prompt" @click="send({ query: prompt.prompt })">{{ prompt.label }}</button>
    </div>
    <div v-if="policy.readOnly" class="read-only-notice">{{ policy.notice }}</div>
    <AgentInteractionDialog
      :interaction="state.pendingInteraction"
      :resolving="interactionResolving"
      @resolve="resolveInteraction"
      @close="resolveInteraction({ decision: 'reject' })"
    />
    <InputBox
      v-model="state.currentMessage"
      :session-id="state.sessionId || ''"
      :disabled="policy.readOnly"
      :is-analyzing="!!state.isAnalyzing"
      :pending-steering-inputs="state.pendingSteeringInputs || []"
      :background-runs="state.backgroundDelegation?.runs || []"
      agent-mode="assistant"
      placeholder="向助手提问，或让它跟进当前工作"
      @send="send"
      @pause="store.pauseAnalysis()"
    />
    <Transition name="items-drawer">
      <div v-if="itemsOpen" class="items-backdrop" @click.self="itemsOpen = false">
        <AssistantPanel class="items-drawer" :is-analyzing="!!state.isAnalyzing" :read-only="policy.readOnly" @close="itemsOpen = false" @continue="continueItem" />
      </div>
    </Transition>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ChevronDown, ListChecks, Maximize2, Plus } from 'lucide-vue-next'
import ReActMessageList from '@/components/ReActMessageList.vue'
import InputBox from '@/components/InputBox.vue'
import AgentInteractionDialog from '@/components/reactAnalysis/dialogs/AgentInteractionDialog.vue'
import AssistantPanel from '@/components/reactAnalysis/AssistantPanel.vue'
import { projectConfig } from '@/config/projectConfig.js'
import { getCoordinatorQuickPrompts } from '@/api/coordinatorConfig.js'
import { useReactStore } from '@/stores/reactStore.js'
import { useAssistantFloatingStore } from '@/stores/assistantFloating.js'
import { useConversationActions } from '@/composables/reactAnalysis/useConversationActions.js'
import { buildAssistantPageContext } from '@/services/assistantPageContext.js'

const emit = defineEmits(['close', 'open-workspace'])
const store = useReactStore()
const floating = useAssistantFloatingStore()
const route = useRoute()
const { handleSend, currentConversationPolicy: policy } = useConversationActions(store, {
  getState: () => floating.state,
  preserveCurrentMode: true,
  onSettled: () => floating.refresh()
})
const state = computed(() => floating.state)
const itemsOpen = ref(false)
const error = ref('')
const interactionResolving = ref(false)
// 常用问题：运行时配置优先（管理端可配、无需重建），失败回落项目内置配置。
const runtimeQuickPrompts = ref(null)
const quickPrompts = computed(() => Array.isArray(runtimeQuickPrompts.value)
  ? runtimeQuickPrompts.value
  : (Array.isArray(projectConfig.coordinator?.quickPrompts) ? projectConfig.coordinator.quickPrompts : []))

onMounted(() => {
  getCoordinatorQuickPrompts().then(data => {
    const items = Array.isArray(data?.items) ? data.items : []
    runtimeQuickPrompts.value = items.filter(item => item?.label && item?.prompt)
  }).catch(() => { runtimeQuickPrompts.value = null })
})

async function send(payload) {
  error.value = ''
  try { await handleSend({ ...payload, agentMode: 'assistant', pageContext: buildAssistantPageContext(route) }) }
  catch (failure) { error.value = failure.message || '发送失败，请稍后重试' }
}
async function continueItem({ query, sessionId }) {
  try {
    // 浮窗内切换 assistant 上下文到来源会话并增量同步，不切全局模式、不跳全页。
    floating.switchAssistantSession(sessionId)
    await floating.refresh()
    await send({ query })
  } catch (failure) { error.value = failure.message || '会话切换失败' }
}
function newConversation() { floating.newConversation() }
function openWorkspace() { emit('open-workspace', state.value.sessionId) }
function preview(payload) { emit('open-workspace', payload.sessionId, payload) }
function close() { emit('close') }
async function resolveInteraction(resolution) {
  if (interactionResolving.value) return
  interactionResolving.value = true
  try { await store.resolvePendingInteraction(resolution) }
  catch (failure) { error.value = failure.message || '操作失败' }
  finally { interactionResolving.value = false }
}
</script>

<style scoped>
.assistant-floating-panel { position: relative; display: flex; flex-direction: column; height: 100%; min-height: 0; background: var(--bg-container, #fff); color: var(--text-primary, #1f2d3d); overflow: hidden; }
.floating-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px 8px 14px; border-bottom: 1px solid var(--border-color, #e4eaf0); flex-shrink: 0; }
.assistant-title { display: flex; align-items: center; gap: 8px; } .assistant-title strong { font-size: 15px; }
.status-dot { width: 9px; height: 9px; border-radius: 50%; background: #36a778; box-shadow: 0 0 0 4px #36a77815; flex-shrink: 0; } .status-dot.running { background: #4386e8; animation: pulse 1.4s infinite; }
.header-actions { display: flex; gap: 2px; } button { font: inherit; } .header-actions button { position: relative; border: 0; background: transparent; color: inherit; padding: 6px; cursor: pointer; border-radius: 6px; display: flex; } .header-actions button:hover { background: var(--bg-hover, #f0f4f8); }
.items-toggle.has-unread::after { content: ''; position: absolute; top: 4px; right: 4px; width: 7px; height: 7px; border-radius: 50%; background: #e45555; border: 1.5px solid #fff; }
.delegation-banner { padding: 6px 14px; font-size: 12px; background: #edf5ff; color: #34638d; flex-shrink: 0; } .delegation-banner.completed { background: #eaf7f0; color: #26754d; }
.floating-quick-prompts { display: flex; flex-wrap: wrap; gap: 6px; padding: 6px 10px 0; flex-shrink: 0; }
.floating-quick-prompts button { padding: 5px 10px; border: 1px solid var(--border-color, #dfe7ef); border-radius: 999px; background: var(--bg-container, #fff); color: var(--text-secondary, #5a6b7d); font-size: 12px; cursor: pointer; }
.floating-quick-prompts button:hover { border-color: #4386e8; color: #2a5da8; }
.assistant-floating-panel :deep(.message-viewport) { min-height: 0; flex: 1; }
.assistant-floating-panel :deep(.message-list-content) { padding: 12px 10px; }
.assistant-floating-panel :deep(.agent-message.final) { background: transparent; padding: 2px 2px; }
.assistant-floating-panel :deep(.welcome-message) { padding: 14px 6px; } .assistant-floating-panel :deep(.welcome-message h2) { font-size: 18px; } .assistant-floating-panel :deep(.welcome-capabilities) { display: none; }
.assistant-floating-panel :deep(.input-area) { padding: 6px 8px 8px; }
.assistant-floating-panel :deep(.input-wrapper) { flex-direction: row; align-items: flex-end; gap: 4px; }
.assistant-floating-panel :deep(.input-field) { flex: 1; min-width: 0; min-height: 40px; max-height: 110px; padding: 10px 4px 10px 12px; font-size: 14px; }
.assistant-floating-panel :deep(.input-footer) { min-height: 40px; align-items: flex-end; padding: 2px 2px 4px 0; border-top: none; }
.assistant-floating-panel :deep(.action-group) { padding: 2px; }
.assistant-floating-panel :deep(.pending-steering-indicator) { position: absolute; top: -22px; left: 10px; padding: 0; }
.assistant-floating-panel :deep(.input-box), .assistant-floating-panel :deep(.input-area) { flex-shrink: 0; }
.floating-error { padding: 6px 14px; background: #fff0f0; color: #b73838; font-size: 12px; display: flex; justify-content: space-between; gap: 8px; } .floating-error button { border: 0; color: inherit; background: transparent; cursor: pointer; } .read-only-notice { font-size: 12px; padding: 6px 14px; color: #78612c; background: #fff9e7; }
.items-backdrop { position: absolute; inset: 0; z-index: 6; background: rgba(13, 34, 54, .24); display: flex; justify-content: flex-end; }
.items-drawer { position: absolute !important; top: 0; right: 0; bottom: 0; left: auto; width: min(400px, 92%) !important; border: 0 !important; border-left: 1px solid var(--border-color, #dce1e7) !important; border-radius: 0 !important; box-shadow: -14px 0 34px rgba(13, 34, 54, .16) !important; }
.items-drawer-enter-active, .items-drawer-leave-active { transition: opacity .2s ease; } .items-drawer-enter-active :deep(.assistant-panel), .items-drawer-leave-active :deep(.assistant-panel) { transition: transform .22s ease; } .items-drawer-enter-from, .items-drawer-leave-to { opacity: 0; } .items-drawer-enter-from :deep(.assistant-panel), .items-drawer-leave-to :deep(.assistant-panel) { transform: translateX(24px); }
@keyframes pulse { 50% { opacity: .45; } }
</style>
