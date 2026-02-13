// 改进的状态管理 - 与后端API完全集成
import { defineStore } from 'pinia'
import { api } from '@/services/api'

export const useAnalysisStore = defineStore('analysis', {
  state: () => ({
    // 基础状态
    sessionId: null,
    isAnalyzing: false,
    error: null,

    // 对话
    messages: [],
    currentMessage: '',

    // 分析状态
    analysisState: 'INITIAL', // INITIAL, COLLECTING_PARAMS, ANALYZING, COMPLETED
    currentStep: null,
    stepMessage: '',
    progress: 0,

    // 结果数据
    analysisData: null,
    extractedParams: null,
    dashboardTitle: '',

    // 可视化
    currentVisualization: null,
    visualizationHistory: [],

    // 调试
    debugEnabled: false,
    toolCalls: [],

    // 配置
    config: null,
  }),

  getters: {
    // 会话状态
    hasSession: (state) => state.sessionId !== null,
    canInput: (state) => !state.isAnalyzing || state.analysisState === 'COLLECTING_PARAMS',

    // 消息列表
    messageList: (state) => {
      return state.messages.filter(msg => msg.type !== 'step' && msg.type !== 'kpi')
    },

    // KPI数据
    kpiData: (state) => {
      if (state.analysisData?.kpi_summary) {
        return {
          peakValue: state.analysisData.kpi_summary.peak_value,
          exceedPeriods: state.analysisData.kpi_summary.exceed_periods,
          windSector: state.analysisData.kpi_summary.wind_sector,
          topSources: state.analysisData.kpi_summary.top_sources
        }
      }
      return null
    },

    // 分析完成状态
    isCompleted: (state) => state.analysisState === 'COMPLETED',
    hasResults: (state) => state.analysisData !== null,
  },

  actions: {
    // 初始化
    async init() {
      try {
        // 获取配置
        this.config = await api.getConfig()
        console.log('Config loaded:', this.config)
      } catch (error) {
        console.error('Failed to load config:', error)
        this.error = '加载配置失败'
      }
    },

    // 创建会话
    createSession() {
      if (!this.sessionId) {
        this.sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        console.log('Created new session:', this.sessionId)
      }
    },

    // 添加消息
    addMessage(type, content, data = null) {
      const message = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type,
        content,
        data,
        timestamp: new Date().toISOString()
      }
      this.messages.push(message)
      return message.id
    },

    // 更新消息
    updateMessage(id, updates) {
      const index = this.messages.findIndex(m => m.id === id)
      if (index !== -1) {
        this.messages[index] = { ...this.messages[index], ...updates }
      }
    },

    // 清空会话
    clearSession() {
      this.sessionId = null
      this.messages = []
      this.analysisData = null
      this.extractedParams = null
      this.dashboardTitle = ''
      this.analysisState = 'INITIAL'
      this.currentStep = null
      this.progress = 0
      this.error = null
    },

    // 处理流式事件
    handleStreamEvent(event) {
      console.log('Received SSE event:', event)

      switch (event.type) {
        case 'session':
          // 会话信息
          this.sessionId = event.session_id
          console.log('Session established:', this.sessionId)
          break

        case 'title':
          // 动态标题
          this.dashboardTitle = event.title
          this.addMessage('system', `开始分析: ${event.title}`)
          break

        case 'step':
          // 分析步骤
          this.handleStepEvent(event)
          break

        case 'result':
          // 模块结果
          this.handleResultEvent(event)
          break

        case 'kpi':
          // KPI数据
          this.handleKpiEvent(event)
          break

        case 'message':
          // AI消息
          this.addMessage('agent', event.message)
          break

        case 'done':
          // 分析完成
          this.handleDoneEvent(event)
          break

        case 'error':
          // 错误
          this.handleErrorEvent(event)
          break

        default:
          console.warn('Unknown event type:', event.type)
      }
    },

    // 处理步骤事件
    handleStepEvent(event) {
      this.currentStep = event.step
      this.stepMessage = event.message || ''

      if (event.status === 'start') {
        this.addMessage('step', `开始: ${event.step}`, event)
        this.updateProgress(event.step, 'start')
      } else if (event.status === 'success') {
        this.addMessage('step', `完成: ${event.step}`, event)
        this.updateProgress(event.step, 'success')
      } else if (event.status === 'error') {
        this.addMessage('step', `错误: ${event.step}`, event)
        this.updateProgress(event.step, 'error')
      }
    },

    // 处理结果事件
    handleResultEvent(event) {
      const { module, data } = event

      // 保存分析数据
      if (!this.analysisData) {
        this.analysisData = {}
      }
      this.analysisData[module] = data

      // 处理可视化数据
      if (data?.map) {
        this.setVisualization({
          type: 'map',
          title: '污染源分布图',
          data: data.map
        })
      }

      if (data?.charts) {
        data.charts.forEach((chart, index) => {
          this.setVisualization({
            type: 'chart',
            title: chart.title || `图表 ${index + 1}`,
            data: chart
          })
        })
      }

      if (data?.tables) {
        data.tables.forEach((table, index) => {
          this.setVisualization({
            type: 'table',
            title: table.title || `表格 ${index + 1}`,
            data: table
          })
        })
      }

      // 添加结果消息
      this.addMessage('result', `${module} 分析完成`, { module, data })
    },

    // 处理KPI事件
    handleKpiEvent(event) {
      if (!this.analysisData) {
        this.analysisData = {}
      }
      this.analysisData.kpi_summary = event.data

      this.addMessage('kpi', 'KPI数据已更新', event.data)
    },

    // 处理完成事件
    handleDoneEvent(event) {
      this.isAnalyzing = false
      this.analysisState = 'COMPLETED'
      this.progress = 100

      if (event.success) {
        // 成功
        this.addMessage('agent', event.message || '✅ 分析完成！')

        // 保存最终结果
        if (event.data) {
          this.analysisData = { ...this.analysisData, ...event.data }
        }

        console.log('Analysis completed:', this.analysisData)
      } else {
        // 失败 - 缺少参数
        this.analysisState = 'COLLECTING_PARAMS'
        this.addMessage('agent', event.message || '需要更多信息才能开始分析')
        if (event.missing_params) {
          this.addMessage('agent', `请提供: ${event.missing_params.join(', ')}`)
        }
      }
    },

    // 处理错误事件
    handleErrorEvent(event) {
      this.isAnalyzing = false
      this.analysisState = 'INITIAL'
      this.error = event.message

      this.addMessage('agent', `❌ 错误: ${event.message}`)
    },

    // 更新进度
    updateProgress(step, status) {
      const steps = [
        'extract_params',
        'weather',
        'regional',
        'component',
        'comprehensive',
        'kpi'
      ]
      const stepIndex = steps.indexOf(step)
      if (stepIndex !== -1) {
        let progress = 0
        if (status === 'success') {
          progress = ((stepIndex + 1) / steps.length) * 100
        } else if (status === 'start') {
          progress = ((stepIndex) / steps.length) * 100
        }
        this.progress = Math.round(progress)
      }
    },

    // 设置可视化内容
    setVisualization(content) {
      this.currentVisualization = content
      this.visualizationHistory.push({
        ...content,
        id: `viz_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        timestamp: new Date().toISOString()
      })
    },

    // 开始分析
    async startAnalysis(message) {
      if (!message.trim()) {
        return
      }

      // 创建会话
      this.createSession()

      // 添加用户消息
      this.addMessage('user', message)
      this.currentMessage = ''

      // 重置状态
      this.isAnalyzing = true
      this.analysisState = 'ANALYZING'
      this.error = null
      this.analysisData = null
      this.progress = 0

      try {
        // 调用流式分析API
        await api.streamAnalysis(message, this.sessionId, (event) => {
          this.handleStreamEvent(event)
        })
      } catch (error) {
        console.error('Analysis failed:', error)
        this.handleErrorEvent({ message: error.message })
      }
    },

    // 停止分析
    stopAnalysis() {
      api.cancel()
      this.isAnalyzing = false
      this.analysisState = 'INITIAL'
      this.addMessage('agent', '分析已停止')
    },

    // 继续分析（新问题）
    async continueAnalysis(message) {
      // 如果当前正在分析，询问是否停止
      if (this.isAnalyzing) {
        const confirmStop = confirm('当前正在分析中，是否停止并开始新分析？')
        if (!confirmStop) {
          return
        }
        this.stopAnalysis()
      }

      // 开始新分析
      await this.startAnalysis(message)
    },

    // 切换调试模式
    toggleDebug() {
      this.debugEnabled = !this.debugEnabled
    },

    // 重新开始分析
    async restartAnalysis() {
      this.clearSession()
    }
  }
})
