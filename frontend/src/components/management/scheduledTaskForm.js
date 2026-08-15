export const selectableWeixinUsers = (users = []) => users.filter(user =>
  user.status === 'active' &&
  Boolean(user.social_user_id) &&
  String(user.channel || '').startsWith('weixin')
)


export const buildExecutionModeOptions = (
  projectModes = [],
  currentMode = '',
) => {
  const options = projectModes.map(mode => ({
    value: mode.id,
    label: `${mode.id}（${mode.shortName || mode.name || mode.id}）`
  }))
  options.push(
    { value: 'social', label: 'social（社交任务）' },
    { value: 'custom', label: 'custom（自选工具）' }
  )
  if (currentMode && !options.some(option => option.value === currentMode)) {
    options.push({ value: currentMode, label: `${currentMode}（当前任务模式）` })
  }
  return options.filter((option, index, values) => (
    values.findIndex(candidate => candidate.value === option.value) === index
  ))
}


export const applyTriggerDefaults = (form, triggerType, eventTypes = []) => {
  form.trigger_type = triggerType
  if (triggerType === 'event') {
    form.execution_mode = 'social'
    form.tool_names = []
    form.broadcast_enabled = true
    if (!form.event_type && eventTypes.length > 0) {
      form.event_type = eventTypes[0].event_type
    }
  }
  return form
}


export const applyExecutionMode = (form, mode) => {
  form.execution_mode = mode
  if (mode !== 'custom') form.tool_names = []
  return form
}


export const buildTaskPayload = (form) => {
  const isEvent = form.trigger_type === 'event'
  const payload = {
    name: String(form.name || '').trim(),
    description: String(form.description || '').trim(),
    execution_mode: form.execution_mode || 'assistant',
    skill_id: String(form.skill_id || '').trim() || null,
    trigger_type: isEvent ? 'event' : 'schedule',
    schedule_type: isEvent ? null : form.schedule_type,
    event_type: isEvent ? form.event_type : null,
    event_filters: isEvent ? (form.event_filters || {}) : {},
    broadcast_enabled: Boolean(form.broadcast_enabled),
    target_user_ids: form.broadcast_enabled ? [...(form.target_user_ids || [])] : [],
    enabled: Boolean(form.enabled),
    steps: [{
      step_id: 'step_1',
      description: String(form.description || '').trim(),
      agent_prompt: String(form.agent_prompt || form.description || '').trim(),
      timeout_seconds: isEvent ? 1800 : 600,
      retry_on_failure: false
    }],
    tags: String(form.tagsText || '')
      .split(',')
      .map(tag => tag.trim())
      .filter(Boolean)
  }

  payload.workspace_entry = {
    enabled: Boolean(form.workspaceEntryEnabled),
    title: String(form.workspaceEntryTitle || form.name || '').trim()
  }

  if (payload.execution_mode === 'custom') {
    payload.tool_names = [...new Set(
      (form.tool_names || []).map(name => String(name).trim()).filter(Boolean)
    )]
  }

  if (!isEvent && form.schedule_type === 'once') {
    payload.run_at = form.run_at
  } else if (!isEvent && form.schedule_type === 'interval') {
    payload.interval_minutes = Number(form.interval_minutes) || 30
  } else if (!isEvent && form.schedule_type === 'daily_custom') {
    payload.hour = Number(form.hour)
    payload.minute = Number(form.minute)
  }

  return payload
}
