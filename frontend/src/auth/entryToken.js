// 统一鉴权平台子系统入口：平台以带 token 的 URL 打开本系统时，
// 前端提取平台签发的访问令牌换取登录会话，实现免二次登录。
// 兼容两类入口形态：
//   1) http://host:5175/?token=x          （query 在路径前）
//   2) http://host:5175/#/path?token=x    （query 在 hash 内）

export const ENTRY_TOKEN_KEYS = Object.freeze(['token', 'accessToken', 'access_token'])


function mergeSearchParams(base, extra) {
  const merged = new URLSearchParams(base)
  for (const [key, value] of new URLSearchParams(extra)) {
    if (!merged.has(key)) merged.append(key, value)
  }
  return merged
}

function locationSearchParams(locationLike) {
  let params = new URLSearchParams(locationLike.search || '')
  const hash = locationLike.hash || ''
  const queryAt = hash.indexOf('?')
  if (queryAt >= 0) params = mergeSearchParams(params, hash.slice(queryAt + 1))
  return params
}

function dropKeysFromSearch(search, keys) {
  const params = new URLSearchParams(search)
  let changed = false
  for (const key of keys) {
    if (params.has(key)) {
      params.delete(key)
      changed = true
    }
  }
  return { search: params.toString(), changed }
}

export function extractEntryToken(locationLike) {
  if (!locationLike) return ''
  const params = locationSearchParams(locationLike)
  for (const key of ENTRY_TOKEN_KEYS) {
    const value = (params.get(key) || '').trim()
    if (value) return value.replace(/^Bearer\s+/i, '')
  }
  return ''
}

export function stripEntryToken(locationLike, historyLike) {
  if (!locationLike || !historyLike || typeof historyLike.replaceState !== 'function') {
    return false
  }
  let url
  try {
    url = new URL(locationLike.href)
  } catch {
    return false
  }
  let changed = false
  const search = dropKeysFromSearch(url.search, ENTRY_TOKEN_KEYS)
  if (search.changed) {
    url.search = search.search
    changed = true
  }
  const hash = url.hash || ''
  const queryAt = hash.indexOf('?')
  if (queryAt >= 0) {
    const hashPath = hash.slice(0, queryAt)
    const hashSearch = dropKeysFromSearch(hash.slice(queryAt + 1), ENTRY_TOKEN_KEYS)
    if (hashSearch.changed) {
      url.hash = hashSearch.search ? `${hashPath}?${hashSearch.search}` : hashPath
      changed = true
    }
  }
  if (changed) historyLike.replaceState(historyLike.state, '', url.toString())
  return changed
}
