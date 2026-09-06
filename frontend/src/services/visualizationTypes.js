export const FAULT_WORK_ORDER_REVIEW_TYPE = 'fault_work_order_review'

export const isFaultWorkOrderReviewVisual = value => {
  const metadata = value?.metadata || {}
  const meta = value?.meta || {}
  return (
    value?.type === FAULT_WORK_ORDER_REVIEW_TYPE ||
    metadata.type === FAULT_WORK_ORDER_REVIEW_TYPE ||
    metadata.visual_behavior === FAULT_WORK_ORDER_REVIEW_TYPE ||
    meta.type === FAULT_WORK_ORDER_REVIEW_TYPE ||
    meta.visual_behavior === FAULT_WORK_ORDER_REVIEW_TYPE
  )
}
