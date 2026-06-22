import assert from 'node:assert/strict'
import test from 'node:test'

import { createPinia, setActivePinia } from 'pinia'
import {
  applyQueryDashboardMetadata,
  extractAnswerEvidence,
  extractDashboardFocus,
  useReactStore
} from './reactStore.js'

test('query dashboard metadata can be applied without losing final answer', () => {
  const state = {
    finalAnswer: '广州臭氧偏高',
    dashboardFocus: null,
    answerEvidence: null
  }

  applyQueryDashboardMetadata(state, {
    dashboard_focus: { scope: 'city', cities: ['广州'] },
    answer_evidence: { claims: [{ text: 'O3 偏高' }] }
  })

  assert.equal(state.finalAnswer, '广州臭氧偏高')
  assert.deepEqual(state.dashboardFocus, { scope: 'city', cities: ['广州'] })
  assert.deepEqual(state.answerEvidence, { claims: [{ text: 'O3 偏高' }] })
})

test('query dashboard metadata can be read from nested metadata paths', () => {
  const state = { dashboardFocus: null, answerEvidence: null }

  const data = {
    result: {
      metadata: {
        dashboard_focus: { scope: 'station', stations: ['麓湖'] },
        answer_evidence: { claims: [{ text: '站点 AQI 可追溯' }] }
      }
    }
  }

  applyQueryDashboardMetadata(state, data)

  assert.deepEqual(state.dashboardFocus, { scope: 'station', stations: ['麓湖'] })
  assert.deepEqual(state.answerEvidence, { claims: [{ text: '站点 AQI 可追溯' }] })
  assert.deepEqual(extractDashboardFocus(data), { scope: 'station', stations: ['麓湖'] })
  assert.deepEqual(extractAnswerEvidence(data), { claims: [{ text: '站点 AQI 可追溯' }] })
})

test('query dashboard metadata keeps existing values when payload omits them', () => {
  const state = {
    dashboardFocus: { scope: 'province' },
    answerEvidence: { claims: [{ text: '保留既有证据' }] }
  }

  applyQueryDashboardMetadata(state, { result: { metadata: {} } })

  assert.deepEqual(state.dashboardFocus, { scope: 'province' })
  assert.deepEqual(state.answerEvidence, { claims: [{ text: '保留既有证据' }] })
})

test('complete event writes nested dashboard metadata to final message data', () => {
  const storage = new Map()
  globalThis.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
    clear: () => storage.clear()
  }

  setActivePinia(createPinia())
  const store = useReactStore()
  const originalLog = console.log
  const originalWarn = console.warn
  console.log = () => {}
  console.warn = () => {}

  try {
    store.handleEvent({
      type: 'complete',
      data: {
        mode: 'query',
        response: '广州臭氧偏高',
        result: {
          metadata: {
            dashboard_focus: { scope: 'city', cities: ['广州'] },
            answer_evidence: { claims: [{ text: 'O3 偏高' }] }
          }
        }
      }
    })
  } finally {
    console.log = originalLog
    console.warn = originalWarn
  }

  const finalMessage = store.modeStates.query.messages.find(message => message.type === 'final')
  assert.deepEqual(store.modeStates.query.dashboardFocus, { scope: 'city', cities: ['广州'] })
  assert.deepEqual(store.modeStates.query.answerEvidence, { claims: [{ text: 'O3 偏高' }] })
  assert.deepEqual(finalMessage?.data?.dashboard_focus, { scope: 'city', cities: ['广州'] })
  assert.deepEqual(finalMessage?.data?.answer_evidence, { claims: [{ text: 'O3 偏高' }] })
})
