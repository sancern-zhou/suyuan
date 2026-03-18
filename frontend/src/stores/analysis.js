import { defineStore } from 'pinia'

export const useAnalysisStore = defineStore('analysis', {
  state: () => ({
    // 对话
    messages: [],
    input: '',

    // 分析状态
    status: 'idle',
    isAnalyzing: false,
    cancelToken: null,  // 取消令牌

    // 调试
    debugEnabled: false,
    currentContext: '',
    toolCalls: [],

    // 可视化
    currentVisualization: null,
    visualizationHistory: [],

    // 报告
    reportData: null,
    hasReport: false,
  }),

  getters: {
    latestMessage: (state) => state.messages[state.messages.length - 1],

    canInput: (state) => true, // 始终可输入，支持打断
  },

  actions: {
    addMessage(message) {
      const newMessage = {
        ...message,
        id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        timestamp: new Date().toISOString()
      }
      this.messages.push(newMessage)
      return newMessage.id
    },

    // 暂停分析
    pauseAnalysis() {
      if (!this.isAnalyzing) return

      // 标记为已取消
      if (this.cancelToken) {
        this.cancelToken.cancelled = true
        if (this.cancelToken.timeout) {
          clearTimeout(this.cancelToken.timeout)
        }
      }

      this.status = 'idle'
      this.isAnalyzing = false
      this.cancelToken = null

      this.addMessage({
        type: 'agent',
        content: '分析已暂停'
      })
    },

    updateMessage(id, updates) {
      const index = this.messages.findIndex(m => m.id === id)
      if (index !== -1) {
        this.messages[index] = { ...this.messages[index], ...updates }
      }
    },

    async startAnalysis(query) {
      // 添加用户消息
      this.addMessage({
        type: 'user',
        content: query
      })

      this.status = 'running'
      this.isAnalyzing = true
      this.cancelToken = { cancelled: false }

      try {
        await this.analyze(query, this.cancelToken)
        if (!this.cancelToken.cancelled) {
          this.status = 'completed'
          this.hasReport = true
        }
      } catch (error) {
        if (!this.cancelToken.cancelled) {
          console.error('分析失败:', error)
          this.status = 'error'
          this.addMessage({
            type: 'agent',
            content: `分析失败: ${error.message}`
          })
        }
      } finally {
        if (!this.cancelToken.cancelled) {
          this.isAnalyzing = false
          this.cancelToken = null
        }
      }
    },

    async analyze(query, cancelToken) {
      // 模拟分析流程
      this.addMessage({
        type: 'agent',
        content: '我正在分析您的查询。这需要几个步骤...'
      })

      await this.sleep(1000, cancelToken)

      // 检查是否被取消
      if (cancelToken.cancelled) return

      // 获取数据
      this.addMessage({
        type: 'agent',
        content: '步骤1: 获取监测数据...\n已成功获取数据',
        debugInfo: this.debugEnabled ? '工具调用: get_monitoring_data\n参数: {station: "天河站", pollutant: "O3", date: "2025-11-01"}' : undefined
      })

      await this.sleep(1500, cancelToken)

      // 检查是否被取消
      if (cancelToken.cancelled) return

      // 分析风向
      this.addMessage({
        type: 'agent',
        content: '步骤2: 分析风向数据...\n主导风向: 东南风',
        debugInfo: this.debugEnabled ? '工具调用: get_wind_data\n参数: {station: "天河站", date: "2025-11-01"}' : undefined
      })

      await this.sleep(1500, cancelToken)

      // 检查是否被取消
      if (cancelToken.cancelled) return

      // 生成可视化
      this.currentVisualization = {
        type: 'chart',
        title: '污染浓度分析',
        data: {
          xData: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'],
          series: [120, 150, 185, 170, 145, 110]
        }
      }

      // 最终总结
      this.addMessage({
        type: 'agent',
        content: '分析完成。峰值浓度185 μg/m³，主导风向东南风，主要污染源为工业排放。建议加强上风向企业监管。'
      })
    },

    setVisualization(content) {
      this.currentVisualization = content
      if (content) {
        this.visualizationHistory.push(content)
      }
    },

    addToolCall(call) {
      const newCall = {
        ...call,
        id: `call-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        timestamp: new Date().toISOString()
      }
      this.toolCalls.push(newCall)
      return newCall.id
    },

    updateToolCall(id, updates) {
      const index = this.toolCalls.findIndex(c => c.id === id)
      if (index !== -1) {
        this.toolCalls[index] = { ...this.toolCalls[index], ...updates }
      }
    },

    setLlmContext(context) {
      this.currentContext = context
    },

    toggleDebug() {
      this.debugEnabled = !this.debugEnabled
    },

    generateReport() {
      return `
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="UTF-8">
        <title>大气污染溯源分析报告</title>
        <style>
          body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px;
            color: #333;
            line-height: 1.6;
          }
          .header {
            border-bottom: 3px solid #1976D2;
            padding-bottom: 20px;
            margin-bottom: 30px;
          }
          .header h1 {
            color: #1976D2;
            margin: 0 0 10px 0;
            font-size: 32px;
          }
          .meta {
            color: #666;
            font-size: 14px;
          }
          .section {
            margin: 30px 0;
          }
          .section h2 {
            color: #1976D2;
            font-size: 24px;
            margin-bottom: 16px;
          }
          .kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin: 20px 0;
          }
          .kpi-card {
            background: #F5F5F5;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #1976D2;
          }
          .kpi-card h3 {
            margin: 0 0 8px 0;
            font-size: 14px;
            color: #666;
            font-weight: 500;
          }
          .kpi-card p {
            margin: 0;
            font-size: 28px;
            font-weight: 600;
            color: #1976D2;
          }
          .chart-container {
            margin: 20px 0;
            min-height: 400px;
            background: #F5F5F5;
            border-radius: 8px;
            padding: 20px;
          }
          .conclusion {
            background: #E3F2FD;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #1976D2;
          }
        </style>
      </head>
      <body>
        <div class="header">
          <h1>大气污染溯源分析报告</h1>
          <div class="meta">
            <p>生成时间：${new Date().toLocaleString()}</p>
            <p>分析系统：风清气智Agent v2.0</p>
          </div>
        </div>

        <div class="section">
          <h2>执行摘要</h2>
          <p>根据监测数据分析，广州天河站2025-11-01的O3污染情况如下：</p>
          <ul>
            <li>峰值浓度：185 μg/m³</li>
            <li>超标时段：4小时</li>
            <li>主导风向：东南风</li>
            <li>主要污染源：工业排放</li>
          </ul>
        </div>

        <div class="section">
          <h2>关键指标</h2>
          <div class="kpi-grid">
            <div class="kpi-card">
              <h3>峰值浓度</h3>
              <p>185 μg/m³</p>
            </div>
            <div class="kpi-card">
              <h3>超标时段</h3>
              <p>4小时</p>
            </div>
            <div class="kpi-card">
              <h3>主风向</h3>
              <p>东南风</p>
            </div>
            <div class="kpi-card">
              <h3>主要污染源</h3>
              <p>工业排放</p>
            </div>
          </div>
        </div>

        <div class="section">
          <h2>结论与建议</h2>
          <div class="conclusion">
            <p>1. 本次O3污染主要受工业排放影响，建议加强上风向企业监管</p>
            <p>2. 污染峰值出现在下午时段，与日照强度相关</p>
            <p>3. 建议采取错峰生产、限产等措施</p>
          </div>
        </div>
      </body>
      </html>
      `
    },

    openReport() {
      const reportWindow = window.open('', '_blank')
      reportWindow.document.write(this.generateReport())
      reportWindow.document.close()
    },

    sleep(ms, cancelToken) {
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          if (!cancelToken?.cancelled) {
            resolve()
          } else {
            reject(new Error('分析已取消'))
          }
        }, ms)

        // 存储超时ID，以便取消
        if (cancelToken) {
          cancelToken.timeout = timeout
        }
      })
    }
  }
})
