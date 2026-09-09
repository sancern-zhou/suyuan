import test from 'node:test'
import assert from 'node:assert/strict'

import {
  SMART_EVENT_WORKSPACE_COMMANDS,
  applySmartEventWorkspaceCommand,
  createSmartEventWorkspaceState,
  toSmartEventAgentContext,
  extractSmartEventWorkspaceCommand,
} from './jiangsuSmartEventWorkspace.js'

test('opens a detail view and preserves the focus requested by the Agent', () => {
    const state = applySmartEventWorkspaceCommand(
      createSmartEventWorkspaceState({ taskId: 'task-1' }),
      { type: SMART_EVENT_WORKSPACE_COMMANDS.OPEN_DETAIL, event_id: 'event-1', focus: 'monitoring_data' },
    )
    assert.equal(state.mode, 'detail')
    assert.equal(state.eventId, 'event-1')
    assert.equal(state.focus, 'monitoring_data')
    assert.equal(state.taskId, 'task-1')
})

test('converts an Agent list query to a workspace context', () => {
    const state = applySmartEventWorkspaceCommand(
      createSmartEventWorkspaceState(),
      { type: SMART_EVENT_WORKSPACE_COMMANDS.SHOW_LIST, query: { status: '待人工确认', level: ['P0', 'P1'] } },
    )
    assert.equal(state.filters.status, '待人工确认')
    assert.deepEqual(toSmartEventAgentContext(state), {
      event_id: null,
      event_ids: [],
      task_id: null,
      conversation_id: null,
      workspace_mode: 'list',
      focus: null,
      filters: { status: '待人工确认', level: ['P0', 'P1'] },
    })
})

test('rejects an invalid compare command without changing the current view', () => {
    const state = createSmartEventWorkspaceState({ mode: 'detail', eventId: 'event-1' })
    const next = applySmartEventWorkspaceCommand(state, {
      type: SMART_EVENT_WORKSPACE_COMMANDS.COMPARE_EVENTS,
      event_ids: ['event-1'],
    })
    assert.equal(next, state)
})

test('focuses evidence and selects the event supplied by the Agent', () => {
    const state = applySmartEventWorkspaceCommand(
      createSmartEventWorkspaceState(),
      { type: SMART_EVENT_WORKSPACE_COMMANDS.FOCUS_EVIDENCE, event_id: 'event-2', focus: 'timeline' },
    )
    assert.equal(state.mode, 'evidence')
    assert.equal(state.eventId, 'event-2')
    assert.equal(state.focus, 'timeline')
})

test('extracts the latest Agent right-panel command from a tool result', () => {
  const command = extractSmartEventWorkspaceCommand([
    { type: 'tool_result', data: { result: { data: { ui_command: { type: 'show_event_list' } } } } },
    { type: 'tool_result', data: { result: { data: { ui_command: { type: 'open_event_detail', event_id: 'alarm:9' } } } } },
  ])
  assert.deepEqual(command, { type: 'open_event_detail', event_id: 'alarm:9' })
})
