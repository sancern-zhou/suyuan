/**
 * 时区处理工具函数
 *
 * 后端数据库使用UTC时间存储，前端需要转换为北京时间（UTC+8）显示
 */

/**
 * 将数据库的UTC时间转换为北京时间
 * @param {string|Date} timestamp - UTC时间戳
 * @returns {Date} 北京时间的Date对象
 */
export function toBeijingTime(timestamp) {
  if (!timestamp) return null
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp
  // UTC时间 + 8小时 = 北京时间
  return new Date(date.getTime() + 8 * 60 * 60 * 1000)
}

/**
 * 格式化相对时间（刚刚、X分钟前等）
 * @param {string|Date} timestamp - UTC时间戳
 * @returns {string} 格式化后的时间字符串
 */
export function formatRelativeTime(timestamp) {
  if (!timestamp) return '-'

  const beijingDate = toBeijingTime(timestamp)
  if (!beijingDate) return '-'

  const now = new Date()
  const diff = now - beijingDate

  // 小于1分钟
  if (diff < 60000) {
    return '刚刚'
  }
  // 小于1小时
  if (diff < 3600000) {
    const minutes = Math.floor(diff / 60000)
    return `${minutes}分钟前`
  }
  // 小于1天
  if (diff < 86400000) {
    const hours = Math.floor(diff / 3600000)
    return `${hours}小时前`
  }
  // 小于7天
  const days = Math.floor(diff / 86400000)
  if (days < 7) {
    return `${days}天前`
  }

  // 超过7天显示日期
  return beijingDate.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

/**
 * 格式化完整时间
 * @param {string|Date} timestamp - UTC时间戳
 * @returns {string} 格式化后的完整时间字符串
 */
export function formatFullTime(timestamp) {
  if (!timestamp) return '-'

  const beijingDate = toBeijingTime(timestamp)
  if (!beijingDate) return '-'

  return beijingDate.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}

/**
 * 格式化时间（时分秒）
 * @param {string|Date} timestamp - UTC时间戳
 * @returns {string} 格式化后的时间字符串
 */
export function formatTime(timestamp) {
  if (!timestamp) return ''

  const beijingDate = toBeijingTime(timestamp)
  if (!beijingDate) return ''

  return beijingDate.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}
