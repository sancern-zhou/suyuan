// 外部平台通常按 history 风格跳转 /sso?ticket=...，但独立部署构建使用
// hash 路由（BASE_URL=./）。这里在应用启动前把入口规整成 #/sso 形式，
// 避免票据在 hash 路由下被丢弃。
export function ssoEntryRedirect(url) {
  if (!url) return ''
  let parsed
  try {
    parsed = new URL(url, 'http://localhost/')
  } catch {
    return ''
  }
  const ticket = parsed.searchParams.get('ticket') || ''
  if (!ticket) return ''
  const hash = parsed.hash || ''
  if (hash.startsWith('#/')) return ''
  if (!/(^|\/)sso\/?$/.test(parsed.pathname)) return ''
  const pathname = parsed.pathname.replace(/\/+$/, '')
  return `${pathname}#/sso${parsed.search}`
}


export function normalizeSsoEntry(location, history) {
  const target = ssoEntryRedirect(location?.href)
  if (!target) return false
  history?.replaceState?.(null, '', target)
  return true
}
