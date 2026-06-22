import assert from 'node:assert/strict'
import test from 'node:test'

function applyDashboardMetadata(state, data = {}) {
  const focus = data?.dashboard_focus ||
    data?.metadata?.dashboard_focus ||
    data?.result?.dashboard_focus ||
    data?.result?.metadata?.dashboard_focus ||
    null
  const evidence = data?.answer_evidence ||
    data?.metadata?.answer_evidence ||
    data?.result?.answer_evidence ||
    data?.result?.metadata?.answer_evidence ||
    null

  if (focus) {
    state.dashboardFocus = focus
  }
  if (evidence) {
    state.answerEvidence = evidence
  }
  return state
}

test('query dashboard metadata can be applied without losing final answer', () => {
  const state = {
    finalAnswer: '广州臭氧偏高',
    dashboardFocus: null,
    answerEvidence: null
  }

  applyDashboardMetadata(state, {
    dashboard_focus: { scope: 'city', cities: ['广州'] },
    answer_evidence: { claims: [{ text: 'O3 偏高' }] }
  })

  assert.equal(state.finalAnswer, '广州臭氧偏高')
  assert.deepEqual(state.dashboardFocus, { scope: 'city', cities: ['广州'] })
  assert.deepEqual(state.answerEvidence, { claims: [{ text: 'O3 偏高' }] })
})

test('query dashboard metadata can be read from nested metadata paths', () => {
  const state = { dashboardFocus: null, answerEvidence: null }

  applyDashboardMetadata(state, {
    result: {
      metadata: {
        dashboard_focus: { scope: 'station', stations: ['麓湖'] },
        answer_evidence: { claims: [{ text: '站点 AQI 可追溯' }] }
      }
    }
  })

  assert.deepEqual(state.dashboardFocus, { scope: 'station', stations: ['麓湖'] })
  assert.deepEqual(state.answerEvidence, { claims: [{ text: '站点 AQI 可追溯' }] })
})

test('query dashboard metadata keeps existing values when payload omits them', () => {
  const state = {
    dashboardFocus: { scope: 'province' },
    answerEvidence: { claims: [{ text: '保留既有证据' }] }
  }

  applyDashboardMetadata(state, { result: { metadata: {} } })

  assert.deepEqual(state.dashboardFocus, { scope: 'province' })
  assert.deepEqual(state.answerEvidence, { claims: [{ text: '保留既有证据' }] })
})
