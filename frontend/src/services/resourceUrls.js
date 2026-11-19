import { gatewayUrl } from '../auth/http.js'

// iframe src、img src、a href 这类浏览器直接发起的导航不经过 authFetch，
// 不会补上网关前缀。服务端下发的 content_url 是站点根绝对路径
// （/api/suyuan/...），在子路径部署（如 /AI/）下会被解析到站点根，
// 命中错误的上游并返回 X-Frame-Options: DENY，导致内嵌预览被浏览器拦截。
// 这里统一按应用基址（VITE_API_BASE_URL）归一化后再交给浏览器。
export const browserResourceUrl = (url, apiBaseUrl) => (
  typeof url === 'string' && url.startsWith('/') ? gatewayUrl(url, apiBaseUrl) : url
)
