// ReAct Agent API测试脚本
// 验证前后端交互是否顺畅

const API_BASE_URL = 'http://localhost:8000/api'

class ReactAgentTest {
  constructor() {
    this.passed = 0
    this.failed = 0
    this.tests = []
  }

  // 记录测试
  test(name, fn) {
    this.tests.push({ name, fn })
  }

  // 运行所有测试
  async run() {
    console.log('🚀 开始测试ReAct Agent API\n')
    console.log('='.repeat(50))

    for (const { name, fn } of this.tests) {
      try {
        await fn()
        this.passed++
        console.log(`✅ ${name}`)
      } catch (error) {
        this.failed++
        console.log(`❌ ${name}`)
        console.log(`   Error: ${error.message}`)
      }
    }

    console.log('='.repeat(50))
    console.log(`\n📊 测试结果: ${this.passed} 通过, ${this.failed} 失败\n`)

    return this.failed === 0
  }

  // 通用请求方法
  async request(url, options = {}) {
    const response = await fetch(url, options)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }
    return response
  }

  // 测试健康检查
  testHealthCheck() {
    this.test('健康检查', async () => {
      const response = await this.request(`${API_BASE_URL}/agent/health`)
      const data = await response.json()

      if (data.status !== 'healthy') {
        throw new Error(`Expected status 'healthy', got '${data.status}'`)
      }

      if (data.agent_type !== 'ReAct Agent') {
        throw new Error(`Expected agent_type 'ReAct Agent', got '${data.agent_type}'`)
      }

      console.log('   Response:', JSON.stringify(data, null, 2))
    })
  }

  // 测试工具列表
  testGetTools() {
    this.test('获取工具列表', async () => {
      const response = await this.request(`${API_BASE_URL}/agent/tools`)
      const data = await response.json()

      if (!data.tools || !Array.isArray(data.tools)) {
        throw new Error('Expected tools to be an array')
      }

      if (data.count !== data.tools.length) {
        throw new Error(`Count mismatch: ${data.count} vs ${data.tools.length}`)
      }

      console.log(`   Found ${data.count} tools:`, data.tools.slice(0, 3).join(', '), '...')
    })
  }

  // 测试流式分析
  testStreamAnalysis() {
    this.test('流式分析（SSE）', async () => {
      const query = '分析广州天河站2025-11-01的O3污染情况'

      const response = await fetch(`${API_BASE_URL}/agent/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query,
          max_iterations: 3,
          debug_mode: false
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      if (!response.body) {
        throw new Error('Response body is null')
      }

      // 检查是否为流式响应
      const contentType = response.headers.get('content-type')
      if (!contentType || !contentType.includes('text/event-stream')) {
        throw new Error(`Expected text/event-stream, got ${contentType}`)
      }

      console.log('   ✓ Content-Type: text/event-stream')

      // 读取前几个事件
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let eventCount = 0
      let eventTypes = new Set()

      while (eventCount < 5) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (data) {
              try {
                const event = JSON.parse(data)
                eventTypes.add(event.type)
                eventCount++
                console.log(`   Event ${eventCount}: ${event.type}`)
              } catch (e) {
                // 忽略解析错误
              }
            }
          }
        }
      }

      if (eventTypes.size === 0) {
        throw new Error('No events received')
      }

      console.log(`   ✓ Received ${eventCount} events`)
      console.log(`   ✓ Event types: ${Array.from(eventTypes).join(', ')}`)
    })
  }

  // 测试简单查询
  testSimpleQuery() {
    this.test('简单查询（非流式）', async () => {
      const query = '什么是O3污染？'

      const response = await this.request(`${API_BASE_URL}/agent/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query,
          max_iterations: 3
        })
      })

      const data = await response.json()

      if (!data.answer) {
        throw new Error('Expected answer in response')
      }

      if (!data.session_id) {
        throw new Error('Expected session_id in response')
      }

      if (typeof data.completed !== 'boolean') {
        throw new Error('Expected completed to be boolean')
      }

      console.log('   Answer length:', data.answer.length, 'chars')
      console.log('   Session ID:', data.session_id)
      console.log('   Completed:', data.completed)
    })
  }

  // 测试错误处理
  testErrorHandling() {
    this.test('错误处理', async () => {
      try {
        // 发送空查询
        const response = await this.request(`${API_BASE_URL}/agent/query`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            query: '',
            max_iterations: 3
          })
        })

        // 如果没有抛出错误，检查响应
        const data = await response.json()
        console.log('   Response:', data)
      } catch (error) {
        // 期望的错误
        console.log('   ✓ Error handled correctly:', error.message)
      }
    })
  }
}

// 创建测试实例并运行
const tester = new ReactAgentTest()

// 添加测试用例
tester.testHealthCheck()
tester.testGetTools()
tester.testStreamAnalysis()
tester.testSimpleQuery()
tester.testErrorHandling()

// 运行测试
tester.run().then(success => {
  if (success) {
    console.log('🎉 所有测试通过！前后端交互正常。')
    process.exit(0)
  } else {
    console.log('⚠️  部分测试失败，请检查API。')
    process.exit(1)
  }
}).catch(error => {
  console.error('❌ 测试执行失败:', error)
  process.exit(1)
})
