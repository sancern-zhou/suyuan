/**
 * 键盘快捷键 Composable
 * 处理全局键盘快捷键
 */
import { onMounted, onBeforeUnmount } from 'vue'
import { KEYBOARD_SHORTCUTS } from '@/utils/constants'

export function useKeyboardShortcuts(handlers = {}) {
  /**
   * 检查是否按下了指定的快捷键
   * @param {KeyboardEvent} event - 键盘事件
   * @param {string} shortcut - 快捷键字符串（如 'Ctrl+Enter'）
   * @returns {boolean}
   */
  const isShortcutMatch = (event, shortcut) => {
    const keys = shortcut.split('+').map(k => k.trim().toLowerCase())
    const eventKey = event.key.toLowerCase()

    // 检查每个键
    return keys.every(key => {
      switch (key) {
        case 'ctrl':
        case 'control':
          return event.ctrlKey || event.metaKey
        case 'shift':
          return event.shiftKey
        case 'alt':
          return event.altKey
        case 'meta':
        case 'cmd':
          return event.metaKey
        default:
          return eventKey === key
      }
    })
  }

  /**
   * 处理键盘事件
   * @param {KeyboardEvent} event - 键盘事件
   */
  const handleKeyDown = (event) => {
    // 如果在输入框中，不处理快捷键（除了特定情况）
    const target = event.target
    const isInputElement = target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.contentEditable === 'true'

    // 遍历所有注册的快捷键处理器
    for (const [shortcut, handler] of Object.entries(handlers)) {
      if (isShortcutMatch(event, shortcut)) {
        // 对于输入框中的快捷键，只处理特定的
        if (isInputElement) {
          const allowedInInput = [
            KEYBOARD_SHORTCUTS.SEND_MESSAGE,
            KEYBOARD_SHORTCUTS.PAUSE_ANALYSIS
          ].includes(shortcut)

          if (!allowedInInput) {
            return
          }
        }

        // 调用处理器
        if (typeof handler === 'function') {
          handler(event)
        }

        // 阻止默认行为
        event.preventDefault()
        event.stopPropagation()

        return true
      }
    }

    return false
  }

  // ========== 生命周期 ==========

  /**
   * 添加全局键盘监听器
   */
  const setupGlobalListeners = () => {
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', handleKeyDown)
    }
  }

  /**
   * 移除全局键盘监听器
   */
  const cleanupGlobalListeners = () => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }

  // ========== 初始化 ==========

  onMounted(() => {
    setupGlobalListeners()
  })

  onBeforeUnmount(() => {
    cleanupGlobalListeners()
  })

  return {
    // 方法
    isShortcutMatch,
    setupGlobalListeners,
    cleanupGlobalListeners
  }
}

/**
 * 创建默认的快捷键处理器
 * @param {object} customHandlers - 自定义处理器
 * @returns {object} 快捷键处理器映射
 */
export function createDefaultHandlers(customHandlers = {}) {
  const defaultHandlers = {
    [KEYBOARD_SHORTCUTS.SEND_MESSAGE]: null,
    [KEYBOARD_SHORTCUTS.PAUSE_ANALYSIS]: null,
    [KEYBOARD_SHORTCUTS.TOGGLE_VIZ_PANEL]: null,
    [KEYBOARD_SHORTCUTS.NEW_SESSION]: null,
    [KEYBOARD_SHORTCUTS.OPEN_SESSION_MANAGER]: null
  }

  return { ...defaultHandlers, ...customHandlers }
}
