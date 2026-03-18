/**
 * 图表截图缓存管理器
 *
 * 功能：
 * 1. 统一管理所有图表的截图
 * 2. 支持宽幅截图，自动移除滑动轴
 * 3. LRU缓存策略，自动清理
 *
 * 【注意】图表匹配功能（findMatching/findAllMatching）已废弃
 * 新方案：后端直接生成图片URL，前端无需匹配占位符
 */

import { screenshotConfig } from './chartConfig'

/**
 * 图表记录类
 */
class ChartRecord {
  constructor(options) {
    this.id = options.id
    this.type = options.type
    this.title = options.title || ''
    this.instance = options.instance || null
    this.meta = options.meta || {}
    this.registeredAt = Date.now()
    this.captured = false
    this.screenshot = null
  }
}

/**
 * 截图缓存类
 */
class ScreenshotCache {
  constructor(data) {
    this.id = data.id
    this.type = data.type
    this.chartType = data.chartType || data.type
    this.title = data.title || ''
    this.dataURL = data.dataURL || ''
    this.width = data.width || 0
    this.height = data.height || 0
    this.mode = data.mode || 'standard'
    this.capturedAt = data.capturedAt || Date.now()
    this.meta = data.meta || {}
  }

  /**
   * 获取有效的Base64数据
   */
  getValidDataURL() {
    if (!this.dataURL) return null
    if (this.dataURL.startsWith('data:')) return this.dataURL
    return `data:image/png;base64,${this.dataURL}`
  }

  /**
   * 检查是否过期
   */
  isExpired(maxAge = screenshotConfig.cache.maxAge) {
    return Date.now() - this.capturedAt > maxAge
  }
}

/**
 * 图表截图缓存管理器
 */
class ChartScreenshotManager {
  constructor() {
    // 图表记录 Map<chartId, ChartRecord>
    this.charts = new Map()

    // 截图缓存 Map<chartId, ScreenshotCache>
    this.screenshots = new Map()

    // 正在进行的截图操作 Map<chartId, Promise>
    this.pendingCaptures = new Map()

    // 截图状态
    this.isCapturing = false
    this.lastCaptureTime = 0
    this.captureCount = 0

    // 定时清理定时器
    this.cleanupTimer = null

    // 启动定时清理
    this.startCleanupTimer()

    console.log('[ChartScreenshotManager] 截图管理器已初始化')
  }

  // ========== 图表注册 ==========

  /**
   * 注册图表实例
   * @param {Object} options - 图表选项
   * @param {string} options.id - 图表唯一ID（必填）
   * @param {string} options.type - 图表类型
   * @param {string} options.title - 图表标题
   * @param {Object} options.instance - ECharts实例
   * @param {Object} options.meta - 额外元数据
   * @returns {string} 图表ID
   */
  registerChart(options) {
    const { id, type, title, instance, meta = {} } = options

    if (!id) {
      console.warn('[ChartScreenshotManager] 注册失败: 图表缺少ID')
      return null
    }

    const record = new ChartRecord({ id, type, title, instance, meta })

    this.charts.set(id, record)
    console.log(`[ChartScreenshotManager] 注册图表: ${id} (${type || 'unknown'})`)

    // 如果已有截图，恢复关联
    if (this.screenshots.has(id)) {
      record.screenshot = this.screenshots.get(id)
      record.captured = true
    }

    return id
  }

  /**
   * 注销图表
   * @param {string} chartId - 图表ID
   */
  unregisterChart(chartId) {
    if (!chartId) return

    this.charts.delete(chartId)
    this.pendingCaptures.delete(chartId)
    console.log(`[ChartScreenshotManager] 注销图表: ${chartId}`)
  }

  /**
   * 更新图表信息
   * @param {string} chartId - 图表ID
   * @param {Object} updates - 更新内容
   */
  updateChart(chartId, updates) {
    const record = this.charts.get(chartId)
    if (record) {
      Object.assign(record, updates)
      console.log(`[ChartScreenshotManager] 更新图表: ${chartId}`)
    }
  }

  /**
   * 批量注册图表
   * @param {Array} chartList - 图表列表
   */
  registerCharts(chartList) {
    const results = []
    for (const chart of chartList) {
      const id = this.registerChart(chart)
      if (id) results.push(id)
    }
    console.log(`[ChartScreenshotManager] 批量注册图表: ${results.length}个`)
    return results
  }

  /**
   * 批量注销图表
   * @param {Array} chartIds - 图表ID列表
   */
  unregisterCharts(chartIds) {
    for (const id of chartIds) {
      this.unregisterChart(id)
    }
  }

  // ========== 截图核心 ==========

  /**
   * 批量截图（主方法）
   * @param {Object} options - 截图选项
   * @param {boolean} options.excludeMaps - 排除地图类型
   * @param {Array} options.excludeTypes - 排除的图表类型
   * @param {Array} options.onlyTypes - 只截取指定类型
   * @param {boolean} options.waitForRender - 等待图表渲染
   * @param {number} options.timeout - 超时时间（毫秒）
   * @param {string} options.mode - 截图模式 ('auto', 'wide', 'standard', 'thumbnail', 'original')
   * @returns {Object} 截图结果 { success, failed, screenshots }
   */
  async captureAll(options = {}) {
    const {
      excludeMaps = true,
      excludeTypes = [],
      onlyTypes = [],
      waitForRender = true,
      timeout = screenshotConfig.waitRenderTimeout,
      mode = 'auto'
    } = options

    const startTime = Date.now()
    console.log(`[ChartScreenshotManager] 开始批量截图...`, { mode, excludeMaps, onlyTypes })

    // 等待图表渲染
    if (waitForRender) {
      await this.waitForCharts(timeout)
    }

    const results = {}
    let successCount = 0
    let failCount = 0
    let skipCount = 0

    for (const [chartId, record] of this.charts) {
      // 过滤条件
      if (excludeMaps && (record.type === 'map' || record.type === 'upwind_enterprise_map')) {
        skipCount++
        continue
      }
      if (excludeTypes.length > 0 && excludeTypes.includes(record.type)) {
        skipCount++
        continue
      }
      if (onlyTypes.length > 0 && !onlyTypes.includes(record.type)) {
        skipCount++
        continue
      }

      // 检查是否正在截图
      if (this.pendingCaptures.has(chartId)) {
        console.log(`[ChartScreenshotManager] 跳过正在截图的图表: ${chartId}`)
        continue
      }

      try {
        // 确定截图模式
        const chartMode = this.getChartMode(record.type, mode)

        // 截图
        const screenshot = await this.captureOne(record, chartMode)

        if (screenshot) {
          this.screenshots.set(chartId, screenshot)
          record.screenshot = screenshot
          record.captured = true
          results[chartId] = screenshot
          successCount++
        } else {
          failCount++
        }
      } catch (e) {
        failCount++
        console.error(`[ChartScreenshotManager] 截图异常: ${chartId}`, e)
      }
    }

    this.lastCaptureTime = Date.now()
    this.captureCount = successCount

    console.log(`[ChartScreenshotManager] 批量截图完成: 成功${successCount}, 失败${failCount}, 跳过${skipCount}, 耗时${Date.now() - startTime}ms`)

    return {
      success: successCount,
      failed: failCount,
      skipped: skipCount,
      screenshots: results
    }
  }

  /**
   * 单个图表截图
   * @param {ChartRecord} record - 图表记录
   * @param {string} mode - 截图模式
   * @returns {ScreenshotCache|null}
   */
  async captureOne(record, mode) {
    const { id, type, title } = record

    if (!record.instance || !record.instance.getDom) {
      console.warn(`[ChartScreenshotManager] 图表实例无效: ${id}`)
      return null
    }

    const dom = record.instance.getDom()
    if (!dom || dom.clientWidth === 0 || dom.clientHeight === 0) {
      console.warn(`[ChartScreenshotManager] 图表DOM不可见: ${id}`)
      return null
    }

    // 获取配置
    const config = this.getScreenshotConfig(type, mode)

    try {
      // 获取截图（使用ECharts的getDataURL方法，自动处理宽幅和滑动轴）
      const dataURL = record.instance.getDataURL({
        type: config.format,
        pixelRatio: config.pixelRatio,
        backgroundColor: config.backgroundColor
      })

      // 解析Base64获取尺寸
      const size = await this.parseBase64Size(dataURL)

      const screenshot = new ScreenshotCache({
        id,
        type,
        chartType: type,
        title,
        dataURL,
        width: size.width,
        height: size.height,
        mode,
        meta: record.meta
      })

      return screenshot

    } catch (e) {
      console.error(`[ChartScreenshotManager] 获取截图失败: ${id}`, e)
      return null
    }
  }

  /**
   * 截图单个图表（按ID）
   * @param {string} chartId - 图表ID
   * @param {string} mode - 截图模式
   * @returns {ScreenshotCache|null}
   */
  async captureById(chartId, mode = 'auto') {
    const record = this.charts.get(chartId)
    if (!record) {
      console.warn(`[ChartScreenshotManager] 图表不存在: ${chartId}`)
      return null
    }

    const chartMode = this.getChartMode(record.type, mode)
    const screenshot = await this.captureOne(record, chartMode)

    if (screenshot) {
      this.screenshots.set(chartId, screenshot)
      record.screenshot = screenshot
      record.captured = true
    }

    return screenshot
  }

  /**
   * 重新截图所有图表
   * @returns {Object} 截图结果
   */
  async recaptureAll() {
    // 清除现有截图
    this.screenshots.clear()
    for (const record of this.charts.values()) {
      record.screenshot = null
      record.captured = false
    }

    // 重新截图
    return await this.captureAll()
  }

  // ========== 配置获取 ==========

  /**
   * 获取截图配置
   * @param {string} chartType - 图表类型
   * @param {string} mode - 截图模式
   * @returns {Object} 截图配置
   */
  getScreenshotConfig(chartType, mode) {
    const baseConfig = screenshotConfig.base
    const typeMode = mode === 'auto'
      ? screenshotConfig.chartTypeModes[chartType] || 'standard'
      : mode

    const modeConfig = screenshotConfig[typeMode] || screenshotConfig.standard

    return {
      ...baseConfig,
      ...modeConfig,
      mode: typeMode
    }
  }

  /**
   * 获取图表的截图模式
   * @param {string} chartType - 图表类型
   * @param {string} globalMode - 全局模式
   * @returns {string} 实际使用的模式
   */
  getChartMode(chartType, globalMode) {
    if (globalMode !== 'auto') return globalMode
    return screenshotConfig.chartTypeModes[chartType] || 'standard'
  }

  // ========== 截图获取 ==========

  /**
   * 按ID获取截图
   * @param {string} chartId - 图表ID
   * @returns {ScreenshotCache|null}
   */
  getScreenshot(chartId) {
    return this.screenshots.get(chartId) || null
  }

  /**
   * 按类型获取所有截图
   * @param {string} chartType - 图表类型
   * @returns {Array<ScreenshotCache>}
   */
  getScreenshotsByType(chartType) {
    const results = []
    for (const [id, screenshot] of this.screenshots) {
      if (screenshot.chartType === chartType || screenshot.type === chartType) {
        results.push(screenshot)
      }
    }
    return results
  }

  /**
   * 获取所有截图
   * @returns {Object} 所有截图 { id: ScreenshotCache, ... }
   */
  getAllScreenshots() {
    const results = {}
    for (const [id, screenshot] of this.screenshots) {
      results[id] = screenshot
    }
    return results
  }

  /**
   * 获取有效截图（用于报告插入）
   * 过滤掉无效的截图
   * @returns {Object} 有效截图
   */
  getValidScreenshots() {
    const results = {}
    for (const [id, screenshot] of this.screenshots) {
      if (screenshot.dataURL && screenshot.dataURL.length > 1000) {
        results[id] = screenshot
      }
    }
    return results
  }

  // ========== 缓存管理 ==========

  // 【已废弃】findMatching 和 findAllMatching 方法已删除
  // 新方案：后端直接生成图片URL，无需前端匹配占位符


  /**
   * 清理过期缓存
   * @returns {number} 清理数量
   */
  cleanup() {
    const maxAge = screenshotConfig.cache.maxAge
    const now = Date.now()
    let cleaned = 0

    for (const [chartId, screenshot] of this.screenshots) {
      if (screenshot.isExpired(maxAge)) {
        this.screenshots.delete(chartId)

        const record = this.charts.get(chartId)
        if (record) {
          record.screenshot = null
          record.captured = false
        }

        cleaned++
      }
    }

    if (cleaned > 0) {
      console.log(`[ChartScreenshotManager] 清理过期截图: ${cleaned}张`)
    }

    return cleaned
  }

  /**
   * 清空所有缓存
   */
  clear() {
    this.screenshots.clear()
    for (const record of this.charts.values()) {
      record.screenshot = null
      record.captured = false
    }
    this.lastCaptureTime = 0
    this.captureCount = 0
    console.log('[ChartScreenshotManager] 清空所有截图缓存')
  }

  /**
   * 清空并重置
   */
  reset() {
    this.clear()
    this.charts.clear()
    this.pendingCaptures.clear()
    this.isCapturing = false
    console.log('[ChartScreenshotManager] 重置截图管理器')
  }

  // ========== 状态查询 ==========

  /**
   * 获取管理器状态
   * @returns {Object} 状态信息
   */
  getStatus() {
    const capturedCount = Array.from(this.charts.values()).filter(r => r.captured).length

    return {
      chartCount: this.charts.size,
      screenshotCount: this.screenshots.size,
      capturedCount: capturedCount,
      pendingCount: this.pendingCaptures.size,
      lastCaptureTime: this.lastCaptureTime,
      captureCount: this.captureCount
    }
  }

  /**
   * 检查图表是否存在
   * @param {string} chartId - 图表ID
   * @returns {boolean}
   */
  hasChart(chartId) {
    return this.charts.has(chartId)
  }

  /**
   * 检查图表是否有截图
   * @param {string} chartId - 图表ID
   * @returns {boolean}
   */
  hasScreenshot(chartId) {
    const screenshot = this.screenshots.get(chartId)
    return screenshot && screenshot.dataURL && screenshot.dataURL.length > 1000
  }

  // ========== 内部辅助 ==========

  /**
   * 等待图表渲染
   * @param {number} timeout - 超时时间（毫秒）
   * @returns {boolean} 是否成功
   */
  async waitForCharts(timeout = 15000) {
    const startTime = Date.now()
    const checkInterval = 200
    const minCharts = 1  // 至少有一个图表

    while (Date.now() - startTime < timeout) {
      let allReady = true
      let visibleCount = 0

      for (const [chartId, record] of this.charts) {
        if (!record.instance || !record.instance.getDom) {
          allReady = false
          break
        }

        const dom = record.instance.getDom()
        if (!dom || dom.clientWidth === 0 || dom.clientHeight === 0) {
          allReady = false
        } else {
          visibleCount++
        }
      }

      if (allReady && visibleCount >= minCharts) {
        // 再等待一点时间确保渲染完成
        await new Promise(r => setTimeout(r, 300))
        console.log(`[ChartScreenshotManager] 图表渲染完成，等待${Date.now() - startTime}ms，${visibleCount}个图表`)
        return true
      }

      await new Promise(r => setTimeout(r, checkInterval))
    }

    console.warn(`[ChartScreenshotManager] 等待图表渲染超时，当前图表数: ${this.charts.size}`)
    return false
  }

  /**
   * 解析Base64获取图片尺寸
   * @param {string} dataURL - Base64数据URL
   * @returns {Promise<{width: number, height: number}>}
   */
  async parseBase64Size(dataURL) {
    return new Promise((resolve) => {
      try {
        const img = new Image()
        img.onload = () => {
          resolve({ width: img.width, height: img.height })
          // 释放内存
          URL.revokeObjectURL?.(img.src)
        }
        img.onerror = () => {
          resolve({ width: 0, height: 0 })
        }
        img.src = dataURL
      } catch {
        resolve({ width: 0, height: 0 })
      }
    })
  }

  /**
   * 启动定时清理
   */
  startCleanupTimer() {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer)
    }

    this.cleanupTimer = setInterval(() => {
      this.cleanup()
    }, screenshotConfig.cache.cleanupInterval)

    console.log(`[ChartScreenshotManager] 启动定时清理，间隔${screenshotConfig.cache.cleanupInterval}ms`)
  }

  /**
   * 停止定时清理
   */
  stopCleanupTimer() {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer)
      this.cleanupTimer = null
    }
  }
}

// ========== 导出 ==========

// 创建单例
export const chartScreenshotManager = new ChartScreenshotManager()

// 导出类（用于测试或创建多个实例）
export { ChartScreenshotManager, ChartRecord, ScreenshotCache }

// 导出默认单例
export default chartScreenshotManager
