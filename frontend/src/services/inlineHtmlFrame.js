// 对话区内嵌 HTML 报告卡片的宿主侧协议。
// 后端在 inline text/html 响应中注入常量命名的内联运行时，运行时经
// postMessage 上报内容高度；iframe 为 opaque sandbox origin（无
// allow-same-origin），事件 origin 恒为 "null"，因此只认 event.source
// 与消息形状。

export const HTML_RUNTIME_SOURCE = 'suyuan-html-runtime'
export const FRAME_DEFAULT_HEIGHT = 420
export const FRAME_MIN_HEIGHT = 240
// 预览态钳制上限：报告主体走“展开”全屏查看，对话流里保持可读不霸屏。
export const FRAME_PREVIEW_MAX_HEIGHT = 560

export function isRuntimeHeightEvent(data) {
  return Boolean(data)
    && data.source === HTML_RUNTIME_SOURCE
    && data.type === 'height'
    && Number.isFinite(Number(data.height))
    && Number(data.height) > 0
}

export function previewFrameHeight(reportedHeight) {
  const height = Number(reportedHeight)
  if (!Number.isFinite(height) || height <= 0) return FRAME_DEFAULT_HEIGHT
  return Math.min(Math.max(Math.round(height), FRAME_MIN_HEIGHT), FRAME_PREVIEW_MAX_HEIGHT)
}
