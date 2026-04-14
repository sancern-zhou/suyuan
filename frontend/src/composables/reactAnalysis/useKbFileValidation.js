/**
 * 知识库文件验证 Composable
 * 处理文件类型、大小等验证逻辑
 */
import { FILE_SIZE_LIMITS, ALLOWED_FILE_TYPES } from '@/utils/constants'

/**
 * 验证单个文件
 * @param {File} file - 文件对象
 * @param {object} options - 验证选项
 * @returns {object} 验证结果
 */
export function validateFile(file, options = {}) {
  const {
    maxSize = FILE_SIZE_LIMITS.LARGE,
    allowedTypes = null
  } = options

  const errors = []

  // 检查文件大小
  if (file.size > maxSize) {
    errors.push(`文件"${file.name}"超过大小限制`)
  }

  // 检查文件类型
  if (allowedTypes) {
    const allAllowedTypes = Object.values(ALLOWED_FILE_TYPES).flat()
    const isAllowed = allAllowedTypes.includes(file.type)

    if (!isAllowed) {
      errors.push(`文件"${file.name}"的类型不被支持`)
    }
  }

  return {
    valid: errors.length === 0,
    errors
  }
}

/**
 * 验证文件列表
 * @param {FileList|Array} files - 文件列表
 * @param {object} options - 验证选项
 * @returns {object} 验证结果
 */
export function validateFiles(files, options = {}) {
  const fileArray = Array.from(files)
  const allErrors = []

  for (const file of fileArray) {
    const result = validateFile(file, options)
    allErrors.push(...result.errors)
  }

  return {
    valid: allErrors.length === 0,
    errors: allErrors
  }
}

/**
 * 获取文件扩展名
 * @param {string} filename - 文件名
 * @returns {string} 扩展名
 */
export function getFileExtension(filename) {
  const parts = filename.split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
}

/**
 * 检查是否为支持的文档类型
 * @param {string} filename - 文件名
 * @returns {boolean}
 */
export function isSupportedDocument(filename) {
  const ext = getFileExtension(filename)
  const supportedExts = ['pdf', 'doc', 'docx', 'txt', 'md']
  return supportedExts.includes(ext)
}

/**
 * 检查是否为支持的图片类型
 * @param {string} filename - 文件名
 * @returns {boolean}
 */
export function isSupportedImage(filename) {
  const ext = getFileExtension(filename)
  const supportedExts = ['jpg', 'jpeg', 'png', 'gif', 'webp']
  return supportedExts.includes(ext)
}

/**
 * 检查是否为支持的表格类型
 * @param {string} filename - 文件名
 * @returns {boolean}
 */
export function isSupportedSpreadsheet(filename) {
  const ext = getFileExtension(filename)
  const supportedExts = ['xls', 'xlsx']
  return supportedExts.includes(ext)
}

/**
 * 获取文件类型分类
 * @param {File} file - 文件对象
 * @returns {string} 类型分类
 */
export function getFileCategory(file) {
  const filename = file.name || file.path || ''

  if (isSupportedImage(filename)) return 'image'
  if (isSupportedSpreadsheet(filename)) return 'spreadsheet'
  if (isSupportedDocument(filename)) return 'document'

  return 'unknown'
}
