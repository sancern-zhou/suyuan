<template>
  <div class="board">
    <p v-if="loading">正在加载...</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <DrawioBoardPanel
      v-else
      :board-id="activeBoardId"
      :xml="displayXml"
      :title="boardState.title || resource.label"
      :version-files="boardState.versions || []"
      :current-version-id="boardState.currentVersionId"
      :board-dirty="boardState.dirty"
      :draft-revision="boardState.draftRevision"
      :sync-status="boardState.syncStatus"
      @xml-change="handleXmlChange"
      @draft-saved="handleDraftSaved"
    />
  </div>
</template>
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'
import DrawioBoardPanel from '@/components/board/DrawioBoardPanel.vue'
import { useReactStore } from '@/stores/reactStore.js'

const props = defineProps({
  resource: { type: Object, required: true },
  group: { type: Object, default: null },
  contentUrl: { type: String, required: true }
})
const store = useReactStore()
const xml = ref('')
const loading = ref(false)
const error = ref('')
const boardState = computed(() => store.currentState?.board || {})
const resourceBoardId = computed(() => {
  const explicit = props.resource?.board_id || props.resource?.metadata?.board_id || props.resource?.locator?.board_id
  if (explicit) return String(explicit)
  const candidates = [
    props.resource?.locator?.path,
    props.resource?.locator?.local_path,
    props.resource?.path,
    props.resource?.local_path,
    props.resource?.file_path,
    props.resource?.label
  ].filter(Boolean).map(String)
  for (const candidate of candidates) {
    const match = candidate.match(/drawio_boards\/([0-9a-f-]{36})(?:\/|$)/i)
      || candidate.match(/^[0-9a-f-]{36}$/i)
    if (match) return match[1] || match[0]
  }
  return ''
})
const activeBoardId = computed(() => boardState.value.activeBoardId || resourceBoardId.value)
const displayXml = computed(() => boardState.value.currentXml || xml.value)

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await authFetch(props.contentUrl)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    xml.value = await response.text()
  } catch (failure) {
    error.value = failure?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

const handleXmlChange = value => store.updateDrawioBoardXml(value)
const handleDraftSaved = response => {
  const board = store.ensureDrawioBoardState(store.currentState)
  if (response?.draft_revision !== undefined) board.draftRevision = Number(response.draft_revision)
  if (response?.draft_xml_ref) board.draftXmlRef = response.draft_xml_ref
}

onMounted(() => {
  const board = store.ensureDrawioBoardState(store.currentState)
  if (!board.activeBoardId && resourceBoardId.value) board.activeBoardId = resourceBoardId.value
  load()
})
watch(() => props.contentUrl, load)
</script>
<style scoped>.board { height: 100%; }.error { color: #b42318; }</style>
