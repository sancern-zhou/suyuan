import test from 'node:test'
import assert from 'node:assert/strict'

import {
  DEVICE_CONTROL_WORKSPACE_COMMAND,
  DEVICE_CONTROL_WORKSPACE_STEPS,
  applyDeviceControlWorkspaceCommand,
  createDeviceControlWorkspaceState,
  collectDeviceControlWorkspaceCommands,
  extractDeviceControlWorkspaceCommand,
} from './jiangsuDeviceControlWorkspace.js'

const station = { station_id: '320100001', station_name: '鼓楼', resolved_by: 'station_directory' }

test('applies a prepare command as a confirmation-card step', () => {
  const state = applyDeviceControlWorkspaceCommand(
    createDeviceControlWorkspaceState(),
    {
      type: DEVICE_CONTROL_WORKSPACE_COMMAND,
      step: DEVICE_CONTROL_WORKSPACE_STEPS.PREPARE,
      station,
      command: '站点 320100001：O3质控阀开启',
      expires_at: '2026-09-17T08:00:00+00:00',
      confirmation_token: 'token-1',
    },
  )
  assert.equal(state.latestStep, DEVICE_CONTROL_WORKSPACE_STEPS.PREPARE)
  assert.equal(state.station.station_name, '鼓楼')
  assert.equal(state.command, '站点 320100001：O3质控阀开启')
  assert.equal(state.history.length, 1)
})

test('ignores foreign commands and duplicate replays', () => {
  const base = createDeviceControlWorkspaceState()
  assert.equal(applyDeviceControlWorkspaceCommand(base, { type: 'open_event_detail' }), base)
  const command = { type: DEVICE_CONTROL_WORKSPACE_COMMAND, step: 'state', station, success: true }
  const once = applyDeviceControlWorkspaceCommand(base, command)
  assert.equal(applyDeviceControlWorkspaceCommand(once, command), once)
})

test('extracts the latest device-control command from a tool result', () => {
  const command = extractDeviceControlWorkspaceCommand([
    { type: 'tool_result', data: { result: { data: { ui_command: { type: 'show_event_list' } } } } },
    { type: 'tool_result', data: { result: { data: { ui_command: { type: DEVICE_CONTROL_WORKSPACE_COMMAND, step: 'execute', accepted: true } } } } },
    { type: 'tool_result', data: { result: { data: { ui_command: { type: DEVICE_CONTROL_WORKSPACE_COMMAND, step: 'prepare', command: '空调设为制冷 24℃' } } } } },
  ])
  assert.equal(command.type, DEVICE_CONTROL_WORKSPACE_COMMAND)
  assert.equal(command.step, DEVICE_CONTROL_WORKSPACE_STEPS.PREPARE)
})

test('collects the full process history from the message log in order', () => {
  const messages = [
    { type: 'user', data: { content: '读取鼓楼站设备状态' } },
    { type: 'tool_result', data: { result: { data: { ui_command: { type: DEVICE_CONTROL_WORKSPACE_COMMAND, step: 'state', station, success: true } } } } },
    { type: 'tool_result', data: { result: { data: { ui_command: { type: DEVICE_CONTROL_WORKSPACE_COMMAND, step: 'prepare', station, command: '空调设为制冷 24℃' } } } } },
    { type: 'tool_result', data: { result: { data: { ui_command: { type: DEVICE_CONTROL_WORKSPACE_COMMAND, step: 'execute', station, command: '空调设为制冷 24℃', accepted: true, readback_available: true } } } } },
  ]
  const commands = collectDeviceControlWorkspaceCommands(messages)
  assert.deepEqual(commands.map(item => item.step), ['state', 'prepare', 'execute'])

  let state = createDeviceControlWorkspaceState()
  for (const command of commands) {
    state = applyDeviceControlWorkspaceCommand(state, command)
  }
  assert.equal(state.latestStep, DEVICE_CONTROL_WORKSPACE_STEPS.EXECUTE)
  assert.equal(state.history.length, 3)
})
