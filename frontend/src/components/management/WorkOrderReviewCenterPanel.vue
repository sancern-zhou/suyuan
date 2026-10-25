<template>
  <section class="wor-panel" aria-label="故障工单审核工作台">
    <header class="wor-header">
      <div class="wor-title">
        <h3>故障工单审核</h3>
        <p>按故障日期查看工单、AI 研判与证据</p>
      </div>
      <div class="wor-header-actions">
        <button v-if="showListActions" type="button" class="btn btn--secondary" :disabled="listLoading || detailLoading" @click="refreshView">
          <span v-if="listLoading || detailLoading" class="spinner spinner--sm" aria-hidden="true"></span>
          {{ listLoading ? '刷新中…' : '刷新' }}
        </button>
        <button v-if="showListActions && selectedCode" type="button" class="btn btn--secondary" @click="backToList">返回列表</button>
        <button type="button" class="btn btn--text close-btn" aria-label="关闭" @click="$emit('close')">
          <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 6l12 12" />
            <path d="M18 6L6 18" />
          </svg>
        </button>
      </div>
    </header>

    <div v-if="actionError" class="wor-banners">
      <p class="action-error" role="alert">{{ actionError }}</p>
    </div>

    <!-- 列表视图 -->
    <section v-if="!selectedCode" class="wor-list-view">
      <div class="wor-toolbar">
        <input
          v-model="keyword"
          class="wor-search"
          type="search"
          placeholder="搜索工单号 / 站点 / 标题 / 污染物"
          aria-label="搜索工单"
          @keyup.enter="applyFilters"
        />
        <input v-model="startDate" class="wor-date" type="date" aria-label="故障开始日期" @change="applyFilters" />
        <span class="wor-date-sep" aria-hidden="true">~</span>
        <input v-model="endDate" class="wor-date" type="date" aria-label="故障结束日期" @change="applyFilters" />
        <select v-model="statusFilter" class="wor-status-select" aria-label="按状态筛选" @change="applyFilters">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
        <button type="button" class="btn btn--secondary" :disabled="listLoading" @click="applyFilters">查询</button>
        <button type="button" class="btn btn--text" @click="resetFilters">重置</button>
      </div>

      <div v-if="listLoading && !orders.length" class="wor-state">
        <span class="spinner" aria-hidden="true"></span>
        <span>正在加载审核工单…</span>
      </div>

      <div v-else-if="!orders.length" class="empty-state">
        <svg class="empty-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 4.5h6v3H9v-3Z" />
          <path d="M9 6H6.5A1.5 1.5 0 0 0 5 7.5v12A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5v-12A1.5 1.5 0 0 0 17.5 6H15" />
        </svg>
        <p class="empty-title">暂无审核工单</p>
        <p class="empty-hint">在对话中对工单执行取证审核后，证据会自动归档到这里。</p>
      </div>

      <template v-else>
        <div class="table-scroll">
          <table class="evidence-table wor-order-table">
            <thead>
              <tr>
                <th>工单号</th>
                <th>标题</th>
                <th>站点</th>
                <th>污染物</th>
                <th>故障时段</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="order in orders"
                :key="order.working_order_code"
                class="wor-order-row"
                @click="openDetail(order.working_order_code)"
              >
                <td class="order-code">{{ order.working_order_code }}</td>
                <td class="order-title-cell" :title="order.title">{{ order.title || '未命名工单' }}</td>
                <td>{{ order.site_name || order.site_id || '未设置站点' }}</td>
                <td>{{ order.pollutant || '—' }}</td>
                <td>{{ order.window_start ? `${shortTime(order.window_start)} ~ ${shortTime(order.window_end)}` : '—' }}</td>
                <td><span class="status-badge" :class="statusClass(order.status)">{{ order.status || '待审核' }}</span></td>
                <td>
                  <button type="button" class="link-btn" @click.stop="openDetail(order.working_order_code)">详情</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <nav v-if="total > 0" class="wor-pagination" aria-label="工单分页">
          <button type="button" :disabled="listLoading || page <= 1" @click="changePage(page - 1)">上一页</button>
          <span>第 {{ page }} / {{ totalPages }} 页，共 {{ total }} 条</span>
          <button type="button" :disabled="listLoading || page >= totalPages" @click="changePage(page + 1)">下一页</button>
        </nav>
      </template>
    </section>

    <!-- 详情视图 -->
    <section v-else class="wor-detail-view">
      <div v-if="detailLoading" class="wor-state">
        <span class="spinner" aria-hidden="true"></span>
        <span>正在加载审核包…</span>
      </div>

      <div v-else-if="!detail" class="empty-state">
        <p class="empty-title">审核包不存在或已被清理</p>
        <p class="empty-hint">请返回列表后重新选择工单。</p>
      </div>

      <template v-else>
        <header class="detail-header">
          <div class="detail-heading">
            <strong class="order-code">{{ entry.working_order_code }}</strong>
            <h3>{{ entry.title || '故障工单审核' }}</h3>
            <p>{{ entry.site_name || entry.site_id || '未设置站点' }} · {{ entry.pollutant || '未设置污染物' }} · {{ shortTime(entry.window_start) }} ~ {{ shortTime(entry.window_end) }}</p>
          </div>
          <span class="status-badge" :class="statusClass(entry.status)">{{ entry.status || '待审核' }}</span>
        </header>

        <p class="action-hint">人工操作（确认归档 / 退回工单，退回需说明原因）统一在任务调度中心的审核卡片中进行，本页仅作证据查看。</p>

        <div class="workbench-layout">
          <aside class="workbench-index" aria-label="审核目录">
            <div class="workbench-index-title">审核目录</div>
            <button
              v-for="section in workbenchSections"
              :key="section.key"
              type="button"
              class="workbench-index-item"
              :class="{ active: activeSectionKey === section.key }"
              @click="scrollToSection(section.key)"
            >
              <span>{{ section.index }}. {{ section.label }}</span>
              <i class="index-state" :class="section.stateClass"></i>
            </button>
          </aside>

          <main ref="sectionContent" class="workbench-content" @scroll.passive="updateActiveSection">
            <!-- AI 研判结果 -->
            <article id="wor-section-judgment" class="section-card judgment" aria-label="AI 研判结果">
              <header class="section-head">
                <h4>AI 研判结果</h4>
                <span v-if="judgment?.judged_at" class="muted">{{ formatTime(judgment.judged_at) }}</span>
              </header>
              <div v-if="!judgment" class="source-empty">尚未提交 AI 研判。在对话中要求审核该工单并提交结论后，这里会展示研判结果。</div>
              <template v-else>
                <div class="judgment-chips">
                  <span class="chip" :class="decisionChipClass">结论：{{ decisionText }}</span>
                  <span v-for="(impact, index) in dataImpactChips" :key="index" class="chip neutral">{{ impact }}</span>
                </div>
                <MarkdownRenderer v-if="judgment.comment" :content="judgment.comment" :streaming="false" />
                <table v-if="judgment.checks?.length" class="evidence-table">
                  <thead><tr><th>核验项</th><th>结论</th><th>依据</th><th>范围</th></tr></thead>
                  <tbody>
                    <tr v-for="(check, index) in judgment.checks" :key="index">
                      <td>{{ check.name }}</td>
                      <td><span class="chip" :class="check.status === 'pass' ? 'ok' : (check.status === 'fail' ? 'bad' : 'neutral')">{{ checkStatusLabel(check.status) }}</span></td>
                      <td class="basis-cell">{{ check.basis }}</td>
                      <td>{{ checkScopeLabel(check.scope) }}</td>
                    </tr>
                  </tbody>
                </table>
              </template>
            </article>

            <!-- 事件脉络：AI 时间线结论梳理，节点按关键词对应证据节，可跳转核验 -->
            <article v-if="narrativeSections.length" id="wor-section-narrative" class="section-card narrative" aria-label="事件脉络">
              <header class="section-head">
                <h4>事件脉络</h4>
                <span class="muted">AI 时间线梳理 · 节点可跳转对应证据</span>
              </header>
              <ol class="narrative-timeline">
                <li v-for="(section, index) in narrativeSections" :key="index" class="narrative-node">
                  <div class="narrative-node-head">
                    <span class="narrative-index">{{ index + 1 }}</span>
                    <strong>{{ section.title }}</strong>
                    <button
                      v-if="narrativeTarget(section.title)"
                      type="button"
                      class="link-btn"
                      @click="scrollToSection(narrativeTarget(section.title))"
                    >
                      查看{{ sectionLabelOf(narrativeTarget(section.title)) }}
                    </button>
                  </div>
                  <dl class="narrative-fields">
                    <template v-for="(field, n) in section.fields" :key="n">
                      <dt>{{ field.label }}</dt>
                      <dd>{{ field.value }}</dd>
                    </template>
                  </dl>
                </li>
              </ol>
            </article>

            <!-- 证据数据 -->
            <article
              v-for="source in evidenceSections"
              :id="`wor-section-${source.key}`"
              :key="source.key"
              class="section-card"
              aria-label="证据数据"
            >
              <header class="section-head">
                <h4>{{ source.label }}</h4>
                <span class="source-meta" :class="`st-${source.status}`">
                  {{ sourceStatusLabel(source.status) }}<template v-if="source.recordCount != null"> · {{ source.recordCount }} 条</template>
                </span>
              </header>
              <p v-if="source.summary" class="source-summary">{{ source.summary }}</p>

              <template v-if="source.key === 'work_order'">
                <div v-if="woFacts.length" class="fact-list">
                  <div v-for="fact in woFacts" :key="fact.label" class="fact-row" :class="{ wide: fact.value.length > 40 }">
                    <span>{{ fact.label }}</span>
                    <strong>{{ fact.value }}</strong>
                  </div>
                </div>
                <p v-else class="source-empty">未获取到工单信息（未提供工单号）。</p>

                <div v-for="device in deviceSections" :key="device.key" class="fact-block">
                  <h5>{{ device.label }}</h5>
                  <div class="fact-list">
                    <div v-for="fact in device.entries" :key="fact.label" class="fact-row" :class="{ wide: fact.value.length > 40 }">
                      <span>{{ fact.label }}</span>
                      <strong>{{ fact.value }}</strong>
                    </div>
                  </div>
                </div>

                <div v-if="woSteps.length" class="fact-block">
                  <h5>流程节点</h5>
                  <ol class="step-list">
                    <li v-for="(step, index) in woSteps" :key="index">
                      <span class="step-dot" :class="`st-${step.statusKey}`"></span>
                      <strong>{{ step.name }}</strong>
                      <em>{{ step.statusText }}</em>
                      <small v-if="step.time">{{ shortTime(step.time) }}</small>
                    </li>
                  </ol>
                </div>

                <div v-if="woDetails.length" class="fact-block">
                  <h5>处置过程（{{ woDetails.length }} 条）</h5>
                  <ol class="history-list">
                    <li v-for="(item, index) in woDetails" :key="index">
                      <strong>{{ item.step ? `${item.step} · ${item.user || '平台记录'}` : (item.user || '平台记录') }}</strong>
                      <span v-if="item.content">{{ item.content }}</span>
                      <small v-if="item.time">{{ formatTime(item.time) }}</small>
                    </li>
                  </ol>
                </div>

                <div v-if="woAttachments.length" class="fact-block">
                  <h5>附件（{{ woAttachments.length }}）</h5>
                  <div class="attachment-grid">
                    <figure v-for="att in woAttachments" :key="att.index" :class="{ failed: att.status !== 'success' }">
                      <button
                        v-if="att.isImage && att.url"
                        type="button"
                        class="attachment-thumb"
                        @click="previewUrl = att.url"
                      >
                        <img :src="att.url" :alt="att.name" loading="lazy" />
                      </button>
                      <a v-else-if="att.status === 'success' && att.url" class="attachment-file" :href="att.url" :download="att.name">{{ att.name }}</a>
                      <span v-else class="attachment-file muted">{{ att.name }}（{{ att.status }}）</span>
                      <figcaption>
                        {{ att.name }}
                        <em v-if="att.size">{{ Math.round(att.size / 1024) }} KB</em>
                      </figcaption>
                    </figure>
                  </div>
                </div>
              </template>

              <template v-else-if="source.key === 'station_hour'">
                <!-- 多目标污染物拆成多张时序图：每张图只画该污染物的本站曲线、配对对照曲线
                     与它自己的剔除区间，避免同图叠加时互相遮挡；互为配对的污染物（NO↔NO2、
                     PM10↔PM2.5）合并为一张图，避免两张图曲线完全相同的重复。 -->
                <ReviewTimeSeriesChart
                  v-for="chart in pollutantCharts"
                  :key="chart.pollutant"
                  :title="pollutantCharts.length > 1 ? chart.title : ''"
                  :series="chart.series"
                  :mark-areas="chart.markAreas"
                  :unit="chart.unit"
                  :height="300"
                />
                <p v-if="!pollutantCharts.length" class="source-empty">该来源暂无小时数据。</p>
              </template>

              <template v-else-if="source.key === 'band'">
                <!-- 同城对比曲线（最低/中位/最高）已叠加在上方小时时序图上与站内序列同图对照，
                     本区块不再重复画图，只保留范围说明与数据表入口。 -->
                <p v-if="bandRows.length" class="band-scope-note">
                  {{ bandSubtitle }}；对比曲线已叠加在上方「污染物小时时序」图中
                </p>
                <p v-else class="source-empty">该来源暂无同城对比数据。</p>
                <template v-if="source.rows.length">
                  <button type="button" class="link-btn" @click="toggleSourceRows(source.key)">
                    {{ expandedSourceKeys.includes(source.key) ? '收起数据表' : `查看数据表（${source.rows.length} 条）` }}
                  </button>
                  <div v-if="expandedSourceKeys.includes(source.key)" class="table-scroll">
                    <table class="evidence-table">
                      <thead><tr><th v-for="col in source.columns" :key="col.key">{{ col.label }}</th></tr></thead>
                      <tbody>
                        <tr v-for="(row, rowIndex) in source.rows" :key="rowIndex">
                          <td v-for="col in source.columns" :key="col.key">{{ row[col.key] }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </template>
              </template>

              <template v-else-if="source.key === 'weather'">
                <template v-if="weatherRows.length">
                  <!-- 污染物切换器（参照智能事件对比图）：一次只画选中组的本站/同站互证曲线 -->
                  <div v-if="weatherPollutantOptions.length > 1" class="pollutant-switch" role="group" aria-label="气象图污染物切换">
                    <button
                      v-for="option in weatherPollutantOptions"
                      :key="option.code"
                      type="button"
                      :class="{ active: weatherActiveGroup?.label === option.code }"
                      :aria-pressed="weatherActiveGroup?.label === option.code"
                      @click="weatherPollutant = option.code"
                    ><i class="switch-swatch" :style="{ background: option.color }"></i>{{ option.label }}</button>
                  </div>
                  <JiangsuWeatherReviewChart :entry="weatherEntry" :weather="weatherPayload" :mark-areas="weatherSelectedAreas" />
                </template>
                <p v-else class="source-empty">未获取到城市气象数据。</p>
              </template>

              <template v-else-if="source.key === 'qc'">
                <div v-if="qcTasks.length" class="qc-task-list">
                  <article v-for="(task, index) in qcTasks" :key="task.rId || index" class="qc-task-card">
                    <header class="qc-task-head">
                      <div class="qc-task-title">
                        <strong>{{ task.qcType || task.task_type_name || '质控任务' }}</strong>
                        <span class="muted">{{ task.poll || entry.pollutant }} · {{ task.sStart || task.rStart || '—' }}</span>
                      </div>
                      <span class="chip" :class="qcResultClass(task)" :title="task.qc_result">{{ qcResultText(task) }}</span>
                    </header>
                    <div class="qc-task-actions">
                      <button
                        v-if="task.detail"
                        type="button"
                        class="link-btn"
                        @click="toggleQcDetail(task.rId || index)"
                      >
                        {{ expandedQcKeys.includes(task.rId || index) ? '收起详情' : '展开详情 / 质控曲线' }}
                      </button>
                      <span v-else-if="task.detail_status === 'failed'" class="muted">详情获取失败{{ task.detail_error ? `：${task.detail_error}` : '' }}</span>
                    </div>
                    <div v-if="task.detail && expandedQcKeys.includes(task.rId || index)" class="qc-task-detail">
                      <QcTaskDetailPanel :data="{ data: { qc_task_detail: task.detail } }" />
                    </div>
                  </article>
                </div>
                <p v-else class="source-empty">该时间窗内无{{ entry.pollutant || '目标污染物' }}质控任务。</p>
              </template>

              <template v-else-if="source.key === 'env_power'">
                <div v-if="source.rows.length" class="table-scroll">
                  <table class="evidence-table">
                    <thead><tr><th v-for="col in source.columns" :key="col.key">{{ col.label }}</th></tr></thead>
                    <tbody>
                      <tr v-for="(row, rowIndex) in source.rows" :key="rowIndex">
                        <td v-for="col in source.columns" :key="col.key">{{ row[col.key] }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-else class="source-empty">{{ envEmptyHint }}</p>
              </template>

              <template v-else-if="source.columns.length">
                <div class="table-scroll">
                  <table class="evidence-table">
                    <thead><tr><th v-for="col in source.columns" :key="col.key">{{ col.label }}</th></tr></thead>
                    <tbody>
                      <tr v-for="(row, rowIndex) in visibleRows(source)" :key="rowIndex">
                        <td v-for="col in source.columns" :key="col.key">{{ row[col.key] }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <button
                  v-if="source.rows.length > TABLE_ROW_LIMIT"
                  type="button"
                  class="link-btn"
                  @click="toggleSourceRows(source.key)"
                >
                  {{ expandedSourceKeys.includes(source.key) ? '收起' : `展开全部 ${source.rows.length} 条` }}
                </button>
                <p v-if="source.truncatedNote" class="truncated-note">{{ source.truncatedNote }}</p>
              </template>

              <p v-else-if="source.rows.length" class="source-empty">该来源数据暂不支持在此预览，请在对话中查看完整证据。</p>
              <p v-else class="source-empty">该来源暂无数据。</p>
            </article>

            <!-- 操作记录 -->
            <article id="wor-section-operations" class="section-card" aria-label="操作记录">
              <header class="section-head">
                <h4>操作记录</h4>
                <span v-if="operations.length" class="muted">{{ operations.length }} 条</span>
              </header>
              <div v-if="!operations.length" class="source-empty">暂无操作记录。</div>
              <ol v-else class="history-list">
                <li v-for="(op, index) in operations" :key="index">
                  <strong>{{ operationActionLabel(op.action, op.label) }}</strong>
                  <span>{{ op.comment || '无意见' }}</span>
                  <small>{{ op.actor?.username || '系统' }} · {{ formatTime(op.at) }}</small>
                </li>
              </ol>
            </article>
          </main>
        </div>
      </template>
    </section>

    <!-- 附件图片放大预览 -->
    <div v-if="previewUrl" class="dialog-mask image-mask" @click.self="previewUrl = null">
      <img class="preview-image" :src="previewUrl" alt="附件预览" @click="previewUrl = null" />
      <button type="button" class="ghost-btn close-btn preview-close" aria-label="关闭预览" @click="previewUrl = null">✕</button>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import JiangsuWeatherReviewChart from '@/components/visualization/JiangsuWeatherReviewChart.vue'
import QcTaskDetailPanel from '@/components/visualization/QcTaskDetailPanel.vue'
import ReviewTimeSeriesChart from '@/components/visualization/ReviewTimeSeriesChart.vue'
import {
  areaPollutant,
  buildPollutantCharts,
  CHART_COMPARISON_PAIRS,
  EXTRA_POLLUTANT_COLORS,
  POLLUTANT_UNIT_OVERRIDES,
  switcherPollutantGroups,
} from '@/components/visualization/reviewTimeSeriesData.js'
import {
  getWorkOrderReview,
  getWorkOrderReviewSource,
  fetchWorkOrderReviewAttachmentUrl,
  listWorkOrderReviews,
} from '@/services/jiangsuWorkOrderReviewApi.js'
import {
  TABLE_PREFERRED_COLUMNS,
  checkScopeLabel,
  checkStatusLabel,
  columnLabel,
  dataImpactLabel,
  decisionLabelOf,
  operationActionLabel,
  sourceStatusLabel,
  woDetailLabel,
  WO_FIELD_ORDER,
  WO_RAW_ENUM_KEYS,
  woValueLabel,
  DEVICE_SECTION_LABELS,
  DETAIL_TIME_KEYS,
  DETAIL_USER_KEYS,
  DETAIL_CONTENT_KEYS,
  DETAIL_STEP_KEYS,
} from '@/services/jiangsuWorkOrderReviewLabels.js'

const props = defineProps({
  workspaceCommand: { type: Object, default: null },
  // 对话右侧 tab 模式置 false：定位是当前工单的分析与展示，不提供列表操作（刷新/返回列表）
  showListActions: { type: Boolean, default: true },
  // 整页模式（任务调度中心「查看详情」直达）置 true：「返回列表」直接关闭面板回到任务调度中心，
  // 不再展示组件内部的故障工单审核列表页
  listReturnCloses: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

const SECTION_LABELS = {
  work_order: '工单信息',
  station_hour: '污染物小时时序',
  band: '同城对比带',
  weather: '气象时序',
  alarms: '站房设备告警',
  env_power: '站房动环历史',
  qc: '质控任务清单',
}
const SOURCE_TABLE_FIELDS = {
  band: 'band',
  alarms: 'alarm_logs',
  env_power: 'table_rows',
  qc: 'qc_tasks',
}

const PAGE_SIZE = 10
const orders = ref([])
const statuses = ref([])
const total = ref(0)
const listLoading = ref(false)
const keyword = ref('')
const statusFilter = ref('')
const startDate = ref('')
const endDate = ref('')
const page = ref(1)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

const selectedCode = ref(null)
const detail = ref(null)
const detailLoading = ref(false)
const sourceCache = ref({})
const actionError = ref('')

const entry = computed(() => detail.value?.entry || {})
const index = computed(() => detail.value?.index || {})
const judgment = computed(() => index.value.judgment || null)
// AI 时间线结论梳理（task_reviews.sections 回写）：工作台以"事件脉络"卡片展示，
// 与快速研判卡片分工——卡片只留结论，详细脉络在这里与证据数据对照。
const narrativeSections = computed(() => (judgment.value?.sections || [])
  .filter(section => section && Array.isArray(section.fields) && section.fields.length))
const operations = computed(() => index.value.operations || [])

function tableRows(key) {
  const data = sourceCache.value[key]?.data || {}
  const field = SOURCE_TABLE_FIELDS[key]
  return field ? (data[field] || []) : []
}

function tableColumns(key, rows) {
  if (!rows.length) return []
  const keys = Object.keys(rows[0] || {})
  const preferred = TABLE_PREFERRED_COLUMNS[key] || []
  const ordered = [
    ...preferred.filter(name => keys.includes(name)),
    ...keys.filter(name => !preferred.includes(name)),
  ]
  return ordered
    .map(name => ({ key: name, label: columnLabel(name) }))
    .filter(column => column.label)
    .slice(0, 12)
}

const evidenceSections = computed(() => {
  const sources = index.value.sources || {}
  return Object.keys(SECTION_LABELS)
    .filter(key => sources[key])
    .map(key => {
      const rows = tableRows(key)
      return {
        key,
        label: SECTION_LABELS[key],
        status: sources[key].status || 'skipped',
        recordCount: sources[key].record_count,
        summary: sources[key].summary || '',
        truncatedNote: sources[key].truncated ? '索引未含全部行，完整数据在分文件中' : '',
        rows,
        columns: tableColumns(key, rows),
      }
    })
})

// 剔除建议涉及的目标/对照之外的污染物：补画曲线用色与单位覆盖由共享模块提供，
// 气象图污染物面板续取同一套。
const stationHourData = computed(() => sourceCache.value.station_hour?.data || {})

// 小时时序图按污染物拆图（目标曲线/对照曲线/剔除区间逐项独立成图），装配逻辑与
// 气象图污染物面板共用 reviewTimeSeriesData，保证曲线名称与颜色两图一致。
const hourlyChartBundle = computed(() => buildPollutantCharts({
  data: stationHourData.value,
  fallbackPollutant: entry.value.pollutant,
  markAreas: index.value.mark_areas || [],
  bandRows: bandRows.value,
  bandComparisonCollapsed: bandComparisonCollapsed.value,
  bandDistrictName: sourceCache.value.band?.data?.district_name || '同域',
}))
const pollutantCharts = computed(() => hourlyChartBundle.value.charts)
const pollutantColorMap = computed(() => hourlyChartBundle.value.colorMap)

// 同城对比带：取证侧只存聚合行（本站 target + 同城最低/中位/最高）。聚合行叠加在小时时序图上
// 与站内序列同图对照；同区只有 1 个省控对比站时最低/中位/最高三值相同，合并为一条"同城对比站"线。
// 对比带区块本身不再重复画图（与主图完全重叠），只展示范围说明与数据表。
const bandRows = computed(() => (sourceCache.value.band?.data?.band || [])
  .filter(row => row && row.time)
  .slice()
  .sort((left, right) => String(left.time).localeCompare(String(right.time))))
const bandComparisonCollapsed = computed(() => bandRows.value.length > 0 && bandRows.value.every(row => (
  row.min == null || row.max == null || Number(row.min) === Number(row.max)
)))
const bandSubtitle = computed(() => {
  const data = sourceCache.value.band?.data || {}
  const scopeText = data.scope === 'same_city' ? '同城' : '同区县'
  const base = `${scopeText}省控对比${data.district_name ? `（${data.district_name}）` : ''} · 共 ${bandRows.value.length} 小时`
  return bandComparisonCollapsed.value ? `${base}；同域仅 1 个对比站，最低/中位/最高为同一序列` : base
})
const weatherRows = computed(() => sourceCache.value.weather?.data?.rows || [])
const weatherPayload = computed(() => ({
  start: entry.value.window_start,
  end: entry.value.window_end,
  data: weatherRows.value,
}))
// 气象图污染物切换（参照智能事件「目标站与对比站小时趋势」的右上角切换器）：
// 全污染物同图叠加难以辨认，改为一次只画选中组的曲线：互为配对的污染物（NO↔NO2、
// PM10↔PM2.5）并成一组（两组的曲线完全相同，本站/互证只是互换，拆开是重复），
// 组内两条都是本站曲线；单向配对（O3→NO2）与无配对（SO2/CO）独立成组，选中时
// 补配对污染物的同站互证曲线。默认选中工单目标污染物所在组。
const WEATHER_POLLUTANT_ORDER = ['PM10', 'PM2.5', 'SO2', 'NO', 'NO2', 'CO', 'O3']
const weatherPollutant = ref('')
const weatherPointsByPollutant = computed(() => hourlyChartBundle.value.seriesPointsByPollutant || {})
const weatherTargetCode = computed(() => String(hourlyChartBundle.value.targetCode || entry.value.pollutant || '').toUpperCase())
const weatherPollutantCodes = computed(() => {
  const pointsByPollutant = weatherPointsByPollutant.value
  return [
    ...WEATHER_POLLUTANT_ORDER,
    ...Object.keys(pointsByPollutant).map(code => String(code).toUpperCase()),
  ]
    .map(code => (code === 'PM2_5' || code === 'PM25' ? 'PM2.5' : code))
    .filter((code, idx, list) => list.indexOf(code) === idx && (pointsByPollutant[code] || []).length)
})
// 污染物 → 曲线色：小时时序图已有的沿用（跨图同色），其余从补画色板续取且整图内不重色。
const weatherColorMap = computed(() => {
  const colors = { ...pollutantColorMap.value }
  const used = new Set(Object.values(colors))
  let extraIndex = 0
  for (const code of weatherPollutantCodes.value) {
    if (colors[code]) continue
    let color = EXTRA_POLLUTANT_COLORS[extraIndex++ % EXTRA_POLLUTANT_COLORS.length]
    for (let step = 0; step < EXTRA_POLLUTANT_COLORS.length && used.has(color); step += 1) {
      color = EXTRA_POLLUTANT_COLORS[extraIndex++ % EXTRA_POLLUTANT_COLORS.length]
    }
    colors[code] = color
    used.add(color)
  }
  return colors
})
const weatherPollutantGroups = computed(() => switcherPollutantGroups(weatherPollutantCodes.value)
  .map(group => ({ members: group.members, label: group.members.join('/') })))
const weatherPollutantOptions = computed(() => weatherPollutantGroups.value.map(group => ({
  code: group.label,
  label: group.label,
  color: weatherColorMap.value[group.members[0]],
})))
const weatherActiveGroup = computed(() => {
  const groups = weatherPollutantGroups.value
  if (!groups.length) return null
  const selected = groups.find(group => group.label === weatherPollutant.value)
  if (selected) return selected
  const target = weatherTargetCode.value
  return groups.find(group => group.members.includes(target)) || groups[0]
})
const weatherSelectedSeries = computed(() => {
  const group = weatherActiveGroup.value
  const pointsByPollutant = weatherPointsByPollutant.value
  if (!group) return []
  const unitOf = pollutant => POLLUTANT_UNIT_OVERRIDES[pollutant] || stationHourData.value.unit || 'μg/m³'
  const series = group.members
    .filter(member => (pointsByPollutant[member] || []).length)
    .map(member => ({
      name: `${member}（本站）`, unit: unitOf(member),
      color: weatherColorMap.value[member] || '#2f86e0', points: pointsByPollutant[member],
    }))
  if (!series.length) return []
  // 单向配对组（如 O3）补配对污染物的同站互证曲线；双向组两条本站曲线本身即互为同站互证，不另补
  if (group.members.length === 1) {
    const pair = CHART_COMPARISON_PAIRS[group.members[0]]
    if (pair && pair !== group.members[0] && (pointsByPollutant[pair] || []).length) {
      series.push({
        name: `${pair}（同站互证）`, unit: unitOf(pair),
        color: weatherColorMap.value[pair] || '#9b8cff', points: pointsByPollutant[pair],
      })
    }
  }
  return series
})
// 区间归属与小时时序图一致：标注了污染物的区间随所属组显示，
// 无归属（或归属污染物无曲线）回落主目标组，由图表回退默认琥珀色。
const weatherSelectedAreas = computed(() => {
  const group = weatherActiveGroup.value
  if (!group) return []
  const targetCode = weatherTargetCode.value
  const pointsByPollutant = weatherPointsByPollutant.value
  return (index.value.mark_areas || []).filter(area => {
    const owner = areaPollutant(area)
    if (!owner) return group.members.includes(targetCode)
    return group.members.includes(owner)
      || (group.members.includes(targetCode) && !(pointsByPollutant[owner] || []).length)
  }).map(area => {
    const color = weatherColorMap.value[areaPollutant(area)]
    return color ? { ...area, color } : { ...area }
  })
})
const weatherEntry = computed(() => ({
  title: '站点污染物与气象时序',
  unit: stationHourData.value.unit || 'μg/m3',
  // 只画切换器选中组的本站/同站互证曲线，名称与颜色和小时时序图保持一致
  series: weatherSelectedSeries.value,
}))

const workOrderData = computed(() => sourceCache.value.work_order?.data || {})
const sectionContent = ref(null)
const activeSectionKey = ref('judgment')
const expandedQcKeys = ref([])
const expandedSourceKeys = ref([])
const TABLE_ROW_LIMIT = 20

function toggleQcDetail(key) {
  expandedQcKeys.value = expandedQcKeys.value.includes(key)
    ? expandedQcKeys.value.filter(item => item !== key)
    : [...expandedQcKeys.value, key]
}

function toggleSourceRows(key) {
  expandedSourceKeys.value = expandedSourceKeys.value.includes(key)
    ? expandedSourceKeys.value.filter(item => item !== key)
    : [...expandedSourceKeys.value, key]
}

function visibleRows(source) {
  if (expandedSourceKeys.value.includes(source.key)) return source.rows
  return source.rows.slice(0, TABLE_ROW_LIMIT)
}

// 质控任务：只保留目标污染物任务，展示合格结果并可展开质控曲线。
// 证据包 qc 分文件里的 detail 是取证侧结构（status / run_log / curve 均为工具返回包裹，
// 曲线原始行键为 timePoint / dataValue），而 QcTaskDetailPanel 期望对话侧 visual 的
// qc_task_detail 结构（steps / curve[{time_point, value}] / …）。这里做一次归一化投影，
// 与 AI 事件研判右侧的质控详情展示同构。
function pickFirst(source, ...keys) {
  for (const key of keys) {
    const value = source?.[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return undefined
}

const STEP_STATUS_BY_TEXT = [['待执行', 0], ['执行中', 1], ['已完成', 2], ['已中止', 3], ['中止中', 4]]

function stepStatusValue(status) {
  if (typeof status === 'number') return status
  const text = String(status ?? '')
  const hit = STEP_STATUS_BY_TEXT.find(([label]) => text.includes(label))
  return hit ? hit[1] : undefined
}

function normalizeSteps(steps) {
  return (Array.isArray(steps) ? steps : [])
    .filter(step => step && typeof step === 'object')
    .map(step => ({
      name: pickFirst(step, 'name', 'StepName', 'stepName', 'label'),
      status: stepStatusValue(pickFirst(step, 'status', 'Status')),
      actions: (Array.isArray(step.actions) ? step.actions : [])
        .filter(action => action && typeof action === 'object')
        .map(action => ({
          name: pickFirst(action, 'name', 'ActionName', 'actionName'),
          value: pickFirst(action, 'value', 'ActionParameter', 'actionParameter'),
          status: stepStatusValue(pickFirst(action, 'status', 'Status')),
        })),
    }))
}

function normalizeValueRows(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter(row => row && typeof row === 'object')
    .map(row => ({
      name: pickFirst(row, 'name', 'DataName', 'dataName', 'Name'),
      value: pickFirst(row, 'value', 'DataValue', 'dataValue', 'Value') ?? '',
    }))
}

function normalizeRunLogs(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter(row => row && typeof row === 'object')
    .map(row => ({
      record_time: pickFirst(row, 'record_time', 'recordTime', 'RecordTime'),
      target: pickFirst(row, 'target', 'Target'),
      message: pickFirst(row, 'message', 'Message', 'strEvent', 'StrEvent'),
    }))
}

// 平台无效观测值以 -99 / -999 标记，绘图前与对话侧一致地过滤。
function normalizeCurve(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter(row => row && typeof row === 'object')
    .map(row => ({
      time_point: pickFirst(row, 'time_point', 'timePoint', 'TimePoint', 'time', 'Time'),
      value: Number(pickFirst(row, 'value', 'dataValue', 'DataValue', 'Value')),
      unit: pickFirst(row, 'unit', 'Unit') || '',
      is_qcing: Boolean(pickFirst(row, 'is_qcing', 'isQCing', 'IsQCing')),
    }))
    .filter(point => point.time_point && Number.isFinite(point.value))
    .sort((left, right) => String(left.time_point).localeCompare(String(right.time_point)))
}

function qcPanelDetail(detail) {
  if (!detail || typeof detail !== 'object') return null
  // 证据包直接存 visual 同构结构时无需投影
  if (Array.isArray(detail.steps) || Array.isArray(detail.curve)) return detail
  const statusData = detail.status?.data
  const statusTask = (statusData && typeof statusData === 'object' && statusData.task) || {}
  const snapshot = detail.status_detail || {}
  const ref = (detail.task && typeof detail.task === 'object') ? detail.task : {}
  const historyRow = ref.history_row || {}
  const historyDetail = ref.history_detail || snapshot.history_detail || {}
  return {
    task: {
      ...ref,
      r_id: statusTask.r_id ?? ref.r_id,
      r_start: statusTask.r_start ?? ref.r_start,
      station_code: statusTask.station_code ?? historyRow.stationCode,
      unique_code: statusTask.unique_code ?? historyRow.uniqueCode,
      station_name: statusTask.station_name ?? historyRow.stationName,
      poll: statusTask.poll ?? ref.pollutant ?? historyRow.poll,
      qc_type: statusTask.qc_type ?? ref.qc_type ?? historyRow.qcType,
      task_status: statusTask.task_status,
      task_status_label: statusTask.task_status_label,
      qc_result: statusTask.qc_result ?? ref.qc_result ?? historyRow.qcResult ?? historyDetail.QCResult,
      relevant_value: statusTask.relevant_value ?? historyRow.rValue ?? historyDetail.RelevantValue,
      inaccuracy: statusTask.inaccuracy ?? historyRow.inac ?? historyDetail.Inaccuracy,
      start_time: statusTask.start_time ?? ref.r_start ?? historyRow.rStartStr ?? historyRow.rStart,
      end_time: statusTask.end_time ?? ref.end_time ?? historyRow.endTimeStr ?? historyRow.endTime,
      zero_air_flow: statusTask.zero_air_flow ?? historyDetail.ZeroAirFlow,
      std_air_flow: statusTask.std_air_flow ?? historyDetail.StdAirFlow,
      task_type_name: statusTask.task_type_name ?? historyRow.qcType,
    },
    steps: normalizeSteps(statusData?.steps ?? snapshot.steps),
    result_values: normalizeValueRows(statusData?.result_values ?? snapshot.result_values ?? ref.result_values),
    data_values: normalizeValueRows(statusData?.data_values ?? snapshot.data_values ?? ref.data_values),
    run_logs: normalizeRunLogs(statusData?.run_logs ?? detail.run_log?.data),
    curve: normalizeCurve(detail.curve?.data),
    updated_at: detail.status?.metadata?.queried_at ?? null,
  }
}

const qcTasks = computed(() => {
  const tasks = sourceCache.value.qc?.data?.qc_tasks || []
  return tasks.map(task => {
    const detail = qcPanelDetail(task.detail)
    const detailTask = detail?.task || {}
    return {
      ...task,
      poll: task.target_pollutant || task.poll || detailTask.poll,
      qcType: task.qcType || detailTask.qc_type,
      qc_result: detailTask.qc_result || task.qc_result || task.result,
      task_status_label: detailTask.task_status_label,
      detail,
    }
  })
})

// 注意顺序：必须先判"不合格"再判"合格"，否则"不合格"作为子串会先命中 /合格/。
const QC_FAIL_PATTERN = /不合格|异常|超(?:控制|警告)限|fail|ng/i
const QC_PASS_PATTERN = /合格|pass|normal|success/i

function qcResultText(task) {
  const result = String(task.qc_result || '').trim()
  if (!result) return task.task_status_label || '结果未知'
  if (QC_FAIL_PATTERN.test(result)) return '不合格'
  if (QC_PASS_PATTERN.test(result)) return '合格'
  return result
}

function qcResultClass(task) {
  const result = String(task.qc_result || '').trim()
  if (QC_FAIL_PATTERN.test(result)) return 'bad'
  if (QC_PASS_PATTERN.test(result)) return 'ok'
  return 'neutral'
}

const envEmptyHint = computed(() => {
  const source = index.value.sources?.env_power || {}
  if (source.status === 'skipped') return source.summary || '无动环类告警，未抓取动环历史。'
  return '窗口内无动环异常记录（正常逐时数据已过滤，不参与研判）。'
})

// 事件脉络节点 → 证据节映射：section 标题由模型生成、不同单差异大（如"处置与附件"
// "关键数据事实""审核结论与数据处置"），按关键词模糊对应，规则顺序即优先级。
function narrativeTarget(title) {
  if (/结论/.test(title)) return 'station_hour' // 数据处置/剔除区间标注在时序图上
  if (/处置|处理|附件|流程/.test(title)) return 'work_order'
  if (/恢复/.test(title)) return 'station_hour'
  if (/质控|复测|校准|零跨|跨度/.test(title)) return 'qc'
  if (/站点|设备|工单|概况/.test(title)) return 'work_order'
  if (/事实|异常|数据/.test(title)) return 'station_hour'
  if (/同区|同城|对比/.test(title)) return 'band'
  if (/气象/.test(title)) return 'weather'
  if (/告警|动环/.test(title)) return 'alarms'
  return null
}
function sectionLabelOf(key) {
  return SECTION_LABELS[key] || '证据'
}

const workbenchSections = computed(() => {
  const sources = index.value.sources || {}
  const entries = [
    { key: 'judgment', label: 'AI 研判结果', state: judgment.value ? 'ok' : 'empty' },
    ...(narrativeSections.value.length
      ? [{ key: 'narrative', label: '事件脉络', state: 'ok' }]
      : []),
    ...Object.keys(SECTION_LABELS)
      .filter(key => sources[key])
      .map(key => ({
        key,
        label: SECTION_LABELS[key],
        state: sources[key].status === 'success' ? 'ok' : (sources[key].status === 'skipped' ? 'empty' : 'warn'),
      })),
    { key: 'operations', label: '操作记录', state: operations.value.length ? 'ok' : 'empty' },
  ]
  return entries.map((item, position) => ({ ...item, index: position + 1, stateClass: item.state }))
})

function scrollToSection(key) {
  activeSectionKey.value = key
  const container = sectionContent.value
  const target = document.getElementById(`wor-section-${key}`)
  if (!container || !target) return
  const offset = target.getBoundingClientRect().top - container.getBoundingClientRect().top
  container.scrollTo({ top: Math.max(0, container.scrollTop + offset), behavior: 'smooth' })
}

function updateActiveSection() {
  const container = sectionContent.value
  if (!container) return
  const sections = [...container.querySelectorAll('[id^="wor-section-"]')]
  const containerTop = container.getBoundingClientRect().top
  const current = sections.filter(section => section.getBoundingClientRect().top <= containerTop + 8).at(-1) || sections[0]
  if (current?.id) activeSectionKey.value = current.id.replace('wor-section-', '')
}

const attachmentUrls = ref({})
const previewUrl = ref(null)

// 平台序列化残留（如 wo.stationCode = System.Collections.Generic.List`1[System.String]）不展示。
const SERIALIZER_NOISE = /^System\./
// 平台时间串统一成 "YYYY-MM-DD HH:mm:ss"（去掉 T 与毫秒），与平台页面显示一致。
const ISO_TIME = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/

function factValue(value) {
  if (typeof value === 'boolean') return value ? '是' : '否'
  const text = String(value)
  const time = text.match(ISO_TIME)
  if (time) return `${time[1]} ${time[2].length === 5 ? `${time[2]}:00` : time[2]}`
  return woValueLabel(text)
}

function scalarFacts(source, excludeKeys = []) {
  if (!source || typeof source !== 'object') return []
  return Object.entries(source)
    .filter(([key, value]) => !excludeKeys.includes(key)
      && value != null && value !== '' && ['string', 'number', 'boolean'].includes(typeof value)
      // 有 *Str 中文字段时丢弃同名的枚举原值字段（orderType/orderStatus…）
      && !(WO_RAW_ENUM_KEYS.has(key) && source[`${key}Str`] != null))
    .map(([key, value]) => ({ key, label: woDetailLabel(key), value: factValue(value) }))
    .filter(item => item.label && !SERIALIZER_NOISE.test(item.value))
}

// 流程节点：详单里的 currentPoint / prevPoint 是节点 GUID，按 workFlowInfo.stepList 的
// guid→taskName 映射成平台页面显示的中文节点名。
const workflowNodeNames = computed(() => Object.fromEntries(
  (workOrderData.value.workFlowInfo?.stepList || [])
    .filter(step => step?.guid)
    .map(step => [String(step.guid), String(step.taskName || '').trim()])
    .filter(([, name]) => name)))

// 源平台详单结构：data.order（清单条目）+ data.wo（详单主表）；主表优先，清单补缺
const woFacts = computed(() => {
  const data = workOrderData.value
  const merged = { ...(data.order || {}), ...(data.wo || {}) }
  const nodes = workflowNodeNames.value
  const currentPoint = merged.currentPointName || nodes[String(merged.currentPoint || '')] || ''
  const prevPoint = nodes[String(merged.prevPoint || '')] || ''
  const resolved = [
    currentPoint ? { key: 'currentPointName', label: '当前节点', value: currentPoint } : null,
    prevPoint ? { key: 'prevPoint', label: '上一节点', value: prevPoint } : null,
  ].filter(Boolean)
  return [...resolved, ...scalarFacts(merged, ['currentPoint', 'prevPoint', 'currentPointName', 'stationCode'])]
    .sort((left, right) => {
      const leftIndex = WO_FIELD_ORDER.indexOf(left.key)
      const rightIndex = WO_FIELD_ORDER.indexOf(right.key)
      if (leftIndex >= 0 || rightIndex >= 0) {
        return (leftIndex < 0 ? WO_FIELD_ORDER.length : leftIndex)
          - (rightIndex < 0 ? WO_FIELD_ORDER.length : rightIndex)
      }
      return left.label.localeCompare(right.label, 'zh-Hans')
    })
    .slice(0, 32)
})

const deviceSections = computed(() => Object.entries(DEVICE_SECTION_LABELS)
  .map(([key, label]) => ({ key, label, entries: scalarFacts(workOrderData.value[key]).slice(0, 12) }))
  .filter(section => section.entries.length))

// 流程节点：stepList 是工作流定义（status/ createTime 都是模板信息，不能当进度与时间用），
// 进度按 details 里的 processStep 是否已处理判断，当前节点取 order.currentPointFormCode。
const woSteps = computed(() => {
  const data = workOrderData.value
  const steps = data.workFlowInfo?.stepList || []
  const currentNodeCode = String(data.order?.currentPointFormCode || '').trim()
  const processedAt = new Map()
  ;(data.details || []).forEach(row => {
    const code = String(row?.processStep || '').trim()
    if (!code) return
    const time = row.processTimeStr || row.processEdtTime || row.processSdtTime || ''
    if (!processedAt.has(code) || String(time) > String(processedAt.get(code))) processedAt.set(code, time)
  })
  return steps
    .map(step => {
      const code = String(step?.formCode || '').trim()
      const done = processedAt.has(code)
      const active = !done && code && code === currentNodeCode
      return {
        name: String(step?.taskName || step?.name || '').trim(),
        statusText: done ? '已完成' : (active ? '进行中' : '待处理'),
        statusKey: done ? 'ok' : (active ? 'info' : 'pending'),
        time: done ? processedAt.get(code) : '',
      }
    })
    .filter(step => step.name)
})

const woDetails = computed(() => (workOrderData.value.details || [])
  .map(row => {
    if (!row || typeof row !== 'object') return null
    const pick = keys => keys.map(key => row[key]).find(value => value != null && value !== '') || ''
    return {
      time: pick(DETAIL_TIME_KEYS),
      user: pick(DETAIL_USER_KEYS),
      content: pick(DETAIL_CONTENT_KEYS),
      step: pick(DETAIL_STEP_KEYS),
    }
  })
  .filter(item => item && (item.content || item.time || item.user || item.step)))

const woAttachments = computed(() => (workOrderData.value.attachments || [])
  .map((attachment, index) => {
    const name = String(attachment?.fileName || `附件 ${index + 1}`)
    const type = String(attachment?.content_type || '')
    const isImage = type.startsWith('image/')
      || /\.(png|jpe?g|gif|bmp|webp)$/i.test(name)
    return {
      index,
      name,
      type,
      status: attachment?.download_status || 'pending',
      isImage,
      size: attachment?.size_bytes || 0,
      url: attachmentUrls.value[index] || null,
    }
  }))

function releaseAttachmentUrls() {
  Object.values(attachmentUrls.value).forEach(url => URL.revokeObjectURL(url))
  attachmentUrls.value = {}
  previewUrl.value = null
}

async function loadAttachmentUrls(code) {
  releaseAttachmentUrls()
  const attachments = workOrderData.value.attachments || []
  if (!attachments.length) return
  const urls = {}
  await Promise.all(attachments.map(async (attachment, index) => {
    if (attachment?.download_status !== 'success') return
    try {
      urls[index] = await fetchWorkOrderReviewAttachmentUrl(code, index)
    } catch {
      // 单个附件加载失败不阻断整体展示，卡片显示原始状态
    }
  }))
  attachmentUrls.value = urls
}

const decisionText = computed(() => judgment.value?.decision_label || decisionLabelOf(judgment.value?.decision))
const decisionChipClass = computed(() => {
  const decision = String(judgment.value?.decision || '').toLowerCase()
  if (decision === 'pass' || decision === 'confirm') return 'ok'
  if (decision === 'reject' || decision === 'needs_evidence') return 'bad'
  return 'neutral'
})
const dataImpactChips = computed(() => (judgment.value?.data_impact || [])
  .map(item => {
    const impact = dataImpactLabel(item.decision)
    const pollutant = String(item.pollutant || '').trim()
    return pollutant ? `${pollutant} ${impact}` : impact
  })
  .filter(Boolean))

const statusClass = status => ({
  '已归档': 'st-ok',
  '待归档': 'st-info',
  '已退回': 'st-bad',
  '待补证': 'st-warn',
  '处置中': 'st-warn',
  '待审核': 'st-info',
}[status] || 'st-info')

function pad(value) {
  return String(value).padStart(2, '0')
}

function shortTime(value) {
  const text = String(value || '')
  return text.length >= 16 ? text.slice(5, 16) : text
}

function formatTime(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (!Number.isFinite(parsed.getTime())) return String(value).slice(0, 16)
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
}

async function loadOrders() {
  listLoading.value = true
  actionError.value = ''
  try {
    const payload = await listWorkOrderReviews({
      keyword: keyword.value || undefined,
      status: statusFilter.value || undefined,
      start_date: startDate.value || undefined,
      end_date: endDate.value || undefined,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    orders.value = payload.orders || []
    statuses.value = payload.statuses || []
    total.value = payload.total || orders.value.length
  } catch (error) {
    actionError.value = error.message
  } finally {
    listLoading.value = false
  }
}

function applyFilters() {
  page.value = 1
  loadOrders()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  startDate.value = ''
  endDate.value = ''
  applyFilters()
}

function changePage(target) {
  if (target < 1 || target > totalPages.value || target === page.value) return
  page.value = target
  loadOrders()
}

async function loadSource(code, name) {
  if (sourceCache.value[name]) return
  try {
    const payload = await getWorkOrderReviewSource(code, name)
    sourceCache.value = { ...sourceCache.value, [name]: payload }
  } catch {
    sourceCache.value = { ...sourceCache.value, [name]: { source: name, data: null } }
  }
}

async function openDetail(code) {
  selectedCode.value = code
  detail.value = null
  sourceCache.value = {}
  releaseAttachmentUrls()
  expandedQcKeys.value = []
  expandedSourceKeys.value = []
  weatherPollutant.value = ''
  activeSectionKey.value = 'judgment'
  actionError.value = ''
  detailLoading.value = true
  try {
    detail.value = await getWorkOrderReview(code)
    await Promise.all(Object.keys(SECTION_LABELS).map(name => loadSource(code, name)))
    await loadAttachmentUrls(code)
  } catch (error) {
    detail.value = null
    actionError.value = error.message
  } finally {
    detailLoading.value = false
  }
}

// 刷新当前视图：详情态重取当前工单证据包，列表态刷新工单清单
function refreshView() {
  if (selectedCode.value) openDetail(selectedCode.value)
  else loadOrders()
}

function backToList() {
  if (props.listReturnCloses) {
    emit('close')
    return
  }
  selectedCode.value = null
  detail.value = null
  releaseAttachmentUrls()
  loadOrders()
}

watch(() => props.workspaceCommand, command => {
  const code = command?.working_order_code
  if (!code) return
  if (code === selectedCode.value && detail.value) return
  openDetail(String(code))
}, { immediate: true })

loadOrders()
</script>

<style scoped>
.wor-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--bg-muted);
  color: var(--text-1);
  font-size: var(--text-size-sm);
}

.wor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: var(--panel-header-h);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--border-1);
  background: var(--bg-container);
}

.wor-title h3 {
  margin: 0;
  font-size: var(--text-size-lg);
  font-weight: var(--font-weight-semibold);
  line-height: var(--line-height-title);
  color: var(--text-1);
}

.wor-title p {
  margin: 2px 0 0;
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.wor-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* 按钮：默认 / hover / active / disabled 四态 + focus-visible */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  min-height: var(--control-h-md);
  padding: 0 var(--space-3);
  border: 1px solid var(--border-3);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
  color: var(--text-1);
  font-family: inherit;
  font-size: var(--text-size-sm);
  line-height: var(--line-height-compact);
  cursor: pointer;
  white-space: nowrap;
  transition: color var(--transition-base), background var(--transition-base), border-color var(--transition-base);
}

.btn:hover:not(:disabled) {
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.btn:disabled {
  background: var(--bg-disabled);
  border-color: var(--border-3);
  color: var(--text-disabled);
  cursor: not-allowed;
}

.btn--primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--bg-container);
}

.btn--primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  color: var(--bg-container);
}

.btn--primary:active:not(:disabled) {
  background: var(--color-primary-active);
  border-color: var(--color-primary-active);
}

.btn--danger {
  background: var(--color-danger);
  border-color: var(--color-danger);
  color: var(--bg-container);
}

.btn--danger:hover:not(:disabled) {
  background: var(--color-danger-hover);
  border-color: var(--color-danger-hover);
  color: var(--bg-container);
}

.btn--text {
  padding: 0 var(--space-2);
  border-color: transparent;
  background: transparent;
  color: var(--text-2);
}

.btn--text:hover:not(:disabled) {
  color: var(--color-primary);
  background: var(--color-primary-bg);
  border-color: transparent;
}

.close-btn .icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
}

.wor-banners {
  display: grid;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-4) 0;
}

.action-error {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--color-danger);
}

.action-message {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--color-success);
}

.wor-list-view,
.wor-detail-view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-3) var(--space-4) var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.wor-detail-view {
  overflow: hidden;
}

/* 审核工作台：左侧目录 + 右侧分节内容（参照智能事件） */
.workbench-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  margin: 0 calc(var(--space-4) * -1) calc(var(--space-5) * -1);
  background: var(--bg-muted);
}

.workbench-index {
  flex: 0 0 176px;
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  padding: 0 var(--space-2) var(--space-3) 0;
}

.workbench-index-title {
  margin: 0 0 var(--space-2);
  padding: var(--space-3) 0 var(--space-2) var(--space-3);
  color: var(--text-1);
  font-size: var(--text-size-base);
  font-weight: var(--font-weight-semibold);
}

.workbench-index-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  min-height: 36px;
  border: 0;
  border-left: 3px solid transparent;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
  padding: var(--space-2) var(--space-3);
  text-align: left;
  font-size: var(--text-size-sm);
  font-family: inherit;
  transition: background 0.15s ease, color 0.15s ease;
}

.workbench-index-item:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.workbench-index-item.active {
  border-left-color: var(--color-primary);
  background: var(--color-primary-bg);
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
}

.index-state {
  flex: 0 0 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-disabled);
}

.index-state.ok { background: var(--color-success); }
.index-state.warn { background: var(--color-warning, #d7a84e); }
.index-state.empty { background: var(--text-disabled); }

.workbench-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0 var(--space-4) var(--space-5) 0;
}

/* 质控任务卡片 */
.qc-task-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.qc-task-card {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
}

.qc-task-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.qc-task-title {
  display: grid;
  gap: 2px;
}

.qc-task-title strong {
  font-size: var(--text-size-sm);
  color: var(--text-1);
}

.link-btn {
  align-self: flex-start;
  border: 0;
  background: transparent;
  color: var(--color-primary);
  cursor: pointer;
  padding: 0;
  font-size: var(--text-size-sm);
  font-family: inherit;
}

.link-btn:hover {
  text-decoration: underline;
}

.qc-task-detail {
  border-top: 1px dashed var(--border-2);
  padding-top: var(--space-3);
}

.wor-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.wor-date-sep {
  color: var(--text-3);
}

.wor-date {
  min-height: var(--control-h-md);
  padding: 0 var(--space-2);
  border: 1px solid var(--border-3);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
  color: var(--text-1);
  font-family: inherit;
  font-size: var(--text-size-sm);
}

.wor-date:hover {
  border-color: var(--color-primary-hover);
}

.wor-date:focus {
  outline: none;
  border-color: var(--color-primary);
}

.wor-date:focus-visible {
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.wor-search {
  flex: 1;
  min-height: var(--control-h-md);
  padding: 0 var(--space-3);
  border: 1px solid var(--border-3);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
  color: var(--text-1);
  font-family: inherit;
  font-size: var(--text-size-sm);
}

.wor-search::placeholder {
  color: var(--text-3);
}

.wor-search:hover {
  border-color: var(--color-primary-hover);
}

.wor-search:focus {
  outline: none;
  border-color: var(--color-primary);
}

.wor-search:focus-visible {
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.wor-status-select {
  min-height: var(--control-h-md);
  padding: 0 var(--space-2);
  border: 1px solid var(--border-3);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
  color: var(--text-1);
  font-family: inherit;
  font-size: var(--text-size-sm);
}

.wor-status-select:hover {
  border-color: var(--color-primary-hover);
}

.wor-status-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.wor-status-select:focus-visible {
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.wor-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-7) var(--space-3);
  color: var(--text-3);
  font-size: var(--text-size-sm);
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--color-primary-bg-hover);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: wor-spin 0.8s linear infinite;
}

.spinner--sm {
  width: 12px;
  height: 12px;
}

@keyframes wor-spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-7) var(--space-4);
  text-align: center;
}

.empty-icon {
  width: 48px;
  height: 48px;
  fill: none;
  stroke: var(--text-disabled);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.empty-title {
  margin: 0;
  font-size: var(--text-size-base);
  color: var(--text-2);
}

.empty-hint {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

/* 工单列表：智能事件中心同款表格形态，整行可点，操作列显式“详情” */
.wor-order-table th {
  white-space: nowrap;
}

.wor-order-table .order-title-cell {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wor-order-table .status-badge {
  vertical-align: middle;
}

.wor-order-row {
  cursor: pointer;
}

.wor-order-row:hover td {
  background: var(--color-primary-bg);
}

.wor-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  font-size: var(--text-size-xs);
  color: var(--text-2);
}

.wor-pagination button {
  min-width: 64px;
  min-height: 28px;
  padding: 0 var(--space-2);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-sm);
  background: var(--bg-container);
  color: var(--text-1);
  cursor: pointer;
  font-size: var(--text-size-xs);
  font-family: inherit;
}

.wor-pagination button:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.wor-pagination button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.order-code {
  font-family: var(--font-mono);
  font-size: var(--text-size-xs);
  color: var(--text-2);
}

/* 状态徽章（规范 §6.3） */
.status-badge {
  flex: none;
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-size-xs);
}

.st-ok { background: var(--color-success-bg); color: var(--color-success); }
.st-info { background: var(--color-primary-bg); color: var(--color-primary); }
.st-warn { background: var(--color-warning-bg); color: var(--color-warning-text); }
.st-bad { background: var(--color-danger-bg); color: var(--color-danger); }

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.detail-heading h3 {
  margin: var(--space-1) 0;
  font-size: var(--text-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-1);
}

.detail-heading p {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

/* 人工操作统一到任务调度中心审核卡片后，这里只留引导说明 */
.action-hint {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border: 1px dashed var(--border-2);
  border-radius: var(--radius-sm);
  color: var(--text-3);
  font-size: var(--text-size-xs);
}

.section-card {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-md);
  background: var(--bg-container);
}

.section-card.judgment {
  border-left: 3px solid var(--color-primary);
}

/* 事件脉络：纵向时间轴，节点 = AI 结论 section，字段为 label/value 对照 */
.section-card.narrative {
  border-left: 3px solid var(--color-primary);
}
.narrative-timeline {
  margin: 0;
  padding: 0;
  list-style: none;
}
.narrative-node {
  position: relative;
  padding: 0 0 var(--space-3) var(--space-4);
  border-left: 2px solid var(--border-2);
}
.narrative-node:last-child {
  padding-bottom: 0;
  border-left-color: transparent;
}
.narrative-node::before {
  content: "";
  position: absolute;
  left: -6px;
  top: 2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-primary);
}
.narrative-node-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.narrative-node-head strong {
  font-size: 14px;
}
.narrative-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 4px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 700;
}
.narrative-fields {
  display: grid;
  grid-template-columns: minmax(96px, 22%) 1fr;
  gap: 8px 16px;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-1);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary, rgba(148, 163, 184, .08));
}
.narrative-fields dt {
  color: var(--text-muted, #64748b);
  font-weight: 600;
}
.narrative-fields dd {
  margin: 0;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
@media (max-width: 720px) {
  .narrative-fields {
    grid-template-columns: 1fr;
    gap: 2px;
  }
  .narrative-fields dd {
    margin-bottom: 8px;
  }
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.section-head h4 {
  margin: 0;
  font-size: var(--text-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-1);
}

.source-meta {
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.source-meta.st-success,
.source-meta.st-pass { color: var(--color-success); }
.source-meta.st-failed,
.source-meta.st-empty { color: var(--color-danger); }
.source-meta.st-partial,
.source-meta.st-unavailable { color: var(--color-warning-text); }

.source-summary {
  margin: 0;
  font-size: var(--text-size-sm);
  color: var(--text-2);
}

.source-empty {
  margin: 0;
  font-size: var(--text-size-sm);
  color: var(--text-3);
}

/* 气象图污染物切换器（参照智能事件对比图的右上角切换按钮组），色标与曲线同色 */
.pollutant-switch {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  border-radius: 4px;
  padding: 2px;
  background: #f5f7fa;
}

.pollutant-switch button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 48px;
  border: 0;
  border-radius: 4px;
  padding: 5px 8px;
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
  transition: all 0.15s ease;
}

.pollutant-switch button.active {
  background: var(--bg-container);
  color: var(--color-primary);
  box-shadow: 0 1px 3px rgba(31, 42, 68, 0.14);
  font-weight: 600;
}

.pollutant-switch .switch-swatch {
  width: 12px;
  height: 3px;
  border-radius: 2px;
  flex: 0 0 auto;
}

/* 同城对比带区块的范围说明（图已并入上方小时时序图，本区块只剩说明与数据表） */
.band-scope-note {
  margin: 0;
  font-size: var(--text-size-sm);
  color: var(--text-2);
}

.muted {
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.judgment-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.chip {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-size-xs);
  background: var(--bg-muted);
  color: var(--text-2);
}

.chip.ok { background: var(--color-success-bg); color: var(--color-success); }
.chip.bad { background: var(--color-danger-bg); color: var(--color-danger); }
.chip.neutral { background: var(--bg-muted); color: var(--text-2); }

/* 工单信息：信息表样式（对齐平台详单排版）——标签+取值成对排列，不用逐个字段的框线，
   长文本（描述、内容）自动占满整行。 */
.fact-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 2px var(--space-5);
}

.fact-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  min-width: 0;
  padding: 3px 0;
}

.fact-row.wide {
  grid-column: 1 / -1;
}

.fact-row > span {
  flex: none;
  width: 76px;
  font-size: var(--text-size-xs);
  color: var(--text-3);
}

.fact-row > strong {
  min-width: 0;
  font-size: var(--text-size-sm);
  font-weight: 500;
  color: var(--text-1);
  overflow-wrap: anywhere;
}

.fact-row.wide > strong {
  white-space: pre-wrap;
  line-height: 1.6;
}

.table-scroll {
  overflow-x: auto;
}

/* 卡片内数据表：规范 §6.4 无边框紧凑变体 */
.evidence-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-size-sm);
}

.evidence-table th,
.evidence-table td {
  padding: var(--space-2);
  text-align: left;
  vertical-align: top;
  color: var(--text-1);
  border-bottom: 1px solid var(--border-1);
}

.evidence-table th {
  background: var(--bg-muted);
  color: var(--text-2);
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
}

.evidence-table tbody tr:last-child td {
  border-bottom: 0;
}

.basis-cell {
  max-width: 420px;
}

.truncated-note {
  margin: 0;
  font-size: var(--text-size-xs);
  color: var(--color-warning-text);
}

.history-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--space-2);
  font-size: var(--text-size-sm);
  color: var(--text-1);
}

.history-list li {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.history-list li strong {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-1);
}

.history-list li span {
  color: var(--text-2);
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.history-list small {
  color: var(--text-3);
}

/* 遮罩：仅图片预览使用（人工操作对话框已移除，操作统一在任务调度中心审核卡片） */
.dialog-mask {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: var(--space-4);
  background: rgba(15, 23, 42, 0.38);
}

/* 工单信息分区（设备/流程/处置/附件）：只用一条细分割线分区，不再套框 */
.fact-block {
  display: grid;
  gap: var(--space-1);
  padding-top: var(--space-2);
  border-top: 1px solid var(--border-1);
}

.fact-block h5 {
  margin: 0;
  font-size: 12px;
  color: var(--text-2);
  font-weight: 600;
}

.step-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  font-size: 12px;
  color: var(--text-1);
}

.step-list li small {
  margin-left: auto;
  color: var(--text-3);
}

.step-list li em {
  font-style: normal;
  font-size: 11px;
  color: var(--text-3);
}

.step-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #b6c2d2;
  flex: none;
}

.step-dot.st-ok {
  background: #1e7f46;
}

.step-dot.st-info {
  background: #2563c4;
}

.attachment-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: var(--space-3);
}

.attachment-grid figure {
  margin: 0;
  display: grid;
  gap: 4px;
  min-width: 0;
  font-size: 11px;
  color: var(--text-3);
}

.attachment-grid figure.failed {
  opacity: 0.6;
}

.attachment-thumb {
  width: 100%;
  height: 96px;
  padding: 0;
  border: 1px solid var(--border-1, #e2e8f1);
  border-radius: 4px;
  overflow: hidden;
  background: #f6f8fb;
  cursor: zoom-in;
}

.attachment-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.attachment-file {
  font-size: 12px;
  color: #2563c4;
  text-decoration: none;
  overflow-wrap: anywhere;
}

.attachment-file.muted {
  color: var(--text-3);
}

.attachment-grid figcaption {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.attachment-grid figcaption em {
  font-style: normal;
  flex: none;
}

.image-mask {
  z-index: calc(var(--z-modal) + 1);
}

.preview-image {
  max-width: min(92vw, 1200px);
  max-height: 86vh;
  border-radius: 8px;
  box-shadow: var(--shadow-3);
  cursor: zoom-out;
}

.preview-close {
  position: fixed;
  top: 16px;
  right: 20px;
  background: #fff;
}
</style>


