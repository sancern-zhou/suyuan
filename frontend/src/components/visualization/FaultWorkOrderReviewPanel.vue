<template>
  <section class="qc-review-panel">
    <div v-if="message" class="banner" :class="messageTone">{{ message }}</div>

    <div class="panel-body">
          <details  class="review-details" @toggle="detailsOpen.work_order = $event.target.open">
            <summary>工单详情与附件<span>详情</span></summary>
        <section v-if="detailsOpen.work_order" class="section">
          <h4>工单详情</h4>
          <div v-if="evidenceLoading" class="empty">正在加载工单详单...</div>
          <div v-else-if="!evidence" class="empty">暂无工单详单</div>
          <div v-else class="platform-detail">
            <article class="evidence-card wide">
              <h5>基本信息</h5>
              <dl>
                <template v-for="field in workOrderFields" :key="field.label">
                  <dt>{{ field.label }}</dt>
                  <dd>{{ field.value }}</dd>
                </template>
              </dl>
            </article>

            <div class="evidence-columns">
              <article class="evidence-card">
                <h5>故障设备</h5>
                <dl v-if="faultDeviceFields.length">
                  <template v-for="field in faultDeviceFields" :key="field.label">
                    <dt>{{ field.label }}</dt>
                    <dd>{{ field.value }}</dd>
                  </template>
                </dl>
                <div v-else class="empty">无故障设备明细</div>
              </article>
              <article class="evidence-card">
                <h5>故障内容</h5>
                <div v-if="!faultContentRows.length" class="empty">无故障内容明细</div>
                <div v-else class="compact-list">
                  <p v-for="(row, index) in faultContentRows" :key="index">{{ row }}</p>
                </div>
              </article>
            </div>

            <div class="platform-table">
              <div class="flow-head">
                <span>步骤</span><span>处理人</span><span>处理时间</span><span>处理意见</span>
              </div>
              <div v-for="row in workOrderFlowRows" :key="row.key" class="flow-row">
                <strong>{{ row.step }}</strong>
                <span>{{ row.user }}</span>
                <span>{{ row.time }}</span>
                <p>{{ row.remark }}</p>
              </div>
              <div v-if="!workOrderFlowRows.length" class="empty">无工单流转记录</div>
            </div>

            <div v-if="attachmentRows.length" class="platform-table">
              <div class="attachment-head">
                <span>照片</span><span>附件名</span><span>类型</span><span>状态</span>
              </div>
              <div v-for="row in attachmentRows" :key="row.key" class="attachment-row">
                <button
                  v-if="row.isImage && row.contentUrl"
                  type="button"
                  class="attachment-thumb"
                  :disabled="!row.previewUrl"
                  :title="row.previewUrl ? '查看大图' : '图片加载中'"
                  @click="openAttachmentLightbox(row)"
                >
                  <AuthenticatedImage
                    :source="row.contentUrl"
                    :alt="row.fileName"
                    @resolved="url => setAttachmentPreviewUrl(row.key, url)"
                    @error="error => setAttachmentPreviewError(row.key, error)"
                  />
                  <span v-if="row.previewLoading" class="attachment-thumb-state">加载中</span>
                  <span v-else-if="row.previewError" class="attachment-thumb-state error">加载失败</span>
                </button>
                <div v-else class="attachment-thumb placeholder">
                  <span>{{ row.contentUrl ? '附件' : '无预览' }}</span>
                </div>
                <strong>{{ row.fileName }}</strong>
                <span>{{ row.typeCode }}</span>
                <span>
                  {{ row.status }}
                  <em v-if="row.error">{{ row.error }}</em>
                </span>
              </div>
            </div>
          </div>
        </section>
          </details>



          <details  class="review-details" @toggle="detailsOpen.quality = $event.target.open">
            <summary>质控/复测曲线<span>详情</span></summary>
        <section v-if="detailsOpen.quality" class="section">
          <h4>{{ qualityModuleLabel }}</h4>
          <div v-if="evidenceLoading" class="empty">正在加载质控信息...</div>
          <div v-else-if="!evidence" class="empty">暂无质控信息</div>
          <div v-else class="quality-layout">
            <div v-if="qcCurveEntries.length" class="chart-stack">
              <ReviewTimeSeriesChart
                v-for="entry in qcCurveEntries"
                :key="entry.key"
                :title="entry.title"
                :subtitle="entry.subtitle"
                :unit="entry.unit"
                :series="entry.series"
                :mark-areas="entry.markAreas"
                :height="230"
              />
            </div>

            <div class="summary-grid">
              <div v-for="field in qcSummaryFields" :key="field.label">
                <span>{{ field.label }}</span>
                <strong>{{ field.value }}</strong>
              </div>
            </div>

            <div class="qc-table">
              <div class="qc-head">
                <span>状态</span><span>因子</span><span>类型</span><span>开始</span><span>结束</span><span>目标/读数</span><span>结果</span>
              </div>
              <div v-for="row in qcHistoryTableRows" :key="row.key" class="qc-row">
                <span>{{ row.status }}</span>
                <strong>{{ row.pollutant }}</strong>
                <span>{{ row.qcType }}</span>
                <span>{{ row.start }}</span>
                <span>{{ row.end }}</span>
                <span>{{ row.values }}</span>
                <strong>{{ row.result }}</strong>
              </div>
              <div v-if="!qcHistoryTableRows.length" class="empty">未查询到质控或复测任务记录</div>
            </div>

            <div v-if="qcTaskDetailEntries.length" class="task-detail-stack">
              <article v-for="task in qcTaskDetailEntries" :key="task.key" class="task-detail-card">
                <div class="task-detail-head">
                  <strong>{{ task.title }}</strong>
                  <span>{{ task.window }}</span>
                </div>
                <div class="qc-stage-strip">
                  <div v-for="stage in task.platformStages" :key="`${task.key}-${stage.name}`" :class="{ filled: stage.value }">
                    <span>{{ stage.name }}</span>
                    <strong>{{ stage.value || '-' }}</strong>
                  </div>
                </div>
                <div class="task-detail-meta">
                  <span>任务窗口：{{ task.curveWindow }}</span>
                  <span>步骤数：{{ task.stepCount || 0 }}</span>
                  <span>日志：{{ task.logCount || 0 }} 条</span>
                  <span>曲线：{{ task.curveCount || 0 }} 条</span>
                  <span v-if="task.statusText">状态：{{ task.statusText }}</span>
                  <span v-if="task.statusMessage">说明：{{ task.statusMessage }}</span>
                </div>
                <p v-if="task.curveSummary" class="task-note">{{ task.curveSummary }}</p>
                <p v-if="task.parseError" class="task-note critical">{{ task.parseError }}</p>

                <div class="task-summary-grid">
                  <div v-for="field in task.historySummary" :key="field[0]">
                    <span>{{ field[0] }}</span>
                    <strong>{{ valueText(field[1]) || '-' }}</strong>
                  </div>
                </div>

                <div v-if="task.steps.length" class="step-list">
                  <div v-for="step in task.steps" :key="`${task.key}-${step.index}`" class="step-item">
                    <div class="step-index">{{ step.index }}</div>
                    <div class="step-body">
                      <div class="step-top">
                        <strong>{{ step.phase || step.label }}</strong>
                        <span>{{ step.time || '-' }}</span>
                      </div>
                      <p>
                        {{ step.label }}
                        <template v-if="step.status"> · {{ step.status }}</template>
                        <template v-if="step.detail"> · {{ step.detail }}</template>
                      </p>
                    </div>
                  </div>
                </div>

                <div class="task-detail-columns">
                  <div>
                    <span>历史详情</span>
                    <p>{{ compactPreview(task.historyDetail) }}</p>
                  </div>
                  <div>
                    <span>DataValues</span>
                    <p>{{ compactPreview(task.dataValues) }}</p>
                  </div>
                  <div>
                    <span>ResultValues</span>
                    <p>{{ compactPreview(task.resultValues) }}</p>
                  </div>
                </div>

                <div v-if="task.logs.length" class="task-log-list">
                  <p v-for="(log, logIndex) in task.logs.slice(0, 6)" :key="`${task.key}-log-${logIndex}`">
                    {{ compactRow(log) }}
                  </p>
                </div>
                <div v-else class="empty">未查询到质控日志</div>
              </article>
            </div>
          </div>
        </section>
          </details>

          <details v-if="isSop03" class="review-details" @toggle="detailsOpen.transmission = $event.target.open">
            <summary>传输与补传<span>详情</span></summary>
        <section v-if="detailsOpen.transmission" class="section">
          <h4>传输与补传证据</h4>
          <div v-if="evidenceLoading" class="empty">正在加载传输证据...</div>
          <div v-else-if="!evidence" class="empty">暂无传输证据</div>
          <div v-else class="quality-layout">
            <div class="status-table">
              <div v-for="row in transmissionStatusRows" :key="row.key">
                <span>{{ row.label }}</span>
                <strong>{{ row.status }}</strong>
                <em>{{ row.summary }}</em>
              </div>
            </div>
            <article v-if="transmissionGapEntries.length" class="evidence-card gap-card">
              <h5>传输证据缺口</h5>
              <ul class="gap-list">
                <li v-for="gap in transmissionGapEntries" :key="`transmission-${gap.group}-${gap.item}-${gap.reason}`">
                  <strong>{{ gap.group }} / {{ gap.item }}</strong>
                  <span>{{ gap.reason }}</span>
                </li>
              </ul>
            </article>
          </div>
        </section>
          </details>

          <details  class="review-details" @toggle="detailsOpen.monitoring = $event.target.open">
            <summary>监测数据曲线<span>详情</span></summary>
        <section v-if="detailsOpen.monitoring" class="section">
          <h4>监测数据曲线</h4>
          <div v-if="evidenceLoading" class="empty">正在加载监测数据...</div>
          <div v-else-if="!evidence" class="empty">暂无监测数据</div>
          <div v-else class="quality-layout">
            <div class="status-table">
              <div v-for="row in monitoringStatusRows" :key="row.key">
                <span>{{ row.label }}</span>
                <strong>{{ row.status }}</strong>
                <em>{{ row.summary }}</em>
              </div>
            </div>
            <div v-if="monitoringEntries.length" class="chart-stack">
              <ReviewTimeSeriesChart
                v-for="entry in monitoringEntries"
                :key="entry.key"
                :title="entry.title"
                :subtitle="entry.subtitle"
                :unit="entry.unit"
                :series="entry.series"
                :mark-areas="markAreasForEntry(entry)"
                :height="260"
              />
            </div>
            <div v-else class="empty">无可绘制监测曲线</div>
          </div>
        </section>
          </details>

          <details v-if="!isSop03" class="review-details" @toggle="detailsOpen.same_city = $event.target.open">
            <summary>同城对比曲线<span>详情</span></summary>
        <section v-if="detailsOpen.same_city" class="section">
          <h4>同城小时对比曲线</h4>
          <div v-if="evidenceLoading" class="empty">正在加载同城对比...</div>
          <div v-else-if="evidenceError" class="empty critical">{{ evidenceError }}</div>
          <div v-else-if="!evidence" class="empty">暂无同城对比数据</div>
          <div v-else class="quality-layout">
            <div class="status-table">
              <div v-for="row in sameCityStatusRows" :key="row.key">
                <span>{{ row.label }}</span>
                <strong>{{ row.status }}</strong>
                <em>{{ row.summary }}</em>
              </div>
            </div>
            <div v-if="sameCityMonitoringEntries.length" class="chart-stack">
              <ReviewTimeSeriesChart
                v-for="entry in sameCityMonitoringEntries"
                :key="entry.key"
                :title="entry.title"
                :subtitle="entry.subtitle"
                :unit="entry.unit"
                :series="entry.series"
                :mark-areas="markAreasForEntry(entry)"
                :height="280"
              />
            </div>
            <div v-else class="empty">无可绘制同城小时对比曲线</div>
          </div>
        </section>
          </details>
          <details v-if="isSop02" class="review-details" @toggle="detailsOpen.weather = $event.target.open">
            <summary>城区气象与污染物时序<span>详情</span></summary>
            <section v-if="detailsOpen.weather" class="section">
              <div v-if="evidenceLoading" class="empty">正在加载气象数据...</div>
              <div v-else-if="evidenceError" class="empty critical">{{ evidenceError }}</div>
              <template v-else>
                <p>{{ cityWeather.city_name }} {{ cityWeather.station_name }} {{ cityWeather.station_code }}</p>
                <p>{{ cityWeather.message || '暂无城区气象数据' }}</p>
                <p v-if="cityWeather.missing_hours?.length">缺测 {{ cityWeather.missing_hours.length }} 小时</p>
                <p v-if="cityWeather.gaps?.length" class="critical">{{ cityWeather.gaps.length }} 个气象取证时段请求失败</p>
                <div v-if="cityWeather.start && cityWeather.end" class="chart-stack">
                  <JiangsuWeatherReviewChart v-for="entry in weatherMonitoringEntries" :key="entry.key"
                    :entry="entry" :weather="cityWeather" :mark-areas="markAreasForEntry(entry)" />
                </div>
              </template>
            </section>
          </details>
        <section class="section">
          <h4>AI 审核结论</h4>
          <div class="decision-row">
            <label class="field">
              <span>人工最终工单结论</span>
              <select v-model="form.final_work_order_decision" :disabled="!editable">
                <option value="approve">通过</option>
                <option value="reject">退回修改</option>
              </select>
            </label>
            <div class="ai-decision">
              <span>AI 建议</span>
              <strong>{{ decisionLabel(review.work_order_decision) }}</strong>
            </div>
          </div>
          <div class="summary-grid conclusion-grid">
            <div>
              <span>AI 摘要</span>
              <strong>{{ review.review_summary || '暂无审核摘要' }}</strong>
            </div>
            <div>
              <span>详细意见</span>
              <strong>{{ review.review_comment || '暂无审核意见' }}</strong>
            </div>
            <div>
              <span>归档记录</span>
              <strong>{{ reviewStatusDetail }}</strong>
            </div>
          </div>
          <ul v-if="review.audit_warnings?.length" class="warning-list">
            <li v-for="warning in review.audit_warnings" :key="warning">{{ warning }}</li>
          </ul>
        </section>
        <section v-if="review.exclusion_required || form.exclusion_intervals.length" class="section exclusion-section">
          <h4>剔除异常区间确认</h4>
          <p class="hint">先核对 AI 的数据影响建议，再确认每个剔除候选的异常起止时间、边界来源和合理性判断。</p>
          <div v-if="dataImpacts.length" class="impact-table">
            <div class="impact-head">
              <span>污染物</span><span>粒度</span><span>时段</span><span>处置建议</span>
            </div>
            <div v-for="(item, index) in dataImpacts" :key="index" class="impact-row">
              <span>{{ item.pollutant || '-' }}</span>
              <span>{{ item.granularity || '-' }}</span>
              <span>{{ formatRange(item.start, item.end) }}</span>
              <strong>{{ dataDecisionLabel(item.decision) }}</strong>
            </div>
          </div>
          <div v-else class="empty">未形成数据影响结论</div>
          <div v-if="!form.exclusion_intervals.length" class="empty critical">涉及数据剔除，但 AI 未提供可确认区间。</div>
          <article
            v-for="(interval, index) in form.exclusion_intervals"
            :key="index"
            class="interval-item"
          >
            <div class="interval-grid">
              <label class="field">
                <span>污染物</span>
                <input v-model="interval.pollutant" :disabled="!editable" />
              </label>
              <label class="field">
                <span>粒度</span>
                <select v-model="interval.granularity" :disabled="!editable">
                  <option value="hour">小时</option>
                </select>
              </label>
              <label class="field">
                <span>开始</span>
                <input type="datetime-local" v-model="interval.start_local" :disabled="!editable" />
              </label>
              <label class="field">
                <span>结束</span>
                <input type="datetime-local" v-model="interval.end_local" :disabled="!editable" />
              </label>
            </div>
            <label class="field">
              <span>边界来源</span>
              <textarea v-model="interval.boundary_text" rows="2" :disabled="!editable"></textarea>
            </label>
            <div class="interval-grid two">
              <label class="field">
                <span>合理性判断</span>
                <select v-model="interval.reasonableness_status" :disabled="!editable">
                  <option value="pass">合理</option>
                  <option value="uncertain">不确定</option>
                  <option value="fail">不合理</option>
                </select>
              </label>
              <label class="field">
                <span>判断依据</span>
                <input v-model="interval.reasonableness_basis" :disabled="!editable" />
              </label>
            </div>
          </article>
        </section>
        <section class="section review-comment-section">
          <label class="field">
            <span>审核意见</span>
            <textarea v-model="form.review_comment" :disabled="!editable" rows="3" maxlength="2000" />
          </label>
        </section>
    </div>

    <footer class="panel-footer">
      <span>{{ footerHint }}</span>
      <div class="actions">
        <button type="button" class="danger" :disabled="submitting || !editable" @click="rejectReview">
          退回修改
        </button>
        <button type="button" class="primary" :disabled="submitting || !editable" @click="confirmReview">
          {{ submitting ? '归档中...' : '确认归档' }}
        </button>
      </div>
    </footer>

    <ImageLightbox
      v-model:visible="attachmentLightboxVisible"
      :images="attachmentLightboxImages"
      :start-index="attachmentLightboxStartIndex"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { authFetch } from '@/auth/http.js'
import AuthenticatedImage from '@/components/AuthenticatedImage.vue'
import ImageLightbox from '@/components/ImageLightbox.vue'
import ReviewTimeSeriesChart from './ReviewTimeSeriesChart.vue'
import JiangsuWeatherReviewChart from './JiangsuWeatherReviewChart.vue'

const props = defineProps({ data: { type: Object, required: true } })

const review = ref(props.data?.data?.review || {})
const station = computed(() => review.value?.station || {})
const detailsOpen = reactive({ work_order: false, quality: false, monitoring: false, transmission: false, same_city: false, weather: false })
const submitting = ref(false)
const message = ref('')
const messageTone = ref('info')
const evidence = ref(null)
const evidenceLoading = ref(false)
const evidenceError = ref('')
const attachmentPreviewState = reactive({})
const attachmentLightboxVisible = ref(false)
const attachmentLightboxStartIndex = ref(0)

const form = reactive({
  final_work_order_decision: 'needs_evidence',
  review_comment: '',
  exclusion_intervals: []
})

const sop01GateLabels = {
  M1: ['M1', '对象一致性'],
  M2: ['M2', '失败事实'],
  M3: ['M3', '处置对应性'],
  M4: ['M4', '复测闭环'],
  M5: ['M5', '数据影响'],
  M6: ['M6', '数据标识'],
  M1_object_consistency: ['M1', '对象一致性'],
  M2_failure_fact: ['M2', '失败事实'],
  M3_disposal_match: ['M3', '处置对应性'],
  M4_retest_loop: ['M4', '复测闭环'],
  M5_data_impact: ['M5', '数据影响'],
  M6_flag_boundary: ['M6', '数据标识']
}

const sop02GateLabels = {
  E1: ['E1', '对象一致性'],
  E2: ['E2', '异常事实'],
  E3: ['E3', '机理证据'],
  E4: ['E4', '影响范围'],
  E5: ['E5', '处置对应性'],
  E6: ['E6', '恢复验证'],
  E7: ['E7', '数据分类'],
  E8: ['E8', '边界与标识'],
  E1_object_consistency: ['E1', '对象一致性'],
  E2_abnormal_fact: ['E2', '异常事实'],
  E3_mechanism_evidence: ['E3', '机理证据'],
  E4_impact_scope: ['E4', '影响范围'],
  E5_disposal_match: ['E5', '处置对应性'],
  E6_recovery_verification: ['E6', '恢复验证'],
  E7_data_classification: ['E7', '数据分类'],
  E8_boundary_flags: ['E8', '边界与标识']
}

const sop03GateLabels = {
  T1: ['T1', '对象一致性'],
  T2: ['T2', '数据产生状态'],
  T3: ['T3', '本地缓存'],
  T4: ['T4', '平台接收'],
  T5: ['T5', '补传闭环'],
  T6: ['T6', '时间戳连续性'],
  T7: ['T7', '数据分类'],
  T1_object_consistency: ['T1', '对象一致性'],
  T2_data_generation: ['T2', '数据产生状态'],
  T3_local_cache: ['T3', '本地缓存'],
  T4_platform_receipt: ['T4', '平台接收'],
  T5_retransmission_loop: ['T5', '补传闭环'],
  T6_timestamp_continuity: ['T6', '时间戳连续性'],
  T7_data_classification: ['T7', '数据分类']
}

const allGateLabels = { ...sop01GateLabels, ...sop02GateLabels, ...sop03GateLabels }
const chartColors = ['#62c6ff', '#61d394', '#f6bd4a', '#ff8a75', '#9b8cff', '#56d6c9', '#d7a84e', '#8fb4ff']

const colorWithAlpha = (hex, alpha) => {
  const text = String(hex || '').replace('#', '')
  if (text.length !== 6) return hex
  const red = parseInt(text.slice(0, 2), 16)
  const green = parseInt(text.slice(2, 4), 16)
  const blue = parseInt(text.slice(4, 6), 16)
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

const joinList = value => Array.isArray(value) && value.length ? value.join('、') : '-'

const cleanTime = value => {
  if (!value) return ''
  return String(value).replace('T', ' ').replace(/\.\d+$/, '').slice(0, 19)
}

const formatTime = value => {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? cleanTime(value) || String(value)
    : date.toLocaleString('zh-CN', { hour12: false })
}

const firstText = (...values) => {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== '') return value
  }
  return ''
}

const valueText = value => {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) return value.length ? `${value.length} 项` : ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const compactRow = row => {
  if (!row || typeof row !== 'object') return valueText(row) || '-'
  const pairs = Object.entries(row)
    .filter(([, value]) => value !== null && value !== undefined && value !== '' && typeof value !== 'object')
    .slice(0, 7)
    .map(([key, value]) => `${key}: ${value}`)
  return pairs.length ? pairs.join('；') : '-'
}

const compactObject = value => {
  if (!value || typeof value !== 'object') return valueText(value) || '-'
  const pairs = Object.entries(value)
    .filter(([, item]) => item !== null && item !== undefined && item !== '' && typeof item !== 'object')
    .slice(0, 8)
    .map(([key, item]) => `${key}: ${item}`)
  return pairs.length ? pairs.join('；') : '-'
}

const compactPreview = value => {
  if (Array.isArray(value)) {
    if (!value.length) return '-'
    return value.slice(0, 6).map(item => compactObject(item)).join('；')
  }
  return compactObject(value)
}

const decisionLabel = value => ({
  approve: '通过',
  reject: '退回修改',
  needs_evidence: '退回修改'
}[value] || '-')

const dataDecisionLabel = value => ({
  keep: '保留',
  partial_exclude: '部分剔除',
  exclude: '全部剔除',
  missing_no_delete: '缺失不剔除',
  not_applicable: '不适用',
  needs_evidence: '暂不处置'
}[value] || value || '-')

const eventTypeLabel = value => ({
  high: '高值',
  low: '低值',
  zero: '零值',
  constant: '恒值',
  missing: '缺失/无数据',
  flow: '流量/泵',
  power: '供电/断电',
  temperature: '温湿度/制冷',
  offline: '离线/通信中断',
  not_uploaded: '未上传/未更新',
  retransmitted: '补传/重传',
  timestamp_error: '时间戳/重复异常',
  uncertain: '不确定'
}[value] || value || '-')

const gateStatusLabel = value => ({
  pass: '通过',
  fail: '不通过',
  uncertain: '不确定',
  not_applicable: '不适用'
}[value] || '不确定')

const gateScopeLabel = value => ({
  core: '核心',
  supporting: '辅助',
  rebuttal: '反证'
}[String(value || 'core').toLowerCase()] || '核心')

const resultSummary = result => {
  if (!result || typeof result !== 'object') return ''
  if (result.summary) return result.summary
  if (result.record_count !== undefined) return `${result.record_count || 0} 条`
  const raw = result.station_hour_raw || {}
  const audited = result.station_hour_audited || {}
  if (raw.record_count !== undefined || audited.record_count !== undefined) {
    return `原始 ${raw.record_count || 0} 条，审核 ${audited.record_count || 0} 条`
  }
  if (result.status) return result.status
  return ''
}

const dataStatusText = result => {
  if (!result || typeof result !== 'object') return '-'
  if (result.success === false) return '失败'
  const count = Number(result.record_count || result.returned_records || 0)
  if (result.status === 'empty') return '0 条'
  if (Number.isFinite(count)) return `${count} 条`
  return result.status || '-'
}

const toLocalInput = value => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).replace(' ', 'T').slice(0, 16)
  const pad = number => String(number).padStart(2, '0')
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate())
  ].join('-') + `T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const fromLocalInput = value => {
  const text = String(value || '').trim()
  return text ? `${text.replace('T', ' ')}:00` : ''
}

const formatRange = (start, end) => {
  if (!start && !end) return '-'
  return `${cleanTime(start) || '-'} 至 ${cleanTime(end) || '-'}`
}

const shortText = (value, maxLength = 120) => {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text
}

const firstSentence = value => {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  const match = text.match(/^.*?[。！？!?]/)
  return match ? match[0] : text
}

const granularityLabel = value => ({
  '5min': '5分钟',
  hour: '小时'
}[String(value || '').toLowerCase()] || value || '-')

const normalizePollutant = value => {
  const text = String(value || '').trim().toUpperCase().replace(/\s+/g, '')
  if (['PM25', 'PM2_5', 'PM2.5'].includes(text)) return 'PM2.5'
  return text
}

const pollutantFieldAliases = {
  SO2: ['SO2', 'so2', 'sO2'],
  NO: ['NO', 'no', 'nO'],
  NO2: ['NO2', 'no2', 'nO2'],
  NOX: ['NOX', 'nox', 'nOX', 'nOx'],
  CO: ['CO', 'co', 'cO'],
  O3: ['O3', 'o3'],
  PM10: ['PM10', 'pm10', 'pM10'],
  'PM2.5': ['PM2.5', 'PM2_5', 'pM2_5', 'pm25', 'PM25']
}
const pollutantDisplayOrder = ['PM2.5', 'PM10', 'SO2', 'NO2', 'O3', 'CO', 'NO', 'NOx']
const genericValueFields = ['value', 'Value', 'val']

const pollutantFieldCandidates = pollutants => {
  const keys = [...genericValueFields]
  for (const pollutant of pollutants || []) {
    const normalized = String(pollutant).toUpperCase()
    for (const key of pollutantFieldAliases[normalized] || [pollutant]) {
      if (key && !keys.includes(key)) keys.push(key)
    }
  }
  return keys
}

const readTimeLabel = row => {
  for (const key of ['timePoint', 'monitorTime', 'dataTime', 'dateTime', 'dateTimeString', 'time', 'rStart', 'sStart']) {
    if (row?.[key]) return String(row[key])
  }
  return ''
}

const numericValue = (row, preferredKeys, allowFallback = true) => {
  for (const key of preferredKeys) {
    const value = Number(row?.[key])
    if (Number.isFinite(value)) return value
  }
  if (!allowFallback) return null
  for (const [key, raw] of Object.entries(row || {})) {
    if (/id|code|time|rank|mark|status|type|name/i.test(key)) continue
    const value = Number(raw)
    if (Number.isFinite(value)) return value
  }
  return null
}

const numberValue = value => {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

const pointsFromRecords = (records, preferredKeys, allowFallback = false) => {
  const points = []
  for (const row of records || []) {
    if (!row || typeof row !== 'object') continue
    const time = readTimeLabel(row)
    const value = numericValue(row, preferredKeys, allowFallback)
    if (!time || value === null) continue
    points.push({ time, value })
  }
  return points
}

const pollutantUnit = pollutant => String(pollutant).toUpperCase() === 'CO' ? '毫克/立方米' : '微克/立方米'
const pollutantAxis = pollutant => normalizePollutant(pollutant) === 'O3' ? 'right' : 'left'

const unitFromRecords = records => {
  const row = (records || []).find(item => item?.unit)
  return row?.unit || ''
}

const buildPollutantSeries = (records, pollutants) => (pollutants || [])
  .map((pollutant, index) => ({
    name: pollutant,
    color: chartColors[index % chartColors.length],
    unit: pollutantUnit(pollutant),
    axis: pollutantAxis(pollutant),
    points: pointsFromRecords(records, pollutantFieldCandidates([pollutant]), false)
  }))
  .filter(item => item.points.length)

const pollutantHasValues = (records, pollutant) => {
  const fields = pollutantFieldCandidates([pollutant]).filter(key => !genericValueFields.includes(key))
  return (records || []).some(row => fields.some(key => Number.isFinite(Number(row?.[key]))))
}

const availablePollutantsFromRecords = records => pollutantDisplayOrder
  .filter(pollutant => pollutantHasValues(records, pollutant))

const buildStationComparisonSeries = (records, pollutant, targetStationCode) => {
  const groups = new Map()
  const keys = pollutantFieldCandidates([pollutant])
  for (const row of records || []) {
    if (!row || typeof row !== 'object') continue
    const time = readTimeLabel(row)
    const value = numericValue(row, keys, false)
    if (!time || value === null) continue
    const code = String(row.code || row.stationCode || row.uniqueCode || row.station_code || '').trim()
    const name = String(row.name || row.stationName || row.station_name || code || '未知站点').trim()
    const groupKey = code || name
    if (!groups.has(groupKey)) groups.set(groupKey, { code, name, points: [] })
    groups.get(groupKey).points.push({ time, value })
  }
  const target = String(targetStationCode || '').trim()
  return Array.from(groups.values())
    .sort((left, right) => {
      if (left.code === target) return -1
      if (right.code === target) return 1
      return right.points.length - left.points.length || left.name.localeCompare(right.name)
    })
    .slice(0, 12)
    .map((group, index) => ({
      name: `${group.name}${group.code === target ? '（本站）' : ''}`,
      color: group.code === target ? '#ff8a75' : chartColors[(index + 1) % chartColors.length],
      points: group.points
    }))
}

const pointCountForEntries = entries => entries.reduce(
  (sum, entry) => sum + (entry.series || []).reduce((inner, series) => inner + (series.points?.length || 0), 0),
  0
)

const actorLabel = actor => {
  if (!actor || typeof actor !== 'object') return valueText(actor) || '—'
  return actor.username ||
    actor.user_name ||
    actor.display_name ||
    actor.name ||
    actor.user_id ||
    actor.id ||
    '—'
}

const summaryFromObject = (value, keys = [], maxLength = 160) => {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') return shortText(value, maxLength)
  if (Array.isArray(value)) {
    return shortText(value.map(item => valueText(item)).filter(Boolean).join('；'), maxLength)
  }
  if (typeof value !== 'object') return shortText(valueText(value), maxLength)
  const parts = []
  for (const key of keys) {
    const raw = value[key]
    if (raw === null || raw === undefined || raw === '') continue
    if (Array.isArray(raw)) {
      const text = raw.map(item => valueText(item)).filter(Boolean).join('、')
      if (text) parts.push(text)
    } else {
      parts.push(cleanTime(raw) || String(raw))
    }
  }
  return shortText(parts.join(' · ') || compactPreview(value), maxLength)
}

const historyActionLabel = value => {
  const text = String(value || '').trim()
  if (!text) return '未知轨迹'
  if (text.startsWith('agent_review_rerun')) return 'AI 重新生成'
  return {
    agent_review_submitted: 'AI 提交草案',
    human_confirm: '人工确认归档',
    human_needs_evidence: '人工退回修改',
    human_reject: '人工退回修改'
  }[text] || text.replace(/_/g, ' ')
}

const sopId = computed(() => String(review.value.sop_id || '').toUpperCase())
const isSop02 = computed(() => sopId.value === 'SOP-02')
const isSop03 = computed(() => sopId.value === 'SOP-03')
const editable = computed(() => review.value.status === 'pending_review')
const reviewStatusLabel = computed(() => ({
  pending_review: '待人工确认',
  archived: '已归档',
  rejected: '已退回',
  needs_evidence: '退回修改'
}[review.value.status] || review.value.status || '未知'))
const reviewStatusDetail = computed(() => {
  const confirmedBy = actorLabel(review.value.confirmed_by)
  if (review.value.status === 'archived') {
    return `已归档 · ${confirmedBy} · ${formatTime(review.value.confirmed_at)}`
  }
  if (review.value.status === 'rejected') {
    return `已退回修改 · ${confirmedBy} · ${formatTime(review.value.confirmed_at)}`
  }
  if (review.value.status === 'needs_evidence') {
    return `已退回修改 · ${confirmedBy} · ${formatTime(review.value.confirmed_at)}`
  }
  return `创建于 ${formatTime(review.value.created_at)}`
})
const reviewHistoryEntries = computed(() => {
  const history = Array.isArray(review.value.history) ? [...review.value.history] : []
  return history.slice(-5).reverse().map((item, index) => {
    const detailParts = []
    if (item?.event_id) detailParts.push(`事件 ${item.event_id}`)
    if (item?.source) detailParts.push(`来源 ${item.source}`)
    if (item?.final_work_order_decision) detailParts.push(`结论 ${decisionLabel(item.final_work_order_decision)}`)
    const actor = item?.actor ? actorLabel(item.actor) : ''
    return {
      key: `${index}-${item?.occurred_at || item?.action || 'history'}`,
      action: historyActionLabel(item?.action),
      time: formatTime(item?.occurred_at),
      detail: detailParts.length ? detailParts.join(' · ') : '—',
      meta: actor && actor !== '—' ? [actor] : []
    }
  })
})
const dataImpacts = computed(() => {
  if (Array.isArray(review.value.final_data_impact) && review.value.final_data_impact.length) {
    return review.value.final_data_impact
  }
  return Array.isArray(review.value.data_impact) ? review.value.data_impact : []
})
const impactDecisions = computed(() => dataImpacts.value.map(item => String(item?.decision || '').trim()).filter(Boolean))
const userDecisionText = computed(() => decisionLabel(form.final_work_order_decision || review.value.work_order_decision))
const overviewDecisionNote = computed(() => shortText(review.value.review_summary || firstSentence(review.value.review_comment) || '', 100) || 'AI 已完成结构化审核')
const overviewDispositionNote = computed(() => {
  if (!dataImpacts.value.length) return '暂未形成数据处置结论'
  const unique = Array.from(new Set(impactDecisions.value))
  if (!unique.length) return '数据处置待确认'
  if (unique.length === 1) return dataDecisionLabel(unique[0])
  return unique.map(dataDecisionLabel).join('、')
})
const overviewEvidenceNote = computed(() => {
  if (evidenceLoading.value) return '证据包加载中'
  if (evidenceError.value) return '证据包加载异常'
  if (Array.isArray(evidenceGapEntries.value) && evidenceGapEntries.value.length) {
    return `证据缺口 ${evidenceGapEntries.value.length} 项`
  }
  if (evidence.value) return '证据包已加载'
  return '等待加载证据包'
})
const nextActionNote = computed(() => {
  if (review.value.status !== 'pending_review') return reviewStatusDetail.value
  return review.value.exclusion_required
    ? '确认归档前需同步核对剔除异常时间段'
    : '可直接确认归档'
})
const dataDispositionText = computed(() => {
  const decisions = impactDecisions.value
  if (form.exclusion_intervals.length) {
    const hasWholeExclude = decisions.includes('exclude')
    const hasPartialExclude = decisions.includes('partial_exclude')
    if (hasWholeExclude && !hasPartialExclude) return `全部剔除 ${form.exclusion_intervals.length} 段`
    return `局部剔除 ${form.exclusion_intervals.length} 段`
  }
  if (!decisions.length) return '不适用'
  const unique = Array.from(new Set(decisions))
  if (unique.length === 1) return dataDecisionLabel(unique[0])
  if (unique.every(item => item === 'keep' || item === 'missing_no_delete' || item === 'not_applicable')) return '分段处置'
  return unique.map(dataDecisionLabel).join('、')
})
const auxiliaryGateEntries = computed(() => gateEntries.value.filter(gate => gate.scope !== 'core'))
const auxiliaryGapCount = computed(() => evidenceGapEntries.value.filter(gap => {
  const role = String(gap?.role || gap?.scope || 'supporting').toLowerCase()
  return role !== 'core'
}).length)
const hasContradictionSignal = computed(() => {
  const warningText = (review.value.audit_warnings || []).join(' ')
  return /冲突|矛盾|不一致|不合理/.test(warningText) ||
    auxiliaryGateEntries.value.some(gate => gate.status === 'fail')
})
const auxiliaryVerificationText = computed(() => {
  if (evidenceLoading.value) return '加载中'
  if (evidenceError.value) return '系统取证异常'
  if (hasContradictionSignal.value) return '有矛盾'
  if (!evidence.value || auxiliaryGapCount.value > 0 || auxiliaryGateEntries.value.some(gate => gate.status === 'uncertain')) {
    return '未覆盖'
  }
  return '一致'
})
const nextActionText = computed(() => {
  const decision = form.final_work_order_decision || review.value.work_order_decision
  if (review.value.status === 'archived') return '已归档'
  if (review.value.status === 'rejected') return '已退回'
  if (review.value.status === 'needs_evidence') return '等待运维补材料'
  if (decision === 'approve' && review.value.exclusion_required) return '确认剔除区间后归档'
  if (decision === 'approve') return '确认归档'
  if (decision === 'reject') return '退回运维修改'
  if (decision === 'needs_evidence') return '退回运维补材料'
  return '人工确认'
})
const overviewTone = computed(() => {
  if (review.value.status === 'archived') return 'good'
  if (review.value.status === 'rejected') return 'bad'
  if (review.value.status === 'needs_evidence') return 'warn'
  const decision = form.final_work_order_decision || review.value.work_order_decision
  if (decision === 'approve') return 'good'
  if (decision === 'reject') return 'bad'
  return 'warn'
})
const coreGateIssueRows = computed(() => gateEntries.value
  .filter(gate => gate.scope === 'core' && ['fail', 'uncertain'].includes(gate.status))
  .map(gate => shortText(gate.missing || gate.basis || gate.label))
  .filter(Boolean))
const overviewIssueTitle = computed(() => (
  (form.final_work_order_decision || review.value.work_order_decision) === 'approve'
    ? '注意事项'
    : '需处理问题'
))
const overviewIssueRows = computed(() => {
  const warnings = Array.isArray(review.value.audit_warnings) ? review.value.audit_warnings.map(item => shortText(item)).filter(Boolean) : []
  if ((form.final_work_order_decision || review.value.work_order_decision) === 'approve') {
    return warnings.slice(0, 3)
  }
  const fallbackGaps = evidenceGapEntries.value
    .filter(gap => String(gap?.role || gap?.scope || 'core').toLowerCase() === 'core')
    .map(gap => shortText(`${gap.group || '证据'} / ${gap.item || '缺口'}：${gap.reason || ''}`))
    .filter(Boolean)
  return [...coreGateIssueRows.value, ...warnings, ...fallbackGaps].slice(0, 3)
})
const coreReasonText = computed(() => (
  shortText(review.value.review_summary || firstSentence(review.value.review_comment) || overviewIssueRows.value[0]) ||
  'AI 已完成结构化审核，详细依据可在下方追溯。'
))
const reviewFactCards = computed(() => {
  const failureFact = review.value.failure_fact || {}
  const disposal = review.value.disposal || {}
  const recovery = review.value.recovery || {}
  const flagBoundary = review.value.flag_boundary || {}
  const cards = [
    {
      key: 'failure_fact',
      label: '失败事实',
      summary: summaryFromObject(failureFact, ['summary', 'event_type', 'pollutant', 'reported_start'], 180) || '暂无失败事实摘要',
      detail: summaryFromObject(failureFact, ['fact_basis', 'basis'], 220)
    },
    {
      key: 'disposal',
      label: '处置建议',
      summary: summaryFromObject(disposal, ['action', 'status'], 180) || '暂无处置建议',
      detail: summaryFromObject(disposal, ['basis', 'reason'], 220)
    },
    {
      key: 'recovery',
      label: '恢复验证',
      summary: summaryFromObject(recovery, ['status', 'recovery_time', 'stable_window', 'stability_window'], 180) || '暂无恢复验证',
      detail: summaryFromObject(recovery, ['basis'], 220)
    },
    {
      key: 'flag_boundary',
      label: '标识边界',
      summary: summaryFromObject(flagBoundary, ['status', 'start', 'end'], 180) || '暂无标识边界',
      detail: summaryFromObject(flagBoundary, ['basis', 'sources'], 220)
    },
    {
      key: 'neighbor_comparison',
      label: '同城对比',
      summary: shortText(review.value.neighbor_comparison || '', 180) || '暂无同城对比说明',
      detail: ''
    }
  ]
  return cards.filter(card => card.summary || card.detail)
})
const evidenceCoverageGroups = computed(() => {
  const fault = isSop03.value ? transmissionFault.value : environmentalFault.value
  const groups = [
    { key: 'required', label: '必备证据', items: Array.isArray(fault.required_evidence) ? fault.required_evidence : [] },
    { key: 'supporting', label: '辅助证据', items: Array.isArray(fault.supporting_evidence) ? fault.supporting_evidence : [] },
    { key: 'rebuttal', label: '反证线索', items: Array.isArray(fault.rebuttal_evidence) ? fault.rebuttal_evidence : [] }
  ]
  return groups.filter(group => group.items.length)
})
const collectionNotes = computed(() => {
  const notes = Array.isArray(evidence.value?.collection_notes) ? evidence.value.collection_notes : []
  return notes.filter(note => String(note || '').trim())
})
const footerHint = computed(() => (
  review.value.status !== 'pending_review'
    ? reviewStatusDetail.value
    : review.value.exclusion_required
    ? '涉及剔除候选，确认归档会同时确认异常时段和合理性判断。'
    : '确认归档只记录本系统审核结论，不自动回写江苏平台。'
))
const gateEntries = computed(() => {
  const gates = review.value.gates || {}
  return Object.entries(gates).map(([key, raw]) => {
    const [code, label] = allGateLabels[key] || [key, key]
    const item = raw && typeof raw === 'object' ? raw : { status: raw }
    const missing = Array.isArray(item.missing_evidence) ? item.missing_evidence.join('；') : ''
    const scope = String(item.scope || item.evidence_role || 'core').toLowerCase()
    return {
      key,
      code,
      label,
      status: item.status || 'uncertain',
      scope,
      scopeLabel: gateScopeLabel(scope),
      basis: item.basis || '',
      missing
    }
  })
})

const evidenceWindow = computed(() => evidence.value?.evidence_time_window || null)
const environmentalFault = computed(() => evidence.value?.environmental_fault || {})
const transmissionFault = computed(() => evidence.value?.transmission_fault || {})
const transmissionEvidence = computed(() => evidence.value?.transmission_evidence || {})
const sopRoute = computed(() => evidence.value?.sop_route || {})
const evidenceGapEntries = computed(() => {
  const gaps = environmentalFault.value?.evidence_gaps ||
    transmissionFault.value?.evidence_gaps ||
    evidence.value?.evidence_gaps ||
    []
  return Array.isArray(gaps) ? gaps : []
})
const sop02RouteFields = computed(() => {
  const route = sopRoute.value || {}
  const fault = environmentalFault.value || {}
  const fields = [
    ['SOP', evidence.value?.sop_id || sopId.value],
    ['异常表现', eventTypeLabel(fault.event_type || route.fault_event_type || review.value.event_type)],
    ['路由依据', route.route_reason],
    ['关键词', joinList(route.keyword_hits)]
  ]
  return fields
    .map(([label, value]) => ({ label, value: valueText(value) }))
    .filter(field => field.value)
})
const environmentalEvidenceFields = computed(() => {
  const alarm = evidence.value?.station_alarm_logs || {}
  const environment = evidence.value?.station_environment_history || {}
  const inspection = evidence.value?.auto_inspection || {}
  const sameCity = evidence.value?.same_city_monitoring || {}
  const fields = [
    ['站房告警', resultSummary(alarm)],
    ['动环历史', resultSummary(environment)],
    ['自动巡检', resultSummary(inspection)],
    ['同城对比', resultSummary(sameCity)],
    ['缺口数量', evidenceGapEntries.value.length ? `${evidenceGapEntries.value.length} 项` : '0 项']
  ]
  return fields
    .map(([label, value]) => ({ label, value: valueText(value) }))
    .filter(field => field.value)
})
const sop03RouteFields = computed(() => {
  const route = sopRoute.value || {}
  const fault = transmissionFault.value || {}
  const fields = [
    ['SOP', evidence.value?.sop_id || sopId.value],
    ['传输状态', eventTypeLabel(fault.event_type || route.fault_event_type || review.value.event_type || review.value.transmission_status)],
    ['路由依据', route.route_reason],
    ['关键词', joinList(route.keyword_hits)]
  ]
  return fields
    .map(([label, value]) => ({ label, value: valueText(value) }))
    .filter(field => field.value)
})
const routeFields = computed(() => (isSop03.value ? sop03RouteFields.value : sop02RouteFields.value))
const transmissionEvidenceFields = computed(() => {
  const evidenceGroup = transmissionEvidence.value || {}
  const fields = [
    ['本地数据/缓存', resultSummary(evidenceGroup.local_data)],
    ['平台接收记录', resultSummary(evidenceGroup.platform_receipt)],
    ['补传记录', resultSummary(evidenceGroup.retransmission)],
    ['时间戳连续性', resultSummary(evidenceGroup.timestamp_continuity)],
    ['通信/站点告警', resultSummary(evidenceGroup.communication_alarms || evidence.value?.station_alarm_logs)],
    ['平台监测断点', resultSummary(evidenceGroup.platform_monitoring || evidence.value?.monitoring)],
    ['缺口数量', evidenceGapEntries.value.length ? `${evidenceGapEntries.value.length} 项` : '0 项']
  ]
  return fields
    .map(([label, value]) => ({ label, value: valueText(value) }))
    .filter(field => field.value)
})
const routeEvidenceFields = computed(() => (
  isSop03.value ? transmissionEvidenceFields.value : environmentalEvidenceFields.value
))

const workOrderDetail = computed(() => {
  const rows = evidence.value?.work_order?.detail?.data
  return Array.isArray(rows) && rows.length ? rows[0] : {}
})
const workOrderWo = computed(() => workOrderDetail.value?.wo || {})
const workflowNode = computed(() => evidence.value?.workflow_node || {})
const workOrderFields = computed(() => {
  const wo = workOrderWo.value || {}
  const fields = [
    ['工单标题', wo.orderTitle || wo.title || evidence.value?.summary],
    ['工单内容', wo.orderContent || wo.content || wo.faultDescription],
    ['工单类型', wo.orderTypeStr || wo.orderType],
    ['创建类型', wo.orderCreateTypeStr || wo.orderCreateType],
    ['紧急程度', wo.urgencyTypeStr || wo.urgencyType],
    ['创建时间', cleanTime(wo.createTime)],
    ['创建人', wo.createUserName],
    ['运维单位', wo.operationUnitName],
    ['当前节点', workflowNode.value.current_point],
    ['节点状态', workflowNode.value.workflow_status || wo.workFlowStatusStr || wo.workFlowStatus],
    ['工单状态', workflowNode.value.order_status || wo.orderStatusStr || wo.orderStatus],
    ['附件', Array.isArray(workOrderDetail.value.attachments) ? `${workOrderDetail.value.attachments.length} 个` : '']
  ]
  return fields
    .map(([label, value]) => ({ label, value: valueText(value) }))
    .filter(field => field.value)
})
const faultDeviceFields = computed(() => {
  const device = workOrderDetail.value?.faultDevice || {}
  const fields = [
    ['设备编码', device.deviceCode],
    ['设备类型', device.deviceTypeName || device.deviceType],
    ['品牌', device.deviceBrand],
    ['型号', device.deviceModel],
    ['状态', device.deviceStats],
    ['投用日期', cleanTime(device.useDate)]
  ]
  return fields
    .map(([label, value]) => ({ label, value: valueText(value) }))
    .filter(field => field.value)
})
const faultContentRows = computed(() => {
  const rows = workOrderDetail.value?.faultContentItems
  if (!Array.isArray(rows)) return []
  return rows.map(row => row.faultContentName || compactRow(row)).filter(Boolean)
})
const workOrderFlowRows = computed(() => {
  const rows = workOrderDetail.value?.details
  if (!Array.isArray(rows)) return []
  return rows.map((row, index) => ({
    key: row.id || row.taskId || index,
    step: row.processStepName || row.processStep || '-',
    user: row.processUserName || '-',
    time: cleanTime(row.processTimeStr || row.processEdtTime || row.processSdtTime) || '-',
    remark: row.submitRemark || row.processRemark || compactObject(row.faultDto) || '-'
  }))
})
const attachmentRows = computed(() => {
  const rows = workOrderDetail.value?.attachments
  if (!Array.isArray(rows)) return []
  return rows.map((row, index) => {
    const contentUrl = row.content_url || row.preview_url || row.read_url || ''
    const key = `${row.id || row.filePath || index}:${contentUrl}`
    const state = attachmentPreviewState[key] || {}
    const isImage = /^image\//i.test(row.content_type || row.media_type || '')
      || /\.(png|jpe?g|gif|webp|bmp)$/i.test(String(row.fileName || row.filePath || ''))
    return {
      key,
      fileName: row.fileName || row.filePath || '-',
      typeCode: row.typeCode || row.functionCode || '-',
      status: row.download_status || row.status || '-',
      error: row.download_error || '',
      contentUrl,
      contentType: row.content_type || row.media_type || '',
      isImage,
      previewUrl: state.url || '',
      previewError: state.error || '',
      previewLoading: isImage && Boolean(contentUrl) && !state.url && !state.error
    }
  })
})

const setAttachmentPreviewUrl = (key, url) => {
  attachmentPreviewState[key] = { url: url || '', error: '' }
}

const setAttachmentPreviewError = (key, error) => {
  attachmentPreviewState[key] = {
    url: '',
    error: error?.message || String(error || '图片加载失败')
  }
}

const attachmentLightboxImages = computed(() => attachmentRows.value
  .filter(row => row.isImage && row.previewUrl)
  .map(row => ({ src: row.previewUrl, alt: row.fileName, key: row.key }))
)

const openAttachmentLightbox = row => {
  if (!row?.previewUrl) return
  const index = attachmentLightboxImages.value.findIndex(image => image.key === row.key)
  attachmentLightboxStartIndex.value = index >= 0 ? index : 0
  attachmentLightboxVisible.value = true
}

const qualityControl = computed(() => evidence.value?.quality_control || {})
const qcHistoryRows = computed(() => {
  const rows = qualityControl.value?.history?.data
  return Array.isArray(rows) ? rows : []
})
const qcRunLogCount = computed(() => {
  const runLogs = qualityControl.value?.run_logs
  if (!Array.isArray(runLogs)) return 0
  return runLogs.reduce((sum, item) => {
    const rows = item?.result?.data || item?.data
    return sum + (Array.isArray(rows) ? rows.length : 0)
  }, 0)
})
const qcHistoryTableRows = computed(() => qcHistoryRows.value.map((row, index) => ({
  key: row.id || row.rId || index,
  status: row.tStatusStr || row.status || '-',
  pollutant: row.poll || row.pollutant || '-',
  qcType: row.qcType || row.qc_type || row.group || '-',
  start: cleanTime(row.rStartStr || row.rStart || row.sStartStr || row.sStart) || '-',
  end: cleanTime(row.endTimeStr || row.endTime) || '-',
  values: `${valueText(row.tValue) || '-'} / ${valueText(row.rValue) || '-'}`,
  result: row.qcResult || row.qc_result || '-'
})))
const qcPlatformStages = (task, history, statusDetail, steps, curveWindow) => {
  const historyRow = task.history_row || history.history_row || {}
  const target = firstText(task.t_value, task.tValue, history.t_value, history.tValue, historyRow.tValue)
  const reading = firstText(task.r_value, task.rValue, history.r_value, history.rValue, historyRow.rValue)
  const hasReading = target !== '' || reading !== ''
  const progress = steps.find(step => /进行|稳定|读数|检查/.test(`${step.phase || ''}${step.label || ''}`))
  return [
    { name: '质控参数检查', value: cleanTime(firstText(historyRow.sStartStr, historyRow.sStart, task.s_start, history.s_start)) || '已取证' },
    { name: '开始质控任务', value: cleanTime(firstText(historyRow.rStartStr, historyRow.rStart, task.r_start, history.r_start, curveWindow.start)) },
    { name: '质控进行中检查', value: progress ? `${progress.phase || progress.label}${progress.status ? ` · ${progress.status}` : ''}` : '' },
    { name: '稳定后读数', value: hasReading ? `${valueText(target) || '-'} / ${valueText(reading) || '-'}` : '' },
    { name: '结束质控任务', value: cleanTime(firstText(historyRow.endTimeStr, historyRow.endTime, task.end_time, history.end_time, curveWindow.end)) }
  ]
}
const qcTaskDetailEntries = computed(() => {
  const tasks = qualityControl.value?.task_details
  if (!Array.isArray(tasks)) return []
  return tasks.map((item, index) => {
    const task = item?.task || {}
    const history = item?.history || {}
    const status = item?.status || {}
    const statusDetail = item?.status_detail || {}
    const runLog = item?.run_log || {}
    const curve = item?.curve || {}
    const curveWindow = item?.curve_window || {}
    const steps = Array.isArray(statusDetail.steps) ? statusDetail.steps : []
    const logs = Array.isArray(runLog.data) ? runLog.data : []
    const historyDetail = statusDetail.history_detail || history.history_detail || history.HistoryDetail || {}
    const dataValues = history.data_values || history.DataValues || statusDetail.data_values || []
    const resultValues = history.result_values || history.ResultValues || statusDetail.result_values || []
    const windowStart = curveWindow.start || task.r_start || history.r_start
    const windowEnd = curveWindow.end || task.end_time || history.end_time
    return {
      key: `qc-task-${index}`,
      title: [task.qc_type, task.pollutant, task.qc_result || history.qc_result].filter(Boolean).join(' · ') || `质控任务 ${index + 1}`,
      window: formatRange(windowStart, windowEnd),
      curveWindow: formatRange(curveWindow.start, curveWindow.end),
      statusText: statusDetail.status || status.status || '',
      statusMessage: statusDetail.message || status.summary || '',
      parseError: statusDetail.parse_error || '',
      stepCount: statusDetail.step_count || steps.length,
      steps,
      logs,
      logCount: logs.length,
      curveCount: Array.isArray(curve.data) ? curve.data.length : 0,
      curveSummary: curve.summary || '',
      historyDetail,
      dataValues,
      resultValues,
      platformStages: qcPlatformStages(task, history, statusDetail, steps, curveWindow),
      historySummary: [
        ['开始时间', task.r_start || history.r_start],
        ['结束时间', task.end_time || history.end_time],
        ['质控类型', task.qc_type || history.qc_type],
        ['污染物', task.pollutant || history.pollutant],
        ['质控结果', task.qc_result || history.qc_result]
      ].filter(([, value]) => valueText(value))
    }
  })
})
const qcSummaryFields = computed(() => {
  const history = qualityControl.value?.history || {}
  const curves = qualityControl.value?.monitoring_curves
  const tasks = qualityControl.value?.task_details
  return [
    { label: '历史任务', value: dataStatusText(history) },
    { label: '任务详情', value: `${Array.isArray(tasks) ? tasks.length : 0} 条` },
    { label: '运行日志', value: `${qcRunLogCount.value} 条` },
    { label: '质控曲线', value: `${Array.isArray(curves) ? curves.length : 0} 组` }
  ]
})

const selectedPollutants = computed(() => {
  const pollutants = (review.value.pollutants || []).filter(Boolean)
  return pollutants.length ? pollutants : ['PM2.5', 'PM10', 'SO2', 'NO2', 'O3', 'CO']
})
const qcCurveEntries = computed(() => {
  const directCurves = qualityControl.value?.monitoring_curves
  const taskDetails = qualityControl.value?.task_details
  const curves = Array.isArray(directCurves) && directCurves.length
    ? directCurves
    : (Array.isArray(taskDetails) ? taskDetails.map(item => ({ task: item?.task, result: item?.curve, window: item?.curve_window })) : [])
  return curves.map((item, index) => {
    const task = item?.task || {}
    const result = item?.result || {}
    const window = item?.window || {}
    const records = Array.isArray(result.data) ? result.data : []
    const pollutant = task.pollutant || records[0]?.poll || '目标污染物'
    const points = pointsFromRecords(records, ['dataValue', 'value', ...pollutantFieldCandidates([pollutant])], true)
    const target = numberValue(firstText(task.t_value, task.tValue, task.history_row?.tValue))
    const series = [{
      name: `${pollutant} 分钟浓度`,
      color: '#61d394',
      points
    }]
    if (target !== null && points.length) {
      series.push({
        name: '目标值',
        color: '#f6bd4a',
        points: points.map(point => ({ time: point.time, value: target }))
      })
    }
    return {
      key: `qc-${index}`,
      title: [pollutant, task.qc_type || '质控曲线', task.qc_result].filter(Boolean).join(' · '),
      subtitle: `${formatRange(window.start, window.end)}；${resultSummary(result) || `${points.length} 点`}`,
      unit: unitFromRecords(records),
      markAreas: window.start && window.end ? [{ name: '质控期间', start: window.start, end: window.end }] : [],
      series
    }
  }).filter(entry => entry.series.some(series => series.points.length))
})
const monitoringLabels = {
  station_5minute_raw: '5分钟原始数据',
  station_5minute_audited: '5分钟审核数据',
  station_hour_raw: '小时原始数据',
  station_hour_audited: '小时审核数据'
}
const monitoringStatusRows = computed(() => {
  const monitoring = evidence.value?.monitoring || {}
  return Object.entries(monitoringLabels).map(([key, label]) => ({
    key,
    label,
    status: dataStatusText(monitoring[key]),
    summary: resultSummary(monitoring[key]) || '-'
  }))
})
const transmissionStatusRows = computed(() => {
  const evidenceGroup = transmissionEvidence.value || {}
  const rows = [
    ['local_data', '本地数据/缓存', evidenceGroup.local_data],
    ['platform_receipt', '平台接收记录', evidenceGroup.platform_receipt],
    ['communication_alarms', '通信/站点告警', evidenceGroup.communication_alarms || evidence.value?.station_alarm_logs],
    ['retransmission', '补传记录', evidenceGroup.retransmission],
    ['timestamp_continuity', '时间戳连续性', evidenceGroup.timestamp_continuity],
    ['platform_monitoring', '平台监测数据', evidenceGroup.platform_monitoring || evidence.value?.monitoring]
  ]
  return rows.map(([key, label, result]) => ({
    key,
    label,
    status: dataStatusText(result),
    summary: resultSummary(result) || '-'
  }))
})
const transmissionGapEntries = computed(() => {
  const gaps = transmissionFault.value?.evidence_gaps || evidence.value?.evidence_gaps || []
  return Array.isArray(gaps) ? gaps : []
})
const monitoringEntries = computed(() => {
  const monitoring = evidence.value?.monitoring || {}
  const fiveMinuteEntries = ['station_5minute_raw', 'station_5minute_audited']
    .map(key => {
      const result = monitoring[key] || {}
      const records = Array.isArray(result.data) ? result.data : []
      const availablePollutants = key === 'station_5minute_raw' ? availablePollutantsFromRecords(records) : []
      const pollutants = availablePollutants.length ? availablePollutants : selectedPollutants.value
      const series = buildPollutantSeries(records, pollutants)
      const unitSet = Array.from(new Set(series.map(item => item.unit).filter(Boolean)))
      return {
        key,
        title: monitoringLabels[key],
        granularity: '5min',
        pollutants: series.map(item => item.name),
        subtitle: resultSummary(result) || `${records.length} 条`,
        unit: unitSet.length === 1 ? unitSet[0] : '浓度',
        series
      }
    })
    .filter(entry => entry.series.length || (monitoring[entry.key]?.record_count || 0) > 0)

  const rawResult = monitoring.station_hour_raw || {}
  const auditedResult = monitoring.station_hour_audited || {}
  const rawRecords = Array.isArray(rawResult.data) ? rawResult.data : []
  const auditedRecords = Array.isArray(auditedResult.data) ? auditedResult.data : []
  const hourSeries = []
  const hourPollutants = []
  selectedPollutants.value.forEach((pollutant, index) => {
    const color = chartColors[index % chartColors.length]
    const rawPoints = pointsFromRecords(rawRecords, pollutantFieldCandidates([pollutant]), false)
    const auditedPoints = pointsFromRecords(auditedRecords, pollutantFieldCandidates([pollutant]), false)
    if (rawPoints.length || auditedPoints.length) hourPollutants.push(pollutant)
    if (rawPoints.length) {
      hourSeries.push({
        name: `${pollutant} 原始`,
        color: colorWithAlpha(color, 0.5),
        unit: pollutantUnit(pollutant),
        axis: pollutantAxis(pollutant),
        points: rawPoints
      })
    }
    if (auditedPoints.length) {
      hourSeries.push({
        name: `${pollutant} 审核`,
        color,
        unit: pollutantUnit(pollutant),
        axis: pollutantAxis(pollutant),
        points: auditedPoints
      })
    }
  })
  const rawCount = Number(rawResult.record_count ?? rawRecords.length) || 0
  const auditedCount = Number(auditedResult.record_count ?? auditedRecords.length) || 0
  const hourEntry = {
    key: 'station_hour',
    title: '小时数据（原始/审核）',
    granularity: 'hour',
    pollutants: hourPollutants,
    subtitle: `原始 ${rawCount} 条，审核 ${auditedCount} 条`,
    unit: hourPollutants.length === 1 ? pollutantUnit(hourPollutants[0]) : '浓度',
    series: hourSeries
  }
  const hasHourRecords = hourSeries.length || rawCount > 0 || auditedCount > 0
  return hasHourRecords ? [...fiveMinuteEntries, hourEntry] : fiveMinuteEntries
})
const cityWeather = computed(() => evidence.value?.city_weather || {})
const weatherMonitoringEntries = computed(() => selectedPollutants.value.map(pollutant => ({
  key: `weather-${pollutant}`, title: `${pollutant} 小时数据与城区气象`,
  granularity: 'hour', pollutants: [pollutant], unit: pollutantUnit(pollutant),
  series: ['station_hour_raw', 'station_hour_audited'].map(key => ({
    name: `${pollutant} ${key.endsWith('_raw') ? '原始' : '审核'}`,
    points: pointsFromRecords(evidence.value?.monitoring?.[key]?.data || [], pollutantFieldCandidates([pollutant]), false)
  }))
})))
const sameCityLabels = {
  station_hour_raw: '同城小时原始数据',
  station_hour_audited: '同城小时审核数据'
}
const sameCityStatusRows = computed(() => {
  const comparison = evidence.value?.same_city_monitoring || {}
  return Object.entries(sameCityLabels).map(([key, label]) => ({
    key,
    label,
    status: dataStatusText(comparison[key]),
    summary: resultSummary(comparison[key]) || '-'
  }))
})
const sameCityMonitoringEntries = computed(() => {
  const comparison = evidence.value?.same_city_monitoring || {}
  const pollutant = selectedPollutants.value[0] || 'PM2.5'
  const target = comparison.target_station_code || review.value.station?.station_code
  return Object.entries(sameCityLabels)
    .map(([key, title]) => {
      const result = comparison[key] || {}
      const records = Array.isArray(result.data) ? result.data : []
      return {
        key: `same-city-${key}`,
        title: `${title} · ${pollutant}`,
        granularity: 'hour',
        pollutants: [pollutant],
        subtitle: resultSummary(result) || `${records.length} 条`,
        unit: pollutantUnit(pollutant),
        series: buildStationComparisonSeries(records, pollutant, target)
      }
    })
    .filter(entry => entry.series.length || (comparison[entry.key.replace('same-city-', '')]?.record_count || 0) > 0)
})
const exclusionMarkAreas = computed(() => form.exclusion_intervals
  .filter(interval => interval.start_local && interval.end_local)
  .map(interval => ({
    name: `${interval.pollutant || '剔除候选'} ${granularityLabel(interval.granularity)}`,
    pollutant: interval.pollutant || '',
    granularity: interval.granularity || '',
    start: fromLocalInput(interval.start_local),
    end: fromLocalInput(interval.end_local)
  })))
const overviewExclusionRows = computed(() => form.exclusion_intervals
  .filter(interval => interval.start_local && interval.end_local)
  .map(interval => ({
    pollutant: interval.pollutant || '剔除候选',
    granularity: granularityLabel(interval.granularity),
    start: fromLocalInput(interval.start_local),
    end: fromLocalInput(interval.end_local),
    range: formatRange(fromLocalInput(interval.start_local), fromLocalInput(interval.end_local))
  })))
const markAreasForEntry = entry => {
  const granularity = String(entry?.granularity || '').toLowerCase()
  const pollutants = new Set(
    (entry?.pollutants || entry?.series?.map(item => item.name) || [])
      .map(normalizePollutant)
      .filter(Boolean)
  )
  return exclusionMarkAreas.value.filter(area => {
    const areaGranularity = String(area.granularity || '').toLowerCase()
    const areaPollutant = normalizePollutant(area.pollutant)
    const granularityMatches = !areaGranularity || !granularity || areaGranularity === granularity
    const pollutantMatches = !areaPollutant || !pollutants.size || pollutants.has(areaPollutant)
    return granularityMatches && pollutantMatches
  })
}
const monitoringPointCount = computed(() => pointCountForEntries(monitoringEntries.value))
const sameCityPointCount = computed(() => pointCountForEntries(sameCityMonitoringEntries.value))
const qcCurvePointCount = computed(() => pointCountForEntries(qcCurveEntries.value))
const qualityModuleLabel = computed(() => {
  if (isSop02.value) return '质控/复测'
  if (isSop03.value) return '质控/辅助'
  return '质控信息'
})
const notify = (text, tone = 'info') => {
  message.value = text
  messageTone.value = tone
}

const hydrate = () => {
  form.final_work_order_decision = review.value.final_work_order_decision ||
    review.value.work_order_decision || 'needs_evidence'
  if (form.final_work_order_decision === 'needs_evidence') form.final_work_order_decision = 'reject'
  form.review_comment = review.value.human_review_comment || ''
  form.exclusion_intervals = (review.value.final_exclusion_intervals ||
    review.value.exclusion_intervals || []).map(interval => ({
    pollutant: interval.pollutant || '',
    granularity: interval.granularity || 'hour',
    start_local: toLocalInput(interval.start),
    end_local: toLocalInput(interval.end),
    boundary_text: (interval.boundary_sources || []).join('\n'),
    reasonableness_status: interval.reasonableness_check?.status || 'uncertain',
    reasonableness_basis: interval.reasonableness_check?.basis || ''
  }))
}

const reviewPayload = () => ({
  review_comment: form.review_comment.trim(),
  final_work_order_decision: form.final_work_order_decision,
  data_impact: review.value.data_impact || [],
  exclusion_required: review.value.exclusion_required === true,
  exclusion_intervals: form.exclusion_intervals.map(interval => ({
    pollutant: interval.pollutant.trim(),
    granularity: interval.granularity,
    start: fromLocalInput(interval.start_local),
    end: fromLocalInput(interval.end_local),
    boundary_sources: interval.boundary_text.split('\n').map(item => item.trim()).filter(Boolean),
    reasonableness_check: {
      status: interval.reasonableness_status,
      basis: interval.reasonableness_basis.trim()
    }
  }))
})

const refreshReview = async () => {
  const reviewId = review.value.review_id
  if (!reviewId) return
  try {
    const response = await authFetch(`/api/jiangsu/work-order-reviews/${reviewId}`, { cache: 'no-store' })
    if (response.ok) {
      const payload = await response.json()
      if (payload?.review) {
        review.value = payload.review
        hydrate()
      }
    }
  } catch {
    hydrate()
  }
  await refreshEvidence()
}

const refreshEvidence = async () => {
  const reviewId = review.value.review_id
  if (!reviewId) return
  evidenceLoading.value = true
  evidenceError.value = ''
  try {
    const response = await authFetch(`/api/jiangsu/work-order-reviews/${reviewId}/evidence`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      evidence.value = null
      evidenceError.value = response.status === 404
        ? '未找到该审核记录的证据包'
        : (typeof payload?.detail === 'string' ? payload.detail : '证据包加载失败')
      return
    }
    evidence.value = payload.evidence || null
  } catch (failure) {
    evidenceError.value = failure?.message || '证据包加载失败'
  } finally {
    evidenceLoading.value = false
  }
}

const postAction = async (path, body, successText) => {
  submitting.value = true
  message.value = ''
  try {
    const response = await authFetch(`/api/jiangsu/work-order-reviews/${review.value.review_id}/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = typeof payload?.detail === 'string' ? payload.detail : '操作失败'
      return notify(detail, 'error')
    }
    review.value = payload.review || review.value
    hydrate()
    notify(successText, 'success')
  } catch (failure) {
    notify(failure?.message || '网络异常，操作失败', 'error')
  } finally {
    submitting.value = false
  }
}

const validateExclusionIntervals = () => {
  if (!review.value.exclusion_required) return true
  if (!form.exclusion_intervals.length) {
    notify('涉及数据剔除时，必须确认至少一个异常区间。', 'error')
    return false
  }
  for (const interval of form.exclusion_intervals) {
    if (interval.granularity !== 'hour') {
      notify('仅允许确认小时数据剔除，5分钟数据仅作分析参考。', 'error')
      return false
    }
    if (!interval.pollutant.trim() || !interval.start_local || !interval.end_local) {
      notify('请完整填写剔除污染物和异常起止时间。', 'error')
      return false
    }
    if (!interval.boundary_text.trim() || !interval.reasonableness_basis.trim()) {
      notify('请填写剔除区间的边界来源和合理性判断依据。', 'error')
      return false
    }
  }
  return true
}

const confirmReview = () => {
  if (form.final_work_order_decision !== 'approve') return rejectReview()
  if (!validateExclusionIntervals()) return
  postAction('confirm', reviewPayload(), '审核结论已归档')
}

const rejectReview = () => {
  if (!form.review_comment.trim()) return notify('退回修改必须填写审核意见', 'error')
  postAction('reject', reviewPayload(), '审核已退回修改')
}

onMounted(async () => {
  hydrate()
  await refreshReview()
})
</script>

<style scoped>
.qc-review-panel { display: flex; width: 100%; height: 100%; min-height: 0; max-width: none; margin: 0; flex-direction: column; overflow: hidden; border: 0; border-radius: 0; background: transparent; color: #111827; box-sizing: border-box; font-family: "Microsoft YaHei", sans-serif; }
.banner { margin: 12px 20px 0; padding: 9px 12px; border-radius: 5px; font-size: 12px; }
.banner.info { border: 1px solid rgba(130, 200, 255, .35); background: rgba(14, 39, 67, .82); }
.banner.success { border: 1px solid rgba(95, 210, 138, .45); background: rgba(19, 91, 59, .35); color: #a8f0c1; }
.banner.error { border: 1px solid rgba(255, 107, 90, .5); background: rgba(98, 34, 31, .48); color: #ffbeb6; }
.decision-overview { display: grid; flex: 0 0 auto; gap: 10px; margin: 0; padding: 0 0 12px; border: 0; border-bottom: 1px solid rgba(125, 174, 220, .24); background: transparent; }
.decision-overview.good { border-color: rgba(95, 210, 138, .34); }
.decision-overview.warn { border-color: rgba(245, 158, 11, .38); }
.decision-overview.bad { border-color: rgba(255, 107, 90, .42); }
.overview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; }
.overview-grid > div { display: grid; gap: 4px; min-width: 0; padding: 4px 0; }
.overview-grid span, .overview-reason span, .overview-exclusions > span, .overview-issues > span { color: #93bddb; font-size: 11px; }
.overview-grid strong { min-width: 0; color: #fff; font-size: 13px; line-height: 1.35; overflow-wrap: anywhere; }
.overview-grid em { color: #bed6e7; font-size: 10px; font-style: normal; line-height: 1.45; overflow-wrap: anywhere; }
.overview-meta { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; margin: 0; color: #aac5da; font-size: 11px; line-height: 1.4; }
.overview-meta span { white-space: nowrap; }
.overview-reason { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 8px; align-items: start; margin: 0; padding: 2px 0; }
.overview-reason strong { color: #e8f3fb; font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.consistency-summary { display: grid; gap: 12px; min-width: 0; }
.consistency-section { min-width: 0; border-top: 1px solid rgba(125, 174, 220, .22); padding-top: 10px; }
.consistency-section h4 { margin: 0 0 6px; color: #e8f3fb; font-size: 13px; }
.consistency-item { padding: 5px 0; font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.consistency-item p { margin: 0; white-space: pre-wrap; }
.consistency-item strong { color: #e8f3fb; margin-right: 10px; }
.consistency-item span, .consistency-empty { color: #93bddb; font-size: 11px; }
.consistency-item .missing { color: #ffd08a; }
.review-details { min-width: 0; border-top: 1px solid rgba(125, 174, 220, .24); margin-top: 8px; }
.review-details > summary { cursor: pointer; padding: 12px 0; color: #e8f3fb; font-size: 12px; font-weight: 600; overflow-wrap: anywhere; }
.review-details > summary span { float: right; margin-left: 12px; color: #93bddb; font-weight: 400; }
.review-details > summary:focus-visible { outline: 2px solid #62c6ff; outline-offset: 2px; }
.review-details > .section { padding: 0 0 12px; }
.consistency-section { color: #aac5da; }
.panel-body > .section { flex-shrink: 0; }
.overview-meta span { white-space: normal; overflow-wrap: anywhere; }
.overview-refs { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 8px; align-items: start; }
.overview-refs > div { display: flex; flex-wrap: wrap; gap: 6px; min-width: 0; }
.overview-refs em { padding: 4px 7px; border: 1px solid rgba(125, 174, 220, .2); border-radius: 4px; color: #e8f3fb; font-size: 11px; font-style: normal; line-height: 1.35; overflow-wrap: anywhere; }
.overview-exclusions, .overview-issues { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 8px; align-items: start; }
.overview-exclusions > div, .overview-issues > div { display: flex; flex-wrap: wrap; gap: 6px; min-width: 0; }
.overview-exclusions em, .overview-issues em { padding: 4px 7px; border: 1px solid rgba(125, 174, 220, .2); border-radius: 4px; color: #e8f3fb; font-size: 11px; font-style: normal; line-height: 1.35; overflow-wrap: anywhere; }
.overview-exclusions em { border-color: rgba(180, 83, 9, .28); background: rgba(246, 189, 74, .15); }
.panel-body { display: flex; flex-direction: column; gap: 16px; min-height: 0; min-width: 0; flex: 1 1 auto; overflow-y: auto; padding: 16px; }
.section { display: grid; gap: 10px; }
.section h4 { margin: 0; padding-bottom: 7px; border-bottom: 1px solid rgba(125, 174, 220, .24); color: #f5fbff; font-size: 13px; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; }
.summary-grid > div, .ai-decision { display: grid; gap: 4px; padding: 8px 10px; border: 1px solid rgba(125, 174, 220, .22); border-radius: 4px; background: rgba(16, 39, 64, .82); }
.summary-grid span, .ai-decision span, .field span { color: #93bddb; font-size: 11px; }
.summary-grid strong, .ai-decision strong { min-width: 0; color: #fff; font-size: 12px; overflow-wrap: anywhere; }
.decision-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; align-items: end; }
.field { display: grid; gap: 5px; }
.field input, .field select, .field textarea { width: 100%; padding: 7px 9px; border: 1px solid rgba(125, 174, 220, .34); border-radius: 4px; background: rgba(5, 18, 34, .92); box-sizing: border-box; color: #eef7ff; font-family: inherit; font-size: 12px; }
.field textarea { resize: vertical; line-height: 1.5; }
.field input:disabled, .field select:disabled, .field textarea:disabled { opacity: .62; }
.review-text, .hint, .empty { margin: 0; color: #b8d0e4; font-size: 12px; line-height: 1.7; }
.empty { padding: 10px; border: 1px dashed rgba(125, 174, 220, .28); border-radius: 4px; text-align: center; }
.empty.critical { border-color: rgba(255, 107, 90, .55); color: #ffbeb6; }
.warning-list { display: grid; gap: 6px; margin: 0; padding: 9px 12px 9px 28px; border: 1px solid rgba(245, 158, 11, .32); border-radius: 4px; background: rgba(87, 55, 10, .28); color: #ffe0a3; font-size: 12px; }
.evidence-layout, .platform-detail, .quality-layout, .chart-stack { display: grid; gap: 10px; }
.evidence-window { display: grid; gap: 4px; padding: 10px; border: 1px solid rgba(130, 200, 255, .28); border-radius: 4px; background: rgba(15, 47, 78, .72); }
.evidence-window span { color: #93bddb; font-size: 11px; }
.evidence-window strong { color: #fff; font-size: 12px; }
.evidence-window em { color: #ffd08a; font-size: 11px; font-style: normal; line-height: 1.55; }
.evidence-columns { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 8px; }
.evidence-card { display: grid; gap: 8px; padding: 10px; border: 1px solid rgba(125, 174, 220, .22); border-radius: 4px; background: rgba(16, 39, 64, .72); }
.evidence-card.wide { grid-column: 1 / -1; }
.evidence-card h5 { margin: 0; color: #f5fbff; font-size: 12px; }
.evidence-card dl { display: grid; grid-template-columns: 82px 1fr; gap: 6px 8px; margin: 0; font-size: 11px; line-height: 1.55; }
.evidence-card dt { color: #93bddb; }
.evidence-card dd { min-width: 0; margin: 0; color: #e8f3fb; overflow-wrap: anywhere; }
.gap-card { border-color: rgba(245, 158, 11, .34); background: rgba(67, 48, 18, .34); }
.gap-list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.gap-list li { display: grid; gap: 3px; color: #ffd08a; font-size: 11px; line-height: 1.5; }
.gap-list strong { color: #fff0be; font-size: 11px; }
.gap-list span { color: #e9c77f; overflow-wrap: anywhere; }
.structured-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; }
.structure-card { display: grid; gap: 6px; padding: 10px; border: 1px solid rgba(125, 174, 220, .22); border-radius: 4px; }
.structure-card h5 { margin: 0; color: #f5fbff; font-size: 12px; }
.structure-main { margin: 0; color: #dceaf6; font-size: 11px; line-height: 1.55; overflow-wrap: anywhere; }
.structure-detail { margin: 0; color: #aac5da; font-size: 11px; line-height: 1.55; overflow-wrap: anywhere; }
.chip-list { display: flex; flex-wrap: wrap; gap: 6px; }
.ref-chip { display: inline-flex; align-items: center; min-height: 24px; padding: 3px 8px; border: 1px solid rgba(125, 174, 220, .2); border-radius: 12px; color: #dceaf6; font-size: 11px; line-height: 1.3; }
.chip-note { margin: 0; color: #aac5da; font-size: 11px; line-height: 1.4; }
.timeline-list { display: grid; gap: 8px; }
.timeline-item { display: grid; gap: 6px; padding: 9px 10px; border: 1px solid rgba(125, 174, 220, .18); border-left: 3px solid rgba(35, 130, 214, .44); border-radius: 4px; }
.timeline-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; min-width: 0; }
.timeline-head strong { min-width: 0; color: #f5fbff; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.timeline-head span { flex: none; color: #93bddb; font-size: 10px; }
.timeline-item p { margin: 0; color: #bfd5e7; font-size: 11px; line-height: 1.5; overflow-wrap: anywhere; }
.timeline-meta { display: flex; flex-wrap: wrap; gap: 6px; }
.timeline-meta span { padding: 2px 6px; border-radius: 10px; background: rgba(35, 130, 214, .12); color: #82c8ff; font-size: 10px; }
.note-list { margin: 0; padding-left: 18px; color: #bfd5e7; font-size: 11px; line-height: 1.55; }
.note-list li { overflow-wrap: anywhere; }
.compact-list { display: grid; gap: 6px; max-height: 160px; overflow: auto; }
.compact-list p { margin: 0; color: #bfd5e7; font-size: 11px; line-height: 1.55; overflow-wrap: anywhere; }
.platform-table, .qc-table, .status-table { display: grid; border: 1px solid rgba(125, 174, 220, .22); border-radius: 4px; overflow: hidden; }
.flow-head, .flow-row { display: grid; grid-template-columns: 110px 86px 138px minmax(0, 1fr); gap: 8px; align-items: start; padding: 8px 10px; font-size: 12px; }
.attachment-head, .attachment-row { display: grid; grid-template-columns: 74px minmax(0, 1fr) 90px 100px; gap: 8px; align-items: center; padding: 8px 10px; font-size: 12px; }
.qc-head, .qc-row { display: grid; grid-template-columns: 78px 54px 100px 126px 126px 92px 64px; gap: 8px; align-items: center; padding: 8px 10px; font-size: 12px; }
.flow-head, .attachment-head, .qc-head { background: rgba(20, 55, 86, .9); color: #92c5e9; }
.flow-row, .attachment-row, .qc-row { border-top: 1px solid rgba(125, 174, 220, .16); color: #dceaf6; }
.flow-row strong, .attachment-row strong, .qc-row strong { color: #fff; overflow-wrap: anywhere; }
.flow-row p { min-width: 0; margin: 0; color: #bfd5e7; line-height: 1.55; overflow-wrap: anywhere; }
.qc-row span, .attachment-row span, .flow-row span { min-width: 0; overflow-wrap: anywhere; }
.attachment-thumb { position: relative; display: block; width: 74px; height: 58px; padding: 0; overflow: hidden; border: 1px solid rgba(125, 174, 220, .24); border-radius: 4px; background: rgba(8, 23, 40, .72); cursor: zoom-in; }
.attachment-thumb:disabled { cursor: wait; }
.attachment-thumb img { display: block; width: 100%; height: 100%; object-fit: cover; }
.attachment-thumb.placeholder { display: grid; place-items: center; color: #93bddb; font-size: 10px; text-align: center; }
.attachment-thumb-state { position: absolute; inset: 0; display: grid; place-items: center; background: rgba(8, 23, 40, .78); color: #93bddb; font-size: 10px; text-align: center; }
.attachment-thumb-state.error { color: #ffbeb6; }
.attachment-row span em { display: block; margin-top: 2px; color: #ffbeb6; font-style: normal; font-size: 10px; line-height: 1.4; }
.gate-scope { padding: 2px 7px; border-radius: 10px; background: rgba(35, 130, 214, .16); color: #82c8ff; font-size: 10px; font-style: normal; }
.status-table { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0; border: 0; overflow: visible; }
.status-table > div { display: grid; gap: 4px; margin: 0 8px 8px 0; padding: 8px 10px; border: 1px solid rgba(125, 174, 220, .22); border-radius: 4px; background: rgba(16, 39, 64, .72); }
.status-table span { color: #93bddb; font-size: 11px; }
.status-table strong { color: #fff; font-size: 12px; }
.status-table em { color: #aac5da; font-size: 11px; font-style: normal; line-height: 1.45; overflow-wrap: anywhere; }
.task-detail-stack { display: grid; gap: 8px; }
.task-detail-card { display: grid; gap: 10px; padding: 10px; border: 1px solid rgba(125, 174, 220, .22); border-radius: 4px; background: rgba(16, 39, 64, .72); }
.task-detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; min-width: 0; }
.task-detail-head strong { min-width: 0; color: #f5fbff; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-detail-head span { flex: none; color: #93bddb; font-size: 11px; }
.qc-stage-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; }
.qc-stage-strip > div { display: grid; gap: 4px; min-width: 0; padding: 7px 8px; border: 1px solid rgba(125, 174, 220, .18); border-radius: 4px; background: rgba(9, 24, 42, .58); }
.qc-stage-strip > div.filled { border-color: rgba(95, 210, 138, .28); background: rgba(15, 62, 52, .42); }
.qc-stage-strip span { color: #93bddb; font-size: 10px; }
.qc-stage-strip strong { color: #e8f3fb; font-size: 11px; line-height: 1.35; overflow-wrap: anywhere; }
.task-detail-meta, .task-summary-grid, .task-detail-columns { display: grid; gap: 6px; }
.task-detail-meta { grid-template-columns: repeat(2, minmax(0, 1fr)); color: #aac5da; font-size: 11px; line-height: 1.5; }
.task-note { margin: 0; color: #ffd08a; font-size: 11px; line-height: 1.5; }
.task-note.critical { color: #ffbeb6; }
.task-summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.task-summary-grid > div, .task-detail-columns > div { display: grid; gap: 4px; padding: 8px 9px; border: 1px solid rgba(125, 174, 220, .18); border-radius: 4px; background: rgba(9, 24, 42, .58); }
.task-summary-grid span, .task-detail-columns span { color: #93bddb; font-size: 11px; }
.task-summary-grid strong, .task-detail-columns p { margin: 0; color: #e8f3fb; font-size: 11px; line-height: 1.55; overflow-wrap: anywhere; }
.step-list { display: grid; gap: 6px; max-height: 240px; overflow: auto; padding-right: 2px; }
.step-item { display: grid; grid-template-columns: 24px 1fr; gap: 8px; align-items: start; padding: 8px 9px; border: 1px solid rgba(125, 174, 220, .16); border-radius: 4px; background: rgba(8, 23, 40, .56); }
.step-index { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 50%; background: rgba(35, 130, 214, .18); color: #8dc9f1; font-size: 11px; font-weight: 700; }
.step-body { display: grid; gap: 4px; min-width: 0; }
.step-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; min-width: 0; }
.step-top strong { min-width: 0; color: #fff; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-top span { flex: none; color: #93bddb; font-size: 10px; }
.step-body p { margin: 0; color: #bfd5e7; font-size: 11px; line-height: 1.5; overflow-wrap: anywhere; }
.task-detail-columns { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.task-log-list { display: grid; gap: 6px; max-height: 160px; overflow: auto; padding-right: 2px; }
.task-log-list p { margin: 0; color: #bfd5e7; font-size: 11px; line-height: 1.55; overflow-wrap: anywhere; }
.gate-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 8px; }
.gate-item { display: grid; grid-template-columns: 1fr auto; gap: 6px 10px; padding: 10px; border: 1px solid rgba(125, 174, 220, .22); border-radius: 4px; background: rgba(16, 39, 64, .7); }
.gate-item div { display: flex; align-items: center; gap: 8px; min-width: 0; }
.gate-code { color: #82c8ff; font-size: 11px; font-weight: 700; }
.gate-item strong { color: #f5fbff; font-size: 12px; }
.gate-item p { grid-column: 1 / -1; margin: 0; color: #aac5da; font-size: 11px; line-height: 1.6; }
.gate-item .missing { color: #ffd08a; }
.gate-status { padding: 3px 8px; border-radius: 12px; font-size: 11px; }
.gate-status.pass { background: rgba(95, 210, 138, .18); color: #98eab4; }
.gate-status.fail { background: rgba(255, 107, 90, .18); color: #ffada3; }
.gate-status.uncertain { background: rgba(245, 158, 11, .16); color: #ffd08a; }
.gate-status.not_applicable { background: rgba(148, 163, 184, .18); color: #cbd5e1; }
.impact-table { display: grid; border: 1px solid rgba(125, 174, 220, .22); border-radius: 4px; overflow: hidden; }
.impact-head, .impact-row { display: grid; grid-template-columns: 90px 80px 1fr 110px; gap: 8px; align-items: center; padding: 8px 10px; font-size: 12px; }
.impact-head { background: rgba(20, 55, 86, .9); color: #92c5e9; }
.impact-row { border-top: 1px solid rgba(125, 174, 220, .16); color: #dceaf6; }
.impact-row strong { color: #fff; }
.conclusion-grid { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.interval-item { display: grid; gap: 8px; padding: 10px; border: 1px solid rgba(125, 174, 220, .24); border-radius: 4px; background: rgba(16, 39, 64, .78); }
.interval-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.interval-grid.two { grid-template-columns: 140px 1fr; }
.panel-footer { display: flex; flex: 0 0 auto; align-items: center; justify-content: space-between; gap: 14px; padding: 14px 20px; border-top: 1px solid rgba(17, 24, 39, .16); background: transparent; color: #111827; font-size: 12px; }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.actions button { padding: 8px 14px; border-radius: 5px; cursor: pointer; font-size: 12px; font-weight: 700; }
.actions button:disabled { cursor: not-allowed; opacity: .55; }
.secondary { border: 1px solid rgba(125, 174, 220, .45); background: transparent; color: #dceaf6; }
.danger { border: 1px solid rgba(255, 107, 90, .55); background: rgba(104, 30, 28, .4); color: #ffbeb6; }
.primary { border: 0; background: #2382d6; color: #fff; }
.qc-review-panel, .qc-review-panel * { background-color: transparent !important; color: #111827 !important; }
.qc-review-panel .primary { border: 1px solid #111827; }
button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 3px solid rgba(130, 200, 255, .35); outline-offset: 2px; }
@media (max-width: 860px) {
  .panel-body { grid-template-columns: 1fr; }
  .overview-grid, .overview-reason, .overview-refs, .overview-exclusions, .overview-issues, .summary-grid, .evidence-columns, .gate-list, .decision-row, .interval-grid, .interval-grid.two, .task-detail-meta, .task-summary-grid, .task-detail-columns, .qc-stage-strip, .status-table, .conclusion-grid { grid-template-columns: 1fr; }
  .flow-head, .flow-row, .attachment-head, .attachment-row, .qc-head, .qc-row, .impact-head, .impact-row { grid-template-columns: 1fr; }
  .overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .panel-footer { flex-direction: column; align-items: stretch; gap: 8px; padding: 10px 16px; }
  .actions { flex-wrap: nowrap; }
  .actions button { flex: 1; min-width: 0; padding: 8px 4px; }
}
</style>
