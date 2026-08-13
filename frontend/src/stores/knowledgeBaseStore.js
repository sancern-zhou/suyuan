/**
 * 知识库状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/knowledgeBase'
import { collectGraphSnapshot } from './knowledgeGraphSnapshot.js'

export const useKnowledgeBaseStore = defineStore('knowledgeBase', () => {
  // 状态
  const knowledgeBases = ref([])
  const selectedIds = ref([])
  const currentKb = ref(null)
  const documents = ref([])
  const currentDoc = ref(null)
  const documentChunks = ref([])
  const loading = ref(false)
  const error = ref(null)
  const chunksLoading = ref(false)
  const chunksError = ref(null)
  const stats = ref(null)
  const strategies = ref([])
  const graphStatus = ref(null)
  const graphEntities = ref([])
  const graphRelations = ref([])
  const graphLoading = ref(false)
  const graphProgress = ref({ loadedEntities: 0, loadedRelations: 0, entityTotal: 0, relationTotal: 0 })
  const graphSnapshotVersion = ref(null)
  const knowledgeScene = ref(null)
  const sceneLoading = ref(false)
  let graphRequestGeneration = 0
  let graphAbortController = null

  // 计算属性
  const sharedKbs = computed(() =>
    knowledgeBases.value.filter(kb => kb.vector_store_scope === 'shared')
  )

  const localKbs = computed(() =>
    knowledgeBases.value.filter(kb => (
      kb.vector_store_scope === 'local' && kb.kb_type === 'public'
    ))
  )

  const privateKbs = computed(() =>
    knowledgeBases.value.filter(kb => (
      kb.vector_store_scope === 'local' && kb.kb_type === 'private'
    ))
  )

  const publicKbs = computed(() => [...sharedKbs.value, ...localKbs.value])

  const selectedKbs = computed(() =>
    knowledgeBases.value.filter(kb => selectedIds.value.includes(kb.id))
  )

  const selectedCount = computed(() => selectedIds.value.length)

  const hasSelection = computed(() => selectedIds.value.length > 0)

  // Actions
  async function fetchKnowledgeBases() {
    loading.value = true
    error.value = null
    try {
      const data = await api.listKnowledgeBases()
      knowledgeBases.value = [...(data.public || []), ...(data.private || [])]

      // 自动选中所有知识库
      if (selectedIds.value.length === 0) {
        selectedIds.value = knowledgeBases.value.map(kb => kb.id)
      }
    } catch (e) {
      error.value = e.message
      console.error('Failed to fetch knowledge bases:', e)
    } finally {
      loading.value = false
    }
  }

  async function createKnowledgeBase(params) {
    loading.value = true
    try {
      const kb = await api.createKnowledgeBase(params)
      knowledgeBases.value.push(kb)
      return kb
    } finally {
      loading.value = false
    }
  }

  async function updateKnowledgeBase(id, params) {
    loading.value = true
    try {
      const kb = await api.updateKnowledgeBase(id, params)
      const index = knowledgeBases.value.findIndex(k => k.id === id)
      if (index !== -1) {
        knowledgeBases.value[index] = kb
      }
      if (currentKb.value?.id === id) {
        currentKb.value = kb
      }
      return kb
    } finally {
      loading.value = false
    }
  }

  async function deleteKnowledgeBase(id) {
    loading.value = true
    try {
      await api.deleteKnowledgeBase(id)
      knowledgeBases.value = knowledgeBases.value.filter(kb => kb.id !== id)
      selectedIds.value = selectedIds.value.filter(sid => sid !== id)
      if (currentKb.value?.id === id) {
        currentKb.value = null
      }
    } finally {
      loading.value = false
    }
  }

  async function fetchDocuments(kbId) {
    loading.value = true
    try {
      const data = await api.listDocuments(kbId)
      documents.value = data.documents || []
      return data
    } catch (e) {
      console.error('Failed to fetch documents:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function uploadDocument(kbId, file, options = {}) {
    loading.value = true
    try {
      const doc = await api.uploadDocument(kbId, file, options)
      documents.value.unshift(doc)

      // 更新知识库文档计数
      const kb = knowledgeBases.value.find(k => k.id === kbId)
      if (kb) {
        kb.document_count += 1
      }

      return doc
    } finally {
      loading.value = false
    }
  }

  async function deleteDocument(kbId, docId) {
    loading.value = true
    try {
      await api.deleteDocument(kbId, docId)
      documents.value = documents.value.filter(d => d.id !== docId)

      // 更新知识库文档计数
      const kb = knowledgeBases.value.find(k => k.id === kbId)
      if (kb && kb.document_count > 0) {
        kb.document_count -= 1
      }
    } finally {
      loading.value = false
    }
  }

  async function replaceDocument(kbId, docId, file) {
    loading.value = true
    error.value = null
    try {
      const doc = await api.replaceDocument(kbId, docId, file)
      const index = documents.value.findIndex(item => item.id === docId)
      if (index !== -1) documents.value[index] = doc
      return doc
    } catch (e) {
      error.value = e.message || '替换文档失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function loadGraph(kbId, { includeHistory = false } = {}) {
    graphAbortController?.abort()
    graphAbortController = new AbortController()
    const generation = ++graphRequestGeneration
    const signal = graphAbortController.signal
    graphLoading.value = true
    error.value = null
    try {
      const statuses = includeHistory
        ? ['candidate', 'confirmed', 'published', 'rejected', 'archived', 'merged']
        : ['candidate', 'confirmed', 'published']
      const [status, snapshot] = await Promise.all([
        api.getKnowledgeGraphStatus(kbId),
        collectGraphSnapshot(
          params => api.getKnowledgeGraphSnapshotPage(kbId, params),
          {
            statuses,
            signal,
            onProgress: progress => {
              if (generation === graphRequestGeneration) graphProgress.value = progress
            }
          }
        )
      ])
      if (generation !== graphRequestGeneration || signal.aborted) return null
      graphStatus.value = status
      graphEntities.value = snapshot.entities
      graphRelations.value = snapshot.relations
      graphSnapshotVersion.value = snapshot.snapshotVersion
      return { status, entities: snapshot.entities, relations: snapshot.relations }
    } catch (e) {
      if (e?.name === 'AbortError') return null
      error.value = e.message || '加载知识图谱失败'
      throw e
    } finally {
      if (generation === graphRequestGeneration) graphLoading.value = false
    }
  }

  async function loadKnowledgeScene(kbId) {
    sceneLoading.value = true
    try {
      knowledgeScene.value = await api.getKnowledgeScene(kbId)
      return knowledgeScene.value
    } finally {
      sceneLoading.value = false
    }
  }

  async function discoverKnowledgeScene(kbId, payload) {
    sceneLoading.value = true
    try {
      const profile = await api.discoverKnowledgeScene(kbId, payload)
      knowledgeScene.value = {
        ...(knowledgeScene.value || {}),
        knowledge_base_id: kbId,
        scene_status: 'awaiting_confirmation',
        profile
      }
      return profile
    } finally {
      sceneLoading.value = false
    }
  }

  async function confirmKnowledgeScene(kbId, profileId, payload) {
    sceneLoading.value = true
    try {
      const result = await api.confirmKnowledgeScene(kbId, profileId, payload)
      knowledgeScene.value = { ...result, profile: result.profile || result }
      return result
    } finally {
      sceneLoading.value = false
    }
  }

  async function retryDocument(kbId, docId) {
    loading.value = true
    try {
      const doc = await api.retryDocument(kbId, docId)
      const index = documents.value.findIndex(d => d.id === docId)
      if (index !== -1) {
        documents.value[index] = doc
      }
      return doc
    } finally {
      loading.value = false
    }
  }

  async function fetchStats() {
    try {
      stats.value = await api.getKnowledgeBaseStats()
    } catch (e) {
      console.error('Failed to fetch stats:', e)
    }
  }

  async function fetchStrategies() {
    try {
      const data = await api.getChunkingStrategies()
      strategies.value = data.strategies || []
    } catch (e) {
      console.error('Failed to fetch strategies:', e)
    }
  }

  async function fetchDocumentChunks(kbId, docId, targetChunkId = null) {
    chunksLoading.value = true
    chunksError.value = null
    try {
      const data = await api.getDocumentChunks(kbId, docId)
      documentChunks.value = data.chunks || []
      currentDoc.value = {
        id: data.document_id,
        filename: data.filename,
        total: data.total,
        targetChunkId
      }
      return data
    } catch (e) {
      console.error('Failed to fetch document chunks:', e)
      chunksError.value = e.message || '获取分块失败'
      throw e
    } finally {
      chunksLoading.value = false
    }
  }

  function clearCurrentDoc() {
    currentDoc.value = null
    documentChunks.value = []
    chunksError.value = null
  }

  function toggleSelection(id) {
    const index = selectedIds.value.indexOf(id)
    if (index > -1) {
      selectedIds.value.splice(index, 1)
    } else {
      selectedIds.value.push(id)
    }
  }

  function selectKnowledgeBase(kb) {
    currentKb.value = kb
    if (kb) {
      fetchDocuments(kb.id).catch(e => console.error('Failed to fetch documents:', e))
    }
  }

  function clearSelection() {
    selectedIds.value = []
  }

  function selectAll() {
    selectedIds.value = knowledgeBases.value.map(kb => kb.id)
  }

  return {
    // State
    knowledgeBases,
    selectedIds,
    currentKb,
    documents,
    currentDoc,
    documentChunks,
    loading,
    error,
    chunksLoading,
    chunksError,
    stats,
    strategies,
    graphStatus,
    graphEntities,
    graphRelations,
    graphLoading,
    graphProgress,
    graphSnapshotVersion,
    knowledgeScene,
    sceneLoading,

    // Computed
    sharedKbs,
    localKbs,
    publicKbs,
    privateKbs,
    selectedKbs,
    selectedCount,
    hasSelection,

    // Actions
    fetchKnowledgeBases,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    fetchDocuments,
    uploadDocument,
    replaceDocument,
    deleteDocument,
    retryDocument,
    fetchStats,
    fetchStrategies,
    fetchDocumentChunks,
    loadGraph,
    loadKnowledgeScene,
    discoverKnowledgeScene,
    confirmKnowledgeScene,
    clearCurrentDoc,
    toggleSelection,
    selectKnowledgeBase,
    clearSelection,
    selectAll
  }
})
