/**
 * 数据抓取 Composable
 * 管理数据抓取器的状态和操作
 */
import { ref } from 'vue'
import { FETCHER_STATUS, FETCHER_ACTIONS } from '@/utils/constants'

export function useDataFetcher() {
  // ========== 状态 ==========
  const fetcherSystemStatus = ref(null)
  const fetcherLoading = ref(false)
  const fetcherError = ref(null)
  const fetcherOperating = ref(false)

  const era5HistoricalDate = ref('')
  const era5FetchResult = ref(null)

  // ========== 方法 ==========

  /**
   * 刷新抓取器状态
   */
  const refreshFetcherStatus = async () => {
    fetcherLoading.value = true
    fetcherError.value = null

    try {
      const response = await fetch('/api/system/status')
      if (!response.ok) throw new Error('Failed to fetch status')

      const data = await response.json()
      // 从系统状态中提取 fetchers 信息
      fetcherSystemStatus.value = data.fetchers || null
      return true
    } catch (error) {
      fetcherError.value = error.message
      console.error('Failed to refresh fetcher status:', error)
      return false
    } finally {
      fetcherLoading.value = false
    }
  }

  /**
   * 触发抓取器
   * @param {string} fetcherId - 抓取器ID
   * @param {string} action - 操作类型
   */
  const triggerFetcher = async (fetcherId, action = FETCHER_ACTIONS.START) => {
    fetcherOperating.value = true

    try {
      const response = await fetch(`/api/fetchers/${fetcherId}/${action}`, {
        method: 'POST'
      })

      if (!response.ok) throw new Error(`Failed to ${action} fetcher`)

      const data = await response.json()
      await refreshFetcherStatus()
      return { success: true, data }
    } catch (error) {
      console.error(`Failed to ${action} fetcher:`, error)
      return { success: false, error: error.message }
    } finally {
      fetcherOperating.value = false
    }
  }

  /**
   * 暂停抓取器
   * @param {string} fetcherId - 抓取器ID
   */
  const pauseFetcher = async (fetcherId) => {
    return triggerFetcher(fetcherId, FETCHER_ACTIONS.PAUSE)
  }

  /**
   * 恢复抓取器
   * @param {string} fetcherId - 抓取器ID
   */
  const resumeFetcher = async (fetcherId) => {
    return triggerFetcher(fetcherId, FETCHER_ACTIONS.RESUME)
  }

  /**
   * 停止抓取器
   * @param {string} fetcherId - 抓取器ID
   */
  const stopFetcher = async (fetcherId) => {
    return triggerFetcher(fetcherId, FETCHER_ACTIONS.STOP)
  }

  /**
   * 获取ERA5历史数据
   * @param {string} date - 日期字符串（YYYY-MM-DD）
   */
  const fetchEra5Historical = async (date) => {
    if (!date) {
      era5FetchResult.value = {
        success: false,
        message: '请选择日期',
        details: null
      }
      return
    }

    fetcherOperating.value = true
    era5FetchResult.value = null

    try {
      const response = await fetch('/api/fetchers/era5/historical', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date })
      })

      if (!response.ok) throw new Error('Failed to fetch ERA5 data')

      const data = await response.json()
      era5FetchResult.value = {
        success: data.success,
        message: data.message,
        details: data.details
      }
    } catch (error) {
      era5FetchResult.value = {
        success: false,
        message: '获取失败',
        details: { error: error.message }
      }
      console.error('Failed to fetch ERA5 historical data:', error)
    } finally {
      fetcherOperating.value = false
    }
  }

  /**
   * 获取抓取器状态文本
   * @param {string} status - 状态值
   * @returns {string} 状态文本
   */
  const getFetcherStatusText = (status) => {
    const statusMap = {
      [FETCHER_STATUS.IDLE]: '空闲',
      [FETCHER_STATUS.RUNNING]: '运行中',
      [FETCHER_STATUS.PAUSED]: '已暂停',
      [FETCHER_STATUS.DISABLED]: '已禁用',
      [FETCHER_STATUS.ERROR]: '错误'
    }
    return statusMap[status] || status
  }

  /**
   * 获取抓取器状态样式类
   * @param {string} status - 状态值
   * @returns {string} 样式类
   */
  const getFetcherStatusClass = (status) => {
    const classMap = {
      [FETCHER_STATUS.IDLE]: 'idle',
      [FETCHER_STATUS.RUNNING]: 'running',
      [FETCHER_STATUS.PAUSED]: 'paused',
      [FETCHER_STATUS.DISABLED]: 'disabled',
      [FETCHER_STATUS.ERROR]: 'error'
    }
    return classMap[status] || ''
  }

  return {
    // 状态
    fetcherSystemStatus,
    fetcherLoading,
    fetcherError,
    fetcherOperating,
    era5HistoricalDate,
    era5FetchResult,

    // 方法
    refreshFetcherStatus,
    triggerFetcher,
    pauseFetcher,
    resumeFetcher,
    stopFetcher,
    fetchEra5Historical,
    getFetcherStatusText,
    getFetcherStatusClass
  }
}
