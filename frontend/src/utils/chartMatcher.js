/**
 * 图表匹配器
 *
 * 功能：
 * - 支持多种图表匹配方式
 * - 智能识别占位符与实际图表的对应关系
 * - 用于报告中的 [INSERT_CHART:xxx] 占位符匹配
 */

/**
 * 图表匹配器类
 */
export class ChartMatcher {
  constructor() {
    // 已知的图表类型列表（用于验证）
    this.knownTypes = [
      'ternary_SNA', 'sor_nor_scatter', 'charge_balance',
      'ec_oc_scatter', 'crustal_boxplot', 'ion_timeseries',
      'weather_timeseries', 'pressure_pbl_timeseries',
      'stacked_timeseries', 'facet_timeseries', 'timeseries',
      'noaa_trajectory', 'air_quality', 'particulate_stacked',
      'weather_ts', 'pressure_pbl', 'trajectory_image',
      'upwind_enterprise_map', 'upwind_map', 'map',
      'air_quality_timeseries', 'air_quality_facet_timeseries',
      'particulate_stacked_timeseries'
    ]

    // 常见的后缀（用于前缀匹配）
    this.commonSuffixes = [
      '_scatter', '_timeseries', '_boxplot', '_bar', '_line',
      '_pie', '_map', '_image', '_ts', '_chart'
    ]
  }

  /**
   * 主匹配方法：按优先级尝试所有策略
   * @param {Object} screenshotManager - 截图管理器实例
   * @param {string|Object} target - 目标模式（ID、类型、标题等）
   * @returns {Object|null} 匹配结果
   */
  findMatching(screenshotManager, target) {
    // 转换为匹配模式对象
    const pattern = this.normalizePattern(target)
    if (!pattern) {
      console.warn('[ChartMatcher] 无效的匹配目标:', target)
      return null
    }

    console.log('[ChartMatcher] 开始匹配:', pattern)

    // 策略1：ID精确匹配
    const exactMatch = this.matchById(screenshotManager, pattern)
    if (exactMatch) {
      console.log('[ChartMatcher] ID精确匹配成功:', exactMatch.id)
      return exactMatch
    }

    // 策略2：类型精确匹配（大小写不敏感）
    const typeMatch = this.matchByType(screenshotManager, pattern)
    if (typeMatch) {
      console.log('[ChartMatcher] 类型匹配成功:', typeMatch.id, '(类型:', pattern.type, ')')
      return typeMatch
    }

    // 策略3：类型前缀匹配（忽略时间戳）
    const prefixMatch = this.matchByTypePrefix(screenshotManager, pattern)
    if (prefixMatch) {
      console.log('[ChartMatcher] 前缀匹配成功:', prefixMatch.id)
      return prefixMatch
    }

    // 策略4：标题精确匹配
    const titleMatch = this.matchByTitle(screenshotManager, pattern)
    if (titleMatch) {
      console.log('[ChartMatcher] 标题匹配成功:', titleMatch.id)
      return titleMatch
    }

    // 策略5：标题模糊匹配
    const fuzzyTitleMatch = this.matchByTitleFuzzy(screenshotManager, pattern)
    if (fuzzyTitleMatch) {
      console.log('[ChartMatcher] 标题模糊匹配成功:', fuzzyTitleMatch.id)
      return fuzzyTitleMatch
    }

    // 策略6：关键词匹配
    const keywordMatch = this.matchByKeywords(screenshotManager, pattern)
    if (keywordMatch) {
      console.log('[ChartMatcher] 关键词匹配成功:', keywordMatch.id)
      return keywordMatch
    }

    console.log('[ChartMatcher] 匹配失败:', pattern)
    return null
  }

  /**
   * 批量匹配：返回多个匹配结果
   * @param {Object} screenshotManager - 截图管理器实例
   * @param {Array} patterns - 匹配模式列表
   * @returns {Object} 匹配结果 { pattern: result, ... }
   */
  findAllMatching(screenshotManager, patterns) {
    const results = {}
    for (const pattern of patterns) {
      const match = this.findMatching(screenshotManager, pattern)
      if (match) {
        results[pattern] = match
      } else {
        results[pattern] = null
        console.warn('[ChartMatcher] 批量匹配失败:', pattern)
      }
    }
    return results
  }

  /**
   * 标准化匹配模式
   */
  normalizePattern(target) {
    if (!target) return null

    // 如果是字符串，尝试解析占位符格式
    if (typeof target === 'string') {
      // 处理 [INSERT_CHART:xxx] 格式
      const cleaned = target.replace(/^\[INSERT_CHART:/, '').replace(/\]$/, '')

      // 检查是否无效类型
      const lower = cleaned.toLowerCase()
      if (lower.startsWith('no_') ||
          lower === 'n_charts' ||
          lower === 'none' ||
          lower === 'empty' ||
          !cleaned) {
        return null
      }

      return {
        id: cleaned,
        type: cleaned,
        raw: target
      }
    }

    // 如果是对象，直接使用
    if (typeof target === 'object') {
      return {
        id: target.id || target.chartId || target.chart_id,
        type: target.type || target.chartType || target.chart_type,
        title: target.title,
        raw: target.raw
      }
    }

    return null
  }

  // ========== 内部匹配方法 ==========

  /**
   * 策略1：ID精确匹配
   */
  matchById(screenshotManager, pattern) {
    const screenshots = screenshotManager.getAllScreenshots()
    const targetId = pattern.id

    if (!targetId) return null

    // 直接匹配
    if (screenshots[targetId]) {
      return { id: targetId, ...screenshots[targetId] }
    }

    // 尝试添加后缀（占位符可能没有时间戳）
    for (const suffix of this.commonSuffixes) {
      const withSuffix = targetId + suffix
      if (screenshots[withSuffix]) {
        return { id: withSuffix, ...screenshots[withSuffix] }
      }
    }

    return null
  }

  /**
   * 策略2：类型精确匹配（大小写不敏感）
   */
  matchByType(screenshotManager, pattern) {
    const screenshots = screenshotManager.getAllScreenshots()
    const targetType = pattern.type

    if (!targetType) return null

    const lowerType = targetType.toLowerCase()

    for (const [id, info] of Object.entries(screenshots)) {
      // 检查 chartType
      if (info.chartType?.toLowerCase() === lowerType) {
        return { id, ...info }
      }
      // 检查 type
      if (info.type?.toLowerCase() === lowerType) {
        return { id, ...info }
      }
    }

    return null
  }

  /**
   * 策略3：类型前缀匹配（忽略时间戳）
   * 例如：ternary_SNA -> ternary_sna_20251231101150
   * 例如：sor_nor_scatter -> sor_nor_xxx
   */
  matchByTypePrefix(screenshotManager, pattern) {
    const screenshots = screenshotManager.getAllScreenshots()
    const targetType = pattern.type

    if (!targetType) return null

    const lowerType = targetType.toLowerCase()

    for (const [id, info] of Object.entries(screenshots)) {
      const lowerId = id.toLowerCase()

      // 策略3a：占位符作为完整前缀
      if (lowerId.startsWith(lowerType + '_')) {
        return { id, ...info }
      }

      // 策略3b：占位符在ID中间
      if (lowerId.includes('_' + lowerType + '_')) {
        return { id, ...info }
      }

      // 策略3c：完全相等
      if (lowerId === lowerType) {
        return { id, ...info }
      }

      // 策略3d：去除常见后缀后匹配
      // 例如：sor_nor_scatter -> sor_nor_xxx（去除 _scatter 后匹配）
      for (const suffix of this.commonSuffixes) {
        if (lowerType.endsWith(suffix)) {
          const baseType = lowerType.slice(0, -suffix.length)
          if (baseType && lowerId.startsWith(baseType + '_')) {
            return { id, ...info }
          }
          if (baseType && lowerId.includes('_' + baseType + '_')) {
            return { id, ...info }
          }
        }
      }
    }

    return null
  }

  /**
   * 策略4：标题精确匹配
   */
  matchByTitle(screenshotManager, pattern) {
    const screenshots = screenshotManager.getAllScreenshots()
    const targetTitle = pattern.title

    if (!targetTitle) return null

    for (const [id, info] of Object.entries(screenshots)) {
      if (info.title === targetTitle) {
        return { id, ...info }
      }
    }

    return null
  }

  /**
   * 策略5：标题模糊匹配
   */
  matchByTitleFuzzy(screenshotManager, pattern) {
    const screenshots = screenshotManager.getAllScreenshots()
    const targetTitle = pattern.title

    if (!targetTitle) return null

    // 清理标题（去除序号如"图1："前缀）
    const cleanTarget = targetTitle.replace(/^图\d+[：:]/, '').trim()

    for (const [id, info] of Object.entries(screenshots)) {
      const chartTitle = info.title || ''

      // 去除常见后缀
      const cleanChart = chartTitle
        .replace(/时序图$/, '')
        .replace(/分布图$/, '')
        .replace(/分析图$/, '')
        .replace(/趋势图$/, '')
        .replace(/对比图$/, '')
        .replace(/图$/, '')
        .trim()

      const cleanTargetProcessed = cleanTarget
        .replace(/时序图$/, '')
        .replace(/分布图$/, '')
        .replace(/分析图$/, '')
        .replace(/趋势图$/, '')
        .replace(/对比图$/, '')
        .replace(/图$/, '')
        .trim()

      // 包含关系检查
      if (cleanChart.includes(cleanTargetProcessed) ||
          cleanTargetProcessed.includes(cleanChart)) {
        return { id, ...info }
      }
    }

    return null
  }

  /**
   * 策略6：关键词匹配
   * 用于LLM生成名称与实际ID差异较大的情况
   * 例如：ion_timeseries -> 包含 ion 关键词的ID
   */
  matchByKeywords(screenshotManager, pattern) {
    const screenshots = screenshotManager.getAllScreenshots()
    const targetType = pattern.type

    if (!targetType) return null

    const lowerType = targetType.toLowerCase()

    // 跳过无效类型
    if (lowerType.startsWith('no_') ||
        lowerType === 'n_charts' ||
        lowerType === 'none' ||
        lowerType === 'empty') {
      return null
    }

    // 提取核心关键词
    const parts = lowerType.split(/[_\s]+/)
    const keywords = parts.filter(part =>
      part.length > 2 &&
      !['chart', 'plot', 'type', 'figure', 'img', 'the'].includes(part)
    )

    if (keywords.length === 0) return null

    for (const [id, info] of Object.entries(screenshots)) {
      const lowerId = id.toLowerCase()

      for (const keyword of keywords) {
        // 关键词作为独立词匹配（单词边界）
        const regex = new RegExp(`(^|_)${keyword}(_|$)`, 'i')
        if (regex.test(lowerId)) {
          return { id, ...info }
        }
      }
    }

    return null
  }

  /**
   * 检查是否是已知图表类型
   */
  isKnownType(chartType) {
    if (!chartType) return false
    const lower = chartType.toLowerCase()
    return this.knownTypes.some(t => t.toLowerCase() === lower)
  }
}

// 导出单例
export const chartMatcher = new ChartMatcher()

// 导出类
export default ChartMatcher
