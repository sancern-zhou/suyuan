export const mapServerBoardVersions = (versions = [], currentVersionId = null) => (
  (Array.isArray(versions) ? versions : []).map(version => {
    const id = String(version.version_id || version.id || '')
    const screenshotRef = version.screenshot_ref || {}
    return {
      ...version,
      id,
      version_id: id,
      versionNumber: Number(version.version_number || version.versionNumber || 0),
      source: version.source || 'agent',
      lifecycleStatus: version.lifecycle_status || version.lifecycleStatus || 'accepted',
      qualityStatus: version.quality_status || version.qualityStatus || 'pending',
      qualityReport: version.quality_report || version.qualityReport || {},
      agentRunId: version.agent_run_id || version.agentRunId || null,
      screenshotUrl: screenshotRef.read_url || screenshotRef.url || null,
      visibleInHistory: (version.lifecycle_status || 'accepted') === 'accepted',
      is_current: id === currentVersionId,
      createdAt: version.created_at || version.createdAt || null
    }
  })
)

export const isAcceptedBoardPayload = (payload = {}, resultSuccess = true) => {
  const lifecycle = payload.lifecycle_status || payload.lifecycleStatus || ''
  if (lifecycle) return lifecycle === 'accepted' || payload.candidate_accepted === true
  return resultSuccess !== false && payload.requires_visual_review !== true
}

export const shouldPreviewBoardCandidate = (payload = {}) => {
  const lifecycle = payload.lifecycle_status || payload.lifecycleStatus || ''
  return lifecycle === 'candidate' && payload.preview_candidate === true
}
