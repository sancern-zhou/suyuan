<template>
  <section class="assistant-floating-panel" aria-label="AI 助手">
    <header class="floating-header">
      <div class="assistant-title"><span class="status-dot" :class="{ running: state.isAnalyzing }"></span><div><strong>AI 助手</strong><small>{{ state.isAnalyzing ? '正在处理，可继续补充要求' : '随时为你分析和跟进' }}</small></div></div>
      <div class="header-actions">
        <button type="button" title="新建对话" aria-label="新建对话" @click="newConversation"><Plus :size="18" /></button>
        <button type="button" title="展开主工作区" aria-label="展开主工作区" @click="openWorkspace"><Maximize2 :size="17" /></button>
        <button type="button" title="收起助手" aria-label="收起助手" @click="close"><X :size="19" /></button>
      </div>
    </header>
    <div class="floating-tools"><button type="button" @click="itemsOpen = true">事项与建议</button><span v-if="floating.notificationUnread" class="feedback-hint">有 {{ floating.notificationUnread }} 条新反馈，将在对话中展示</span></div>
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
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Maximize2, Plus, X } from 'lucide-vue-next'
import ReActMessageList from '@/components/ReActMessageList.vue'
import InputBox from '@/components/InputBox.vue'
import AgentInteractionDialog from '@/components/reactAnalysis/dialogs/AgentInteractionDialog.vue'
import AssistantPanel from '@/components/reactAnalysis/AssistantPanel.vue'
import { useReactStore } from '@/stores/reactStore.js'
import { useAssistantFloatingStore } from '@/stores/assistantFloating.js'
import { useConversationActions } from '@/composables/reactAnalysis/useConversationActions.js'
import { buildAssistantPageContext } from '@/services/assistantPageContext.js'

const emit = defineEmits(['close', 'open-workspace'])
const store = useReactStore()
const floating = useAssistantFloatingStore()
const route = useRoute()
const { handleSend, restore, currentConversationPolicy: policy } = useConversationActions(store, { onSettled: () => floating.refresh() })
const state = computed(() => floating.state)
const itemsOpen = ref(false)
const error = ref('')
const interactionResolving = ref(false)

async function send(payload) {
  error.value = ''
  try { await handleSend({ ...payload, agentMode: 'assistant', pageContext: buildAssistantPageContext(route) }) }
  catch (failure) { error.value = failure.message || '发送失败，请稍后重试' }
}
async function continueItem({ query, sessionId }) {
  try {
    if (!await restore(sessionId)) { error.value = '会话恢复失败，请稍后重试'; return }
    await send({ query })
  } catch (failure) { error.value = failure.message || '会话恢复失败' }
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
.floating-header { display: flex; align-items: center; justify-content: space-between; padding: 15px 16px; border-bottom: 1px solid var(--border-color, #e4eaf0); flex-shrink: 0; }
.assistant-title { display: flex; align-items: center; gap: 10px; } .assistant-title strong { display: block; font-size: 16px; } .assistant-title small { display: block; font-size: 11px; margin-top: 3px; color: var(--text-secondary, #738195); }
.status-dot { width: 9px; height: 9px; border-radius: 50%; background: #36a778; box-shadow: 0 0 0 4px #36a77815; } .status-dot.running { background: #4386e8; animation: pulse 1.4s infinite; }
.header-actions { display: flex; gap: 3px; } button { font: inherit; } .header-actions button { border: 0; background: transparent; color: inherit; padding: 7px; cursor: pointer; border-radius: 6px; display: flex; } .header-actions button:hover { background: var(--bg-hover, #f0f4f8); }
.floating-tools { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 6px 14px; border-bottom: 1px solid var(--border-color, #e4eaf0); flex-shrink: 0; } .floating-tools button { padding: 3px 0; border: 0; background: transparent; color: #637995; font-size: 12px; cursor: pointer; } .feedback-hint { color: #477895; font-size: 11px; }
.delegation-banner { padding: 8px 15px; font-size: 12px; background: #edf5ff; color: #34638d; flex-shrink: 0; } .delegation-banner.completed { background: #eaf7f0; color: #26754d; }
.assistant-floating-panel :deep(.message-viewport) { min-height: 0; flex: 1; } .assistant-floating-panel :deep(.message-list-content) { padding: 15px 12px; } .assistant-floating-panel :deep(.welcome-message) { padding: 20px 8px; } .assistant-floating-panel :deep(.welcome-message h2) { font-size: 20px; } .assistant-floating-panel :deep(.input-box) { flex-shrink: 0; }
.floating-error { padding: 8px 14px; background: #fff0f0; color: #b73838; font-size: 12px; display: flex; justify-content: space-between; gap: 8px; } .floating-error button { border: 0; color: inherit; background: transparent; cursor: pointer; } .read-only-notice { font-size: 12px; padding: 8px 14px; color: #78612c; background: #fff9e7; }
.items-backdrop { position: absolute; inset: 0; z-index: 6; background: rgba(13, 34, 54, .24); display: flex; justify-content: flex-end; }
.items-drawer { position: absolute !important; top: 0; right: 0; bottom: 0; left: auto; width: min(400px, 92%) !important; border: 0 !important; border-left: 1px solid var(--border-color, #dce1e7) !important; border-radius: 0 !important; box-shadow: -14px 0 34px rgba(13, 34, 54, .16) !important; }
.items-drawer-enter-active, .items-drawer-leave-active { transition: opacity .2s ease; } .items-drawer-enter-active :deep(.assistant-panel), .items-drawer-leave-active :deep(.assistant-panel) { transition: transform .22s ease; } .items-drawer-enter-from, .items-drawer-leave-to { opacity: 0; } .items-drawer-enter-from :deep(.assistant-panel), .items-drawer-leave-to :deep(.assistant-panel) { transform: translateX(24px); }
@keyframes pulse { 50% { opacity: .45; } }
</style>
