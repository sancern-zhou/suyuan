// ReAct Agent状态管理
// 简化的状态管理，专注于ReAct循环

import { defineStore } from 'pinia'
import { agentAPI } from '@/services/reactApi'

export const useReactStore = defineStore('react', {
  state: () => ({
    // 基础状态
    sessionId: null,
    isAnalyzing: false,
    error: null,
    isInterruption: false,  // 标记是否为用户中断后的对话

    // 对话
    messages: [],
    currentMessage: '',

    // 分析状态
    isComplete: false,
    iterations: 0,
    maxIterations: 10,
    debugMode: false,

    // 增强功能
    showReflexion: false,  // 显示Reflexion状态
    reflexionCount: 0,  // Reflexion次数计数

    // 多专家系统状态
    expertSystemEnabled: false,
    expertResults: {},  // 存储各专家结果
    lastExpertResults: null,  // 存储最新的专家结果
    selectedExperts: [],  // 选中的专家列表

    // 结果
    finalAnswer: '',
    finalAnswers: [],
    hasResults: false,

    // 可视化
    currentVisualization: null,
    visualizationHistory: [],
    // 按专家类型分组的可视化数据（优化：一次性处理，避免重复计算）
    groupedVisualizations: {
      weather: [],
      component: []
    },

    // 工具（调试用）
    availableTools: [],

    // 采用原有工作流的结果管理系统
    results: {
      map: null,
      charts: [],
      tables: [],
      text: ''
    },

    // 原有工作流字段
    sessionRound: 0,
    interventionQueue: [],

    // 最终答案流式渲染状态
    streamingAnswerMessageId: null
  }),

  getters: {
    // 对话列表（排除内部事件）
    conversation: (state) => {
      return state.messages.filter(msg =>
        msg.type === 'user' || msg.type === 'agent' || msg.type === 'thought' || msg.type === 'final'
      )
    },

    // 分析日志（内部事件）
    analysisLog: (state) => {
      return state.messages.filter(msg =>
        msg.type === 'start' || msg.type === 'action' || msg.type === 'observation' || msg.type === 'error'
      )
    },

    // 可输入状态
    canInput: (state) => !state.isAnalyzing,

    // 进度
    progress: (state) => {
      if (state.maxIterations === 0) return 0
      return Math.min(100, Math.round((state.iterations / state.maxIterations) * 100))
    },

    // 已完成的工具调用
    completedTools: (state) => {
      return state.messages
        .filter(m => m.type === 'action' && m.data?.status === 'success' && m.data?.tool)
        .map(m => m.data.tool)
    }
  },

  actions: {
    // 获取专家标签
    getExpertLabel(expertType) {
      const labelMap = {
        'weather': '气象专家',
        'component': '组分专家',
        'viz': '可视化专家',
        'report': '报告专家'
      }
      return labelMap[expertType] || expertType
    },

    // 初始化
    async init() {
      try {
        // 获取可用工具
        const tools = await agentAPI.getTools()
        this.availableTools = tools.tools
        console.log('Available tools:', this.availableTools)
      } catch (error) {
        this.availableTools = []
        if (!this.messages.find(msg => msg.type === 'error' && msg.source === 'tools')) {
          this.addMessage('error', '工具列表加载失败，可稍后在顶部“工具管理”里重试。', { source: 'tools', error: error.message })
        }
        console.error('Failed to load tools:', error)
      }
    },

    // 继续会话（原有工作流逻辑）
    continueSession() {
      this.sessionRound = Math.max(this.sessionRound + 1, 1)
      this.isAnalyzing = false
      this.error = null
      // 保留finalAnswer，让它保持直到新答案到来
      // 保留messages，但清空本轮的可视化结果
      this.results = {
        map: null,
        charts: [],
        tables: [],
        text: ''
      }
    },

    // 创建会话ID
    createSessionId() {
      if (!this.sessionId) {
        this.sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        console.log('Created session:', this.sessionId)
      }
    },

    // 重置会话
    reset() {
      this.sessionId = null
      this.messages = []
      this.isAnalyzing = false
      this.isComplete = false
      this.iterations = 0
      this.error = null
      this.finalAnswer = ''
      this.finalAnswers = []
      this.hasResults = false
      this.currentVisualization = null
      this.visualizationHistory = []
      this.sessionRound = 0
      this.expertSystemEnabled = false
      this.expertResults = {}
      this.lastExpertResults = null
      this.selectedExperts = []
      this._lastProcessedExpertResultsHash = null  // 【新增】重置防重复检查
      this.results = {
        map: null,
        charts: [],
        tables: [],
        text: ''
      }
      this.streamingAnswerMessageId = null
    },

    // 添加消息
    addMessage(type, content, data = null) {
      const message = {
        id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type, // 'user', 'agent', 'thought', 'action', 'observation', 'start', 'error', 'final'
        content,
        data,
        timestamp: new Date().toISOString()
      }
      this.messages.push(message)
      return message.id
    },

    // 处理ReAct事件
    handleEvent(event) {
      console.log('ReAct event:', event)

      const { type, data } = event

      switch (type) {
        case 'start':
          // 分析开始
          this.addMessage('start', `开始分析: ${data?.query || ''}`)
          if (data?.session_id) {
            this.sessionId = data.session_id
          }
          this.iterations = 0
          break

        case 'thought':
          // LLM思考
          const thoughtContent = data?.thought || '思考中...'
          // 传递LLM上下文（仅调试模式）
          const thoughtData = this.debugMode && data?.context
            ? { context: data.context }
            : null
          this.addMessage('thought', thoughtContent, thoughtData)

          // 检测Reflexion
          if (data?.thought && data.thought.includes('[Reflexion 反思]')) {
            this.showReflexion = true
            this.reflexionCount++
          }
          break

        case 'action':
          // 行动（工具调用）
          const actionData = data?.action || data

          // 【修复】如果本次“行动”其实是 FINISH（最终回答），不要在这里再渲染一遍，
          // 否则会在“执行行动”步骤和最终答案里各出现一次完整回答。
          if (actionData?.type === 'FINISH') {
            // 仍然保留后台的日志，但前端对话不追加多余的 action 消息
            break
          }

          const toolName = actionData?.tool
          const actionContent = toolName ? `调用工具: ${toolName}` : '执行行动'

          // 构造调试数据
          let debugData = actionData
          if (this.debugMode) {
            // 添加工具信息
            debugData = {
              ...actionData,
              toolInfo: `工具名称: ${toolName || '未知'}\n迭代: ${this.iterations}\n时间: ${new Date().toLocaleTimeString()}`
            }
          }

          this.addMessage('action', actionContent, debugData)
          break

        case 'observation':
          // 观察结果
          const obsContent = data?.observation || '获得结果'
          this.addMessage('observation', obsContent, data)
          break

        case 'complete':
          // 分析完成
          console.log('[event:complete] ========== 收到complete事件 ==========')
          console.log('[event:complete] 数据:', JSON.stringify(data, null, 2))
          console.log('[event:complete] has answer:', !!data?.answer)
          console.log('[event:complete] answer value:', data?.answer)
          console.log('[event:complete] has expert_results:', !!data?.expert_results)
          console.log('[event:complete] has visuals:', !!(data?.visuals && Array.isArray(data.visuals) && data.visuals.length > 0))

          this.isAnalyzing = false
          this.isComplete = true
          this.iterations = data?.iterations || this.iterations
          this.finalAnswer = data?.answer || ''
          this.hasResults = true

          // 记录最终答案（原有工作流逻辑）
          this.finalAnswers.push({
            run: this.sessionRound,
            content: data?.answer || '分析完成',
            timestamp: new Date().toISOString()
          })

          // 添加最终答案消息到UI
          // 如果已经通过 answer_delta 流式创建了最终答案消息，则只更新其元数据，避免重复追加一条消息
          console.log('[event:complete] streamingAnswerMessageId:', this.streamingAnswerMessageId)
          if (this.streamingAnswerMessageId) {
            const msg = this.messages.find(m => m.id === this.streamingAnswerMessageId)
            if (msg) {
              msg.data = {
                ...(msg.data || {}),
                iterations: data?.iterations,
                session_id: data?.session_id,
                timestamp: data?.timestamp,
                expert_results: data?.expert_results || null,  // ✅ 传递专家结果用于显示
                sources: data?.sources || null  // ✅ 知识问答参考来源
              }
              console.log('[event:complete] 更新已有消息的数据')
            }
          } else if (data?.answer) {
            console.log('[event:complete] 添加final消息，answer:', data.answer.substring(0, 50) + '...')
            this.addMessage('final', data.answer, {
              iterations: data?.iterations,
              session_id: data?.session_id,
              timestamp: data?.timestamp,
              expert_results: data?.expert_results || null,  // ✅ 传递专家结果用于显示
              sources: data?.sources || null  // ✅ 知识问答参考来源
            })
            console.log('[event:complete] messages数量:', this.messages.length)
          } else {
            console.log('[event:complete] 警告：没有answer字段，不添加final消息')
          }

          // 处理可视化数据
          if (data?.visualization) {
            console.log('[event:complete] 处理visualization字段')
            this.handleResult(data.visualization)
          }

          // 【关键修复】处理多专家系统的最终结果
          if (data?.expert_results) {
            console.log('[event:complete] 调用 _processExpertResultsForVisualization')
            this._processExpertResultsForVisualization(data.expert_results)
            // 【重要】同时存储完整的专家结果供前端使用
            this.lastExpertResults = {
              expert_results: data.expert_results
            }
            console.log('[event:complete] lastExpertResults已设置')
          }

          // 【新增】直接处理complete事件中的visuals字段（后端多专家系统返回的聚合visuals）
          if (data?.visuals && Array.isArray(data.visuals)) {
            console.log('[event:complete] 直接处理visuals字段，数量:', data.visuals.length)
            console.log('[event:complete] visuals详情:', data.visuals.map(v => ({ id: v.id, type: v.type })))
            for (const viz of data.visuals) {
              console.log('[event:complete] 添加visual:', viz.id, viz.type)
              this.recordVisualization({
                ...viz,
                meta: {
                  ...viz.meta,
                  schema_version: 'v2.0'
                }
              })
              // 【关键修复】同步更新 groupedVisualizations
              const targetGroup = this._classifyVizForComplete(viz)
              if (!this.groupedVisualizations[targetGroup]) {
                this.groupedVisualizations[targetGroup] = []
              }
              this.groupedVisualizations[targetGroup].push({
                ...viz,
                meta: {
                  ...viz.meta,
                  schema_version: 'v2.0'
                }
              })
              console.log(`[event:complete] 已添加到 ${targetGroup} 组，count=${this.groupedVisualizations[targetGroup].length}`)
            }
            this.hasResults = true
            console.log('[event:complete] 更新后的 groupedVisualizations:', JSON.stringify({
              weather: this.groupedVisualizations.weather?.length,
              component: this.groupedVisualizations.component?.length
            }))
          } else {
            console.log('[event:complete] 无visuals字段或为空')
          }

          console.log('[event:complete] ========== complete事件处理完成 ==========')

          // 流式最终答案结束，重置状态
          this.streamingAnswerMessageId = null
          break

        case 'incomplete':
          // 未完成（达到最大迭代）
          this.isAnalyzing = false
          this.isComplete = true
          this.iterations = data?.iterations || this.iterations
          this.finalAnswer = data?.answer || '分析未完成'

          // 记录最终答案（原有工作流逻辑）
          this.finalAnswers.push({
            run: this.sessionRound,
            content: data?.answer || '分析未完成',
            timestamp: new Date().toISOString()
          })

          // 添加最终答案消息到UI
          if (this.streamingAnswerMessageId) {
            const msg = this.messages.find(m => m.id === this.streamingAnswerMessageId)
            if (msg) {
              msg.data = {
                ...(msg.data || {}),
                iterations: data?.iterations,
                reason: data?.reason,
                timestamp: data?.timestamp,
                expert_results: data?.expert_results || null  // ✅ 传递专家结果用于显示
              }
            }
          } else if (data?.answer) {
            this.addMessage('final', data.answer, {
              iterations: data?.iterations,
              reason: data?.reason,
              timestamp: data?.timestamp,
              expert_results: data?.expert_results || null  // ✅ 传递专家结果用于显示
            })
          }

          // 处理多专家系统的最终结果（即使未完成也可能有部分结果）
          if (data?.expert_results) {
            console.log('[incomplete] 处理多专家系统最终结果:', data.expert_results)
            this._processExpertResultsForVisualization(data.expert_results)
            // 【重要】同时存储完整的专家结果供前端使用
            this.lastExpertResults = {
              expert_results: data.expert_results
            }
          }

          // 流式最终答案结束，重置状态
          this.streamingAnswerMessageId = null
          break

        case 'error':
          // 迭代错误
          this.addMessage('error', `错误: ${data?.error || '未知错误'}`, data)
          break

        case 'fatal_error':
          // 致命错误
          this.isAnalyzing = false
          this.error = data?.error || '致命错误'
          this.addMessage('error', `致命错误: ${this.error}`, data)
          this.streamingAnswerMessageId = null
          break

        case 'result':
          // 处理结果事件（原有工作流逻辑）
          this.handleResult(data)
          break

        case 'pipeline_started':
          // 流水线开始事件
          this.addMessage('start', `开始多专家分析: ${data?.query || ''}`)
          break

        case 'query_parsed':
          // 查询解析完成事件
          this.addMessage('observation', `查询解析完成 - 地点: ${data?.location || '未知'} | 分析类型: ${data?.analysis_type || '未知'}`, {
            query_parsed: data
          })
          break

        case 'experts_selected':
          // 专家选择完成事件
          const experts = data?.selected_experts || []
          this.addMessage('observation', `已选择 ${experts.length} 个专家: ${experts.map(e => this.getExpertLabel(e)).join('、')}`, {
            selected_experts: experts
          })
          break

        case 'expert_group_started':
          // 专家组开始事件
          this.addMessage('action', `启动专家组: ${data?.group?.map(e => this.getExpertLabel(e)).join('、')}`, {
            group: data?.group
          })
          break

        case 'expert_started':
          // 单个专家开始事件
          const expertName = this.getExpertLabel(data?.expert_type)
          this.addMessage('action', `执行【${expertName}】专家任务 (工具数: ${data?.tool_count || 0})`, {
            expert_type: data?.expert_type,
            task_id: data?.task_id
          })
          break

        case 'expert_completed':
          // 专家完成事件
          const completedExpertName = this.getExpertLabel(data?.expert_type)
          this.addMessage('observation', `【${completedExpertName}】专家完成 - 状态: ${data?.status} | 数据ID: ${(data?.data_ids || []).length}个`, {
            expert_type: data?.expert_type,
            status: data?.status,
            data_ids: data?.data_ids
          })
          break

        case 'expert_group_completed':
          // 专家组完成事件
          this.addMessage('observation', `专家组执行完成: ${Object.entries(data?.results || {}).map(([k, v]) => `${this.getExpertLabel(k)}(${v})`).join('、')}`, {
            group_results: data?.results
          })
          break

        case 'expert_result':
          // 多专家系统结果事件
          console.log('[event:expert_result] ========== 收到expert_result事件 ==========')
          console.log('[event:expert_result] 完整数据:', JSON.stringify(data, null, 2))

          // 【关键修改】在主对话框中显示专家结果
          if (data && data.expert_results) {
            console.log('[event:expert_result] expert_results keys:', Object.keys(data.expert_results))

            const expertResultsText = Object.keys(data.expert_results)
              .map(expertType => {
                const expertData = data.expert_results[expertType]
                const status = expertData.status || 'unknown'
                const toolCount = expertData.tool_results?.length || 0
                const summary = expertData.analysis?.summary || '无摘要'
                const expertName = this.getExpertLabel(expertType)

                return `【${expertName}】状态: ${status} | 执行工具: ${toolCount}个\n摘要: ${summary.substring(0, 150)}...`
              })
              .join('\n\n')

            // 添加到主对话框显示
            this.addMessage('observation', `多专家系统阶段性结果:\n\n${expertResultsText}`, {
              expert_results: data.expert_results,
              is_expert_result: true
            })

            // 【关键修复】从专家结果中提取visuals并传递给可视化面板
            console.log('[event:expert_result] 调用 _processExpertResultsForVisualization')
            this._processExpertResultsForVisualization(data.expert_results)

            // 【重要】确保lastExpertResults具有正确的结构
            this.lastExpertResults = {
              expert_results: data.expert_results
            }
            console.log('[event:expert_result] lastExpertResults已设置')
          } else {
            // 如果没有expert_results字段，直接存储data
            console.log('[event:expert_result] 无expert_results，直接存储data')
            this.lastExpertResults = data
          }
          break

        case 'pipeline_error':
          // 流水线错误事件
          this.addMessage('error', `多专家系统错误: ${data?.error || '未知错误'}`, data)
          break

        case 'expert_error':
          // 专家错误事件
          const errorExpertName = this.getExpertLabel(data?.expert_type)
          this.addMessage('error', `【${errorExpertName}】专家执行失败: ${data?.error || '未知错误'}`, data)
          break

        case 'answer_delta':
          // 最终答案 token 级流式增量
          if (!data?.delta) {
            break
          }

          // 如果还没有为本轮回答创建消息，先创建一条最终答案消息
          if (!this.streamingAnswerMessageId) {
            const msgId = this.addMessage('final', data.delta, {
              session_id: data?.session_id,
              timestamp: data?.timestamp,
              streaming: true
            })
            this.streamingAnswerMessageId = msgId
          } else {
            // 已存在流式消息，直接在原有内容后追加
            const msg = this.messages.find(m => m.id === this.streamingAnswerMessageId)
            if (msg) {
              msg.content = (msg.content || '') + data.delta
            } else {
              // 找不到消息时，退化为创建新消息，避免用户看不到内容
              const msgId = this.addMessage('final', data.delta, {
                session_id: data?.session_id,
                timestamp: data?.timestamp,
                streaming: true
              })
              this.streamingAnswerMessageId = msgId
            }
          }

          // 同步更新 finalAnswer，方便其他地方直接读取
          this.finalAnswer = (this.finalAnswer || '') + data.delta
          break

        default:
          console.warn('Unknown event type:', type)
      }

      // 更新迭代次数
      if (type === 'thought' || type === 'action' || type === 'observation') {
        this.iterations += 0.5 // 每个循环算作0.5，因为thought+action+observation是一个完整循环
      }
    },

    // 记录可视化历史，并同步当前展示
    recordVisualization(visualization) {
      if (!visualization) return

      const record = {
        ...visualization,
        id: visualization.id || `viz_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
        timestamp: visualization.timestamp || new Date().toISOString()
      }

      this.currentVisualization = record
      this.visualizationHistory.push(record)
    },

    // 处理结果（UDF v2.0格式 + v3.0图表格式）
    handleResult(resultData) {
      if (!resultData) return

      console.log('[handleResult] 处理结果:', resultData)

      // 【UDF v2.0】处理visuals字段
      if (resultData.visuals && Array.isArray(resultData.visuals)) {
        console.log('[handleResult] 检测到UDF v2.0 visuals格式:', resultData.visuals)

        // 将每个visual提取并添加到历史记录
        // 兼容两种格式：VisualBlock格式 和 直接格式（EKMA专业图表等）
        resultData.visuals.forEach((visualBlock, index) => {
          let visualization
          if (visualBlock.payload) {
            // VisualBlock格式: {payload: {...}, meta: {...}}
            visualization = {
              ...visualBlock.payload,
              meta: {
                ...visualBlock.meta,
                schema_version: 'v2.0'
              },
              id: visualBlock.id || visualBlock.payload?.id || `viz_${Date.now()}_${index}_${Math.random().toString(36).substr(2, 5)}`,
              timestamp: new Date().toISOString()
            }
          } else {
            // 直接格式: {id, type, data, meta, ...} (如EKMA专业图表)
            visualization = {
              ...visualBlock,
              meta: {
                ...visualBlock.meta,
                schema_version: 'v2.0'
              },
              id: visualBlock.id || `viz_${Date.now()}_${index}_${Math.random().toString(36).substr(2, 5)}`,
              timestamp: new Date().toISOString()
            }
          }

          // 添加到历史记录
          this.recordVisualization(visualization)
          console.log('[handleResult] 添加visual到历史记录:', visualization)
        })

        console.log('[handleResult] UDF v2.0 visuals处理完成，已添加', resultData.visuals.length, '个图表到历史记录')
        this.hasResults = true
        return
      }

      // 处理v3.0格式或其他格式
      if (resultData.type === 'map' || resultData.mapConfig) {
        const mapData = resultData.mapConfig || resultData
        this.results.map = mapData

        const mapVisualization = {
          ...mapData,
          type: mapData.type || 'map',
          title: mapData.title || '地图可视化',
          data: mapData.data || mapData.config || mapData
        }

        this.recordVisualization(mapVisualization)
        console.log('[handleResult] 设置地图可视化')
      } else if (['chart', 'pie', 'bar', 'line', 'timeseries', 'radar', 'wind_rose', 'profile'].includes(resultData.type) || resultData.chartConfig) {
        // 处理v3.0图表格式：支持所有图表类型
        const chartData = resultData.chartConfig || resultData
        this.results.charts.push(chartData)

        const chartVisualization = {
          ...chartData,
          id: chartData.id || chartData.chartId || `chart_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          type: chartData.type || 'chart',
          title: chartData.title || '',
          data: chartData.data,
          meta: chartData.meta || {}
        }

        this.recordVisualization(chartVisualization)
        console.log('[handleResult] 设置图表可视化 (v3.0):', chartVisualization)
      } else if (resultData.type === 'table' || resultData.tableConfig) {
        const tableData = resultData.tableConfig || resultData
        this.results.tables.push(tableData)

        const tableVisualization = {
          type: 'table',
          title: tableData.title || '表格',
          data: tableData
        }

        this.recordVisualization(tableVisualization)
        console.log('[handleResult] 设置表格可视化')
      } else if (resultData.type === 'image' || resultData.image) {
        const imageVisualization = {
          type: 'image',
          title: resultData.title || '图片',
          data: resultData.data || resultData.image
        }

        this.recordVisualization(imageVisualization)
        console.log('[handleResult] 设置图片可视化')
      } else if (resultData.type === 'text' || resultData.text) {
        const text = resultData.text || resultData.content || ''
        this.results.text = this.results.text ? `${this.results.text}\n${text}` : text

        const textVisualization = {
          type: 'text',
          title: resultData.title || '文本',
          content: text
        }

        this.recordVisualization(textVisualization)
        console.log('[handleResult] 设置文本可视化')
      } else {
        this.recordVisualization(resultData)
        console.log('[handleResult] 设置通用可视化')
      }

      this.hasResults = true
    },
    // 开始分析
    async startAnalysis(query, options = {}) {
      const {
        assistantMode = null,
        useFullChemistry = false,  // RACM2完整化学机理分析选项
        gridResolution = 21,  // 网格分辨率选项
        enableMultiExpert = false  // ✅ 是否启用多专家系统（通用Agent默认关闭）
      } = options

      if (!query.trim()) {
        return
      }

      // 首次分析或继续分析
      if (!this.sessionId) {
        this.createSessionId()
        this.sessionRound = 1
        this.finalAnswers = []
      } else {
        this.continueSession()
      }

      // 重置状态
      this.addMessage('user', query)
      this.currentMessage = ''
      this.isAnalyzing = true
      this.isComplete = false
      this.error = null
      this.iterations = 0

      // 如果是中断状态，传递给后端，然后重置标志
      const isInterruption = this.isInterruption
      if (isInterruption) {
        console.log('[ReAct] 检测到用户中断，将传递给后端')
        this.isInterruption = false  // 重置标志
      }

      // 重置Reflexion状态
      this.showReflexion = false
      this.reflexionCount = 0

      // 清空本轮结果
      this.results = {
        map: null,
        charts: [],
        tables: [],
        text: ''
      }

      try {
        // 调用ReAct Agent
        await agentAPI.analyze(query, {
          sessionId: this.sessionId,
          enhanceWithHistory: true,
          maxIterations: this.maxIterations,
          debugMode: this.debugMode,
          assistantMode: assistantMode,  // 传递助手模式
          useFullChemistry: useFullChemistry,  // RACM2完整化学机理分析选项
          gridResolution: gridResolution,  // 网格分辨率选项
          enableMultiExpert: enableMultiExpert,  // ✅ 传递多专家开关
          isInterruption: isInterruption,  // ✅ 传递中断标志
          onEvent: (event) => {
            this.handleEvent(event)
          }
        })
      } catch (error) {
        // 检查是否为用户主动取消
        if (error.name === 'AbortError' || error.message === 'The user aborted a request.') {
          console.log('分析已取消')
          // 取消不是错误，不需要设置error状态
          // isAnalyzing已在pauseAnalysis中设置为false
        } else {
          console.error('Analysis failed:', error)
          this.isAnalyzing = false
          this.error = error.message
          this.addMessage('error', `分析失败: ${error.message}`)
        }
      }
    },

    // 继续分析（新问题）
    async continueAnalysis(query, options = {}) {
      if (this.isAnalyzing) {
        const confirmStop = confirm('当前正在分析中，是否停止并开始新分析？')
        if (!confirmStop) {
          return
        }
        agentAPI.cancel()
        this.isAnalyzing = false
      }

      // 使用 startAnalysis，它会处理会话延续
      await this.startAnalysis(query, options)
    },

    // 停止分析
    stopAnalysis() {
      agentAPI.cancel()
      this.isAnalyzing = false
      // 不添加系统消息
    },

    // 暂停分析（与stopAnalysis相同）
    pauseAnalysis() {
      agentAPI.cancel()
      this.isAnalyzing = false
      this.isComplete = false
      this.error = null
      this.isInterruption = true  // 标记为中断状态
      // 不添加系统消息
    },

    // 切换调试模式
    toggleDebug() {
      this.debugMode = !this.debugMode
    },

    // 重新分析
    async restart() {
      this.reset()
    },

    // 【新增】在complete事件中直接处理visuals时的分类函数
    _classifyVizForComplete(viz) {
      const meta = viz.meta || {}
      const title = (viz.title || '').toLowerCase()
      const toolName = (meta.tool_name || '').toLowerCase()

      // 气象相关的关键词
      const weatherKeywords = ['轨迹', 'trajectory', '气象', 'weather', 'meteorology', '风向', 'wind', '上风向', 'upwind', 'hysplit', '后向轨迹', '反向轨迹', '高度剖面', 'profile']

      // 1. 优先使用有效的 expert_source
      if (meta.expert_source && ['weather', 'component'].includes(meta.expert_source)) {
        return meta.expert_source
      }

      // 2. 检查标题和工具名是否包含气象关键词
      for (const keyword of weatherKeywords) {
        if (title.includes(keyword.toLowerCase()) || toolName.includes(keyword.toLowerCase())) {
          return 'weather'
        }
      }

      // 3. 检查图表类型 - image类型如果是轨迹相关也归为weather
      if (viz.type === 'map' || viz.type === 'wind_rose' || viz.type === 'profile' ||
          viz.type === 'weather_timeseries' || viz.type === 'pressure_pbl_timeseries') {
        return 'weather'
      }

      // 4. 如果是image类型，根据工具名判断
      if (viz.type === 'image') {
        if (toolName.includes('trajectory') || toolName.includes('meteorological')) {
          return 'weather'
        }
      }

      // 5. 默认归类为 component
      return 'component'
    },

    // 【新增方法】从专家结果中提取visuals并传递给可视化面板
    _processExpertResultsForVisualization(expertResults) {
      if (!expertResults) {
        console.warn('[expert_result] 专家结果为空，跳过处理')
        return
      }

      // 防重复检查
      const expertResultsHash = JSON.stringify(expertResults)
      if (this._lastProcessedExpertResultsHash === expertResultsHash) {
        console.log('[processExpertResults] 跳过重复处理')
        return
      }
      this._lastProcessedExpertResultsHash = expertResultsHash

      console.log('[processExpertResults] 开始处理专家结果')
      console.log('[processExpertResults] expertResults keys:', Object.keys(expertResults))

      // 重置分组
      const groups = { weather: [], component: [] }

      // Schema类型映射表
      const weatherSchemas = ['weather', 'meteorology', 'meteorology_unified', 'trajectory', 'upwind_analysis', 'trajectory_simulation', 'hysplit']
      const componentSchemas = ['air_quality_unified', 'guangdong_stations', 'vocs_unified', 'vocs', 'pmf_result', 'obm_ofp_result', 'particulate_analysis']

      // 气象相关的关键词（用于标题和工具名匹配）
      const weatherKeywords = ['轨迹', 'trajectory', '气象', 'weather', 'meteorology', '风向', 'wind', '上风向', 'upwind', 'hysplit', '后向轨迹', '反向轨迹', '高度剖面', 'profile']

      // 分类函数
      const classifyViz = (viz) => {
        const meta = viz.meta || {}
        const title = (viz.title || '').toLowerCase()
        const toolName = (meta.tool_name || '').toLowerCase()

        // 1. 优先使用有效的 expert_source
        if (meta.expert_source && ['weather', 'component'].includes(meta.expert_source)) {
          return meta.expert_source
        }

        // 2. 检查标题和工具名是否包含气象关键词
        for (const keyword of weatherKeywords) {
          if (title.includes(keyword.toLowerCase()) || toolName.includes(keyword.toLowerCase())) {
            return 'weather'
          }
        }

        // 3. 从 source_data_ids 解析
        if (meta.source_data_ids?.length > 0) {
          const schemaType = meta.source_data_ids[0].split(':')[0]
          if (weatherSchemas.includes(schemaType)) return 'weather'
          if (componentSchemas.includes(schemaType)) return 'component'
        }

        // 4. 检查图表类型 - 【新增】image类型如果是轨迹相关也归为weather
        if (viz.type === 'map' || viz.type === 'wind_rose' || viz.type === 'profile' ||
            viz.type === 'weather_timeseries' || viz.type === 'pressure_pbl_timeseries') {
          return 'weather'
        }

        // 【新增】如果是image类型，根据工具名判断
        if (viz.type === 'image') {
          if (toolName.includes('trajectory') || toolName.includes('meteorological')) {
            return 'weather'
          }
        }

        // 5. 默认归类为 component
        return 'component'
      }

      // 一次性遍历并分类
      for (const [expertType, expertData] of Object.entries(expertResults)) {
        console.log(`[processExpertResults] 处理专家: ${expertType}`)
        const toolResults = expertData.tool_results || []
        console.log(`[processExpertResults] 工具数量: ${toolResults.length}`)

        for (const toolResult of toolResults) {
          const result = toolResult.result || toolResult.data || toolResult
          if (!result) {
            console.log(`[processExpertResults] 工具 ${toolResult.tool} result为空，跳过`)
            continue
          }

          console.log(`[processExpertResults] 工具 ${toolResult.tool}: result type=${result.type}, visuals=`, result.visuals)

          // 提取 visuals
          // 兼容两种格式：VisualBlock格式 和 直接格式（EKMA专业图表等）
          const visuals = result.visuals || []
          console.log(`[processExpertResults] 提取到 ${visuals.length} 个visuals`)

          for (const visualBlock of visuals) {
            console.log(`[processExpertResults] 处理visual: id=${visualBlock.id || visualBlock.payload?.id}, type=${visualBlock.type || visualBlock.payload?.type}`)

            let viz
            if (visualBlock.payload) {
              // VisualBlock格式: {payload: {...}, meta: {...}}
              viz = {
                ...visualBlock.payload,
                meta: {
                  ...visualBlock.meta,
                  tool_name: toolResult.tool || toolResult.tool_name,
                  schema_version: 'v2.0'
                }
              }
            } else {
              // 直接格式: {id, type, data, meta, ...} (如EKMA专业图表)
              viz = {
                ...visualBlock,
                meta: {
                  ...visualBlock.meta,
                  tool_name: toolResult.tool || toolResult.tool_name,
                  schema_version: 'v2.0'
                }
              }
            }

            // 分类并存储
            const targetGroup = classifyViz(viz)
            console.log(`[processExpertResults] 分类结果: ${viz.id} -> ${targetGroup}`)
            viz.meta.expert_source = targetGroup  // 确保 meta 中有正确的分类
            groups[targetGroup].push(viz)
            this.visualizationHistory.push(viz)
          }

          // 兼容直接的可视化格式（包括EKMA专业图表的image类型）
          if (result.type && ['map', 'chart', 'pie', 'bar', 'line', 'timeseries', 'radar', 'profile', 'wind_rose', 'weather_timeseries', 'pressure_pbl_timeseries', 'heatmap', 'image'].includes(result.type)) {
            console.log(`[processExpertResults] 处理直接格式: type=${result.type}`)
            const viz = {
              ...result,
              meta: {
                ...result.meta,
                tool_name: toolResult.tool || toolResult.tool_name,
                schema_version: 'v2.0'
              }
            }
            const targetGroup = classifyViz(viz)
            console.log(`[processExpertResults] 直接格式分类: ${result.type} -> ${targetGroup}`)
            viz.meta.expert_source = targetGroup
            groups[targetGroup].push(viz)
            this.visualizationHistory.push(viz)
          }
        }
      }

      // 更新分组状态
      this.groupedVisualizations = groups
      this.expertResults = expertResults
      this.lastExpertResults = { expert_results: expertResults }

      console.log(`[processExpertResults] 完成: weather=${groups.weather.length}, component=${groups.component.length}`)
      console.log(`[processExpertResults] weather图表详情:`, groups.weather.map(v => ({ id: v.id, type: v.type, title: v.title })))
    }
  }
})
