/**
 * 对话框管理 Composable
 * 统一管理各种对话框的状态
 */
import { ref } from 'vue'

export function useDialogManager() {
  // ========== 对话框状态 ==========
  const dialogs = ref({
    // 知识库相关
    kbCreate: false,
    kbEdit: false,
    kbChunks: false,

    // 会话相关
    sessionManager: false,

    // 其他
    confirm: false
  })

  // ========== 对话框数据 ==========
  const dialogData = ref({
    // 知识库编辑表单
    kbEdit: {
      name: '',
      description: '',
      is_default: false
    },

    // 知识库创建表单
    kbCreate: {
      name: '',
      description: '',
      kb_type: 'private',
      chunking_strategy: 'llm',
      chunk_size: 800,
      chunk_overlap: 100
    },

    // 管理员确认
    kbAdminConfirm: false,

    // 确认对话框
    confirm: {
      title: '',
      message: '',
      onConfirm: null,
      onCancel: null
    }
  })

  // ========== 通用方法 ==========

  /**
   * 打开对话框
   * @param {string} dialogName - 对话框名称
   * @param {object} data - 对话框数据
   */
  const openDialog = (dialogName, data = {}) => {
    if (dialogs.value.hasOwnProperty(dialogName)) {
      dialogs.value[dialogName] = true
      if (data && typeof data === 'object') {
        dialogData.value[dialogName] = { ...dialogData.value[dialogName], ...data }
      }
    } else {
      console.warn(`对话框 "${dialogName}" 不存在`)
    }
  }

  /**
   * 关闭对话框
   * @param {string} dialogName - 对话框名称
   */
  const closeDialog = (dialogName) => {
    if (dialogs.value.hasOwnProperty(dialogName)) {
      dialogs.value[dialogName] = false
    }
  }

  /**
   * 切换对话框状态
   * @param {string} dialogName - 对话框名称
   */
  const toggleDialog = (dialogName) => {
    if (dialogs.value.hasOwnProperty(dialogName)) {
      dialogs.value[dialogName] = !dialogs.value[dialogName]
    }
  }

  /**
   * 检查对话框是否打开
   * @param {string} dialogName - 对话框名称
   * @returns {boolean}
   */
  const isDialogOpen = (dialogName) => {
    return dialogs.value[dialogName] || false
  }

  /**
   * 关闭所有对话框
   */
  const closeAllDialogs = () => {
    Object.keys(dialogs.value).forEach(key => {
      dialogs.value[key] = false
    })
  }

  // ========== 知识库对话框快捷方法 ==========

  /**
   * 打开知识库创建对话框
   * @param {object} formData - 表单初始数据
   */
  const openKbCreateDialog = (formData = {}) => {
    openDialog('kbCreate', formData)
  }

  /**
   * 关闭知识库创建对话框
   */
  const closeKbCreateDialog = () => {
    closeDialog('kbCreate')
    // 重置表单
    dialogData.value.kbCreate = {
      name: '',
      description: '',
      kb_type: 'private',
      chunking_strategy: 'llm',
      chunk_size: 800,
      chunk_overlap: 100
    }
  }

  /**
   * 打开知识库编辑对话框
   * @param {object} kbData - 知识库数据
   */
  const openKbEditDialog = (kbData) => {
    openDialog('kbEdit', {
      name: kbData.name || '',
      description: kbData.description || '',
      is_default: kbData.is_default || false
    })
  }

  /**
   * 关闭知识库编辑对话框
   */
  const closeKbEditDialog = () => {
    closeDialog('kbEdit')
  }

  /**
   * 打开知识库分块查看对话框
   */
  const openKbChunksDialog = () => {
    openDialog('kbChunks')
  }

  /**
   * 关闭知识库分块查看对话框
   */
  const closeKbChunksDialog = () => {
    closeDialog('kbChunks')
  }

  // ========== 会话对话框快捷方法 ==========

  /**
   * 打开会话管理对话框
   */
  const openSessionManager = () => {
    openDialog('sessionManager')
  }

  /**
   * 关闭会话管理对话框
   */
  const closeSessionManager = () => {
    closeDialog('sessionManager')
  }

  // ========== 确认对话框快捷方法 ==========

  /**
   * 显示确认对话框
   * @param {string} title - 标题
   * @param {string} message - 消息
   * @param {function} onConfirm - 确认回调
   * @param {function} onCancel - 取消回调
   */
  const showConfirm = (title, message, onConfirm, onCancel) => {
    dialogData.value.confirm = {
      title,
      message,
      onConfirm,
      onCancel
    }
    openDialog('confirm')
  }

  /**
   * 确认操作
   */
  const handleConfirm = () => {
    const { onConfirm } = dialogData.value.confirm
    if (typeof onConfirm === 'function') {
      onConfirm()
    }
    closeDialog('confirm')
  }

  /**
   * 取消操作
   */
  const handleCancel = () => {
    const { onCancel } = dialogData.value.confirm
    if (typeof onCancel === 'function') {
      onCancel()
    }
    closeDialog('confirm')
  }

  return {
    // 状态
    dialogs,
    dialogData,

    // 通用方法
    openDialog,
    closeDialog,
    toggleDialog,
    isDialogOpen,
    closeAllDialogs,

    // 知识库对话框
    openKbCreateDialog,
    closeKbCreateDialog,
    openKbEditDialog,
    closeKbEditDialog,
    openKbChunksDialog,
    closeKbChunksDialog,

    // 会话对话框
    openSessionManager,
    closeSessionManager,

    // 确认对话框
    showConfirm,
    handleConfirm,
    handleCancel
  }
}
