export function opsAuditReviewStatus(review) {
  if (review?.category !== '智能事件') return null
  const fields = (review.sections || []).flatMap(section => section.fields || [])
  if (review.status === 'pending_review') return fields.find(field => field.key === 'suggested_level')?.value === 'P3' ? '待归档' : '待复核'
  return { in_disposal: '待反馈', archived: '已归档', rejected: '待复核' }[review.status] || null
}
