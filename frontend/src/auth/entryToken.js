// 统一鉴权平台子系统入口：平台以带 token / 授权码 / des 加密串的 URL 打开本系统时，
// 前端提取入口凭证换取登录会话，实现免二次登录。
// 兼容三类入口形态（query 可在路径前或 hash 内）：
//   1) http://host:5175/?token=x              （入口 token 直连）
//   2) http://host:5175/?code=xxx&state=yyy   （OAuth2.0 授权码回跳）
//   3) http://host:5175/?des=<3DES 密文>       （菜单"需单点登录" des 加密串）

export const ENTRY_TOKEN_KEYS = Object.freeze(['token', 'accessToken', 'access_token'])

// OAuth2.0 授权码入口（directAuthorize 302 回跳 ?code=xxx&state=yyy）
export const ENTRY_OAUTH_KEYS = Object.freeze(['code', 'state'])

// 统一鉴权平台"需单点登录"菜单入口（dockingThirdUrl ?des=<3DES 密文>）
export const ENTRY_DES_KEYS = Object.freeze(['des'])

const STRIP_KEYS = Object.freeze([...ENTRY_TOKEN_KEYS, ...ENTRY_OAUTH_KEYS, ...ENTRY_DES_KEYS])


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

function locationHashQuery(locationLike) {
  const hash = locationLike.hash || ''
  const queryAt = hash.indexOf('?')
  return queryAt >= 0 ? hash.slice(queryAt + 1) : ''
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

export function extractOAuthCode(locationLike) {
  if (!locationLike) return ''
  const params = locationSearchParams(locationLike)
  return (params.get('code') || '').trim()
}

export function oauthRedirectUri(locationLike) {
  if (!locationLike || !locationLike.origin) return ''
  return `${locationLike.origin}/`
}

// 按 URLSearchParams 语义解析会把 Base64 里的 '+' 解成空格，
// 这里用 decodeURIComponent 保留原始 '+'；配合调用方的空格还原。
function rawQueryPairs(queryString) {
  const pairs = {}
  const text = (queryString || '').replace(/^\?/, '')
  if (!text) return pairs
  for (const part of text.split('&')) {
    if (!part) continue
    const eq = part.indexOf('=')
    const key = eq >= 0 ? part.slice(0, eq) : part
    const raw = eq >= 0 ? part.slice(eq + 1) : ''
    let decodedKey = key
    let decodedValue = raw
    try {
      decodedKey = decodeURIComponent(key)
      decodedValue = decodeURIComponent(raw)
    } catch {
      // 保留原始串
    }
    if (!(decodedKey in pairs)) pairs[decodedKey] = decodedValue
  }
  return pairs
}

export function extractDesToken(locationLike) {
  if (!locationLike) return ''
  let params = rawQueryPairs(locationLike.search || '')
  const hashQuery = locationHashQuery(locationLike)
  if (hashQuery) {
    for (const [key, value] of Object.entries(rawQueryPairs(hashQuery))) {
      if (!(key in params)) params[key] = value
    }
  }
  let value = String(params.des || '').trim()
  if (!value && params.redirect) {
    // /login?redirect=/?des=x：入口凭证嵌在回跳参数里
    const marker = params.redirect.indexOf('?')
    if (marker >= 0) {
      const nested = rawQueryPairs(params.redirect.slice(marker))
      value = String(nested.des || '').trim()
    }
  }
  // base64 中的 '+' 若被中间环节转成空格则还原
  return value.replace(/ /g, '+')
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
  const search = dropKeysFromSearch(url.search, STRIP_KEYS)
  if (search.changed) {
    url.search = search.search
    changed = true
  }
  const hash = url.hash || ''
  const queryAt = hash.indexOf('?')
  if (queryAt >= 0) {
    const hashPath = hash.slice(0, queryAt)
    const hashSearch = dropKeysFromSearch(hash.slice(queryAt + 1), STRIP_KEYS)
    if (hashSearch.changed) {
      url.hash = hashSearch.search ? `${hashPath}?${hashSearch.search}` : hashPath
      changed = true
    }
  }
  if (changed) historyLike.replaceState(historyLike.state, '', url.toString())
  return changed
}
