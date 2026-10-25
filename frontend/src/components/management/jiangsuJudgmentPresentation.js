export function jiangsuJudgmentDetails(result) {
  if (!result) return []
  const fields = [
    ['event_type', '事件类型'], ['data_impact', '数据影响'], ['suggested_level', '建议等级'],
    ['compliance_explanation_result', '合规解释'], ['primary_evidence_tags', '主要证据标签'],
    ['supporting_evidence_tags', '辅助证据标签'], ['manual_review_suggestion', '人工复核建议'],
    ['continuity_basis', '连续性依据']
  ]
  const items = fields.filter(([key]) => result[key]).map(([key, label]) => ({ key, label, value: String(result[key]) }))
  if (result.data_impact === '有数据影响') {
    for (const [key, label] of [['station_series_analysis', '本站时序分析'], ['regional_comparison_analysis', '区域背景分析'], ['data_impact_assessment', '数据影响判断'], ['logic_direction_check', '事件与数据逻辑方向校验']]) {
      items.push({ key, label, value: result.data_analysis?.[key] || '本轮未提交该项分析，需补充研判。' })
    }
  }
  if (result.disposal_suggestions?.length) items.push({ key: 'actions', label: '处置建议', value: result.disposal_suggestions.map(text => `- ${text}`).join('\n') })
  return items
}

export function jiangsuReviewStatus(review) {
  if (review?.category !== '智能事件') return null
  const fields = (review.sections || []).flatMap(section => section.fields || [])
  if (review.status === 'pending_review') return fields.find(field => field.key === 'suggested_level')?.value === 'P3' ? '待归档' : '待复核'
  return { in_disposal: '待反馈', archived: '已归档', rejected: '待复核' }[review.status] || null
}
