import { authFetch } from '@/auth/http.js'
// ReAct Agent状态管理
// 多模式并行任务系统 - 按模式隔离状态

import { defineStore } from 'pinia'
import { agentAPI } from '../services/reactApi.js'
import { uploadChatFile } from '../services/uploadApi.js'
import {
  isProjectAgentMode,
  projectConfig,
  resolveProjectDefaultAgentMode
} from '../config/projectConfig.js'
import {
  commitManualBoardVersion,
  getBoardVersions,
  saveBoardDraft
} from '../api/board.js'
import {
  confirmActiveDrawioBoardCommit,
  exportActiveDrawioBoardXml,
  getActiveDrawioBoardWorkingVersionId
} from '../components/board/drawioBoardBridge.js'
import { prepareBoardForSend } from '../components/board/boardSendPreparation.js'
import {
  isAcceptedBoardPayload,
  mapServerBoardVersions,
  shouldPreviewBoardCandidate
} from '../components/board/boardVersionHistory.js'
import { createQueryVoicePlaybackQueue } from '../services/voicePlaybackQueue.js'
import { autoSaveSession } from '../api/session.js'
import { useSessionResourceStore } from './sessionResourceStore.js'
import { applyResourceStreamEvent } from '../services/sessionResourceLifecycle.js'
import {
  convertStreamingAnswerToThoughtIfToolPlanning,
  freezeActiveAssistantOutput
} from './reactStoreStreaming.js'
import {
  addPendingSteeringInput,
  applyPendingSteeringInputs,
  fallbackSteeringInputToQueue,
  promoteUnappliedSteeringInputsToQueue,
  removePendingSteeringInput
} from './reactStoreSteering.js'
import { getEventRunId, shouldApplyRunEvent } from './reactStoreRunOwnership.js'
import {
  acknowledgeQueuedInput,
  enqueueUserInput,
  hasShownClientMessage,
  peekNextQueuedInput,
  queueIncomingBehindPendingAndTakeNext,
} from './reactStoreQueue.js'
import { restoreMapScene } from './reactStoreMapScene.js'
import { normalizeRestoredMessages } from './sessionContent.js'
import { mergeMapPrograms } from '../components/queryDashboard/mapProgramMerge.js'

const VALID_MODES = ['assistant', 'ppt', 'expert', 'query', 'jiangsu_query', 'smart_inspection', 'operations_analysis', 'device_control', 'station_fault_diagnosis', 'report', 'chart', 'board', 'ops', 'graph']
const DEFAULT_AGENT_MODE = resolveProjectDefaultAgentMode(projectConfig, VALID_MODES)
const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const drawioDraftTimers = new Map()
const DRAWIO_DRAFT_DEBOUNCE_MS = 1000

const cancelDrawioDraftSave = (boardId) => {
  const timer = drawioDraftTimers.get(boardId)
  if (timer) clearTimeout(timer)
  drawioDraftTimers.delete(boardId)
}

const scheduleDrawioDraftSave = (board) => {
  const boardId = board?.activeBoardId
  if (!boardId || !board?.currentXml) return
  cancelDrawioDraftSave(boardId)
  const xml = board.currentXml
  const timer = setTimeout(async () => {
    drawioDraftTimers.delete(boardId)
    try {
      await saveBoardDraft(boardId, xml)
    } catch (error) {
      console.warn('[drawio-board] draft autosave failed', {
        boardId,
        error: error?.message || error
      })
    }
  }, DRAWIO_DRAFT_DEBOUNCE_MS)
  drawioDraftTimers.set(boardId, timer)
}

export const isQueryVoiceOutputEnabled = () => {
  if (typeof localStorage === 'undefined') return false
  return localStorage.getItem('query-voice-output-enabled') === 'true'
}

export const extractMapProgram = (data = {}) => data?.map_program ||
  data?.metadata?.map_program ||
  data?.result?.map_program ||
  data?.result?.data?.map_program ||
  data?.result?.metadata?.map_program ||
  null

export const buildMapContext = (targetState = {}, options = {}) => {
  const { consume = true, limit = 10 } = options
  const events = Array.isArray(targetState.mapEvents) ? targetState.mapEvents : []
  if (events.length === 0) return null

  const selectedEvents = events.slice(-limit)
  if (consume) {
    targetState.mapEvents = []
  }

  return {
    type: 'map_context',
    session_id: targetState.sessionId || selectedEvents[selectedEvents.length - 1]?.session_id || null,
    current_program: targetState.currentMapProgram || null,
    events: selectedEvents
  }
}

export const applyMapProgramMetadata = (targetState, data = {}) => {
  const mapProgram = extractMapProgram(data)
  if (mapProgram) {
    if (!Array.isArray(targetState.mapPrograms)) {
      targetState.mapPrograms = []
    }
    targetState.currentMapProgram = mergeMapPrograms(targetState.currentMapProgram, mapProgram)
    targetState.mapPrograms.push(mapProgram)
  }
  return targetState
}

// 辅助函数：将 content 转换为字符串（支持字符串和 content blocks 格式）
const contentToString = (content) => {
  if (content === null || content === undefined) {
    return ''
  }
  if (typeof content === 'string') {
    return content
  }
  if (Array.isArray(content)) {
    // Anthropic content blocks 格式：提取可显示文本块并拼接
    const textBlocks = content
      .filter(block => block.type === 'text' || block.type === 'thinking')
      .map(block => block.text || block.thinking || '')
    return textBlocks.length > 0 ? textBlocks.join('') : ''
  }
  if (typeof content === 'object') {
    if (content.text) return String(content.text)
    if (content.thinking) return String(content.thinking)
    if (content.message) return String(content.message)
    try {
      return JSON.stringify(content)
    } catch {
      return String(content)
    }
  }
  return String(content)
}

// 辅助函数：安全提取 content 预览（支持字符串和 content blocks 格式）
const getContentPreview = (content, maxLength = 100) => {
  const text = contentToString(content)
  return text.substring(0, maxLength)
}

const createEmptyDrawioBoardState = () => ({
  activeBoardId: null,
  title: '',
  currentXml: '',
  previousXml: '',
  undoStack: [],
  redoStack: [],
  applyingHistory: false,
  versions: [],
  currentVersionId: null,
  baseVersionId: null,
  selectedCells: [],
  pendingSnapshotAttachment: null,
  revision: 0,
  currentVersionSha256: null,
  syncStatus: 'idle',
  syncError: null,
  readOnly: false,
  qualityStatus: null,
  qualityReport: {},
  version: 0,
  dirty: false,
  updatedAt: null
})

const isDrawioBoardToolResult = (result = {}) => {
  const data = result?.data || {}
  const metadata = result?.metadata || {}
  return metadata?.generator === 'create_drawio_board' ||
    metadata.generator === 'create_drawio_board' ||
    data?.artifact_kind === 'drawio_board' ||
    data.artifact_kind === 'drawio_board'
}

const getDrawioBoardPayload = (result = {}) => {
  const data = result?.data || {}
  return data.board || data
}

const getDrawioBoardXml = (payload = {}) => {
  return payload.currentXml ||
    payload.current_xml ||
    payload.xml ||
    payload.drawio_xml ||
    payload.mxfile ||
    ''
}

const getDrawioBoardXmlRef = (payload = {}, result = {}) => {
  if (payload.xml_ref && typeof payload.xml_ref === 'object') {
    return payload.xml_ref
  }
  const artifacts = result?.refs?.artifacts
  if (Array.isArray(artifacts)) {
    return artifacts.find(item => item?.kind === 'drawio_board_xml' || item?.artifact_kind === 'drawio_board') || null
  }
  return null
}

const readDrawioBoardXmlFromRef = async (xmlRef = {}) => {
  const directUrl = xmlRef.read_url || xmlRef.url || xmlRef.download_url
  const localPath = xmlRef.local_path || xmlRef.path || xmlRef.file_path
  const normalizedDirectUrl = directUrl?.startsWith('/api/') && API_BASE_URL !== '/api'
    ? `${API_BASE_URL}${directUrl.slice(4)}`
    : directUrl
  const url = normalizedDirectUrl || (localPath ? `${API_BASE_URL}/file/${encodeURIComponent(localPath)}` : '')
  if (!url) return ''
  const response = await authFetch(url, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`Failed to read drawio xml ref: ${response.status}`)
  }
  return await response.text()
}

const sanitizeDrawioVersionFileName = (title = 'drawio-board') => {
  const safeTitle = String(title || 'drawio-board')
    .replace(/[\\/:*?"<>|]+/g, '_')
    .trim() || 'drawio-board'
  return safeTitle
}

const createDrawioBoardVersionRecord = ({
  board = {},
  payload = {},
  result = {},
  xml = '',
  source = 'agent'
} = {}) => {
  const versions = Array.isArray(board.versions) ? board.versions : []
  const requestedVersionNumber = Number(payload.version_number || payload.version || 0)
  const versionNumber = requestedVersionNumber > 0 ? requestedVersionNumber : versions.length + 1
  const stableId = payload.version_id ||
    payload.versionId ||
    `${payload.artifact_id || payload.board_id || board.activeBoardId || 'drawio'}_v${versionNumber}_${Date.now()}`
  const title = payload.title || payload.name || board.title || 'Draw.io Board'
  const fileName = payload.file_name ||
    payload.fileName ||
    `${sanitizeDrawioVersionFileName(title)}-v${versionNumber}.drawio`

  return {
    id: String(stableId),
    version_id: String(stableId),
    versionNumber,
    version_number: versionNumber,
    title,
    xml,
    file_name: fileName,
    file_path: payload.file_path || payload.path || `drawio_versions/${fileName}`,
    format: 'drawio',
    source,
    lifecycleStatus: payload.lifecycle_status || payload.lifecycleStatus || 'accepted',
    qualityStatus: payload.quality_status || payload.qualityStatus || 'pending',
    qualityReport: payload.quality_report || payload.qualityReport || {},
    screenshotUrl: payload.screenshot_ref?.read_url || payload.screenshot_ref?.url || null,
    visibleInHistory: (payload.lifecycle_status || payload.lifecycleStatus || 'accepted') === 'accepted',
    downloadLabel: fileName,
    summary: result.summary || payload.summary || '',
    created_at: payload.created_at || payload.createdAt || result.timestamp || new Date().toISOString(),
    is_current: true
  }
}

const getDrawioBoardResultsFromMessage = (message = {}) => {
  if (!message || message.type !== 'tool_result') return []

  const data = message.data || {}
  const candidates = []
  if (data.result) {
    candidates.push(data.result)
  }
  if (Array.isArray(data.results)) {
    candidates.push(...data.results)
  }
  if (isDrawioBoardToolResult(data)) {
    candidates.push(data)
  }
  return candidates.filter(candidate => isDrawioBoardToolResult(candidate))
}

const findLatestDrawioBoardResultFromMessages = (messages = []) => {
  if (!Array.isArray(messages)) return null

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const results = getDrawioBoardResultsFromMessage(messages[index])
    if (results.length > 0) {
      return results[results.length - 1]
    }
  }
  return null
}

// 辅助函数：创建空的模式状态
const createEmptyModeState = () => ({
  // 基础状态
  sessionId: null,
  conversationAccess: {
    source: 'web',
    read_only_on_web: false
  },
  activeRunId: null,
  ignoredRunIds: [],
  pendingPausedRunId: null,
  isAnalyzing: false,
  error: null,
  isInterruption: false,

  // 对话
  messages: [],
  currentMessage: '',

  // 分析状态
  isComplete: false,
  iterations: 0,
  maxIterations: 120,

  // 增强功能
  showReflexion: false,
  reflexionCount: 0,

  // 多专家系统状态
  expertSystemEnabled: false,
  expertResults: {},
  lastExpertResults: null,
  selectedExperts: [],

  // 结果
  finalAnswer: '',
  finalAnswers: [],
  hasResults: false,
  dashboardOverview: null,
  mapPrograms: [],
  currentMapProgram: null,
  mapEvents: [],

  // 画板编辑状态（预览由统一资源目录负责）
  board: createEmptyDrawioBoardState(),

  // 结果管理系统
  results: {
    map: null,
    charts: [],
    tables: [],
    text: ''
  },

  // 原有工作流字段
  sessionRound: 0,
  interventionQueue: [],
  pendingUserInputs: [],
  pendingSteeringInputs: [],

  // 消息分页加载状态
  pagination: {
    hasMoreMessages: false,
    totalMessageCount: 0,
    oldestSequence: null,
    loadingMore: false
  },

  // 流式渲染状态
  streamingAnswerMessageId: null,
  _forceRenderCount: 0
})

export const useReactStore = defineStore('react', {
  state: () => {
    // 从localStorage恢复currentMode
    const savedMode = localStorage.getItem('current-mode')
    const initialMode = isProjectAgentMode(savedMode, projectConfig, VALID_MODES)
      ? savedMode
      : DEFAULT_AGENT_MODE
    if (initialMode !== savedMode) {
      localStorage.setItem('current-mode', initialMode)
    }

    return {
      // 当前激活的模式
      currentMode: initialMode,

      // 用户标识（跨会话持久化，用于记忆共享）
      // 默认为 null，使用模式内共享记忆（不跨模式共享）
      userIdentifier: null,

      // 所有模式的状态（按模式隔离）
      modeStates: {
        assistant: createEmptyModeState(),
        ppt: createEmptyModeState(),
        expert: createEmptyModeState(),
        query: createEmptyModeState(),
        jiangsu_query: createEmptyModeState(),
        smart_inspection: createEmptyModeState(),
        operations_analysis: createEmptyModeState(),
        device_control: createEmptyModeState(),
        station_fault_diagnosis: createEmptyModeState(),
        report: createEmptyModeState(),
        chart: createEmptyModeState(),
        board: createEmptyModeState(),
        ops: createEmptyModeState(),
        graph: createEmptyModeState()
      },

      // 同一模式下的多会话状态，key 为完整 sessionId
      sessionStates: {},
      activeSessionByMode: {},

      // 工具列表（全局共享）
      availableTools: []
    }
  },

  getters: {
    // ✅ 向后兼容：当前模式的状态（核心getter）
    currentState: (state) => {
      const activeSessionId = state.activeSessionByMode[state.currentMode]
      if (activeSessionId && state.sessionStates[activeSessionId]) {
        return state.sessionStates[activeSessionId]
      }
      return state.modeStates[state.currentMode] || state.modeStates.assistant
    },

    // ✅ 向后兼容：sessionId
    sessionId() {
      return this.currentState?.sessionId || null
    },

    // ✅ 向后兼容：isAnalyzing
    isAnalyzing() {
      return this.currentState?.isAnalyzing || false
    },

    // ✅ 向后兼容：messages
    messages() {
      return this.currentState?.messages || []
    },

    // ✅ 向后兼容：agentMode (返回currentMode)
    agentMode: (state) => state.currentMode,

    // ✅ 向后兼容：error
    error() {
      return this.currentState?.error || null
    },

    // ✅ 向后兼容：finalAnswer
    finalAnswer() {
      return this.currentState?.finalAnswer || ''
    },

    // ✅ 向后兼容：hasResults
    hasResults() {
      return this.currentState?.hasResults || false
    },

    // ✅ 向后兼容：lastExpertResults
    lastExpertResults() {
      return this.currentState?.lastExpertResults || null
    },

    // ✅ 向后兼容：isComplete
    isComplete() {
      return this.currentState?.isComplete || false
    },

    // ✅ 向后兼容：iterations
    iterations() {
      return this.currentState?.iterations || 0
    },

    // ✅ 向后兼容：maxIterations
    maxIterations() {
      return this.currentState?.maxIterations || 30
    },

    // ✅ 向后兼容：sessionRound
    sessionRound() {
      return this.currentState?.sessionRound || 0
    },

    // 新增：获取所有正在运行的模式
    runningModes: (state) => {
      const modes = new Set()
      Object.entries(state.modeStates)
        .filter(([_, modeState]) => modeState.isAnalyzing)
        .forEach(([mode]) => modes.add(mode))
      Object.values(state.sessionStates)
        .filter(sessionState => sessionState.isAnalyzing)
        .forEach(sessionState => modes.add(sessionState.mode || state.currentMode))
      return Array.from(modes)
    },

    // 新增：获取每个模式的消息数量
    modeMessageCounts: (state) => {
      const counts = {}
      for (const [mode, modeState] of Object.entries(state.modeStates)) {
        counts[mode] = modeState.messages.length
      }
      return counts
    },

    // 对话列表（排除内部事件）
    conversation: (state) => {
      const currentMessages = state.modeStates[state.currentMode]?.messages || []
      // ✅ 只显示用户消息、最终答案（thought 是过程，应该被折叠）
      return currentMessages.filter(msg =>
        msg.type === 'user' || msg.type === 'agent' || msg.type === 'final'
      )
    },

    // 分析日志（内部事件）
    analysisLog: (state) => {
      const currentMessages = state.modeStates[state.currentMode]?.messages || []
      // ✅ thought、tool_use、tool_result 都是过程消息
      return currentMessages.filter(msg =>
        msg.type === 'start' || msg.type === 'thought' ||
        msg.type === 'tool_use' || msg.type === 'tool_result' || msg.type === 'error'
      )
    },

    // 可输入状态
    canInput: (state) => {
      const currentModeState = state.modeStates[state.currentMode]
      return currentModeState ? !currentModeState.isAnalyzing : true
    },

    // 进度
    progress: (state) => {
      const currentModeState = state.modeStates[state.currentMode]
      if (!currentModeState || currentModeState.maxIterations === 0) return 0
      return Math.min(100, Math.round((currentModeState.iterations / currentModeState.maxIterations) * 100))
    },

    // 已完成的工具调用
    completedTools: (state) => {
      const currentMessages = state.modeStates[state.currentMode]?.messages || []
      return currentMessages
        .filter(m => m.type === 'tool_use' && m.data?.status === 'success' && m.data?.tool_name)
        .map(m => m.data.tool_name)
    }
  },

  actions: {
    // ========== 新增：模式切换核心逻辑 ==========

    _getModeForSessionId(sessionId) {
      return this.extractModeFromSessionId(sessionId) || this.currentMode
    },

    _resolveEventMode(eventData = {}, sessionId = null) {
      const explicitMode = eventData?.mode
      if (VALID_MODES.includes(explicitMode)) {
        return explicitMode
      }

      if (sessionId && this.sessionStates[sessionId]?.mode && VALID_MODES.includes(this.sessionStates[sessionId].mode)) {
        return this.sessionStates[sessionId].mode
      }

      return this.extractModeFromSessionId(sessionId)
    },

    _ensureSessionState(sessionId, mode = null) {
      if (!sessionId) return this.currentState

      const sessionMode = mode || this._getModeForSessionId(sessionId)
      if (!this.sessionStates[sessionId]) {
        const initialState = createEmptyModeState()
        initialState.sessionId = sessionId
        initialState.mode = sessionMode
        this.sessionStates[sessionId] = initialState
      } else {
        this.sessionStates[sessionId].sessionId = sessionId
        this.sessionStates[sessionId].mode = this.sessionStates[sessionId].mode || sessionMode
      }

      return this.sessionStates[sessionId]
    },

    _activateSession(sessionId, mode = null) {
      if (!sessionId) {
        delete this.activeSessionByMode[this.currentMode]
        return this.currentState
      }

      const sessionMode = mode || this._getModeForSessionId(sessionId)
      const sessionState = this._ensureSessionState(sessionId, sessionMode)
      this.activeSessionByMode[sessionMode] = sessionId
      this.currentMode = sessionMode
      localStorage.setItem('current-mode', sessionMode)
      return sessionState
    },

    _addMessageToState(targetState, type, content, data = null, attachments = null, extraFields = {}) {
      const message = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type,
        content,
        data,
        attachments,
        timestamp: new Date().toISOString(),
        ...extraFields
      }
      targetState.messages.push(message)
      return message.id
    },

    /**
     * 切换到指定模式
     * - 保存当前模式状态到localStorage
     * - 切换模式
     * - 恢复目标模式状态
     */
    switchMode(newMode) {
      if (!VALID_MODES.includes(newMode)) {
        console.warn('[switchMode] Invalid mode:', newMode)
        return
      }

      if (newMode === this.currentMode) {
        console.log('[switchMode] Already in mode:', newMode)
        return
      }

      console.log('[switchMode] Switching from', this.currentMode, 'to', newMode)

      // 1. 保存当前模式状态到 localStorage
      this._persistModeState(this.currentMode)

      // 2. 切换模式
      const oldMode = this.currentMode
      this.currentMode = newMode
      localStorage.setItem('current-mode', newMode)

      // 3. 恢复目标模式状态
      if (!this.activeSessionByMode[newMode]) {
        this._restoreModeState(newMode)
      }

      console.log('[switchMode] Mode switched successfully')
      console.log('[switchMode] Old mode running:', this.modeStates[oldMode]?.isAnalyzing)
      console.log('[switchMode] New mode running:', this.modeStates[newMode]?.isAnalyzing)
      console.log('[switchMode] ✅ Multi-mode parallel working enabled')
    },

    /**
     * 保存模式状态到 localStorage
     * - 只保存最近50条消息
     * - 保存完整的模式状态
     */
    _persistModeState(mode) {
      if (!this.modeStates[mode]) return

      const activeSessionId = this.activeSessionByMode[mode]
      const modeState = activeSessionId && this.sessionStates[activeSessionId]
        ? this.sessionStates[activeSessionId]
        : this.modeStates[mode]

      // 只保存最近50条消息（避免localStorage超限）
      const messagesToSave = modeState.messages.slice(-50)

      const stateToSave = {
        sessionId: modeState.sessionId,
        isAnalyzing: modeState.isAnalyzing,
        error: modeState.error,
        isInterruption: modeState.isInterruption,
        messages: messagesToSave,
        currentMessage: modeState.currentMessage,
        isComplete: modeState.isComplete,
        iterations: modeState.iterations,
        maxIterations: modeState.maxIterations,
        showReflexion: modeState.showReflexion,
        reflexionCount: modeState.reflexionCount,
        expertSystemEnabled: modeState.expertSystemEnabled,
        expertResults: modeState.expertResults,
        lastExpertResults: modeState.lastExpertResults,
        selectedExperts: modeState.selectedExperts,
        finalAnswer: modeState.finalAnswer,
        finalAnswers: modeState.finalAnswers,
        hasResults: modeState.hasResults,
        dashboardOverview: modeState.dashboardOverview,
        mapPrograms: modeState.mapPrograms,
        currentMapProgram: modeState.currentMapProgram,
        board: modeState.board
          ? { ...modeState.board, pendingSnapshotAttachment: null }
          : modeState.board,
        results: modeState.results,
        sessionRound: modeState.sessionRound,
        interventionQueue: modeState.interventionQueue,
        pendingUserInputs: modeState.pendingUserInputs,
        pendingSteeringInputs: modeState.pendingSteeringInputs,
        streamingAnswerMessageId: modeState.streamingAnswerMessageId,
        _forceRenderCount: modeState._forceRenderCount
      }

      try {
        localStorage.setItem(`mode-state-${mode}`, JSON.stringify(stateToSave))
        console.log(`[_persistModeState] Saved ${mode} state with ${messagesToSave.length} messages`)
      } catch (error) {
        console.error(`[_persistModeState] Failed to save ${mode} state:`, error)
        // localStorage超限，清空旧状态重试
        try {
          const minimalState = {
            sessionId: modeState.sessionId,
            messages: messagesToSave.slice(-10), // 只保留最后10条
            isAnalyzing: modeState.isAnalyzing
          }
          localStorage.setItem(`mode-state-${mode}`, JSON.stringify(minimalState))
          console.log(`[_persistModeState] Saved minimal ${mode} state`)
        } catch (retryError) {
          console.error(`[_persistModeState] Failed to save minimal state:`, retryError)
        }
      }
    },

    /**
     * 从 localStorage 恢复模式状态
     */
    _restoreModeState(mode) {
      try {
        const savedStateJSON = localStorage.getItem(`mode-state-${mode}`)
        if (!savedStateJSON) {
          console.log(`[_restoreModeState] No saved state for ${mode}`)
          return
        }

        const savedState = JSON.parse(savedStateJSON)
        savedState.isAnalyzing = false
        savedState.isInterruption = false
        savedState.streamingAnswerMessageId = null
        promoteUnappliedSteeringInputsToQueue(savedState, {
          agentMode: mode,
          queuedAlreadyShown: true
        })
        const lastMessage = savedState.messages && savedState.messages[savedState.messages.length - 1]
        if (lastMessage?.type === 'final' && !lastMessage.streaming) {
          savedState.isComplete = true
        }

        // 合并保存的状态到当前模式状态
        Object.assign(this.modeStates[mode], savedState)

        console.log(`[_restoreModeState] Restored ${mode} state with ${savedState.messages?.length || 0} messages`)
      } catch (error) {
        console.error(`[_restoreModeState] Failed to restore ${mode} state:`, error)
      }
    },

    /**
     * 重置指定模式的状态
     */
    resetMode(mode) {
      if (!this.modeStates[mode]) return

      // 创建新的空状态
      const emptyState = createEmptyModeState()
      Object.assign(this.modeStates[mode], emptyState)

      // 清除localStorage
      localStorage.removeItem(`mode-state-${mode}`)

      console.log(`[resetMode] Reset mode: ${mode}`)
    },

    /**
     * 重置所有模式的状态
     */
    resetAllModes() {
      for (const mode of VALID_MODES) {
        this.resetMode(mode)
      }
      console.log('[resetAllModes] All modes reset')
    },

    /**
     * 清理旧的模式状态（超过7天）
     */
    cleanupOldStates() {
      const sevenDaysAgo = Date.now() - (7 * 24 * 60 * 60 * 1000)
      let cleanedCount = 0

      for (const mode of VALID_MODES) {
        const stateKey = `mode-state-${mode}`
        const savedStateJSON = localStorage.getItem(stateKey)

        if (savedStateJSON) {
          try {
            const savedState = JSON.parse(savedStateJSON)

            // 检查最后一条消息的时间戳
            const lastMessage = savedState.messages && savedState.messages[savedState.messages.length - 1]
            if (lastMessage && lastMessage.timestamp) {
              const lastMessageTime = new Date(lastMessage.timestamp).getTime()
              if (lastMessageTime < sevenDaysAgo) {
                localStorage.removeItem(stateKey)
                cleanedCount++
                console.log(`[cleanupOldStates] Cleaned up ${mode} state (last message from ${new Date(lastMessageTime).toLocaleDateString()})`)
              }
            }
          } catch (error) {
            console.error(`[cleanupOldStates] Failed to parse ${mode} state:`, error)
            // 如果解析失败，删除该状态
            localStorage.removeItem(stateKey)
            cleanedCount++
          }
        }
      }

      console.log(`[cleanupOldStates] Cleanup complete: ${cleanedCount} modes cleaned`)
      return cleanedCount
    },

    /**
     * 设置当前模式的消息列表（用于会话恢复）
     */
    setMessages(messages) {
      if (!Array.isArray(messages)) {
        console.warn('[setMessages] Invalid messages:', messages)
        return
      }
      this.currentState.messages = normalizeRestoredMessages(messages)
      console.log(`[setMessages] Set ${messages.length} messages for mode ${this.currentMode}`)
    },

    /**
     * 从 sessionId 中提取模式
     * sessionId 格式: ${mode}_session_${timestamp}_${random}
     */
    extractModeFromSessionId(sessionId) {
      if (!sessionId || typeof sessionId !== 'string') {
        return null
      }
      const match = sessionId.match(/^([a-z]+)_session_/)
      const mode = match ? match[1] : null
      return VALID_MODES.includes(mode) ? mode : null
    },

    /**
     * 根据 sessionId 获取对应模式的状态
     */
    getModeStateBySessionId(sessionId) {
      const mode = this.extractModeFromSessionId(sessionId)
      if (!mode || !this.modeStates[mode]) {
        console.warn('[getModeStateBySessionId] Cannot find mode for sessionId:', sessionId)
        return this.currentState  // 降级：返回当前模式状态
      }
      return this.modeStates[mode]
    },

    /**
     * 设置当前模式的 sessionId（用于会话恢复）
     */
    setSessionId(sessionId, mode = null) {
      if (!sessionId || typeof sessionId !== 'string') {
        console.warn('[setSessionId] Invalid sessionId:', sessionId)
        return
      }
      const sessionMode = VALID_MODES.includes(mode) ? mode : this._getModeForSessionId(sessionId)
      const targetState = this._activateSession(sessionId, sessionMode)
      targetState.sessionId = sessionId
      console.log(`[setSessionId] Set sessionId for mode ${this.currentMode}:`, sessionId)
      useSessionResourceStore().activateSession(sessionId)
    },

    /**
     * 设置当前模式的专家结果（用于会话恢复）
     */
    setLastExpertResults(results) {
      this.currentState.lastExpertResults = results
      console.log(`[setLastExpertResults] Set expert results for mode ${this.currentMode}`)
    },

    /**
     * 设置当前模式的完成状态（用于会话恢复）
     */
    setComplete(isComplete) {
      this.currentState.isComplete = !!isComplete
      if (isComplete) {
        this.currentState.isAnalyzing = false
        this.currentState.isInterruption = false
        this.currentState.streamingAnswerMessageId = null
      }
      console.log(`[setComplete] Set complete=${isComplete} for mode ${this.currentMode}`)
    },

    applyMapProgramMetadata(data = {}, targetState = this.currentState) {
      applyMapProgramMetadata(targetState, data)
    },

    recordMapEvent(event, targetState = this.currentState) {
      if (!event || event.type !== 'map_event') return
      if (!Array.isArray(targetState.mapEvents)) {
        targetState.mapEvents = []
      }
      targetState.mapEvents.push(event)
      if (targetState.mapEvents.length > 50) {
        targetState.mapEvents = targetState.mapEvents.slice(-50)
      }
    },

    /**
     * 批量设置会话状态（用于会话恢复）
     */
    restoreSessionState(sessionData) {
      if (!sessionData) return

      if (sessionData.session_id) {
        this.setSessionId(sessionData.session_id)
      }

      if (sessionData.conversation_history && Array.isArray(sessionData.conversation_history)) {
        this.setMessages(sessionData.conversation_history)
      }

      restoreMapScene(this.currentState, sessionData)

      if (sessionData.last_result) {
        this.currentState.lastExpertResults = sessionData.last_result
      }

      if (sessionData.dashboardOverview) {
        this.currentState.dashboardOverview = sessionData.dashboardOverview
      }

      if (sessionData.state === 'completed') {
        this.setComplete(true)
      }

      console.log(`[restoreSessionState] Session restored for mode ${this.currentMode}`)

      // 恢复分页状态
      if (sessionData.has_more_messages !== undefined) {
        this.currentState.pagination.hasMoreMessages = sessionData.has_more_messages
        this.currentState.pagination.totalMessageCount = sessionData.total_message_count || 0
        this.currentState.pagination.oldestSequence = sessionData.oldest_sequence ?? null
      }
    },

    // ========== 消息分页加载 ==========

    /**
     * 设置分页状态
     */
    setPagination(state) {
      Object.assign(this.currentState.pagination, state)
    },

    /**
     * 前置插入更早的消息（滚动加载更多）
     */
    prependMessages(messages) {
      if (!messages || messages.length === 0) return

      messages = normalizeRestoredMessages(messages)

      // 【修复】过滤掉与现有消息重复内容的消息
      const existingContents = new Set()
      this.currentState.messages.forEach(m => {
        if (m.content) {
          existingContents.add(getContentPreview(m.content, 100)) // 使用前100个字符作为内容指纹
        }
      })

      const beforeCount = messages.length
      messages = messages.filter(m => {
        if (!m.content) return true
        const contentFingerprint = getContentPreview(m.content, 100)
        const isDuplicate = existingContents.has(contentFingerprint)
        if (isDuplicate) {
          console.warn(`[prependMessages] 过滤重复消息: ${m.id}`, { content: getContentPreview(m.content, 50) })
        } else {
          existingContents.add(contentFingerprint)
        }
        return !isDuplicate
      })

      if (messages.length !== beforeCount) {
        console.log(`[prependMessages] 过滤了 ${beforeCount - messages.length} 条重复消息`)
      }

      this.currentState.messages = [...messages, ...this.currentState.messages]
      if (messages.length > 0) {
        this.currentState.pagination.oldestSequence = messages[0].sequence_number
      }
    },

    /**
     * 加载更多历史消息
     */
    async loadMoreMessages() {
      const sessionId = this.currentState.sessionId
      const oldestSequence = this.currentState.pagination.oldestSequence
      const hasMore = this.currentState.pagination.hasMoreMessages

      if (!sessionId || !hasMore) {
        console.log('[loadMoreMessages] 没有更多消息可加载')
        return
      }

      if (this.currentState.pagination.loadingMore) {
        console.log('[loadMoreMessages] 正在加载中，跳过')
        return
      }

      try {
        this.currentState.pagination.loadingMore = true
        console.log(`[loadMoreMessages] 开始加载更多消息，sessionId: ${sessionId}, oldestSequence: ${oldestSequence}`)

        // 调用 API 获取更多消息
        const { getSessionMessages } = await import('@/api/session')
        const result = await getSessionMessages(sessionId, oldestSequence, 30)

        console.log('[loadMoreMessages] API返回:', result)

        // 后端直接返回数据，不是 {success, data} 格式
        const messages = result.messages || []
        console.log(`[loadMoreMessages] 加载了 ${messages.length} 条消息`)

        if (messages.length > 0) {
          this.prependMessages(messages)
        }

        // 更新分页状态（注意字段名映射）
        this.currentState.pagination.hasMoreMessages = result.has_more || false
        this.currentState.pagination.totalMessageCount = result.total_count || this.currentState.pagination.totalMessageCount

        console.log(`[loadMoreMessages] 加载完成，hasMore: ${this.currentState.pagination.hasMoreMessages}, total: ${this.currentState.pagination.totalMessageCount}`)
      } catch (error) {
        console.error('[loadMoreMessages] 加载消息失败:', error)
        // 不抛出错误，避免中断用户体验
      } finally {
        this.currentState.pagination.loadingMore = false
      }
    },

    // ========== 原有方法（适配多模式）==========

    // 获取专家标签
    getExpertLabel(expertType) {
      const labelMap = {
        'weather': '气象专家',
        'component': '组分专家',
        'viz': '可视化专家',
        'report': '报告专家'
      }
      return labelMap[expertType] || expertType
    },

    // 初始化
    async init() {
      try {
        // 获取可用工具
        const tools = await agentAPI.getTools()
        this.availableTools = tools.tools
        console.log('Available tools:', this.availableTools)

        // 恢复所有模式的状态
        for (const mode of VALID_MODES) {
          this._restoreModeState(mode)
        }
      } catch (error) {
        this.availableTools = []
        const currentMsgs = this.currentState.messages
        if (!currentMsgs.find(msg => msg.type === 'error' && msg.source === 'tools')) {
          this.addMessage('error', '工具列表加载失败，可稍后在顶部”工具管理”里重试。', { source: 'tools', error: error.message })
        }
        console.error('Failed to load tools:', error)
      }
    },

    // 继续会话（原有工作流逻辑）
    continueSession() {
      const current = this.currentState
      current.sessionRound = Math.max(current.sessionRound + 1, 1)
      current.isAnalyzing = false
      current.error = null
      // 保留finalAnswer，让它保持直到新答案到来
      // 保留messages，但清空本轮的可视化结果
      current.results = {
        map: null,
        charts: [],
        tables: [],
        text: ''
      }
    },

    // 创建会话ID（按模式隔离）
    createSessionId() {
      let current = this.currentState
      if (!current.sessionId) {
        const mode = this.currentMode
        const sessionId = `${mode}_session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        current = this._activateSession(sessionId, mode)
        current.sessionId = sessionId
        console.log('[createSessionId] Created session for', mode, ':', current.sessionId)
      }
    },

    // 重置当前模式的会话
    reset() {
      const mode = this.currentMode
      const current = this.currentState
      const emptyState = createEmptyModeState()

      // 保留一些字段
      emptyState.maxIterations = current.maxIterations

      if (current.sessionId && current.isAnalyzing) {
        delete this.activeSessionByMode[mode]
        Object.assign(this.modeStates[mode], emptyState)
      } else if (current.sessionId) {
        delete this.sessionStates[current.sessionId]
        delete this.activeSessionByMode[mode]
        Object.assign(this.modeStates[mode], emptyState)
      } else {
        Object.assign(current, emptyState)
      }

      console.log('[reset] Reset current mode:', this.currentMode)
    },

    // 添加消息（添加到当前模式）
    addMessage(type, content, data = null, attachments = null, extraFields = {}) {
      const message = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type, // 'user', 'agent', 'thought', 'tool_use', 'tool_result', 'start', 'error', 'final'
        content,
        data,
        attachments, // 附件信息
        timestamp: new Date().toISOString(),
        ...extraFields  // 支持额外字段（如 streaming, streamingAnswerId 等）
      }
      this.currentState.messages.push(message)
      return message.id
    },

    /**
     * 添加消息到指定模式（用于事件路由）
     */
    addMessageToMode(mode, type, content, data = null, attachments = null, extraFields = {}) {
      console.log(`[addMessageToMode] Called with mode=${mode}, type=${type}`)
      console.log(`[addMessageToMode] this.currentMode=${this.currentMode}`)
      console.log(`[addMessageToMode] Available modes:`, Object.keys(this.modeStates))

      if (!mode || !this.modeStates[mode]) {
        console.warn('[addMessageToMode] Invalid mode:', mode, ', falling back to current mode', this.currentMode)
        mode = this.currentMode
      }

      const message = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type,
        content,
        data,
        attachments,
        timestamp: new Date().toISOString(),
        ...extraFields
      }

      console.log(`[addMessageToMode] Adding message to mode ${mode}, before push: ${this.modeStates[mode].messages.length} messages`)
      this.modeStates[mode].messages.push(message)
      console.log(`[addMessageToMode] After push: ${this.modeStates[mode].messages.length} messages`)
      console.log(`[addMessageToMode] Current mode ${this.currentMode} has ${this.currentState.messages.length} messages`)

      return message.id
    },

    _findLatestFinalMessageForCurrentTurn(modeState, content = '') {
      if (!modeState?.messages?.length) return null

      const lastUserIndex = modeState.messages.reduce((lastIndex, message, index) => {
        return message.type === 'user' ? index : lastIndex
      }, -1)

      const normalizedContent = (content || '').trim()
      let firstFinalAfterUser = null

      for (let i = modeState.messages.length - 1; i > lastUserIndex; i--) {
        const message = modeState.messages[i]
        if (message.type !== 'final') continue

        // 记录第一个final消息（最接近用户消息的）
        if (!firstFinalAfterUser) {
          firstFinalAfterUser = message
        }

        const existingContent = (message.content || '').trim()
        if (
          message.streaming ||
          !normalizedContent ||
          existingContent === normalizedContent ||
          normalizedContent.startsWith(existingContent) ||
          existingContent.startsWith(normalizedContent)
        ) {
          return message
        }
      }

      // 【修复】如果没有找到匹配的消息，但存在第一个final消息，
      // 且它与用户消息之间没有其他final消息，则复用它（避免重复创建）
      // 这处理了streaming标记被移除但消息确实存在的情况
      if (firstFinalAfterUser && normalizedContent) {
        const existingContent = (firstFinalAfterUser.content || '').trim()
        // 如果内容相似（其中一个包含另一个），则复用
        if (normalizedContent.includes(existingContent) || existingContent.includes(normalizedContent)) {
          console.log('[_findLatestFinalMessageForCurrentTurn] 复用第一个final消息（内容相似）')
          return firstFinalAfterUser
        }
      }

      return null
    },

    _mergeFinalMessage(message, content, data = {}) {
      if (!message) return
      // 【根本原因修复】创建新对象而不是修改现有对象，确保 Vue 3 响应式系统能检测到变化
      // 直接修改对象属性在某些情况下不会触发响应式更新
      const updatedMessage = {
        ...message,
        content: content ? contentToString(content) : message.content,
        streaming: false,
        renderVersion: (message.renderVersion || 0) + 1,
        data: {
          ...(message.data || {}),
          ...data
        }
      }
      // 将所有属性复制回原对象，保持引用不变（因为其他地方可能持有这个引用）
      Object.assign(message, updatedMessage)
    },

    _convertStreamingAnswerToThoughtIfToolPlanning(modeState) {
      convertStreamingAnswerToThoughtIfToolPlanning(modeState, contentToString)
    },

    prepareQueryVoiceOutput(mode, targetState = this.currentState) {
      if (targetState.queryVoicePlayback?.queue) {
        targetState.queryVoicePlayback.queue.stop()
      }
      targetState.queryVoicePlayback = null
      if (mode !== 'query' || !isQueryVoiceOutputEnabled()) return
      if (typeof Audio === 'undefined' || typeof URL === 'undefined') return

      targetState.queryVoicePlayback = {
        streamed: false,
        queue: createQueryVoicePlaybackQueue({
          voice: typeof localStorage !== 'undefined'
            ? localStorage.getItem('query-voice-output-voice') || '冰糖'
            : '冰糖',
          stylePrompt: '用专业、清晰、平稳的语气播报空气质量分析结果。'
        })
      }
    },

    stopQueryVoiceOutput(targetState = this.currentState) {
      if (targetState?.queryVoicePlayback?.queue) {
        targetState.queryVoicePlayback.queue.stop()
      }
      if (targetState) {
        targetState.queryVoicePlayback = null
      }
    },

    queueQueryVoiceOutputChunk(chunk, mode, targetState = this.currentState) {
      const text = contentToString(chunk || '')
      if (mode !== 'query' || !text || !isQueryVoiceOutputEnabled()) return
      if (!targetState.queryVoicePlayback?.queue) {
        this.prepareQueryVoiceOutput(mode, targetState)
      }
      if (!targetState.queryVoicePlayback?.queue) return

      targetState.queryVoicePlayback.streamed = true
      targetState.queryVoicePlayback.queue.pushChunk(text)
    },

    finishQueryVoiceOutput(finalText, mode, targetState = this.currentState) {
      if (mode !== 'query' || !isQueryVoiceOutputEnabled()) return
      if (!targetState.queryVoicePlayback?.queue) {
        this.prepareQueryVoiceOutput(mode, targetState)
      }
      const playback = targetState.queryVoicePlayback
      if (!playback?.queue) return

      const fallbackText = contentToString(finalText || '').trim()
      if (!playback.streamed && fallbackText) {
        playback.queue.pushChunk(fallbackText)
      }
      playback.queue.finish()
    },

    /**
     * 获取事件的目标模式状态
     */
    getEventTargetState(eventData) {
      const sessionId = eventData?.session_id
      const eventMode = this._resolveEventMode(eventData, sessionId)
      if (sessionId) {
        return this._ensureSessionState(sessionId, eventMode)
      }

      if (!eventMode) {
        // 无法从事件或 sessionId 提取模式，使用当前模式
        return this.currentState
      }

      if (!this.modeStates[eventMode]) {
        console.warn('[getEventTargetState] Invalid mode:', eventMode)
        return this.currentState
      }

      return this.modeStates[eventMode]
    },

    // 处理ReAct事件（根据sessionId路由到正确的模式）
    handleEvent(event) {
      console.log('[handleEvent] ========================================')
      console.log('[handleEvent] Received event:', event.type)
      console.log('[handleEvent] event.data:', event.data)
      console.log('[handleEvent] event.data?.session_id:', event.data?.session_id)
      console.log('[handleEvent] this.currentMode:', this.currentMode)

      const { type, data } = event

      // 确定目标模式
      // 【修复】完全基于session_id路由，支持真正的多模式并行任务
      const sessionId = data?.session_id || event?.session_id
      console.log('[handleEvent] sessionId:', sessionId)

      if (type === 'resources_changed') {
        const resourceStore = useSessionResourceStore()
        if (sessionId && this.currentState?.sessionId === sessionId) {
          resourceStore.activateSession(sessionId)
        }
        void applyResourceStreamEvent(resourceStore, event)
        return
      }

      const eventMode = this._resolveEventMode(data, sessionId)
      console.log('[handleEvent] Extracted eventMode:', eventMode)

      // 【关键修复】路由逻辑：
      // 1. 优先使用事件中的 mode
      // 2. 再使用已知 session 状态或 session_id 前缀
      // 3. 否则使用 currentMode 作为默认值
      const targetMode = eventMode || this.currentMode
      console.log('[handleEvent] targetMode:', targetMode)

      // 【调试】并行任务状态
      if (eventMode && eventMode !== this.currentMode) {
        console.log(`[handleEvent] ✅ PARALLEL TASK: routing to ${eventMode} (current: ${this.currentMode}, type: ${type})`)
        console.log(`[handleEvent] Current mode state:`, {
          mode: this.currentMode,
          isAnalyzing: this.currentState.isAnalyzing,
          messageCount: this.currentState.messages.length
        })
        console.log(`[handleEvent] Target mode state:`, {
          mode: eventMode,
          isAnalyzing: this.modeStates[eventMode]?.isAnalyzing,
          messageCount: this.modeStates[eventMode]?.messages?.length
        })
      }

      const targetState = sessionId
        ? this._ensureSessionState(sessionId, targetMode)
        : (this.modeStates[targetMode] || this.currentState)
      console.log('[handleEvent] targetState:', targetState)
      console.log('[handleEvent] targetState.messages.length:', targetState?.messages?.length)

      if (!shouldApplyRunEvent(targetState, event)) {
        console.warn('[handleEvent] Ignoring stale run event', {
          eventRunId: getEventRunId(event),
          activeRunId: targetState.activeRunId,
          sessionId,
          type
        })
        return
      }

      // 如果事件属于非当前模式，记录日志
      if (eventMode && eventMode !== this.currentMode) {
        console.log(`[handleEvent] ⚠️ ROUTING event to mode ${eventMode} (current: ${this.currentMode}, type: ${type})`)
      }

      // 创建局部的 addMessage 函数，自动路由到正确的模式
      const addMessage = (msgType, msgContent, msgData = null, msgAttachments = null, msgExtraFields = {}) => {
        // 【修复】使用 contentToString 统一处理各种content格式（字符串、数组等）
        const contentStr = contentToString(msgContent)

        const preview = contentStr.substring(0, 50)
        console.log(`[handleEvent] addMessage called: mode=${targetMode}, type=${msgType}, content=${preview}...`)
        const msgId = this._addMessageToState(targetState, msgType, contentStr, msgData, msgAttachments, msgExtraFields)
        console.log(`[handleEvent] Message added to ${targetMode}/${targetState.sessionId || 'draft'}, total messages: ${targetState.messages?.length}`)
        return msgId
      }

      switch (type) {
        case 'start': {
          // 分析开始
          const runId = getEventRunId(event)
          if (runId) {
            targetState.activeRunId = runId
            if (targetState.pendingPausedRunId && targetState.pendingPausedRunId !== runId) {
              targetState.pendingPausedRunId = null
            }
          }
          addMessage('start', `开始分析: ${data?.query || ''}`)
          if (data?.session_id) {
            targetState.sessionId = data.session_id
            if (targetState === this.currentState) {
              useSessionResourceStore().activateSession(data.session_id)
            }
          }
          targetState.iterations = 0
          break
        }

        case 'thought': {
          // LLM思考（完成事件）
          const thoughtContent = data?.thought || '思考中...'
          addMessage('thought', thoughtContent, {
            iteration: data?.iteration,
            timestamp: data?.timestamp
          })

          // 检测Reflexion
          if (data?.thought && data.thought.includes('[Reflexion 反思]')) {
            targetState.showReflexion = true
            targetState.reflexionCount++
          }
          break
        }

        case 'thinking_delta': {
          // ✅ Thinking 流式更新
          const chunk = data?.chunk || ''
          const isComplete = data?.is_complete || false

          if (chunk) {
            // 如果是第一个块，创建新消息
            if (!targetState.streamingThinkingMessageId) {
              targetState.streamingThinkingMessageId = addMessage('thought', '', {
                timestamp: data?.timestamp
              }, null, { streaming: true })
            }

            // 找到消息并追加内容
            const msg = targetState.messages.find(m => m.id === targetState.streamingThinkingMessageId)
            if (msg) {
              msg.content += chunk
            }
          }

          // 如果是完成标记，清除 streaming 标记
          if (isComplete && targetState.streamingThinkingMessageId) {
            const msg = targetState.messages.find(m => m.id === targetState.streamingThinkingMessageId)
            if (msg) {
              msg.streaming = false
            }
            targetState.streamingThinkingMessageId = null
          }
          break
        }

        case 'tool_use': {
          // ✅ V3: Anthropic tool_use 事件
          this._convertStreamingAnswerToThoughtIfToolPlanning(targetState)

          const toolUseData = data || {}
          const toolName = toolUseData.tool_name || 'unknown'
          const toolUseId = toolUseData.tool_use_id
          const toolInput = toolUseData.input || {}

          // 格式化工具调用信息
          let toolUseContent = `Tool Use: ${toolName}`
          if (toolUseId) {
            toolUseContent += ` (ID: ${toolUseId.substring(0, 8)}...)`
          }

          // 添加工具调用消息
          addMessage('tool_use', toolUseContent, {
            tool_use_id: toolUseId,
            tool_name: toolName,
            input: toolInput,
            iteration: toolUseData.iteration,
            timestamp: toolUseData.timestamp
          })
          break
        }

        case 'tool_result': {
          // ✅ V3: Anthropic tool_result 事件
          this._convertStreamingAnswerToThoughtIfToolPlanning(targetState)
          this.applyMapProgramMetadata(data, targetState)

          const toolResultData = data || {}
          const resultToolUseId = toolResultData.tool_use_id
          const result = toolResultData.result || {}
          const isError = toolResultData.is_error || false

          // 格式化工具结果信息
          let toolResultContent = isError ? 'Tool Error' : 'Tool Result'
          if (resultToolUseId) {
            toolResultContent += ` (ID: ${resultToolUseId.substring(0, 8)}...)`
          }

          // 如果有summary，使用它
          if (result.summary) {
            toolResultContent += `: ${result.summary}`
          }

          // 添加工具结果消息
          addMessage('tool_result', toolResultContent, {
            tool_use_id: resultToolUseId,
            tool_name: toolResultData.tool_name,
            result: result,
            is_error: isError,
            iteration: toolResultData.iteration,
            timestamp: toolResultData.timestamp
          })

          const appliedDrawioBoard = this.applyDrawioBoardToolResult(result, targetState)
          if (!appliedDrawioBoard) {
            this.applyDrawioBoardToolResultFromRef(result, targetState)
          }

          break
        }

        case 'streaming_text': {
          // ✅ 真正的流式文本输出
          const chunk = data?.chunk || ''
          const isComplete = data?.is_complete || false

          // 调试日志已关闭（避免刷屏）
          // if (!this._streamDebug) {
          //   this._streamDebug = { startTime: Date.now(), chunkCount: 0 }
          // }
          // this._streamDebug.chunkCount++
          // const elapsed = Date.now() - this._streamDebug.startTime
          // console.log(`[streaming_text] Chunk #${this._streamDebug.chunkCount}, ${elapsed}ms, length: ${chunk.length}`)

          if (chunk) {
            // 【关键修复】如果是第一个块，创建新消息
            if (!targetState.streamingAnswerMessageId) {
              targetState.streamingAnswerMessageId = addMessage('final', '', {
                timestamp: data?.timestamp
              }, null, { streaming: true })
            }

            // 【关键修复】找到消息并直接追加内容（使用targetState而不是currentState）
            const msg = targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
            if (msg) {
              msg.content += chunk
              // 同步更新 finalAnswer
              targetState.finalAnswer += chunk
            }
            this.queueQueryVoiceOutputChunk(chunk, targetMode, targetState)
          }

          // 如果是最后一块，清除标志并移除 streaming 标记
          if (isComplete) {
            // 调试日志已关闭（避免刷屏）
            // const totalTime = Date.now() - this._streamDebug.startTime
            // console.log(`[streaming_text] 完成！共 ${this._streamDebug.chunkCount} 个 chunks，总耗时 ${totalTime}ms`)
            // this._streamDebug = null

            // ✅ 移除去重逻辑（基于内容长度的判断不准确）
            // 理由：
            // 1. 少于200字的最终答案会被误删（严重问题）
            // 2. 超过200字的中间说明不会被删除（漏删）
            // 3. 保留中间说明不是大问题（用户看到 LLM 的思考过程也挺好）
            // 4. 如果真的需要区分，应该在后端层面解决（添加 text_type 字段）

            if (targetState.streamingAnswerMessageId) {
              const msg = targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
              if (msg) {
                msg.streaming = false
                msg.renderVersion = (msg.renderVersion || 0) + 1
                // 强制触发响应式更新，确保流式完成后重新渲染
                targetState._forceRenderCount++
              }
              // 【修复】不要在这里清除 streamingAnswerMessageId，
              // 让 complete 事件来处理，这样可以找到流式创建的消息并更新它
              // targetState.streamingAnswerMessageId = null  // ← 删除这行
            }

            // ❌ 移除前端自动保存（避免与后端保存冲突）
            // 后端 react_agent.py 已经在分析完成时保存会话（line 498）
            // 前端如果再保存会导致消息重复（删除旧消息 → 插入新消息 → 两次保存 = 两份数据）
            // 保留注释说明为什么这里不保存
            /*
            if (targetState.sessionId && targetState.messages.length > 0) {
              console.log('[autoSave] AI回复完成，自动保存会话')
              autoSaveSession(targetState.sessionId, targetState.messages, 'active').catch(err => {
                console.warn('[autoSave] 自动保存失败:', err)
              })
            }
            */
          }
          break
        }

        case 'synthetic_user_message': {
          const content = data?.content || ''
          if (targetState.streamingAnswerMessageId) {
            const msg = targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
            if (msg) {
              msg.streaming = false
              msg.renderVersion = (msg.renderVersion || 0) + 1
            }
            targetState.streamingAnswerMessageId = null
          }

          if (content) {
            targetState.isAnalyzing = true
            targetState.isComplete = false
            addMessage('user', content, {
              timestamp: data?.timestamp,
              session_id: data?.session_id,
              source: data?.source || 'auto_hook',
              hook_name: data?.hook_name || null
            }, null, { synthetic: true })
          }
          break
        }

        case 'answer_delta': {
          // ✅ 知识问答流式输出（兼容独立路由）
          const delta = data?.delta || ''
          if (delta) {
            // 如果是第一个块，创建新消息
            if (!targetState.streamingAnswerMessageId) {
              targetState.streamingAnswerMessageId = addMessage('final', '', {
                timestamp: data?.timestamp,
                session_id: data?.session_id
              }, null, { streaming: true })
            }

            // 找到消息并追加内容
            const msg = targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
            if (msg) {
              msg.content += delta
              // 同步更新 finalAnswer
              targetState.finalAnswer += delta
            }
          }
          break
        }

        case 'complete': {
          // 分析完成
          console.log('[event:complete] ========== 收到complete事件 ==========')
          console.log('[event:complete] 数据:', JSON.stringify(data, null, 2))
          console.log('[event:complete] has answer:', !!data?.answer)
          console.log('[event:complete] answer value:', data?.answer)
          console.log('[event:complete] has response:', !!data?.response)
          console.log('[event:complete] response value:', data?.response)
          console.log('[event:complete] has expert_results:', !!data?.expert_results)

          // 【修复】使用targetState而不是currentState，确保状态更新到正确的模式
          targetState.isAnalyzing = false
          if (targetMode === 'board' && targetState.board) targetState.board.readOnly = false
          targetState.isInterruption = false
          targetState.isComplete = true
          this.applyMapProgramMetadata(data, targetState)
          targetState.iterations = data?.iterations || targetState.iterations
          // ✅ 优先使用response字段，兼容answer字段
          const finalContent = data?.response || data?.answer || ''
          if (finalContent) {
            targetState.finalAnswer = finalContent
          }
          targetState.hasResults = true

          // 记录最终答案（原有工作流逻辑）
          targetState.finalAnswers.push({
            run: targetState.sessionRound,
            content: finalContent || targetState.finalAnswer || '分析完成',
            timestamp: new Date().toISOString()
          })

          // 添加最终答案消息到UI
          // 如果已经通过 answer_delta 流式创建了最终答案消息，则只更新其元数据，避免重复追加一条消息
          console.log('[event:complete] streamingAnswerMessageId:', targetState.streamingAnswerMessageId)
          const existingFinalMessage = targetState.streamingAnswerMessageId
            ? targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
            : this._findLatestFinalMessageForCurrentTurn(targetState, finalContent)
          if (existingFinalMessage) {
            this._mergeFinalMessage(existingFinalMessage, finalContent, {
              iterations: data?.iterations,
              session_id: data?.session_id,
              timestamp: data?.timestamp,
              expert_results: data?.expert_results || null,  // ✅ 传递专家结果用于显示
              sources: data?.sources || null  // ✅ 知识问答参考来源
            })
            if (finalContent) {
              targetState.finalAnswer = finalContent
            }
            console.log('[event:complete] 复用当前轮次已有final消息，避免重复追加')
          } else if (finalContent) {
            // 【修复】优先使用response字段，兼容answer字段
            console.log('[event:complete] 添加final消息，content:', finalContent.substring(0, 50) + '...')
            addMessage('final', finalContent, {
              iterations: data?.iterations,
              session_id: data?.session_id,
              timestamp: data?.timestamp,
              expert_results: data?.expert_results || null,  // ✅ 传递专家结果用于显示
              sources: data?.sources || null  // ✅ 知识问答参考来源
            }, null, { streaming: false })  // 【修复】明确设置 streaming: false
            console.log('[event:complete] messages数量:', targetState.messages.length)
          } else {
            console.log('[event:complete] 警告：没有answer或response字段，不添加final消息')
          }

          // 【关键修复】处理多专家系统的最终结果
          if (data?.expert_results) {
            // 【重要】同时存储完整的专家结果供前端使用
            targetState.lastExpertResults = {
              expert_results: data.expert_results
            }
            console.log('[event:complete] lastExpertResults已设置')
          }

          // ✅ 处理sources字段（知识问答工作流返回的检索文档）
          if (data?.sources && Array.isArray(data.sources) && data.sources.length > 0) {
            console.log('[event:complete] 保存sources到最后消息，count:', data.sources.length)
            // 保存到当前消息的 sources 字段，供知识溯源标签使用
            if (targetState.messages.length > 0) {
              const lastMsg = targetState.messages[targetState.messages.length - 1]
              // 确保data对象存在
              if (!lastMsg.data) {
                lastMsg.data = {}
              }
              // 保存到data.sources（优先）和msg.sources（兼容）
              lastMsg.data.sources = data.sources
              lastMsg.sources = data.sources
              targetState.messages = [...targetState.messages]
              console.log('[event:complete] sources已保存到lastMsg.data.sources和lastMsg.sources')
            }
          } else {
            console.log('[event:complete] 没有sources字段或为空')
          }

          this.finishQueryVoiceOutput(finalContent || targetState.finalAnswer, targetMode, targetState)

          // 流式最终答案结束，重置状态
          targetState.streamingAnswerMessageId = null
          targetState.activeRunId = null
          if (data?.auto_followup_pending && data?.auto_followup_prompt) {
            targetState._pendingAutoFollowupPrompt = data.auto_followup_prompt
            targetState._pendingAutoFollowupHookName = data.auto_followup_hook_name || 'report_final_review'
          }
          promoteUnappliedSteeringInputsToQueue(targetState, {
            agentMode: targetMode,
            queuedAlreadyShown: true,
            timestamp: data?.timestamp || new Date().toISOString()
          })
          this._persistModeState(targetMode)
          break
        }

        case 'incomplete': {
          // 未完成（达到最大迭代）
          targetState.isAnalyzing = false
          if (targetMode === 'board' && targetState.board) targetState.board.readOnly = false
          targetState.isComplete = true
          targetState.iterations = data?.iterations || targetState.iterations
          // ✅ 优先使用response字段，兼容answer字段
          targetState.finalAnswer = data?.response || data?.answer || '分析未完成'

          // 记录最终答案（原有工作流逻辑）
          targetState.finalAnswers.push({
            run: targetState.sessionRound,
            content: data?.response || data?.answer || '分析未完成',
            timestamp: new Date().toISOString()
          })

          // 添加最终答案消息到UI
          if (targetState.streamingAnswerMessageId) {
            const msg = targetState.messages.find(m => m.id === targetState.streamingAnswerMessageId)
            if (msg) {
              msg.data = {
                ...(msg.data || {}),
                iterations: data?.iterations,
                reason: data?.reason,
                timestamp: data?.timestamp,
                expert_results: data?.expert_results || null  // ✅ 传递专家结果用于显示
              }
            }
          } else if (data?.answer) {
            addMessage('final', data.answer, {
              iterations: data?.iterations,
              reason: data?.reason,
              timestamp: data?.timestamp,
              expert_results: data?.expert_results || null  // ✅ 传递专家结果用于显示
            })
          }

          // 处理多专家系统的最终结果（即使未完成也可能有部分结果）
          if (data?.expert_results) {
            console.log('[incomplete] 处理多专家系统最终结果:', data.expert_results)
            // 【重要】同时存储完整的专家结果供前端使用
            targetState.lastExpertResults = {
              expert_results: data.expert_results
            }
          }

          // 流式最终答案结束，重置状态
          targetState.streamingAnswerMessageId = null
          targetState.activeRunId = null
          promoteUnappliedSteeringInputsToQueue(targetState, {
            agentMode: targetMode,
            queuedAlreadyShown: true,
            timestamp: data?.timestamp || new Date().toISOString()
          })
          this._persistModeState(targetMode)
          break
        }

        case 'error': {
          // 迭代错误
          addMessage('error', `错误: ${data?.error || '未知错误'}`, data)
          break
        }

        case 'interrupted': {
          targetState.isAnalyzing = false
          if (targetMode === 'board' && targetState.board) targetState.board.readOnly = false
          targetState.isComplete = false
          targetState.error = null
          targetState.isInterruption = true
          targetState.streamingAnswerMessageId = null
          targetState.streamingThinkingMessageId = null
          targetState.activeRunId = null
          promoteUnappliedSteeringInputsToQueue(targetState, {
            agentMode: targetMode,
            queuedAlreadyShown: true,
            timestamp: data?.timestamp || new Date().toISOString()
          })
          this._persistModeState(targetMode)
          break
        }

        case 'fatal_error': {
          // 致命错误
          targetState.isAnalyzing = false
          if (targetMode === 'board' && targetState.board) targetState.board.readOnly = false
          targetState.error = data?.error || '致命错误'
          addMessage('error', `致命错误: ${targetState.error}`, data)
          targetState.streamingAnswerMessageId = null
          targetState.activeRunId = null
          promoteUnappliedSteeringInputsToQueue(targetState, {
            agentMode: targetMode,
            queuedAlreadyShown: true,
            timestamp: data?.timestamp || new Date().toISOString()
          })
          this._persistModeState(targetMode)
          break
        }

        case 'pipeline_started': {
          // 流水线开始事件
          addMessage('start', `开始多专家分析: ${data?.query || ''}`)
          break
        }

        case 'query_parsed': {
          // 查询解析完成事件
          addMessage('tool_result', `查询解析完成 - 地点: ${data?.location || '未知'} | 分析类型: ${data?.analysis_type || '未知'}`, {
            query_parsed: data
          })
          break
        }

        case 'experts_selected': {
          // 专家选择完成事件
          const experts = data?.selected_experts || []
          addMessage('tool_result', `已选择 ${experts.length} 个专家: ${experts.map(e => this.getExpertLabel(e)).join('、')}`, {
            selected_experts: experts
          })
          break
        }

        case 'expert_group_started': {
          // 专家组开始事件
          addMessage('tool_use', `启动专家组: ${data?.group?.map(e => this.getExpertLabel(e)).join('、')}`, {
            group: data?.group
          })
          break
        }

        case 'expert_started': {
          // 单个专家开始事件
          const expertName = this.getExpertLabel(data?.expert_type)
          addMessage('tool_use', `执行【${expertName}】专家任务 (工具数: ${data?.tool_count || 0})`, {
            expert_type: data?.expert_type,
            task_id: data?.task_id
          })
          break
        }

        case 'expert_completed': {
          // 专家完成事件
          const completedExpertName = this.getExpertLabel(data?.expert_type)
          addMessage('tool_result', `【${completedExpertName}】专家完成 - 状态: ${data?.status} | 数据文件: ${(data?.file_paths || []).length}个`, {
            expert_type: data?.expert_type,
            status: data?.status,
            file_paths: data?.file_paths
          })
          break
        }

        case 'expert_group_completed': {
          // 专家组完成事件
          addMessage('tool_result', `专家组执行完成: ${Object.entries(data?.results || {}).map(([k, v]) => `${this.getExpertLabel(k)}(${v})`).join('、')}`, {
            group_results: data?.results
          })
          break
        }

        case 'expert_result': {
          // 多专家系统结果事件
          console.log('[event:expert_result] ========== 收到expert_result事件 ==========')
          console.log('[event:expert_result] 完整数据:', JSON.stringify(data, null, 2))

          // 【关键修改】在主对话框中显示专家结果
          if (data && data.expert_results) {
            console.log('[event:expert_result] expert_results keys:', Object.keys(data.expert_results))

            const expertResultsText = Object.keys(data.expert_results)
              .map(expertType => {
                const expertData = data.expert_results[expertType]
                const status = expertData.status || 'unknown'
                const toolCount = expertData.tool_results?.length || 0
                const summary = expertData.analysis?.summary || '无摘要'
                const expertName = this.getExpertLabel(expertType)

                return `【${expertName}】状态: ${status} | 执行工具: ${toolCount}个\n摘要: ${summary.substring(0, 150)}...`
              })
              .join('\n\n')

            // 添加到主对话框显示
            addMessage('tool_result', `多专家系统阶段性结果:\n\n${expertResultsText}`, {
              expert_results: data.expert_results,
              is_expert_result: true
            })

            // 【重要】确保lastExpertResults具有正确的结构
            targetState.lastExpertResults = {
              expert_results: data.expert_results
            }
            console.log('[event:expert_result] lastExpertResults已设置')
          } else {
            // 如果没有expert_results字段，直接存储data
            console.log('[event:expert_result] 无expert_results，直接存储data')
            targetState.lastExpertResults = data
          }
          break
        }

        case 'pipeline_error': {
          // 流水线错误事件
          addMessage('error', `多专家系统错误: ${data?.error || '未知错误'}`, data)
          break
        }

        case 'expert_error': {
          // 专家错误事件
          const errorExpertName = this.getExpertLabel(data?.expert_type)
          addMessage('error', `【${errorExpertName}】专家执行失败: ${data?.error || '未知错误'}`, data)
          break
        }


        case 'message_start': {
          // 原生 Anthropic 事件：消息开始（可扩展为 token 监控）
          console.log('[event:message_start] Anthropic 消息开始', data?.usage)
          break
        }

        case 'message_delta': {
          // 原生 Anthropic 事件：消息增量（含 stop_reason 和 usage）
          console.log('[event:message_delta] Anthropic 消息增量', {
            stop_reason: data?.stop_reason,
            usage: data?.usage
          })
          break
        }

        case 'message_stop': {
          // 原生 Anthropic 事件：消息结束
          console.log('[event:message_stop] Anthropic 消息结束')
          break
        }

        case 'steering_applied': {
          const appliedMessages = Array.isArray(data?.messages) ? data.messages : []
          const appliedInputIds = Array.isArray(data?.input_ids) ? data.input_ids : []
          applyPendingSteeringInputs(
            targetState,
            appliedMessages,
            data?.timestamp || new Date().toISOString(),
            appliedInputIds
          )
          console.log('[event:steering_applied] 执行中补充已应用', {
            count: data?.count,
            session_id: data?.session_id
          })
          break
        }

        default:
          console.warn('Unknown event type:', type)
      }

      // 更新迭代次数
      if (type === 'thought' || type === 'tool_use' || type === 'tool_result') {
        targetState.iterations += 0.5 // 每个循环算作0.5，因为thought+action+observation是一个完整循环
      }
    },

    ensureDrawioBoardState(targetState = this.currentState) {
      if (!targetState.board) {
        targetState.board = createEmptyDrawioBoardState()
      }
      if (!Array.isArray(targetState.board.selectedCells)) {
        targetState.board.selectedCells = []
      }
      if (!Array.isArray(targetState.board.undoStack)) {
        targetState.board.undoStack = []
      }
      if (!Array.isArray(targetState.board.redoStack)) {
        targetState.board.redoStack = []
      }
      if (!Array.isArray(targetState.board.versions)) {
        targetState.board.versions = []
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'currentVersionId')) {
        targetState.board.currentVersionId = null
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'baseVersionId')) {
        targetState.board.baseVersionId = targetState.board.currentVersionId || null
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'applyingHistory')) {
        targetState.board.applyingHistory = false
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'pendingSnapshotAttachment')) {
        targetState.board.pendingSnapshotAttachment = null
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'revision')) {
        targetState.board.revision = 0
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'currentVersionSha256')) {
        targetState.board.currentVersionSha256 = null
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'syncStatus')) {
        targetState.board.syncStatus = 'idle'
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'syncError')) {
        targetState.board.syncError = null
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'readOnly')) {
        targetState.board.readOnly = false
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'qualityStatus')) {
        targetState.board.qualityStatus = null
      }
      if (!Object.prototype.hasOwnProperty.call(targetState.board, 'qualityReport')) {
        targetState.board.qualityReport = {}
      }
      return targetState.board
    },

    pushDrawioBoardHistory(xml, targetState = this.currentState) {
      const board = this.ensureDrawioBoardState(targetState)
      const previousXml = String(xml || '')
      if (!previousXml || previousXml === board.currentXml) return board

      const lastUndo = board.undoStack[board.undoStack.length - 1]
      if (lastUndo !== previousXml) {
        board.undoStack.push(previousXml)
      }
      if (board.undoStack.length > 50) {
        board.undoStack = board.undoStack.slice(board.undoStack.length - 50)
      }
      board.redoStack = []
      return board
    },

    addDrawioBoardVersion(payload = {}, result = {}, targetState = this.currentState, options = {}) {
      const board = this.ensureDrawioBoardState(targetState)
      const xml = getDrawioBoardXml(payload)
      if (!xml) return null

      const payloadVersionId = payload.version_id || payload.versionId || null
      const existing = board.versions.find(version => (
        payloadVersionId
          ? (version.version_id || version.id) === String(payloadVersionId)
          : version.xml === xml
      ))
      const incoming = createDrawioBoardVersionRecord({
        board,
        payload,
        result,
        xml,
        source: payload.source || 'agent'
      })
      const record = existing ? { ...existing, ...incoming, id: existing.id, version_id: existing.version_id } : incoming

      const makeCurrent = options.makeCurrent !== false
      board.versions = board.versions
        .map(version => makeCurrent ? { ...version, is_current: false } : version)
        .filter(version => version.id !== record.id && version.version_id !== record.version_id)
      board.versions.push({ ...record, is_current: makeCurrent })
      if (makeCurrent) {
        board.currentVersionId = record.version_id || record.id
        board.baseVersionId = board.currentVersionId
        board.currentVersionSha256 = payload.xml_sha256 || payload.xml_ref?.sha256 || board.currentVersionSha256
        board.revision = Number(payload.revision ?? board.revision ?? 0)
      }
      return record
    },

    applyDrawioBoardToolResult(result = {}, targetState = this.currentState) {
      if (!isDrawioBoardToolResult(result)) return false

      const payload = getDrawioBoardPayload(result)
      const xml = getDrawioBoardXml(payload)
      if (!xml) return false

      const board = this.ensureDrawioBoardState(targetState)
      const accepted = isAcceptedBoardPayload(payload, result?.success)
      board.activeBoardId = payload.activeBoardId || payload.active_board_id || payload.board_id || payload.artifact_id || payload.id || board.activeBoardId || null
      if (!accepted) {
        if (
          payload.revision !== undefined &&
          Number.isFinite(Number(payload.revision)) &&
          Number(payload.revision) < Number(board.revision || 0)
        ) return true
        const versionRecord = this.addDrawioBoardVersion(
          { ...payload, xml },
          result,
          targetState,
          { makeCurrent: false }
        )
        if (shouldPreviewBoardCandidate(payload)) {
          board.previousXml = board.currentXml || ''
          board.currentXml = xml
          board.title = payload.title || payload.name || board.title || 'Draw.io Board'
          board.version = versionRecord?.versionNumber || board.version
          board.qualityStatus = payload.quality_status || 'pending'
          board.qualityReport = payload.quality_report || {}
          board.updatedAt = payload.updatedAt || payload.updated_at || result.timestamp || new Date().toISOString()
        }
        targetState.hasResults = true
        return true
      }
      const nextVersion = Number(payload.version ?? board.version ?? 0)
      const selectedCells = payload.selectedCells || payload.selected_cells || board.selectedCells || []

      if (!board.applyingHistory && board.currentXml && board.currentXml !== xml) {
        this.pushDrawioBoardHistory(board.currentXml, targetState)
      }
      const versionRecord = this.addDrawioBoardVersion({ ...payload, xml }, result, targetState)
      board.previousXml = board.currentXml || ''
      board.currentXml = xml
      board.title = payload.title || payload.name || board.title || 'Draw.io Board'
      board.selectedCells = Array.isArray(selectedCells) ? selectedCells : []
      board.version = versionRecord?.versionNumber || (Number.isFinite(nextVersion) ? nextVersion : board.version)
      board.revision = Number(payload.revision ?? board.revision ?? 0)
      board.currentVersionSha256 = payload.xml_sha256 || payload.xml_ref?.sha256 || board.currentVersionSha256
      board.qualityStatus = payload.quality_status || board.qualityStatus || null
      board.qualityReport = payload.quality_report || board.qualityReport || {}
      board.dirty = Boolean(payload.dirty ?? false)
      board.updatedAt = payload.updatedAt || payload.updated_at || result.timestamp || new Date().toISOString()
      targetState.hasResults = true
      return true
    },

    async applyDrawioBoardToolResultFromRef(result = {}, targetState = this.currentState) {
      if (!isDrawioBoardToolResult(result)) return false

      const payload = getDrawioBoardPayload(result)
      if (getDrawioBoardXml(payload)) return this.applyDrawioBoardToolResult(result, targetState)

      const xmlRef = getDrawioBoardXmlRef(payload, result)
      if (!xmlRef) return false

      try {
        const xml = await readDrawioBoardXmlFromRef(xmlRef)
        if (!xml) return false
        const board = this.ensureDrawioBoardState(targetState)
        if (
          payload.revision !== undefined &&
          Number.isFinite(Number(payload.revision)) &&
          Number(payload.revision) < Number(board.revision || 0)
        ) return false
        return this.applyDrawioBoardToolResult({
          ...result,
          data: {
            ...(result.data || {}),
            xml
          }
        }, targetState)
      } catch (error) {
        console.warn('[drawio-board] failed to read xml_ref', {
          xmlRef,
          error: error?.message || error
        })
        return false
      }
    },

    restoreDrawioBoardFromSession(sessionData = {}, targetState = this.currentState) {
      if (!sessionData || !targetState) return false

      const metadataBoard = sessionData.metadata?.drawio_board || sessionData.drawio_board || null
      const metadataResult = metadataBoard
        ? {
            metadata: { generator: 'create_drawio_board' },
            data: metadataBoard,
            timestamp: metadataBoard.updated_at || metadataBoard.updatedAt
          }
        : null
      const latestMessageResult = metadataResult
        ? null
        : findLatestDrawioBoardResultFromMessages(sessionData.conversation_history || sessionData.messages || [])

      const restored = this.applyDrawioBoardToolResult(metadataResult || latestMessageResult || {}, targetState)
      if (!restored) return false

      const board = this.ensureDrawioBoardState(targetState)
      board.previousXml = ''
      board.undoStack = []
      board.redoStack = []
      board.applyingHistory = false
      board.baseVersionId = board.currentVersionId || board.baseVersionId || null
      board.pendingSnapshotAttachment = null
      console.log('[drawio-board] restored from session', {
        source: metadataResult ? 'metadata.drawio_board' : 'tool_result',
        currentXmlLength: board.currentXml.length,
        boardId: board.activeBoardId,
        title: board.title
      })
      return true
    },

    updateDrawioBoardXml(xml, options = {}, targetState = this.currentState) {
      const board = this.ensureDrawioBoardState(targetState)
      const nextXml = xml || ''
      if (nextXml === board.currentXml) return board
      if (!board.applyingHistory && board.currentXml) {
        this.pushDrawioBoardHistory(board.currentXml, targetState)
      }
      board.previousXml = board.currentXml || ''
      board.currentXml = nextXml
      board.activeBoardId = options.activeBoardId || options.active_board_id || options.board_id || board.activeBoardId
      board.title = options.title || board.title
      board.version = Number.isFinite(Number(options.version)) ? Number(options.version) : board.version + 1
      board.dirty = options.dirty !== undefined ? Boolean(options.dirty) : true
      board.baseVersionId = board.currentVersionId || board.baseVersionId || null
      board.updatedAt = options.updatedAt || options.updated_at || new Date().toISOString()
      console.log('[drawio-board] XML updated from editor', {
        previousXmlLength: board.previousXml.length,
        currentXmlLength: board.currentXml.length,
        version: board.version,
        dirty: board.dirty,
        updatedAt: board.updatedAt
      })
      if (board.dirty && options.saveDraft !== false) {
        scheduleDrawioDraftSave(board)
      }
      return board
    },

    async loadDrawioBoardVersions(targetState = this.currentState) {
      const board = this.ensureDrawioBoardState(targetState)
      if (!board.activeBoardId) return []
      const response = await getBoardVersions(board.activeBoardId)
      board.currentVersionId = response.current_version_id || board.currentVersionId
      board.baseVersionId = board.currentVersionId
      board.revision = Number(response.revision ?? board.revision ?? 0)
      board.versions = mapServerBoardVersions(response.versions || [], board.currentVersionId)
      return board.versions
    },

    undoDrawioBoard(targetState = this.currentState) {
      const board = this.ensureDrawioBoardState(targetState)
      if (!board.currentXml || board.undoStack.length === 0) return board

      const previousXml = board.undoStack.pop()
      board.redoStack.push(board.currentXml)
      board.previousXml = board.currentXml
      board.applyingHistory = true
      board.currentXml = previousXml
      board.version += 1
      board.dirty = true
      board.updatedAt = new Date().toISOString()
      board.applyingHistory = false
      return board
    },

    redoDrawioBoard(targetState = this.currentState) {
      const board = this.ensureDrawioBoardState(targetState)
      if (!board.currentXml || board.redoStack.length === 0) return board

      const nextXml = board.redoStack.pop()
      board.undoStack.push(board.currentXml)
      if (board.undoStack.length > 50) {
        board.undoStack = board.undoStack.slice(board.undoStack.length - 50)
      }
      board.previousXml = board.currentXml
      board.applyingHistory = true
      board.currentXml = nextXml
      board.version += 1
      board.dirty = true
      board.updatedAt = new Date().toISOString()
      board.applyingHistory = false
      return board
    },

    updateDrawioBoardSelection(selectedCells = [], targetState = this.currentState) {
      const board = this.ensureDrawioBoardState(targetState)
      board.selectedCells = Array.isArray(selectedCells) ? selectedCells : []
      board.updatedAt = new Date().toISOString()
      console.log('[drawio-board] selection updated in store', {
        selectedCount: board.selectedCells.length,
        selectedIds: board.selectedCells.map((cell) => cell?.id).filter(Boolean),
        updatedAt: board.updatedAt
      })
      return board
    },

    setDrawioBoardSnapshotAttachment(attachment = null, targetState = this.currentState) {
      const board = this.ensureDrawioBoardState(targetState)
      board.pendingSnapshotAttachment = attachment
      board.updatedAt = new Date().toISOString()
      return board
    },

    async confirmDrawioBoardSnapshot(snapshot = {}, targetState = this.currentState) {
      if (!snapshot?.file) return null

      if (!targetState?.sessionId) this.createSessionId()
      const uploadResult = await uploadChatFile(
        snapshot.file,
        targetState?.sessionId,
        targetState?.mode || this.currentMode
      )
      const attachment = {
        id: uploadResult.file_id || `drawio_board_snapshot_${Date.now()}`,
        file_id: uploadResult.file_id,
        name: uploadResult.filename || snapshot.filename || snapshot.file.name || 'drawio-board.png',
        filename: uploadResult.filename || snapshot.filename || snapshot.file.name || 'drawio-board.png',
        type: uploadResult.file_type || 'image',
        file_type: uploadResult.file_type || 'image',
        mime_type: uploadResult.mime_type || snapshot.file.type || 'image/png',
        size: uploadResult.file_size || uploadResult.size || snapshot.file.size || 0,
        url: uploadResult.url || uploadResult.file_url || '',
        resourceRefId: uploadResult.resource_ref?.ref_id || null,
        resource_ref: uploadResult.resource_ref || null,
        source: 'drawio_board_snapshot',
        title: snapshot.title || targetState?.board?.title || '画板',
        xml_length: snapshot.xmlLength || 0,
        confirmed_at: snapshot.confirmedAt || new Date().toISOString()
      }

      this.setDrawioBoardSnapshotAttachment(attachment, targetState)
      console.log('[drawio-board] confirmed snapshot uploaded', {
        fileId: attachment.file_id,
        url: attachment.url,
        size: attachment.size
      })
      return attachment
    },

    consumeDrawioBoardSnapshotAttachment(mode = this.currentMode, targetState = this.currentState) {
      if (mode !== 'board') return null
      const board = this.ensureDrawioBoardState(targetState)
      const attachment = board.pendingSnapshotAttachment
      board.pendingSnapshotAttachment = null
      return attachment || null
    },

    async prepareDrawioBoardForSend(mode = this.currentMode, targetState = this.currentState) {
      if (mode !== 'board' || !targetState?.board?.currentXml) return null
      const board = this.ensureDrawioBoardState(targetState)
      board.syncStatus = 'syncing'
      board.syncError = null
      cancelDrawioDraftSave(board.activeBoardId)
      try {
        const result = await prepareBoardForSend({
          board,
          exportXml: exportActiveDrawioBoardXml,
          getSourceVersionId: getActiveDrawioBoardWorkingVersionId,
          updateXml: (xml) => this.updateDrawioBoardXml(xml, { dirty: true, saveDraft: false }, targetState),
          commitManual: (payload) => commitManualBoardVersion(board.activeBoardId, payload),
          onCommitted: (payload) => confirmActiveDrawioBoardCommit(payload)
        })
        const version = result.response?.version
        if (version) {
          const existingIndex = board.versions.findIndex(item => (
            (item.version_id || item.id) === (version.version_id || version.id)
          ))
          const record = {
            ...version,
            id: version.version_id || version.id,
            versionNumber: version.version_number,
            xml: board.currentXml,
            title: board.title,
            is_current: true
          }
          board.versions = board.versions.map(item => ({ ...item, is_current: false }))
          if (existingIndex >= 0) board.versions.splice(existingIndex, 1, record)
          else board.versions.push(record)
        }
        board.syncStatus = 'idle'
        cancelDrawioDraftSave(board.activeBoardId)
        return result.context
      } catch (error) {
        board.syncStatus = 'error'
        board.syncError = error?.code || error?.message || 'board_sync_failed'
        throw error
      }
    },

    buildBoardContext(mode = this.currentMode, targetState = null) {
      if (mode !== 'board') return null

      const state = targetState || this.currentState
      const board = state?.board
      if (!board?.currentXml) return null

      const compactVersionContext = board.currentVersionId && Number.isFinite(Number(board.revision))
      if (compactVersionContext) {
        return {
          artifact_kind: 'drawio_board',
          board_id: board.activeBoardId,
          version_id: board.currentVersionId,
          revision: Number(board.revision),
          selected_cells: board.selectedCells || [],
          title: board.title
        }
      }

      return {
        artifact_kind: 'drawio_board',
        board_id: board.activeBoardId,
        active_board_id: board.activeBoardId,
        title: board.title,
        current_xml: board.currentXml,
        selected_cells: board.selectedCells || [],
        version: board.version,
        current_version_id: board.currentVersionId || null,
        base_version_id: board.baseVersionId || board.currentVersionId || null,
        version_files: (board.versions || []).map(version => ({
          version_id: version.version_id || version.id,
          version_number: version.version_number || version.versionNumber,
          title: version.title,
          file_name: version.file_name,
          file_path: version.file_path,
          format: version.format || 'drawio',
          source: version.source,
          created_at: version.created_at,
          is_current: (version.version_id || version.id) === board.currentVersionId
        })),
        dirty: board.dirty,
        updated_at: board.updatedAt
      }
    },

    // ✅ 向后兼容别名：analyze -> startAnalysis
    async analyze(query, options = {}) {
      return await this.startAnalysis(query, options)
    },

    // 开始分析
    async startAnalysis(query, options = {}) {
      const {
        assistantMode = null,
        useFullChemistry = false,  // RACM2完整化学机理分析选项
        gridResolution = 21,  // 网格分辨率选项
        agentMode = this.agentMode,  // ✅ 双模式架构：assistant | expert
        knowledgeBaseIds = null,  // ✅ 知识库ID列表
        modelTier = 'auto',
        skillIds = [],
        contextRefs = [],
        activeContexts = null,
        messageAttachments = [],
        skipAutoFollowup = false,
        preserveCurrentMode = false,
        synthetic = false,
        syntheticMeta = null,
        queuedAlreadyShown = false,
        dequeuedInput = false,
        onAccepted
      } = options

      const requestedMode = VALID_MODES.includes(agentMode) ? agentMode : this.currentMode
      if (requestedMode !== this.currentMode && !preserveCurrentMode) {
        this.switchMode(requestedMode)
      }
      const sessionStateMode = preserveCurrentMode ? requestedMode : this.currentMode
      const activeSessionId = this.activeSessionByMode[sessionStateMode]

      // 【修复】确定使用的模式：优先尊重本次请求的显式模式，继续已有会话时再使用会话自身记录的模式
      let actualMode = requestedMode
      let sessionState = activeSessionId && this.sessionStates[activeSessionId]
        ? this.sessionStates[activeSessionId]
        : (this.modeStates[sessionStateMode] || this.currentState)
      if (sessionState.sessionId) {
        const sessionMode = VALID_MODES.includes(sessionState.mode)
          ? sessionState.mode
          : this.extractModeFromSessionId(sessionState.sessionId)
        if (sessionMode) {
          actualMode = sessionMode
          console.log(`[startAnalysis] sessionId=${sessionState.sessionId}, 提取模式=${sessionMode}, currentMode=${this.currentMode}`)
        }
      }

      const hasStructuredSelection = skillIds.length > 0 || contextRefs.length > 0

      if (!query.trim() && !hasStructuredSelection) {
        return
      }

      if (sessionState.isAnalyzing) {
        if (actualMode === 'assistant' && !hasStructuredSelection && sessionState.sessionId) {
          await this.steerActiveAnalysis(query, sessionState)
          if (typeof onAccepted === 'function') onAccepted()
          return
        }

        freezeActiveAssistantOutput(sessionState, { reason: 'queued_input' }, contentToString)
        enqueueUserInput(sessionState, {
          query,
          options: {
            ...options,
            onAccepted: undefined,
            agentMode: actualMode,
            skillIds,
            contextRefs,
            activeContexts,
          },
          data: {
            ...(syntheticMeta || {}),
            skill_ids: skillIds,
            context_refs: contextRefs,
            active_contexts: activeContexts
          },
          attachments: messageAttachments.length > 0 ? messageAttachments : null
        })
        sessionState.currentMessage = ''
        console.log('[startAnalysis] 当前模式运行中，用户输入已排队', {
          mode: actualMode,
          queuedCount: sessionState.pendingUserInputs.length
        })
        this._persistModeState(actualMode)
        if (typeof onAccepted === 'function') onAccepted()
        return
      }

      if (!dequeuedInput && sessionState.pendingUserInputs?.length) {
        const next = queueIncomingBehindPendingAndTakeNext(sessionState, {
          query,
          options: {
            ...options,
            onAccepted: undefined,
            agentMode: actualMode,
            skillIds,
            contextRefs,
            activeContexts
          },
          data: {
            ...(syntheticMeta || {}),
            skill_ids: skillIds,
            context_refs: contextRefs,
            active_contexts: activeContexts
          },
          attachments: messageAttachments.length > 0 ? messageAttachments : null
        })
        if (typeof onAccepted === 'function') onAccepted()
        if (next) {
          return await this.startAnalysis(next.query, {
            ...next.options,
            agentMode: next.options?.agentMode || actualMode,
            dequeuedInput: true,
            onAccepted: () => {
              acknowledgeQueuedInput(sessionState, next.clientMessageId)
              this._persistModeState(actualMode)
            }
          })
        }
      }

      // 首次分析或继续分析
      if (!sessionState.sessionId) {
        if (preserveCurrentMode) {
          const sessionId = `${sessionStateMode}_session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
          sessionState = this._ensureSessionState(sessionId, sessionStateMode)
          this.activeSessionByMode[sessionStateMode] = sessionId
          sessionState.sessionId = sessionId
          console.log('[startAnalysis] Created embedded session for', sessionStateMode, ':', sessionState.sessionId)
        } else {
          this.createSessionId()
          sessionState = this.currentState
        }
        sessionState.sessionRound = 1
        sessionState.finalAnswers = []
      } else {
        if (preserveCurrentMode) {
          sessionState.sessionRound = Math.max(sessionState.sessionRound + 1, 1)
          sessionState.isAnalyzing = false
          sessionState.error = null
          sessionState.results = {
            map: null,
            charts: [],
            tables: [],
            text: ''
          }
        } else {
          this.continueSession()
          sessionState = this.currentState
        }
      }

      // 重置状态
      const clientMessageId = options.clientMessageId || null
      const wasAlreadyShown = queuedAlreadyShown || hasShownClientMessage(sessionState, clientMessageId)
      if (!wasAlreadyShown) {
        this._addMessageToState(
          sessionState,
          'user',
          query,
          {
            ...(syntheticMeta || {}),
            skill_ids: skillIds,
            context_refs: contextRefs,
            active_contexts: activeContexts
          },
          messageAttachments.length > 0 ? messageAttachments : null,
          {
            ...(synthetic ? { synthetic: true } : {}),
            ...(clientMessageId ? { clientMessageId } : {})
          }
        )
      }
      sessionState.currentMessage = ''
      sessionState.isAnalyzing = true
      if (actualMode === 'board') this.ensureDrawioBoardState(sessionState).readOnly = true
      sessionState.isComplete = false
      sessionState.error = null
      sessionState.iterations = 0
      this.prepareQueryVoiceOutput(actualMode, sessionState)

      // 如果是中断状态，传递给后端，然后重置标志
      const isInterruption = sessionState.isInterruption
      if (isInterruption) {
        console.log('[ReAct] 检测到用户中断，将传递给后端')
        sessionState.isInterruption = false  // 重置标志
      }

      // 重置Reflexion状态
      sessionState.showReflexion = false
      sessionState.reflexionCount = 0

      // 清空本轮结果
      sessionState.results = {
        map: null,
        charts: [],
        tables: [],
        text: ''
      }

      try {
        const boardContext = actualMode === 'board' ? this.buildBoardContext(actualMode, sessionState) : null
        const mapContext = actualMode === 'graph' ? options.mapContext || null : null
        if (boardContext) {
          console.log('[drawio-board] board_context will be sent', {
            sessionId: sessionState.sessionId,
            currentXmlLength: boardContext.current_xml?.length || 0,
            selectedCount: boardContext.selected_cells?.length || 0,
            version: boardContext.version,
            dirty: boardContext.dirty,
            updatedAt: boardContext.updated_at
          })
        }

        // 调用新架构 ReAct Agent
        await agentAPI.analyze(query, {
          sessionId: sessionState.sessionId,
          requestKey: sessionState.sessionId,
          userIdentifier: this.userIdentifier,  // ✅ 传递用户标识（跨会话持久化）
          enhanceWithHistory: true,
          maxIterations: this.maxIterations,
          assistantMode: assistantMode,  // 传递助手模式
          useFullChemistry: useFullChemistry,  // RACM2完整化学机理分析选项
          gridResolution: gridResolution,  // 网格分辨率选项
          isInterruption: isInterruption,  // ✅ 传递中断标志
          previousPausedRunId: sessionState.pendingPausedRunId,
          agentMode: actualMode,  // ✅ 使用从 sessionId 提取的模式
          knowledgeBaseIds: knowledgeBaseIds,  // ✅ 传递知识库ID列表
          modelTier,
          skillIds,
          contextRefs,
          activeContexts,
          ...(boardContext !== null ? { boardContext } : {}),
          ...(mapContext !== null ? { mapContext } : {}),
          skipAutoFollowup,
          onAccepted,
          onEvent: (event) => {
            if (!event.data) event.data = {}
            if (!event.data.session_id) event.data.session_id = sessionState.sessionId
            this.handleEvent(event)
          }
        })

        const pendingPrompt = sessionState._pendingAutoFollowupPrompt
        const pendingHookName = sessionState._pendingAutoFollowupHookName
        if (pendingPrompt) {
          sessionState._pendingAutoFollowupPrompt = null
          sessionState._pendingAutoFollowupHookName = null
          await this.startAnalysis(pendingPrompt, {
            assistantMode,
            useFullChemistry,
            gridResolution,
            agentMode: actualMode,
            knowledgeBaseIds,
            modelTier,
            skillIds: [],
            contextRefs: [],
            skipAutoFollowup: true,
            synthetic: true,
            syntheticMeta: {
              source: 'auto_hook',
              hook_name: pendingHookName || 'report_final_review'
            }
          })
        }

        await this._runNextQueuedInput(sessionState, actualMode)
      } catch (error) {
        // 检查是否为用户主动取消
        if (error.name === 'AbortError' || error.message === 'The user aborted a request.') {
          console.log('分析已取消')
          // 取消不是错误，不需要设置error状态
          // isAnalyzing已在pauseAnalysis中设置为false
        } else {
          console.error('Analysis failed:', error)
          sessionState.isAnalyzing = false
          if (actualMode === 'board' && sessionState.board) sessionState.board.readOnly = false
          sessionState.error = error.message
          this._addMessageToState(sessionState, 'error', `分析失败: ${error.message}`)
          promoteUnappliedSteeringInputsToQueue(sessionState, {
            agentMode: actualMode,
            queuedAlreadyShown: true
          })
          this._persistModeState(actualMode)
        }
      }
    },

    async steerActiveAnalysis(query, sessionState = this.currentState) {
      const text = (query || '').trim()
      if (!text || !sessionState.sessionId) return

      const steeringInputId = addPendingSteeringInput(sessionState, text)
      sessionState.currentMessage = ''
      this._persistModeState(sessionState.mode || 'assistant')

      let accepted = false
      try {
        const result = await agentAPI.steer(sessionState.sessionId, text, steeringInputId)
        accepted = !!result.accepted
      } catch (error) {
        console.warn('[steerActiveAnalysis] 追加指令失败，已转入队列', error)
      }

      if (!accepted) {
        removePendingSteeringInput(sessionState, text, steeringInputId)
        freezeActiveAssistantOutput(sessionState, { reason: 'steering_fallback' }, contentToString)
        fallbackSteeringInputToQueue(sessionState, text, steeringInputId)
        this._persistModeState(sessionState.mode || 'assistant')
        console.warn('[steerActiveAnalysis] 后端没有可追加任务，已转入队列')
      }
    },

    async _runNextQueuedInput(sessionState, actualMode) {
      const next = peekNextQueuedInput(sessionState)
      if (!next) return

      console.log('[runNextQueuedInput] 开始处理排队输入', {
        mode: actualMode,
        remaining: sessionState.pendingUserInputs.length
      })
      await this.startAnalysis(next.query, {
        ...next.options,
        agentMode: next.options?.agentMode || actualMode,
        dequeuedInput: true,
        onAccepted: () => {
          acknowledgeQueuedInput(sessionState, next.clientMessageId)
          this._persistModeState(actualMode)
        }
      })
    },

    // 继续分析（新问题）
    async continueAnalysis(query, options = {}) {
      if (this.currentState.isAnalyzing) {
        const confirmStop = confirm('当前正在分析中，是否停止并开始新分析？')
        if (!confirmStop) {
          return
        }
        await agentAPI.cancel(this.currentState.sessionId, this.currentState.activeRunId, 'client_cancelled')
        this.currentState.isAnalyzing = false
      }

      // 使用 startAnalysis，它会处理会话延续
      await this.startAnalysis(query, options)
    },

    // 停止分析
    async stopAnalysis() {
      freezeActiveAssistantOutput(this.currentState, { reason: 'stopped' }, contentToString)
      const activeRunId = this.currentState.activeRunId
      if (activeRunId) {
        this.currentState.ignoredRunIds = [...(this.currentState.ignoredRunIds || []), activeRunId]
        this.currentState.activeRunId = null
      }
      await agentAPI.cancel(this.currentState.sessionId, activeRunId, 'client_cancelled')
      this.currentState.isAnalyzing = false
      if (this.currentMode === 'board' && this.currentState.board) this.currentState.board.readOnly = false
      // 不添加系统消息
    },

    // 暂停分析（与stopAnalysis相同）
    async pauseAnalysis() {
      freezeActiveAssistantOutput(this.currentState, { reason: 'paused' }, contentToString)
      const activeRunId = this.currentState.activeRunId
      if (activeRunId) {
        this.currentState.ignoredRunIds = [...(this.currentState.ignoredRunIds || []), activeRunId]
        this.currentState.pendingPausedRunId = activeRunId
        this.currentState.activeRunId = null
      }
      this.currentState.isAnalyzing = false
      if (this.currentMode === 'board' && this.currentState.board) this.currentState.board.readOnly = false
      this.currentState.isComplete = false
      this.currentState.error = null
      this.currentState.isInterruption = false
      void agentAPI.cancel(this.currentState.sessionId, activeRunId)
      // 不添加系统消息
    },

    // 重新分析
    async restart() {
      this.reset()
    }
  }
})
