// State and command contract shared by the device-control conversation and the
// right-side 远程质控 panel.  The panel is display-only: command execution still
// requires the user's explicit confirmation in the chat flow.

export const DEVICE_CONTROL_WORKSPACE_COMMAND = 'device_control_workspace'

export const DEVICE_CONTROL_WORKSPACE_STEPS = Object.freeze({
  STATE: 'state',
  PREPARE: 'prepare',
  BLOCKED: 'blocked',
  EXECUTE: 'execute',
})

const STEP_ORDER = [DEVICE_CONTROL_WORKSPACE_STEPS.STATE, DEVICE_CONTROL_WORKSPACE_STEPS.PREPARE, DEVICE_CONTROL_WORKSPACE_STEPS.BLOCKED, DEVICE_CONTROL_WORKSPACE_STEPS.EXECUTE]

export function createDeviceControlWorkspaceState(overrides = {}) {
  return {
    station: null,
    command: null,
    latestStep: null,
    history: [],
    ...overrides,
  }
}

function commandKey(command) {
  try {
    return JSON.stringify(command)
  } catch {
    return `${command?.step || ''}:${command?.occurred_at || ''}`
  }
}

export function applyDeviceControlWorkspaceCommand(state, command) {
  const current = state || createDeviceControlWorkspaceState()
  if (!command || typeof command !== 'object') return current
  if (command.type !== DEVICE_CONTROL_WORKSPACE_COMMAND) return current
  const key = commandKey(command)
  if ((current.history || []).some(item => item.key === key)) return current
  const entry = { key, step: command.step || null, command }
  const station = command.station || current.station
  const commandSummary = command.command || current.command
  return {
    ...current,
    station,
    command: commandSummary,
    latestStep: entry.step,
    history: [...(current.history || []), entry].slice(-30),
  }
}

export function stepRank(step) {
  const index = STEP_ORDER.indexOf(step)
  return index === -1 ? STEP_ORDER.length : index
}

// Tool results are the transport boundary for Agent-driven right-panel
// navigation.  Keep parsing tolerant so persisted messages from older clients
// can use either result.data.ui_command or result.ui_command.
export function extractDeviceControlWorkspaceCommand(messages = []) {
  for (const message of [...messages].reverse()) {
    if (message?.type !== 'tool_result') continue
    const result = message.data?.result || {}
    const command = result.data?.ui_command || result.ui_command
    if (command && typeof command === 'object' && command.type === DEVICE_CONTROL_WORKSPACE_COMMAND) {
      return command
    }
  }
  return null
}

// Rebuild the full process history from the message log so restored sessions
// render the same timeline as the live conversation.
export function collectDeviceControlWorkspaceCommands(messages = []) {
  const commands = []
  for (const message of messages || []) {
    if (message?.type !== 'tool_result') continue
    const result = message.data?.result || {}
    const command = result.data?.ui_command || result.ui_command
    if (command && typeof command === 'object' && command.type === DEVICE_CONTROL_WORKSPACE_COMMAND) {
      commands.push(command)
    }
  }
  return commands
}
