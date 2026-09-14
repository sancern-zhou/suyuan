export const selectableWeixinUsers = (users = []) => users.filter(user =>
  user.status === 'active' &&
  Boolean(user.social_user_id) &&
  String(user.channel || '').startsWith('weixin')
)

export const selectableSocialUsers = (users = []) => users.filter(user =>
  user.status === 'active' &&
  Boolean(user.social_user_id) &&
  (String(user.channel || '').startsWith('weixin') || String(user.channel || '').startsWith('app'))
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
    { value: 'custom', label: 'custom（自选工具）' },
    { value: 'workflow', label: 'workflow（确定性工作流）' }
  )
  if (currentMode && !options.some(option => option.value === currentMode)) {
    options.push({ value: currentMode, label: `${currentMode}（当前任务模式）` })
  }
  return options.filter((option, index, values) => (
    values.findIndex(candidate => candidate.value === option.value) === index
  ))
}


export const applyTriggerDefaults = (form, triggerType, eventTypes = []) => {
  const previousMode = form.execution_mode
  form.trigger_type = triggerType
  if (triggerType === 'event') {
    // 工作流任务是代码注册的确定性单元，切换触发方式不得改写其执行模式。
    if (previousMode !== 'workflow') {
      form.execution_mode = 'social'
    }
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
  if (mode !== 'workflow') form.workflow_name = ''
  return form
}


export const buildTaskPayload = (form) => {
  const isEvent = form.trigger_type === 'event'
  const payload = {
    name: String(form.name || '').trim(),
    description: String(form.description || '').trim(),
    execution_mode: form.execution_mode || 'assistant',
    model_tier: form.model_tier || 'auto',
    result_requirements: (form.result_requirements || []).map(rule => ({
      field: String(rule.field || '').trim(),
      label: String(rule.label || '').trim(),
      required: rule.required !== false,
      ...(rule.required_when && Object.keys(rule.required_when).length ? { required_when: { ...rule.required_when } } : {}),
      allowed_values: String(rule.allowedValuesText || '').split(/[,，\n]/).map(value => value.trim()).filter(Boolean)
    })),
    skill_id: String(form.skill_id || '').trim() || null,
    trigger_type: isEvent ? 'event' : 'schedule',
    schedule_type: isEvent ? null : form.schedule_type,
    event_type: isEvent ? form.event_type : null,
    event_filters: isEvent ? (form.event_filters || {}) : {},
    broadcast_enabled: Boolean(form.broadcast_enabled),
    target_user_ids: form.broadcast_enabled ? [...(form.target_user_ids || [])] : [],
    enabled: Boolean(form.enabled),
    prompt: String(form.agent_prompt || form.description || '').trim(),
    timeout_seconds: isEvent ? 1800 : 1800,
    tags: String(form.tagsText || '')
      .split(',')
      .map(tag => tag.trim())
      .filter(Boolean)
  }

  payload.workspace_entry = {
    enabled: Boolean(form.workspaceEntryEnabled),
    title: String(form.workspaceEntryTitle || form.name || '').trim()
  }

  payload.history_learning = {
    ...(form.historyLearningBase || {}),
    enabled: form.historyLearningEnabled !== false,
    max_recent_cases: Number(form.historyMaxRecentCases) || 3,
    memory_char_budget: Number(form.historyMemoryCharBudget) || 4000,
    active_retrieval_enabled: Boolean(form.historyActiveRetrievalEnabled)
  }

  if (payload.execution_mode === 'custom') {
    payload.tool_names = [...new Set(
      (form.tool_names || []).map(name => String(name).trim()).filter(Boolean)
    )]
  }

  if (payload.execution_mode === 'workflow') {
    payload.workflow_name = String(form.workflow_name || '').trim() || null
    payload.workflow_args = { ...(form.workflow_args || {}) }
  }

  if (!isEvent && form.schedule_type === 'once') {
    payload.run_at = form.run_at
  } else if (!isEvent && form.schedule_type === 'interval') {
    payload.interval_minutes = Number(form.interval_minutes) || 30
  } else if (!isEvent && form.schedule_type === 'daily_custom') {
    payload.hour = Number(form.hour)
    payload.minute = Number(form.minute)
  } else if (!isEvent && form.schedule_type === 'weekly_custom') {
    payload.day_of_week = Number(form.day_of_week)
    payload.hour = Number(form.hour)
    payload.minute = Number(form.minute)
  }

  return payload
}
