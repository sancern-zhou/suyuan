import { defineStore } from 'pinia'
import { dashboardAssetUrl, fetchScreenSnapshot } from '@/api/bigScreen.js'

const POLL_INTERVAL_MS = 5 * 60 * 1000

export const useBigScreenStore = defineStore('bigScreen', {
  state: () => ({
    snapshot: null,
    etag: null,
    loading: false,
    error: '',
    lastFetchedAt: null,
    _timer: null
  }),
  getters: {
    header: state => state.snapshot?.header || null,
    cityHourRank: state => state.snapshot?.city_hour_rank || null,
    countyHourRank: state => state.snapshot?.county_hour_rank || null,
    cityTrend: state => state.snapshot?.city_trend_24h || null,
    forecast: state => state.snapshot?.forecast_72h || null,
    yearTarget: state => state.snapshot?.year_target || null,
    alerts: state => state.snapshot?.alerts || [],
    broadcast: state => state.snapshot?.broadcast || [],
    stations: state => state.snapshot?.stations || { national: [], townships: [], counties: [] },
    assets: state => state.snapshot?.assets || [],
    rank168: state => state.snapshot?.rank168 || null,
    minute: state => state.snapshot?.minute || null,
    quality: state => state.snapshot?.quality || null
  },
  actions: {
    assetUrl(assetPath) {
      return dashboardAssetUrl(assetPath)
    },
    async refresh() {
      if (this.loading) return
      this.loading = true
      try {
        const result = await fetchScreenSnapshot(this.etag)
        if (!result.notModified) {
          this.snapshot = result.data
          this.etag = result.etag || null
          this.lastFetchedAt = new Date().toISOString()
        }
        this.error = ''
      } catch (error) {
        // 保留上一次整屏数据，仅更新错误角标，避免大屏闪空
        this.error = error?.message || '大屏快照加载失败'
      } finally {
        this.loading = false
      }
    },
    startPolling() {
      if (this._timer) return
      this.refresh()
      this._timer = setInterval(() => this.refresh(), POLL_INTERVAL_MS)
    },
    stopPolling() {
      if (this._timer) {
        clearInterval(this._timer)
        this._timer = null
      }
    }
  }
})
