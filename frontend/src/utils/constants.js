/**
 * 常量定义
 * 集中管理应用中的各种常量
 */

// ========== 面板相关 ==========
export const PANEL_TYPES = {
  KNOWLEDGE_BASE: 'knowledge-base',
  FETCHERS: 'fetchers',
  SCHEDULED_TASKS: 'scheduled-tasks',
  SESSION_HISTORY: 'session-history',
  SOCIAL_PLATFORM: 'social-platform',
  TOOLS_MANAGEMENT: 'tools-management'
}

// ========== 助手模式 ==========
export const ASSISTANT_MODES = {
  GENERAL_AGENT: 'general-agent',
  WEATHER_EXPERT: 'weather-expert',
  COMPONENT_EXPERT: 'component-expert',
  VIZ_EXPERT: 'viz-expert',
  REPORT_GENERATION_EXPERT: 'report-generation-expert',
  OFFICE_ASSISTANT: 'office-assistant'
}

// ========== 知识库相关 ==========
export const KB_TYPES = {
  PRIVATE: 'private',
  PUBLIC: 'public'
}

export const CHUNK_STRATEGIES = {
  LLM: 'llm',
  SENTENCE: 'sentence',
  SEMANTIC: 'semantic',
  MARKDOWN: 'markdown',
  HYBRID: 'hybrid'
}

export const CHUNK_STRATEGY_DESCRIPTIONS = {
  llm: '使用LLM智能识别文档结构，适合复杂文档（较慢）',
  sentence: '按句子分块，保持语义完整，适合通用文本',
  semantic: '基于语义相似度分块，保持主题连贯',
  markdown: '按Markdown结构分块，保留标题层级',
  hybrid: '混合策略，结合多种方法优势'
}

export const CHUNK_TYPES = {
  TEXT: 'text',
  CODE: 'code',
  TABLE: 'table',
  IMAGE: 'image',
  METADATA: 'metadata'
}

export const CHUNK_TYPE_NAMES = {
  text: '文本',
  code: '代码',
  table: '表格',
  image: '图片',
  metadata: '元数据'
}

// 知识库默认配置
export const KB_DEFAULTS = {
  CHUNK_SIZE: 800,
  CHUNK_OVERLAP: 100,
  MIN_CHUNK_SIZE: 64,
  MAX_CHUNK_SIZE: 2048,
  MAX_CHUNK_OVERLAP: 512,
  MAX_NAME_LENGTH: 100,
  MAX_DESCRIPTION_LENGTH: 500
}

// ========== 文件相关 ==========
export const FILE_SIZE_LIMITS = {
  SMALL: 1024 * 1024, // 1MB
  MEDIUM: 10 * 1024 * 1024, // 10MB
  LARGE: 50 * 1024 * 1024, // 50MB
  EXTRA_LARGE: 100 * 1024 * 1024 // 100MB
}

export const ALLOWED_FILE_TYPES = {
  DOCUMENTS: [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'text/markdown'
  ],
  IMAGES: [
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp'
  ],
  SPREADSHEETS: [
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ],
  PRESENTATIONS: [
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation'
  ]
}

// ========== 面板尺寸相关 ==========
export const PANEL_SIZES = {
  DEFAULT_VIZ_WIDTH: 30, // 默认宽度（%）
  COLLAPSED_VIZ_WIDTH: 45, // 左侧折叠时默认宽度（%）
  MIN_VIZ_WIDTH: 20, // 最小宽度（%）
  MAX_VIZ_WIDTH: 60, // 最大宽度（%）
  DEFAULT_SIDEBAR_WIDTH: 60 // 默认侧边栏宽度（px）
}

// ========== 消息相关 ==========
export const MESSAGE_TYPES = {
  USER: 'user',
  ASSISTANT: 'assistant',
  SYSTEM: 'system',
  ERROR: 'error',
  THINKING: 'thinking',
  TOOL_CALL: 'tool_call',
  OBSERVATION: 'observation'
}

export const MESSAGE_STATUS = {
  PENDING: 'pending',
  SENDING: 'sending',
  SENT: 'sent',
  FAILED: 'failed'
}

// ========== 分析状态 ==========
export const ANALYSIS_STATUS = {
  IDLE: 'idle',
  ANALYZING: 'analyzing',
  PAUSED: 'paused',
  COMPLETED: 'completed',
  ERROR: 'error'
}

// ========== 抓取器相关 ==========
export const FETCHER_STATUS = {
  IDLE: 'idle',
  RUNNING: 'running',
  PAUSED: 'paused',
  DISABLED: 'disabled',
  ERROR: 'error'
}

export const FETCHER_ACTIONS = {
  START: 'start',
  PAUSE: 'pause',
  RESUME: 'resume',
  STOP: 'stop',
  STATUS: 'status'
}

// ========== 定时任务相关 ==========
export const TASK_STATUS = {
  ACTIVE: 'active',
  PAUSED: 'paused',
  COMPLETED: 'completed',
  FAILED: 'failed'
}

export const TASK_TAGS = {
  SUCCESS: 'success',
  WARNING: 'warning',
  INFO: 'info',
  ERROR: 'error'
}

// ========== 可视化相关 ==========
export const VISUALIZATION_TYPES = {
  CHART: 'chart',
  MAP: 'map',
  TABLE: 'table',
  IMAGE: 'image'
}

export const CHART_TYPES = {
  PIE: 'pie',
  BAR: 'bar',
  LINE: 'line',
  TIMESERIES: 'timeseries',
  WIND_ROSE: 'wind_rose',
  PROFILE: 'profile',
  SCATTER_3D: 'scatter3d',
  SURFACE_3D: 'surface3d',
  LINE_3D: 'line3d',
  BAR_3D: 'bar3d',
  VOLUME_3D: 'volume3d',
  HEATMAP: 'heatmap',
  RADAR: 'radar',
  MAP: 'map'
}

// ========== 键盘快捷键 ==========
export const KEYBOARD_SHORTCUTS = {
  SEND_MESSAGE: 'Ctrl+Enter',
  PAUSE_ANALYSIS: 'Escape',
  TOGGLE_VIZ_PANEL: 'Ctrl+Shift+V',
  NEW_SESSION: 'Ctrl+Shift+N',
  OPEN_SESSION_MANAGER: 'Ctrl+Shift+H'
}

// ========== 本地存储键 ==========
export const STORAGE_KEYS = {
  IS_ADMIN: 'isAdmin',
  VIZ_WIDTH: 'vizWidth',
  SIDEBAR_COLLAPSED: 'sidebarCollapsed',
  USE_RERANKER: 'useReranker',
  LAST_ASSISTANT_MODE: 'lastAssistantMode',
  THEME: 'theme',
  LANGUAGE: 'language'
}

// ========== API相关 ==========
export const API_STATUS = {
  SUCCESS: 'success',
  ERROR: 'error',
  LOADING: 'loading',
  IDLE: 'idle'
}

export const HTTP_STATUS = {
  OK: 200,
  CREATED: 201,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  INTERNAL_SERVER_ERROR: 500
}

// ========== 分页相关 ==========
export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
  MIN_PAGE_SIZE: 5
}

// ========== 时间相关 ==========
export const TIME_FORMATS = {
  FULL: 'full',
  DATE: 'date',
  TIME: 'time',
  RELATIVE: 'relative',
  ISO: 'iso'
}

export const DATE_FORMATS = {
  ISO: 'YYYY-MM-DD',
  ISO_FULL: 'YYYY-MM-DD HH:mm:ss',
  CN: 'YYYY年MM月DD日',
  CN_FULL: 'YYYY年MM月DD日 HH:mm:ss'
}

// ========== 错误类型 ==========
export const ERROR_TYPES = {
  VALIDATION: 'validation',
  NETWORK: 'network',
  AUTHORIZATION: 'authorization',
  NOT_FOUND: 'not_found',
  SERVER: 'server',
  UNKNOWN: 'unknown'
}

// ========== 通知类型 ==========
export const NOTIFICATION_TYPES = {
  SUCCESS: 'success',
  WARNING: 'warning',
  ERROR: 'error',
  INFO: 'info'
}

// ========== 动画相关 ==========
export const ANIMATION_DURATION = {
  FAST: 150,
  NORMAL: 300,
  SLOW: 500
}

// ========== 响应式断点 ==========
export const BREAKPOINTS = {
  XS: 480,
  SM: 576,
  MD: 768,
  LG: 992,
  XL: 1200,
  XXL: 1600
}
