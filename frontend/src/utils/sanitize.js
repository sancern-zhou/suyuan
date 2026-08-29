import DOMPurify from 'dompurify'

/**
 * 统一的 HTML 净化入口。
 *
 * 所有把 markdown/LLM 输出渲染进 v-html 的组件都必须先经过本函数，
 * 阻断 <iframe onload=...>、<svg onload=...> 等存储型 XSS 载荷。
 */
export function sanitizeRichHtml(html) {
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ['target'],
  })
}

export default sanitizeRichHtml
