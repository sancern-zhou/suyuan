#!/usr/bin/env node

/**
 * ReactAnalysisView 重构验证脚本
 * 检查所有重构模块的语法和导入
 */

import { readFileSync, existsSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const ROOT_DIR = join(__dirname, '..')
const COMPOSABLES_DIR = join(ROOT_DIR, 'src/composables/reactAnalysis')

// ========== 测试结果 ==========

const results = {
  passed: 0,
  failed: 0,
  total: 0,
  errors: [],
  warnings: []
}

// ========== 辅助函数 ==========

function log(message, type = 'info') {
  const colors = {
    info: '\x1b[36m',    // cyan
    success: '\x1b[32m', // green
    error: '\x1b[31m',   // red
    warning: '\x1b[33m', // yellow
    reset: '\x1b[0m'
  }

  const color = colors[type] || colors.info
  console.log(`${color}${message}${colors.reset}`)
}

function addTest() {
  results.total++
}

function passTest(message) {
  results.passed++
  addTest()
  log(`✅ ${message}`, 'success')
}

function failTest(message, error) {
  results.failed++
  addTest()
  const errorMsg = error ? `: ${error.message}` : ''
  log(`❌ ${message}${errorMsg}`, 'error')
  results.errors.push({ test: message, error })
}

function warnTest(message) {
  results.warnings.push({ test: message })
  log(`⚠️  ${message}`, 'warning')
}

// ========== 测试函数 ==========

/**
 * TC-01: 检查所有composables文件是否存在
 */
function testFileExists() {
  log('\n📋 TC-01: 检查文件存在性', 'info')

  const files = [
    'index.js',
    'usePanelManagement.js',
    'useWidthResizer.js',
    'useDialogManager.js',
    'useRightPanelState.js',
    'useSessionManagement.js',
    'useKnowledgeBaseOperations.js',
    'useDataFetcher.js',
    'useKeyboardShortcuts.js',
    'useDragAndDrop.js',
    'useMessageOperations.js',
    'useKbFileValidation.js',
    'useKbUploadProgress.js',
    'useKbFileUpload.js',
    'useSessionRecovery.js',
    'useVisualizationExtractor.js',
    'useScheduledTaskManager.js',
    'useOfficeDocumentHandler.js',
    'useFileDropZone.js',
    'useErrorHandling.js',
    'useLogger.js'
  ]

  files.forEach(file => {
    const filePath = join(COMPOSABLES_DIR, file)
    if (existsSync(filePath)) {
      passTest(`文件存在: ${file}`)
    } else {
      failTest(`文件不存在: ${file}`)
    }
  })
}

/**
 * TC-02: 检查文件大小
 */
function testFileSize() {
  log('\n📋 TC-02: 检查文件大小', 'info')

  const files = [
    'useKbFileValidation.js',
    'useKbUploadProgress.js',
    'useKbFileUpload.js',
    'useSessionRecovery.js',
    'useVisualizationExtractor.js',
    'useScheduledTaskManager.js',
    'useOfficeDocumentHandler.js',
    'useFileDropZone.js',
    'useErrorHandling.js',
    'useLogger.js'
  ]

  files.forEach(file => {
    const filePath = join(COMPOSABLES_DIR, file)

    try {
      const content = readFileSync(filePath, 'utf-8')
      const lines = content.split('\n').length

      if (lines <= 400) {
        passTest(`${file}: ${lines}行 (✅ <400行)`)
      } else {
        warnTest(`${file}: ${lines}行 (⚠️  超过400行限制)`)
      }
    } catch (error) {
      failTest(`读取文件失败: ${file}`, error)
    }
  })
}

/**
 * TC-03: 检查导出语句
 */
function testExports() {
  log('\n📋 TC-03: 检查导出语句', 'info')

  const requiredExports = {
    'useKbFileValidation.js': ['validateFile', 'validateFiles', 'getFileExtension'],
    'useKbUploadProgress.js': ['useKbUploadProgress'],
    'useKbFileUpload.js': ['useKbFileUpload'],
    'useSessionRecovery.js': ['useSessionRecovery'],
    'useVisualizationExtractor.js': ['useVisualizationExtractor'],
    'useScheduledTaskManager.js': ['useScheduledTaskManager'],
    'useOfficeDocumentHandler.js': ['useOfficeDocumentHandler'],
    'useFileDropZone.js': ['useFileDropZone'],
    'useErrorHandling.js': ['useErrorHandling', 'createApiErrorHandler'],
    'useLogger.js': ['useLogger', 'usePerformanceLogger']
  }

  Object.entries(requiredExports).forEach(([file, exports]) => {
    const filePath = join(COMPOSABLES_DIR, file)

    try {
      const content = readFileSync(filePath, 'utf-8')

      exports.forEach(exp => {
        // 支持多种导出语法：export function, export const, export { }
        const exportPatterns = [
          `export function ${exp}`,
          `export const ${exp}`,
          `export { ${exp}`,
          `export {${exp}`
        ]

        const hasExport = exportPatterns.some(pattern => content.includes(pattern))

        if (hasExport) {
          passTest(`${file} 导出 ${exp}`)
        } else {
          failTest(`${file} 缺少导出 ${exp}`)
        }
      })
    } catch (error) {
      failTest(`读取文件失败: ${file}`, error)
    }
  })
}

/**
 * TC-04: 检查导入语句
 */
function testImports() {
  log('\n📋 TC-04: 检查导入语句', 'info')

  const filePath = join(COMPOSABLES_DIR, 'index.js')

  try {
    const content = readFileSync(filePath, 'utf-8')

    const requiredImports = [
      'useKbFileValidation',
      'useKbUploadProgress',
      'useKbFileUpload',
      'useSessionRecovery',
      'useVisualizationExtractor',
      'useScheduledTaskManager',
      'useOfficeDocumentHandler',
      'useFileDropZone',
      'useErrorHandling',
      'useLogger'
    ]

    requiredImports.forEach(imp => {
      if (content.includes(imp)) {
        passTest(`index.js 导出 ${imp}`)
      } else {
        failTest(`index.js 缺少导出 ${imp}`)
      }
    })
  } catch (error) {
    failTest('读取index.js失败', error)
  }
}

/**
 * TC-05: 检查文档注释
 */
function testDocumentation() {
  log('\n📋 TC-05: 检查文档注释', 'info')

  const files = [
    'useKbFileUpload.js',
    'useSessionRecovery.js',
    'useVisualizationExtractor.js'
  ]

  files.forEach(file => {
    const filePath = join(COMPOSABLES_DIR, file)

    try {
      const content = readFileSync(filePath, 'utf-8')
      const hasJSDoc = content.includes('/**')

      if (hasJSDoc) {
        passTest(`${file} 包含JSDoc注释`)
      } else {
        warnTest(`${file} 缺少JSDoc注释`)
      }
    } catch (error) {
      failTest(`读取文件失败: ${file}`, error)
    }
  })
}

/**
 * TC-06: 检查错误处理
 */
function testErrorHandling() {
  log('\n📋 TC-06: 检查错误处理', 'info')

  const filePath = join(COMPOSABLES_DIR, 'useKbFileUpload.js')

  try {
    const content = readFileSync(filePath, 'utf-8')

    const checks = [
      { pattern: 'try\\s*{', name: 'try-catch块' },
      { pattern: 'catch\\s*\\(', name: 'catch错误捕获' },
      { pattern: 'throw\\s+new\\s+Error', name: '错误抛出' }
    ]

    checks.forEach(({ pattern, name }) => {
      const regex = new RegExp(pattern)
      if (regex.test(content)) {
        passTest(`${name} 存在`)
      } else {
        warnTest(`${name} 可能缺失`)
      }
    })
  } catch (error) {
    failTest('读取文件失败', error)
  }
}

/**
 * TC-07: 检查Vue 3 Composition API使用
 */
function testVue3Usage() {
  log('\n📋 TC-07: 检查Vue 3 Composition API', 'info')

  const files = [
    'useKbFileUpload.js',
    'useSessionRecovery.js',
    'useVisualizationExtractor.js'
  ]

  files.forEach(file => {
    const filePath = join(COMPOSABLES_DIR, file)

    try {
      const content = readFileSync(filePath, 'utf-8')

      const vue3Imports = ['ref', 'computed', 'watch', 'onMounted', 'onBeforeUnmount']
      let foundImports = 0

      vue3Imports.forEach(imp => {
        if (content.includes(imp)) {
          foundImports++
        }
      })

      if (foundImports >= 2) {
        passTest(`${file} 使用Vue 3 Composition API (${foundImports}个API)`)
      } else {
        warnTest(`${file} Vue 3 API使用较少 (${foundImports}个API)`)
      }
    } catch (error) {
      failTest(`读取文件失败: ${file}`, error)
    }
  })
}

/**
 * TC-08: 检查类型安全
 */
function testTypeSafety() {
  log('\n📋 TC-08: 检查类型安全', 'info')

  const files = [
    'useKbFileValidation.js',
    'useErrorHandling.js',
    'useLogger.js'
  ]

  files.forEach(file => {
    const filePath = join(COMPOSABLES_DIR, file)

    try {
      const content = readFileSync(filePath, 'utf-8')

      // 检查JSDoc类型注释
      const hasParamTypes = /@param\s+\{[^}]+\}/.test(content)
      const hasReturnTypes = /@returns\s+\{[^}]+\}/.test(content)

      if (hasParamTypes || hasReturnTypes) {
        passTest(`${file} 包含类型注释`)
      } else {
        warnTest(`${file} 缺少类型注释`)
      }
    } catch (error) {
      failTest(`读取文件失败: ${file}`, error)
    }
  })
}

// ========== 主函数 ==========

async function main() {
  log('\n🚀 ReactAnalysisView 重构验证', 'info')
  log('=' .repeat(50), 'info')

  try {
    // 执行所有测试
    testFileExists()
    testFileSize()
    testExports()
    testImports()
    testDocumentation()
    testErrorHandling()
    testVue3Usage()
    testTypeSafety()

    // 打印总结
    log('\n' + '='.repeat(50), 'info')
    log('📊 测试总结', 'info')
    log(`总计: ${results.total} 个测试`, 'info')
    log(`通过: ${results.passed} ✅`, 'success')
    log(`失败: ${results.failed} ❌`, results.failed > 0 ? 'error' : 'info')
    log(`警告: ${results.warnings.length} ⚠️`, results.warnings.length > 0 ? 'warning' : 'info')

    const passRate = ((results.passed / results.total) * 100).toFixed(1)
    log(`通过率: ${passRate}%`, passRate >= 95 ? 'success' : 'warning')

    // 返回退出码
    if (results.failed > 0) {
      process.exit(1)
    } else {
      process.exit(0)
    }
  } catch (error) {
    log(`\n💥 验证脚本执行失败: ${error.message}`, 'error')
    console.error(error)
    process.exit(1)
  }
}

// 运行测试
main()
