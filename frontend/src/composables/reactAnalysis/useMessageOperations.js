/**
 * 消息操作 Composable
 * 处理消息的选择、加载更多、源查看等操作
 */
import { ref, computed } from 'vue'

export function useMessageOperations(store) {
  // ========== 状态 ==========
  const selectedMessageId = ref(null)

  // ========== 计算属性 ==========

  /**
   * 当前消息列表
   */
  const messages = computed(() => store.currentState.messages || [])

  /**
   * 选中的消息
   */
  const selectedMessage = computed(() => {
    if (!selectedMessageId.value) return null
    return messages.value.find(msg => msg.id === selectedMessageId.value)
  })

  /**
   * 选中的消息的源信息
   */
  const selectedMessageSources = computed(() => {
    return selectedMessage.value?.sources || null
  })

  /**
   * 是否有更多消息
   */
  const hasMoreMessages = computed(() => {
    return store.currentState.pagination?.hasMoreMessages || false
  })

  /**
   * 总消息数
   */
  const totalMessageCount = computed(() => {
    return store.currentState.pagination?.totalMessageCount || 0
  })

  /**
   * 是否正在加载更多
   */
  const loadingMore = computed(() => {
    return store.currentState.pagination?.loadingMore || false
  })

  // ========== 方法 ==========

  /**
   * 选择消息
   * @param {string} messageId - 消息ID
   */
  const selectMessage = (messageId) => {
    if (selectedMessageId.value === messageId) {
      // 取消选择
      selectedMessageId.value = null
    } else {
      selectedMessageId.value = messageId
    }
  }

  /**
   * 取消选择消息
   */
  const deselectMessage = () => {
    selectedMessageId.value = null
  }

  /**
   * 加载更多消息
   */
  const handleLoadMore = async () => {
    if (!hasMoreMessages.value || loadingMore.value) return

    await store.loadMoreMessages()
  }

  /**
   * 跳转到消息
   * @param {string} messageId - 消息ID
   */
  const scrollToMessage = (messageId) => {
    selectedMessageId.value = messageId

    // 滚动到消息位置
    nextTick(() => {
      const element = document.querySelector(`[data-message-id="${messageId}"]`)
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    })
  }

  /**
   * 复制消息内容
   * @param {string} messageId - 消息ID
   */
  const copyMessageContent = async (messageId) => {
    const message = messages.value.find(msg => msg.id === messageId)
    if (!message) return false

    try {
      let content = ''

      if (message.type === 'user') {
        content = message.content
      } else if (message.type === 'assistant') {
        content = message.content || ''
      } else if (message.type === 'observation' && message.data?.observation) {
        const obs = message.data.observation
        content = obs.summary || JSON.stringify(obs.data || {})
      }

      if (content) {
        await navigator.clipboard.writeText(content)
        return true
      }

      return false
    } catch (error) {
      console.error('Failed to copy message:', error)
      return false
    }
  }

  /**
   * 删除消息
   * @param {string} messageId - 消息ID
   */
  const deleteMessage = async (messageId) => {
    if (!confirm('确定要删除此消息吗？')) return false

    try {
      await store.deleteMessage(messageId)
      return true
    } catch (error) {
      console.error('Failed to delete message:', error)
      return false
    }
  }

  /**
   * 重新发送消息
   * @param {string} messageId - 消息ID
   */
  const resendMessage = async (messageId) => {
    const message = messages.value.find(msg => msg.id === messageId)
    if (!message || message.type !== 'user') return false

    try {
      await store.analyze(message.content, {
        sessionId: store.currentState.sessionId
      })
      return true
    } catch (error) {
      console.error('Failed to resend message:', error)
      return false
    }
  }

  /**
   * 导出消息为文本
   * @param {string} messageId - 消息ID
   */
  const exportMessageAsText = (messageId) => {
    const message = messages.value.find(msg => msg.id === messageId)
    if (!message) return false

    try {
      let content = ''

      if (message.type === 'user') {
        content = `[用户] ${message.content}`
      } else if (message.type === 'assistant') {
        content = `[助手] ${message.content || ''}`
      } else if (message.type === 'observation') {
        const obs = message.data?.observation
        content = `[工具调用] ${obs?.summary || ''}`
      }

      if (content) {
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `message_${messageId.substring(0, 8)}.txt`
        link.click()
        URL.revokeObjectURL(url)
        return true
      }

      return false
    } catch (error) {
      console.error('Failed to export message:', error)
      return false
    }
  }

  /**
   * 搜索消息
   * @param {string} keyword - 搜索关键词
   * @returns {array} 匹配的消息列表
   */
  const searchMessages = (keyword) => {
    if (!keyword) return []

    const lowerKeyword = keyword.toLowerCase()
    return messages.value.filter(msg => {
      if (msg.type === 'user' || msg.type === 'assistant') {
        return msg.content?.toLowerCase().includes(lowerKeyword)
      } else if (msg.type === 'observation') {
        const summary = msg.data?.observation?.summary || ''
        return summary.toLowerCase().includes(lowerKeyword)
      }
      return false
    })
  }

  /**
   * 获取消息统计信息
   * @returns {object} 统计信息
   */
  const getMessageStats = () => {
    const stats = {
      total: messages.value.length,
      user: 0,
      assistant: 0,
      observation: 0,
      toolCalls: 0,
      errors: 0
    }

    for (const msg of messages.value) {
      stats[msg.type] = (stats[msg.type] || 0) + 1

      if (msg.type === 'observation') {
        stats.toolCalls++
        if (msg.data?.observation?.status === 'error') {
          stats.errors++
        }
      }
    }

    return stats
  }

  return {
    // 状态
    selectedMessageId,

    // 计算属性
    messages,
    selectedMessage,
    selectedMessageSources,
    hasMoreMessages,
    totalMessageCount,
    loadingMore,

    // 方法
    selectMessage,
    deselectMessage,
    handleLoadMore,
    scrollToMessage,
    copyMessageContent,
    deleteMessage,
    resendMessage,
    exportMessageAsText,
    searchMessages,
    getMessageStats
  }
}
