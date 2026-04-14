/**
 * 验证工具函数
 * 提供各种数据验证功能
 */

/**
 * 验证邮箱地址
 * @param {string} email - 邮箱地址
 * @returns {boolean} 是否有效
 */
export function isValidEmail(email) {
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return re.test(email)
}

/**
 * 验证URL
 * @param {string} url - URL字符串
 * @returns {boolean} 是否有效
 */
export function isValidUrl(url) {
  try {
    new URL(url)
    return true
  } catch {
    return false
  }
}

/**
 * 验证文件类型
 * @param {File} file - 文件对象
 * @param {string[]} allowedTypes - 允许的类型列表
 * @returns {boolean} 是否有效
 */
export function isValidFileType(file, allowedTypes) {
  if (!file || !file.type) return false
  return allowedTypes.some(type => file.type.startsWith(type))
}

/**
 * 验证文件大小
 * @param {File} file - 文件对象
 * @param {number} maxSize - 最大大小（字节）
 * @returns {boolean} 是否有效
 */
export function isValidFileSize(file, maxSize) {
  if (!file) return false
  return file.size <= maxSize
}

/**
 * 验证知识库名称
 * @param {string} name - 知识库名称
 * @returns {object} 验证结果 {valid: boolean, message: string}
 */
export function validateKbName(name) {
  if (!name || name.trim() === '') {
    return { valid: false, message: '知识库名称不能为空' }
  }
  if (name.length > 100) {
    return { valid: false, message: '知识库名称不能超过100个字符' }
  }
  if (!/^[\u4e00-\u9fa5a-zA-Z0-9_\-\s]+$/.test(name)) {
    return { valid: false, message: '知识库名称只能包含中文、字母、数字、下划线和连字符' }
  }
  return { valid: true, message: '' }
}

/**
 * 验证知识库描述
 * @param {string} description - 知识库描述
 * @returns {object} 验证结果
 */
export function validateKbDescription(description) {
  if (description && description.length > 500) {
    return { valid: false, message: '知识库描述不能超过500个字符' }
  }
  return { valid: true, message: '' }
}

/**
 * 验证分块大小
 * @param {number} size - 分块大小
 * @returns {object} 验证结果
 */
export function validateChunkSize(size) {
  if (!size || size < 64 || size > 2048) {
    return { valid: false, message: '分块大小必须在64-2048之间' }
  }
  return { valid: true, message: '' }
}

/**
 * 验证分块重叠
 * @param {number} overlap - 分块重叠
 * @param {number} chunkSize - 分块大小
 * @returns {object} 验证结果
 */
export function validateChunkOverlap(overlap, chunkSize) {
  if (overlap < 0 || overlap > 512) {
    return { valid: false, message: '分块重叠必须在0-512之间' }
  }
  if (overlap >= chunkSize) {
    return { valid: false, message: '分块重叠必须小于分块大小' }
  }
  return { valid: true, message: '' }
}

/**
 * 验证日期范围
 * @param {string} startDate - 开始日期
 * @param {string} endDate - 结束日期
 * @returns {object} 验证结果
 */
export function validateDateRange(startDate, endDate) {
  if (!startDate || !endDate) {
    return { valid: false, message: '开始日期和结束日期不能为空' }
  }
  const start = new Date(startDate)
  const end = new Date(endDate)
  if (start > end) {
    return { valid: false, message: '开始日期不能晚于结束日期' }
  }
  return { valid: true, message: '' }
}

/**
 * 验证JSON字符串
 * @param {string} str - JSON字符串
 * @returns {boolean} 是否有效
 */
export function isValidJson(str) {
  try {
    JSON.parse(str)
    return true
  } catch {
    return false
  }
}

/**
 * 验证数字范围
 * @param {number} value - 数值
 * @param {number} min - 最小值
 * @param {number} max - 最大值
 * @returns {boolean} 是否有效
 */
export function isInRange(value, min, max) {
  return value >= min && value <= max
}

/**
 * 验证必填字段
 * @param {any} value - 字段值
 * @returns {boolean} 是否有效
 */
export function isRequired(value) {
  if (value === null || value === undefined) return false
  if (typeof value === 'string' && value.trim() === '') return false
  if (Array.isArray(value) && value.length === 0) return false
  return true
}

/**
 * 验证字符串长度
 * @param {string} str - 字符串
 * @param {number} minLength - 最小长度
 * @param {number} maxLength - 最大长度
 * @returns {boolean} 是否有效
 */
export function isValidLength(str, minLength = 0, maxLength = Infinity) {
  if (!str) return minLength === 0
  return str.length >= minLength && str.length <= maxLength
}

/**
 * 验证正则表达式
 * @param {string} str - 字符串
 * @param {RegExp} pattern - 正则表达式
 * @returns {boolean} 是否匹配
 */
export function matchesPattern(str, pattern) {
  return pattern.test(str)
}

/**
 * 综合验证器
 * @param {object} data - 数据对象
 * @param {object} rules - 验证规则
 * @returns {object} 验证结果 {valid: boolean, errors: object}
 */
export function validate(data, rules) {
  const errors = {}
  let valid = true

  for (const field in rules) {
    const value = data[field]
    const fieldRules = rules[field]

    for (const rule of fieldRules) {
      const result = rule(value, data)
      if (!result.valid) {
        errors[field] = result.message
        valid = false
        break
      }
    }
  }

  return { valid, errors }
}
