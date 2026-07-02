import assert from 'node:assert/strict'
import test from 'node:test'

import { createPinia, setActivePinia } from 'pinia'
import {
  applyMapProgramMetadata,
  useReactStore
} from './reactStore.js'

test('map program metadata can be applied without losing final answer', () => {
  const state = {
    finalAnswer: '广州臭氧偏高',
    mapPrograms: [],
    currentMapProgram: null
  }
  const program = {
    type: 'map_program',
    program_id: 'mapprog_city',
    intent: '定位广州',
    state: { view: { center: [113.2644, 23.1291], zoom: 10 }, layers: [] }
  }

  applyMapProgramMetadata(state, { map_program: program })

  assert.equal(state.finalAnswer, '广州臭氧偏高')
  assert.equal(state.currentMapProgram.program_id, 'mapprog_city')
  assert.equal(state.mapPrograms.length, 1)
})

test('map program metadata can be read from nested metadata paths', () => {
  const state = { mapPrograms: [], currentMapProgram: null }
  const program = {
    type: 'map_program',
    program_id: 'mapprog_station',
    intent: '显示站点',
    state: { layers: [] }
  }

  const data = {
    result: {
      metadata: {
        map_program: program
      }
    }
  }

  applyMapProgramMetadata(state, data)

  assert.equal(state.currentMapProgram.program_id, 'mapprog_station')
  assert.equal(state.mapPrograms.length, 1)
})

test('map program metadata keeps existing values when payload omits map program', () => {
  const state = {
    mapPrograms: [],
    currentMapProgram: {
      type: 'map_program',
      program_id: 'mapprog_existing',
      intent: '已有地图',
      state: { layers: [] }
    }
  }

  applyMapProgramMetadata(state, { result: { metadata: {} } })

  assert.equal(state.currentMapProgram.program_id, 'mapprog_existing')
  assert.equal(state.mapPrograms.length, 0)
})

test('query voice output can be stopped explicitly', () => {
  const storage = new Map()
  globalThis.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
    clear: () => storage.clear()
  }

  setActivePinia(createPinia())
  const store = useReactStore()
  let stopped = false
  store.modeStates.query.queryVoicePlayback = {
    streamed: true,
    queue: {
      stop() {
        stopped = true
      }
    }
  }

  store.stopQueryVoiceOutput()

  assert.equal(stopped, true)
  assert.equal(store.modeStates.query.queryVoicePlayback, null)
})

test('complete event ignores dashboard metadata fields on final message data', () => {
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
  assert.equal('dashboardFocus' in store.modeStates.query, false)
  assert.equal('answerEvidence' in store.modeStates.query, false)
  assert.equal(finalMessage?.data?.dashboard_focus, undefined)
  assert.equal(finalMessage?.data?.answer_evidence, undefined)
})
