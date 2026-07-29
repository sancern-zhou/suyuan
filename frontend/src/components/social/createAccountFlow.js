export function getOnboardingStep({ scanCreated, scanConfirmed }) {
  if (!scanCreated) return 'starting'
  if (!scanConfirmed) return 'qrcode'
  return 'complete'
}

export function scanOwnerLabel(scan) {
  const username = scan?.platform_username || ''
  const displayName = scan?.platform_display_name || username
  return username && displayName !== username ? `${displayName}（${username}）` : displayName
}
