/**
 * ReactAnalysis Composables 索引文件
 * 统一导出所有composables
 */

// 面板管理
export { usePanelManagement } from './usePanelManagement.js'
export { useWidthResizer } from './useWidthResizer.js'

// 状态管理
export { useDialogManager } from './useDialogManager.js'
export { useRightPanelState } from './useRightPanelState.js'

// 功能模块
export { useSessionManagement } from './useSessionManagement.js'
export { useKnowledgeBaseOperations } from './useKnowledgeBaseOperations.js'
export { useDataFetcher } from './useDataFetcher.js'

// 交互功能
export { useKeyboardShortcuts, createDefaultHandlers } from './useKeyboardShortcuts.js'
export { useDragAndDrop, createChatDragHandler } from './useDragAndDrop.js'
export { useMessageOperations } from './useMessageOperations.js'

// ========== 新增功能模块 ==========

// 知识库上传（P0核心功能）
export { validateFile, validateFiles, getFileExtension, isSupportedDocument } from './useKbFileValidation.js'
export { useKbUploadProgress } from './useKbUploadProgress.js'
export { useKbFileUpload } from './useKbFileUpload.js'

// 会话恢复（P0核心功能）
export { useSessionRecovery } from './useSessionRecovery.js'

// 可视化提取（P0核心功能）
export { useVisualizationExtractor } from './useVisualizationExtractor.js'

// 定时任务管理（P1重要功能）
export { useScheduledTaskManager } from './useScheduledTaskManager.js'

// Office文档处理（P1重要功能）
export { useOfficeDocumentHandler } from './useOfficeDocumentHandler.js'

// 文件拖拽（P1重要功能）
export { useFileDropZone } from './useFileDropZone.js'

// 错误处理（P2辅助功能）
export { useErrorHandling, createApiErrorHandler } from './useErrorHandling.js'

// 日志记录（P2辅助功能）
export { useLogger, usePerformanceLogger } from './useLogger.js'
