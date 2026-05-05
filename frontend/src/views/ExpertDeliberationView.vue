<template>
  <div class="deliberation-page">
    <header class="deliberation-header">
      <div>
        <h1>专家会商推演</h1>
        <p>以事实账本为中心，组织多专家审阅、补证、质疑和共识生成。</p>
      </div>
      <nav class="header-actions">
        <RouterLink to="/" class="nav-button">返回分析</RouterLink>
        <button class="primary-button" :disabled="running" @click="runDeliberation">
          {{ running ? '生成中...' : '开始会商' }}
        </button>
      </nav>
    </header>

    <main class="deliberation-workspace">
      <section class="input-pane">
        <div class="section-heading">
          <h2>输入事实来源</h2>
          <span>种子事实</span>
        </div>

        <label class="field">
          <span>会商主题</span>
          <input v-model="form.topic" type="text" />
        </label>

        <div class="field-grid">
          <label class="field">
            <span>区域</span>
            <input v-model="form.region" type="text" />
          </label>
          <label class="field">
            <span>时段</span>
            <input v-model="form.timeRangeDisplay" type="text" />
          </label>
        </div>

        <label class="field">
          <span>污染物</span>
          <input v-model="pollutantsText" type="text" placeholder="PM2.5, O3" />
        </label>

        <section class="upload-box">
          <div class="upload-title">
            <div>
              <h3>事实文件</h3>
              <p>默认读取 /tmp/A会商文件；也可手动上传 Excel/CSV、Markdown/QMD/TXT/DOCX/HTML 覆盖。</p>
            </div>
            <div class="upload-actions">
              <button class="secondary-button" :disabled="loadingDefaultFiles || parsingFiles" @click="loadDefaultInputFiles(false)">
                {{ loadingDefaultFiles ? '读取中...' : '读取默认目录' }}
              </button>
              <button class="secondary-button" :disabled="parsingFiles || loadingDefaultFiles" @click="parseInputFiles">
                {{ parsingFiles ? '解析中...' : '解析上传' }}
              </button>
            </div>
          </div>

          <div class="upload-grid">
            <label class="file-field">
              <span>会商数据表</span>
              <input accept=".xlsx,.xls,.csv" type="file" @change="setUploadFile('consultationFile', $event)" />
            </label>
            <label class="file-field">
              <span>上月报告</span>
              <input accept=".md,.markdown,.qmd,.txt,.docx,.html,.htm" type="file" @change="setUploadFile('monthlyReportFile', $event)" />
            </label>
            <label class="file-field">
              <span>阶段5成果</span>
              <input accept=".md,.markdown,.qmd,.txt,.docx,.html,.htm" type="file" @change="setUploadFile('stage5ReportFile', $event)" />
            </label>
          </div>

          <div v-if="parseWarnings.length" class="warning-list">
            <p v-for="warning in parseWarnings" :key="warning">{{ warning }}</p>
          </div>
        </section>

        <label class="field">
          <span>会商表格 JSON</span>
          <textarea
            v-model="tablesText"
            spellcheck="false"
            placeholder='[{"城市":"广州","污染物":"PM2.5","月均浓度":28,"说明":"污染过程受静稳气象影响"}]'
          />
        </label>

        <label class="field">
          <span>上个月污染特征与溯源分析报告成果</span>
          <textarea v-model="form.monthlyReportText" spellcheck="false" />
        </label>

        <label class="field">
          <span>阶段5深度分析成果</span>
          <textarea v-model="form.stage5ReportText" spellcheck="false" />
        </label>

        <label class="field">
          <span>已有 data_id</span>
          <input v-model="dataIdsText" type="text" placeholder="air_quality:v1:xxx, weather:v1:xxx" />
        </label>

        <label class="field">
          <span>追加讨论/追问</span>
          <textarea
            v-model="discussionPrompt"
            spellcheck="false"
            placeholder="例如：请气象专家重新判断静稳条件影响；质疑高共识结论；补充读取某个 data_id。"
          />
        </label>

        <label class="field">
          <span>指定专家（可选）</span>
          <input
            v-model="targetExpertsText"
            type="text"
            placeholder="monitoring_feature_expert, weather_transport_expert 或 常规监测与污染特征专家"
          />
        </label>

        <p v-if="error" class="error-message">{{ error }}</p>
      </section>

      <section class="result-pane">
        <div v-if="!result" class="empty-state">
          <h2>等待会商结果</h2>
          <p>运行后将展示事实账本、专家意见、共识结论和可插入报告的 Markdown 章节。</p>
        </div>

        <template v-else>
          <div class="summary-strip">
            <div>
              <strong>{{ result.facts.length }}</strong>
              <span>事实</span>
            </div>
            <div>
              <strong>{{ result.analyses.length }}</strong>
              <span>专家意见</span>
            </div>
            <div>
              <strong>{{ result.discussion_turns?.length || 0 }}</strong>
              <span>讨论轮次</span>
            </div>
            <div>
              <strong>{{ result.conclusions.length }}</strong>
              <span>共识</span>
            </div>
            <div>
              <strong>{{ result.evidence_matrix?.length || 0 }}</strong>
              <span>证据矩阵</span>
            </div>
            <div>
              <strong>{{ result.dissents.length }}</strong>
              <span>补证/分歧</span>
            </div>
          </div>

          <div class="tabs" role="tablist">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              :class="{ active: activeTab === tab.key }"
              @click="activeTab = tab.key"
            >
              {{ tab.label }}
            </button>
          </div>

          <div v-if="activeTab === 'facts'" class="result-section">
            <div class="facts-table">
              <div class="facts-row facts-head">
                <span>编号</span>
                <span>来源</span>
                <span>事实</span>
                <span>标签</span>
              </div>
              <div v-for="fact in result.facts" :key="fact.fact_id" class="facts-row">
                <span>{{ fact.fact_id }}</span>
                <span>{{ sourceLabel(fact.source_type) }}</span>
                <span>{{ fact.statement }}</span>
                <span>{{ fact.tags.join('、') }}</span>
              </div>
            </div>
          </div>

          <div v-else-if="activeTab === 'experts'" class="result-section expert-list">
            <article v-for="analysis in result.analyses" :key="analysis.expert_id" class="expert-item">
              <div class="expert-title">
                <h3>{{ analysis.display_name }}</h3>
                <span>{{ analysis.used_fact_ids.length }} 条事实</span>
              </div>
              <p>{{ analysis.position }}</p>
              <div class="tag-line">
                <span v-for="factId in analysis.used_fact_ids.slice(0, 6)" :key="factId">{{ factId }}</span>
              </div>
              <p v-if="analysis.tool_call_plan.length" class="supplement">
                补证建议：{{ analysis.tool_call_plan.map(item => item.purpose).join('；') }}
              </p>
            </article>
          </div>

          <div v-else-if="activeTab === 'consensus'" class="result-section">
            <div class="consensus-list">
              <article v-for="item in result.conclusions" :key="item.claim">
                <h3>{{ item.consensus_level }} · {{ item.confidence.toFixed(2) }}</h3>
                <p>{{ item.claim }}</p>
                <div class="tag-line">
                  <span v-for="factId in item.evidence_fact_ids" :key="factId">{{ factId }}</span>
                </div>
              </article>
            </div>

            <h3 class="subheading">结论-证据矩阵</h3>
            <div class="matrix-table">
              <div class="matrix-row matrix-head">
                <span>结论</span>
                <span>可写性</span>
                <span>支持专家</span>
                <span>关键事实</span>
                <span>风险</span>
              </div>
              <div v-for="row in result.evidence_matrix || []" :key="row.conclusion_id" class="matrix-row">
                <span>{{ row.claim }}</span>
                <span>{{ row.writability }}</span>
                <span>{{ row.supporting_experts.join('、') || '暂无' }}</span>
                <span>{{ row.evidence_fact_ids.slice(0, 5).join('、') || '暂无' }}</span>
                <span>{{ row.risk_flags.join('；') || '暂无' }}</span>
              </div>
            </div>

            <h3 class="subheading">禁写结论</h3>
            <div class="forbidden-list">
              <p v-for="item in result.forbidden_claims" :key="item.claim">
                <strong>{{ item.claim }}</strong>：{{ item.reason }}
              </p>
            </div>
          </div>

          <div v-else-if="activeTab === 'discussion'" class="result-section discussion-list">
            <div class="timeline-list">
              <article v-for="event in result.timeline_events || []" :key="event.event_id" class="timeline-item">
                <div class="expert-title">
                  <h3>{{ event.title }}</h3>
                  <span>{{ event.stage }}<template v-if="event.round_index"> · 第 {{ event.round_index }} 轮</template></span>
                </div>
                <p>{{ event.description }}</p>
                <div v-if="event.fact_ids.length" class="tag-line">
                  <span v-for="factId in event.fact_ids.slice(0, 8)" :key="factId">{{ factId }}</span>
                </div>
              </article>
            </div>
            <h3 class="subheading">专家讨论记录</h3>
            <article v-for="turn in result.discussion_turns || []" :key="turn.turn_id" class="discussion-item">
              <div class="expert-title">
                <h3>{{ turn.turn_id }} · {{ turn.display_name }}</h3>
                <span>第 {{ turn.round_index }} 轮 · {{ turnTypeLabel(turn.turn_type) }}</span>
              </div>
              <p>{{ turn.position }}</p>
              <div v-if="turn.used_fact_ids.length" class="tag-line">
                <span v-for="factId in turn.used_fact_ids.slice(0, 8)" :key="factId">{{ factId }}</span>
              </div>
              <p v-if="turn.questions_to_others.length" class="supplement">
                提问：{{ turn.questions_to_others.map(item => `${item.target_expert}：${item.question}`).join('；') }}
              </p>
              <p v-if="turn.new_fact_ids.length" class="supplement">
                新增补证事实：{{ turn.new_fact_ids.join('、') }}
              </p>
            </article>
            <div v-if="!(result.discussion_turns || []).length" class="empty-inline">暂无共享讨论记录</div>
          </div>

          <div v-else class="result-section markdown-panel">
            <MarkdownRenderer :content="result.report_markdown" />
          </div>
        </template>
      </section>
    </main>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import {
  loadDefaultExpertDeliberationInputFiles,
  parseExpertDeliberationInputFiles,
  runExpertDeliberation
} from '@/services/expertDeliberationApi'

const running = ref(false)
const parsingFiles = ref(false)
const loadingDefaultFiles = ref(false)
const error = ref('')
const result = ref(null)
const activeTab = ref('facts')
const parseWarnings = ref([])
const parsedConsultationTables = ref([])
const uploadedTablesText = ref('')

const tabs = [
  { key: 'facts', label: '事实账本' },
  { key: 'experts', label: '专家意见' },
  { key: 'consensus', label: '共识审查' },
  { key: 'discussion', label: '讨论过程' },
  { key: 'report', label: '报告章节' }
]

const form = reactive({
  topic: '月度空气质量专家会商',
  region: '广东省',
  timeRangeDisplay: '2026年4月',
  monthlyReportText: '4月中旬出现PM2.5污染过程。气象条件表现为风速偏低、降水偏少，二次生成有所增强。轨迹显示部分时段存在区域传输。',
  stage5ReportText: '阶段5分析认为，应重点关注PM2.5和O3协同变化，并对重点城市开展源解析和轨迹补证。'
})

const pollutantsText = ref('PM2.5, O3')
const dataIdsText = ref('air_quality:v1:example, weather:v1:example')
const discussionPrompt = ref('')
const targetExpertsText = ref('')
const tablesText = ref(JSON.stringify([
  { 城市: '广州', 污染物: 'PM2.5', 月均浓度: 28, 同比: '10%', 说明: '污染过程受静稳气象影响' },
  { 城市: '东莞', 污染物: 'O3', 最大8小时浓度: 165, 说明: '臭氧高值需关注VOCs和NOx协同管控' }
], null, 2))
const uploadFiles = reactive({
  consultationFile: null,
  monthlyReportFile: null,
  stage5ReportFile: null
})

function parseList(text) {
  return text.split(/[,，\n]/).map(item => item.trim()).filter(Boolean)
}

function parseTableRows() {
  const parsed = JSON.parse(tablesText.value || '[]')
  if (!Array.isArray(parsed)) {
    throw new Error('会商表格 JSON 必须是数组')
  }
  return parsed
}

function setUploadFile(key, event) {
  uploadFiles[key] = event.target.files?.[0] || null
}

function applyParsedInputFiles(parsed) {
  parsedConsultationTables.value = parsed.consultation_tables || []
  parseWarnings.value = parsed.warnings || []

  if (parsedConsultationTables.value.length) {
    const rows = parsedConsultationTables.value.flatMap(table =>
      (table.rows || []).map(row => ({
        来源表: table.name,
        ...row
      }))
    )
    uploadedTablesText.value = JSON.stringify(rows, null, 2)
    tablesText.value = uploadedTablesText.value
  }
  if (parsed.monthly_report_text) {
    form.monthlyReportText = parsed.monthly_report_text
  }
  if (parsed.stage5_report_text) {
    form.stage5ReportText = parsed.stage5_report_text
  }
}

function buildConsultationTables() {
  if (
    parsedConsultationTables.value.length &&
    uploadedTablesText.value &&
    tablesText.value === uploadedTablesText.value
  ) {
    return parsedConsultationTables.value
  }

  return [
    {
      name: '会商输入表',
      source_type: 'consultation_table',
      rows: parseTableRows()
    }
  ]
}

async function parseInputFiles() {
  error.value = ''
  parseWarnings.value = []

  if (!uploadFiles.consultationFile && !uploadFiles.monthlyReportFile && !uploadFiles.stage5ReportFile) {
    error.value = '请先选择至少一个事实文件'
    return
  }

  parsingFiles.value = true
  try {
    const parsed = await parseExpertDeliberationInputFiles(uploadFiles)
    applyParsedInputFiles(parsed)
  } catch (err) {
    error.value = normalizeError(err)
  } finally {
    parsingFiles.value = false
  }
}

async function loadDefaultInputFiles(showError = true) {
  error.value = ''
  parseWarnings.value = []
  loadingDefaultFiles.value = true
  try {
    const parsed = await loadDefaultExpertDeliberationInputFiles()
    applyParsedInputFiles(parsed)
  } catch (err) {
    if (showError) {
      error.value = normalizeError(err)
    }
  } finally {
    loadingDefaultFiles.value = false
  }
}

async function runDeliberation() {
  error.value = ''
  running.value = true
  try {
    const payload = {
      topic: form.topic,
      region: form.region,
      time_range: {
        display: form.timeRangeDisplay
      },
      pollutants: parseList(pollutantsText.value),
      consultation_tables: buildConsultationTables(),
      monthly_report_text: form.monthlyReportText,
      stage5_report_text: form.stage5ReportText,
      data_ids: parseList(dataIdsText.value),
      discussion_prompt: discussionPrompt.value,
      target_experts: parseList(targetExpertsText.value)
    }
    result.value = await runExpertDeliberation(payload)
    activeTab.value = 'facts'
  } catch (err) {
    error.value = err.message || '会商生成失败'
  } finally {
    running.value = false
  }
}

function normalizeError(err) {
  const message = err.message || '操作失败'
  try {
    const parsed = JSON.parse(message)
    return parsed.detail || message
  } catch {
    return message
  }
}

function sourceLabel(sourceType) {
  const labels = {
    consultation_table: '会商表格',
    monthly_trace_report: '上月报告',
    stage5_analysis: '阶段5',
    data_id: '数据资产'
  }
  return labels[sourceType] || sourceType
}

function turnTypeLabel(turnType) {
  const labels = {
    initial_opinion: '初判',
    cross_review: '交叉复议',
    review_moderation: '审查统稿'
  }
  return labels[turnType] || turnType
}

onMounted(() => {
  loadDefaultInputFiles(false)
})
</script>

<style lang="scss" scoped>
.deliberation-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f6f7f9;
  color: #1f2933;
}

.deliberation-header {
  height: 76px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  background: #ffffff;
  border-bottom: 1px solid #dfe3e8;

  h1 {
    font-size: 20px;
    font-weight: 650;
    margin-bottom: 6px;
  }

  p {
    color: #667085;
    font-size: 13px;
  }
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.nav-button,
.primary-button,
.secondary-button {
  height: 36px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 14px;
  text-decoration: none;
  cursor: pointer;
}

.nav-button {
  color: #475467;
  border: 1px solid #d0d5dd;
  background: #fff;
  display: inline-flex;
  align-items: center;
}

.primary-button {
  color: #fff;
  border: 1px solid #166534;
  background: #16703f;

  &:disabled {
    opacity: 0.65;
    cursor: not-allowed;
  }
}

.secondary-button {
  color: #175cd3;
  border: 1px solid #b2ddff;
  background: #eff8ff;

  &:disabled {
    opacity: 0.65;
    cursor: not-allowed;
  }
}

.deliberation-workspace {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(360px, 440px) minmax(0, 1fr);
}

.input-pane,
.result-pane {
  min-height: 0;
  overflow: auto;
}

.input-pane {
  padding: 22px;
  background: #ffffff;
  border-right: 1px solid #dfe3e8;
}

.result-pane {
  padding: 22px;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;

  h2 {
    font-size: 16px;
  }

  span {
    font-size: 12px;
    color: #0f766e;
    background: #e6fffb;
    border: 1px solid #99f6e4;
    padding: 4px 8px;
    border-radius: 999px;
  }
}

.field-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.upload-box {
  border: 1px solid #dfe3e8;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 14px;
  background: #f8fafc;
}

.upload-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;

  h3 {
    font-size: 14px;
    margin-bottom: 4px;
  }

  p {
    color: #667085;
    font-size: 12px;
    line-height: 1.5;
  }
}

.upload-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.upload-grid {
  display: grid;
  gap: 10px;
}

.file-field {
  display: grid;
  gap: 6px;

  span {
    color: #475467;
    font-size: 13px;
  }

  input {
    width: 100%;
    font-size: 12px;
    color: #475467;
  }
}

.warning-list {
  margin-top: 10px;
  border: 1px solid #fedf89;
  border-radius: 6px;
  background: #fffaeb;
  padding: 8px 10px;

  p {
    color: #92400e;
    font-size: 12px;
    line-height: 1.5;
  }
}

.field {
  display: block;
  margin-bottom: 14px;

  span {
    display: block;
    font-size: 13px;
    color: #475467;
    margin-bottom: 6px;
  }

  input,
  textarea {
    width: 100%;
    border: 1px solid #cfd6df;
    border-radius: 6px;
    background: #fff;
    color: #1f2933;
    font-size: 13px;
    line-height: 1.5;
    padding: 9px 10px;
    outline: none;

    &:focus {
      border-color: #16703f;
      box-shadow: 0 0 0 3px rgba(22, 112, 63, 0.12);
    }
  }

  textarea {
    min-height: 104px;
    resize: vertical;
    font-family: Consolas, 'Microsoft YaHei', monospace;
  }
}

.error-message {
  color: #b42318;
  background: #fff1f0;
  border: 1px solid #ffccc7;
  padding: 10px;
  border-radius: 6px;
  font-size: 13px;
}

.empty-state {
  min-height: 320px;
  display: grid;
  place-content: center;
  text-align: center;
  color: #667085;

  h2 {
    color: #1f2933;
    margin-bottom: 8px;
  }
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  background: #dfe3e8;
  border: 1px solid #dfe3e8;
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 14px;

  div {
    background: #fff;
    padding: 14px;
  }

  strong {
    display: block;
    font-size: 22px;
    margin-bottom: 4px;
  }

  span {
    color: #667085;
    font-size: 13px;
  }
}

.tabs {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid #dfe3e8;
  margin-bottom: 14px;

  button {
    border: 0;
    background: transparent;
    padding: 10px 12px;
    color: #667085;
    cursor: pointer;
    border-bottom: 2px solid transparent;

    &.active {
      color: #16703f;
      border-bottom-color: #16703f;
    }
  }
}

.result-section {
  background: #fff;
  border: 1px solid #dfe3e8;
  border-radius: 6px;
  overflow: auto;
}

.facts-table {
  min-width: 920px;
}

.matrix-table {
  min-width: 980px;
  border-top: 1px solid #eef1f4;
}

.matrix-row {
  display: grid;
  grid-template-columns: minmax(300px, 1.4fr) 90px 150px 190px 180px;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid #eef1f4;
  font-size: 13px;
  line-height: 1.6;

  &:last-child {
    border-bottom: 0;
  }
}

.matrix-head {
  background: #f8fafc;
  font-weight: 650;
  color: #475467;
}

.facts-row {
  display: grid;
  grid-template-columns: 160px 100px minmax(360px, 1fr) 160px;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid #eef1f4;
  font-size: 13px;

  &:last-child {
    border-bottom: 0;
  }
}

.facts-head {
  position: sticky;
  top: 0;
  background: #f8fafc;
  font-weight: 650;
  color: #475467;
}

.expert-list,
.consensus-list,
.discussion-list,
.markdown-panel {
  padding: 16px;
}

.expert-item,
.discussion-item,
.timeline-item,
.consensus-list article {
  border-bottom: 1px solid #eef1f4;
  padding: 14px 0;

  &:first-child {
    padding-top: 0;
  }

  &:last-child {
    border-bottom: 0;
    padding-bottom: 0;
  }

  p {
    line-height: 1.7;
    color: #344054;
    margin-top: 8px;
  }
}

.timeline-list {
  border-bottom: 1px solid #dfe3e8;
  margin-bottom: 16px;
  padding-bottom: 4px;
}

.empty-inline {
  color: #667085;
  font-size: 13px;
  padding: 18px;
}

.expert-title {
  display: flex;
  align-items: center;
  justify-content: space-between;

  h3 {
    font-size: 15px;
  }

  span {
    color: #667085;
    font-size: 12px;
  }
}

.tag-line {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;

  span {
    font-size: 12px;
    color: #175cd3;
    background: #eff8ff;
    border: 1px solid #b2ddff;
    border-radius: 999px;
    padding: 3px 8px;
  }
}

.supplement {
  color: #92400e !important;
}

.subheading {
  margin: 18px 0 10px;
  font-size: 15px;
}

.forbidden-list {
  border-top: 1px solid #eef1f4;
  padding-top: 10px;

  p {
    line-height: 1.7;
    margin-bottom: 8px;
  }
}

@media (max-width: 980px) {
  .deliberation-header {
    height: auto;
    align-items: flex-start;
    gap: 14px;
    padding: 18px;
    flex-direction: column;
  }

  .deliberation-workspace {
    grid-template-columns: 1fr;
  }

  .input-pane {
    border-right: 0;
    border-bottom: 1px solid #dfe3e8;
  }

  .summary-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
