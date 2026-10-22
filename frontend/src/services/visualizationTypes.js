export const TASK_REVIEW_TYPE = 'task_review'

export const isTaskReviewVisual = value => {
  const metadata = value?.metadata || {}
  const meta = value?.meta || {}
  return (
    value?.type === TASK_REVIEW_TYPE ||
    metadata.type === TASK_REVIEW_TYPE ||
    metadata.visual_behavior === TASK_REVIEW_TYPE ||
    meta.type === TASK_REVIEW_TYPE ||
    meta.visual_behavior === TASK_REVIEW_TYPE
  )
}

// 会话资源目录 DTO 不含 metadata，但后端 resources_for_visuals 会把 visual_id 原样透出，
// 审核卡片的 visual_id 固定为 task_review_{review_id}，以此在目录层识别审核卡片产物。
// （对话消息内已由 InlineChartCard 内联渲染同一张卡片，右侧资源面板不再重复展示。）
export const isTaskReviewCatalogResource = resource => (
  typeof resource?.visual_id === 'string' && resource.visual_id.startsWith('task_review_')
)
