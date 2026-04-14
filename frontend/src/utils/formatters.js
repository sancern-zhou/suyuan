/**
 * 格式化工具函数
 * 提供各种数据格式化功能
 */

/**
 * 格式化文件大小
 * @param {number} bytes - 文件大小（字节）
 * @param {number} decimals - 小数位数，默认2
 * @returns {string} 格式化后的文件大小
 */
export function formatFileSize(bytes, decimals = 2) {
  if (bytes === 0) return '0 Bytes'

  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']

  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
}

/**
 * 格式化时间戳
 * @param {number|string|Date} timestamp - 时间戳
 * @param {string} format - 格式类型：'full' | 'date' | 'time' | 'relative'
 * @returns {string} 格式化后的时间
 */
export function formatTimestamp(timestamp, format = 'full') {
  const date = new Date(timestamp)

  if (isNaN(date.getTime())) {
    return 'Invalid Date'
  }

  switch (format) {
    case 'date':
      return date.toLocaleDateString('zh-CN')
    case 'time':
      return date.toLocaleTimeString('zh-CN')
    case 'relative':
      return formatRelativeTime(date)
    case 'full':
    default:
      return date.toLocaleString('zh-CN')
  }
}

/**
 * 格式化相对时间
 * @param {Date} date - 日期对象
 * @returns {string} 相对时间字符串
 */
function formatRelativeTime(date) {
  const now = new Date()
  const diff = now - date
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 7) {
    return date.toLocaleDateString('zh-CN')
  } else if (days > 0) {
    return `${days}天前`
  } else if (hours > 0) {
    return `${hours}小时前`
  } else if (minutes > 0) {
    return `${minutes}分钟前`
  } else {
    return '刚刚'
  }
}

/**
 * 格式化日期为ISO字符串
 * @param {Date} date - 日期对象
 * @returns {string} ISO格式日期字符串
 */
export function formatISODate(date) {
  const d = new Date(date)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * 格式化ID（截取前8位）
 * @param {string} id - 完整ID
 * @param {number} length - 显示长度，默认8
 * @returns {string} 截取后的ID
 */
export function formatId(id, length = 8) {
  if (!id) return ''
  return id.length > length ? id.substring(0, length) : id
}

/**
 * 格式化百分比
 * @param {number} value - 数值
 * @param {number} total - 总数
 * @param {number} decimals - 小数位数，默认1
 * @returns {string} 百分比字符串
 */
export function formatPercentage(value, total, decimals = 1) {
  if (total === 0) return '0%'
  const percentage = (value / total) * 100
  return percentage.toFixed(decimals) + '%'
}

/**
 * 格式化数字（添加千位分隔符）
 * @param {number} num - 数字
 * @returns {string} 格式化后的数字
 */
export function formatNumber(num) {
  if (num === null || num === undefined) return ''
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

/**
 * 格式化持续时间
 * @param {number} seconds - 秒数
 * @returns {string} 格式化后的持续时间
 */
export function formatDuration(seconds) {
  if (seconds < 60) {
    return `${Math.round(seconds)}秒`
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const secs = Math.round(seconds % 60)
    return secs > 0 ? `${minutes}分${secs}秒` : `${minutes}分钟`
  } else {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return minutes > 0 ? `${hours}小时${minutes}分钟` : `${hours}小时`
  }
}

/**
 * 格式化知识库类型
 * @param {string} type - 类型：'private' | 'public'
 * @returns {string} 中文类型名称
 */
export function formatKbType(type) {
  const typeMap = {
    private: '个人知识库',
    public: '公共知识库'
  }
  return typeMap[type] || type
}

/**
 * 格式化分块策略
 * @param {string} strategy - 策略名称
 * @returns {string} 中文策略名称
 */
export function formatChunkStrategy(strategy) {
  const strategyMap = {
    llm: 'LLM智能分块',
    sentence: '句子分块',
    semantic: '语义分块',
    markdown: 'Markdown分块',
    hybrid: '混合分块'
  }
  return strategyMap[strategy] || strategy
}

/**
 * 格式化分块类型
 * @param {string} type - 类型名称
 * @returns {string} 中文类型名称
 */
export function formatChunkType(type) {
  const typeMap = {
    text: '文本',
    code: '代码',
    table: '表格',
    image: '图片',
    metadata: '元数据'
  }
  return typeMap[type] || type
}

/**
 * 截断文本
 * @param {string} text - 原始文本
 * @param {number} maxLength - 最大长度
 * @param {string} suffix - 后缀，默认'...'
 * @returns {string} 截断后的文本
 */
export function truncateText(text, maxLength, suffix = '...') {
  if (!text || text.length <= maxLength) return text
  return text.substring(0, maxLength) + suffix
}

/**
 * 高亮关键词
 * @param {string} text - 原始文本
 * @param {string} keyword - 关键词
 * @returns {string} 高亮后的HTML字符串
 */
export function highlightKeyword(text, keyword) {
  if (!text || !keyword) return text
  const regex = new RegExp(`(${keyword})`, 'gi')
  return text.replace(regex, '<mark>$1</mark>')
}
