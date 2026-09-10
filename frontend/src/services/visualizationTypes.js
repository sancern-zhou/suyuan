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
