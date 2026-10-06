export function workflowCanResume(snapshot = {}, status = snapshot?.status) {
  snapshot ||= {}
  if (snapshot.budget_state?.exhausted) return false
  if (['queued', 'running'].includes(status)) return true
  if (!['failed', 'partial'].includes(status)) return false
  if (snapshot.delivery) return Boolean(snapshot.delivery.retryable_nodes?.length)
  return Object.values(snapshot.runtime?.runs || {}).some(run =>
    run.parent_task_id && run.status === 'failed' &&
    snapshot.node_retryable?.[run.task_id] !== false &&
    Number(run.attempt || 0) < Number(run.max_attempts || 1))
}

export function workflowGaps(snapshot = {}) {
  snapshot ||= {}
  if (snapshot.delivery?.gaps) return snapshot.delivery.gaps
  return Object.entries(snapshot.graph || {}).filter(([, node]) =>
    ['failed', 'blocked'].includes(node.status)).map(([task_id, node]) => ({
    task_id, status: node.status, reason: snapshot.node_errors?.[task_id] || '缺少上游证据',
  }))
}
