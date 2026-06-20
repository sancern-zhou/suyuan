<template>
  <div class="management-panel cognitive-map-panel">
    <div class="panel-header">
      <div>
        <h3>认知地图</h3>
        <p class="panel-subtitle">实体、关系、规则与证据管理</p>
      </div>
      <div class="panel-actions">
        <button class="panel-btn" type="button" @click="refreshAll" :disabled="loading">
          刷新
        </button>
        <button class="panel-btn close-btn" type="button" @click="$emit('close')">
          关闭
        </button>
      </div>
    </div>

    <div v-if="apiUnavailable" class="service-notice">
      <strong>后端接口未就绪</strong>
      <span>当前页面已接入 `/api/cognitive-maps` 契约，等待后端服务化后即可显示真实数据。</span>
    </div>

    <div class="content-grid">
      <aside class="map-list-panel">
        <div class="section-header">
          <span>地图列表</span>
          <span class="count">{{ maps.length }}</span>
        </div>

        <form class="create-form" @submit.prevent="handleCreate">
          <input
            v-model="createForm.name"
            type="text"
            placeholder="新建地图名称"
            @input="createError = ''"
          />
          <button type="submit" :disabled="creating">
            {{ creating ? '创建中' : '新建' }}
          </button>
        </form>
        <div v-if="createError" class="form-error">{{ createError }}</div>

        <div v-if="loading" class="state-text">加载中...</div>
        <div v-else-if="maps.length === 0" class="state-text">暂无认知地图</div>
        <button
          v-for="map in maps"
          v-else
          :key="map.id"
          class="map-item"
          :class="{ active: currentMap?.id === map.id }"
          type="button"
          @click="selectMap(map)"
        >
          <span class="map-name">{{ map.name }}</span>
          <span class="map-meta">
            {{ map.entity_count || 0 }} 实体 / {{ map.relation_count || 0 }} 关系
          </span>
          <span class="map-status">{{ getStatusText(map.status) }}</span>
        </button>
      </aside>

      <main class="map-detail-panel">
        <div v-if="!currentMap" class="empty-detail">
          选择或新建认知地图
        </div>

        <template v-else>
          <div class="detail-header">
            <div>
              <h4>{{ currentMap.name }}</h4>
              <p v-if="currentMap.description">{{ currentMap.description }}</p>
            </div>
            <div class="build-actions">
              <label class="engine-select">
                <span>抽取引擎</span>
                <select v-model="buildOptions.extractorProvider" :disabled="building">
                  <option value="local">本地规则</option>
                  <option value="llamaindex">LlamaIndex</option>
                </select>
              </label>
              <label class="engine-select">
                <span>超时</span>
                <input
                  v-model.number="buildOptions.timeoutSeconds"
                  type="number"
                  min="30"
                  max="900"
                  step="30"
                  :disabled="building"
                />
              </label>
              <button class="primary-btn" type="button" @click="handleBuild" :disabled="building">
                {{ building ? '构建中...' : '构建地图' }}
              </button>
              <button
                v-if="canRetryBuild"
                class="panel-btn"
                type="button"
                @click="handleBuild"
                :disabled="building"
              >
                重试
              </button>
            </div>
          </div>
          <div v-if="buildError" class="form-error build-message">{{ buildError }}</div>
          <div v-else-if="buildMessage" class="form-success build-message">{{ buildMessage }}</div>

          <div class="run-summary">
            <div class="run-summary-item">
              <span class="summary-label">最近引擎</span>
              <span class="run-value">{{ latestRun?.extractor_provider || currentMap.extractor_provider || '未构建' }}</span>
            </div>
            <div class="run-summary-item">
              <span class="summary-label">状态</span>
              <span class="run-value">{{ getStatusText(latestRun?.status || currentMap.status) }}</span>
            </div>
            <div class="run-summary-item">
              <span class="summary-label">耗时</span>
              <span class="run-value">{{ formatDuration(latestRun?.duration_ms) }}</span>
            </div>
            <div class="run-summary-item">
              <span class="summary-label">Chunk</span>
              <span class="run-value">{{ latestRun?.chunk_count ?? '-' }}</span>
            </div>
            <div class="run-summary-item">
              <span class="summary-label">超时</span>
              <span class="run-value">{{ formatSeconds(latestRun?.timeout_seconds || buildOptions.timeoutSeconds) }}</span>
            </div>
            <div class="run-summary-item">
              <span class="summary-label">证据覆盖</span>
              <span class="run-value">{{ formatRatio(evaluation?.entity_evidence_ratio) }}</span>
            </div>
          </div>
          <div v-if="latestRun?.error || currentMap.build_error" class="form-error">
            {{ latestRun?.error || currentMap.build_error }}
          </div>

          <div class="summary-grid">
            <div class="summary-item">
              <span class="summary-value">{{ files.length }}</span>
              <span class="summary-label">文件</span>
            </div>
            <div class="summary-item">
              <span class="summary-value">{{ entities.length }}</span>
              <span class="summary-label">实体</span>
            </div>
            <div class="summary-item">
              <span class="summary-value">{{ relations.length }}</span>
              <span class="summary-label">关系</span>
            </div>
            <div class="summary-item">
              <span class="summary-value">{{ evidence.length }}</span>
              <span class="summary-label">证据</span>
            </div>
          </div>

          <div
            class="upload-area"
            :class="{ dragging: isDragging, uploading }"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @drop.prevent="handleDrop"
            @click="triggerFileInput"
          >
            <input
              ref="fileInput"
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.html,.htm,.txt,.md,.csv,.json"
              @change="handleFileSelect"
            />
            <span v-if="uploading">上传中 {{ uploadProgress.current }}/{{ uploadProgress.total }}</span>
            <span v-else>点击或拖拽文件到此处</span>
          </div>
          <div v-if="uploadError" class="form-error">{{ uploadError }}</div>

          <div class="tabs">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              :class="{ active: activeTab === tab.id }"
              @click="activeTab = tab.id"
            >
              {{ tab.name }}
            </button>
          </div>

          <section v-if="activeTab === 'files'" class="data-section">
            <div v-if="files.length === 0" class="state-text">暂无文件</div>
            <div v-for="file in files" v-else :key="file.file_id || file.id || file.filename" class="data-row">
              <span class="row-title">{{ file.filename || file.name }}</span>
              <span class="row-meta">{{ getStatusText(file.status) }}</span>
            </div>
          </section>

          <section v-else-if="activeTab === 'entities'" class="data-section">
            <div v-if="entities.length === 0" class="state-text">暂无实体</div>
            <div v-for="entity in entities" v-else :key="entity.entity_id || entity.id || entity.name" class="data-row">
              <span class="row-title">{{ entity.name }}</span>
              <span class="row-meta">{{ entity.type || entity.entity_type || '未分类' }}</span>
            </div>
          </section>

          <section v-else-if="activeTab === 'relations'" class="data-section">
            <div v-if="relations.length === 0" class="state-text">暂无关系</div>
            <div v-for="relation in relations" v-else :key="relation.relation_id || relation.id || relation.key" class="data-row">
              <span class="row-title">
                {{ relation.source || relation.source_name }} -> {{ relation.target || relation.target_name }}
              </span>
              <span class="row-meta">{{ relation.type || relation.relation_type }}</span>
            </div>
          </section>

          <section v-else class="data-section">
            <div v-if="evidence.length === 0" class="state-text">暂无证据</div>
            <div v-for="item in evidence" v-else :key="item.evidence_id || item.id || item.chunk_id" class="evidence-row">
              <div class="row-title">{{ item.title || item.source || '证据片段' }}</div>
              <p>{{ item.text || item.content || item.quote || item.text_span || item.normalized_summary }}</p>
            </div>
          </section>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  buildCognitiveMap,
  createCognitiveMap,
  getCognitiveMapEvaluation,
  listCognitiveMapBuildRuns,
  listCognitiveMapEntities,
  listCognitiveMapEvidence,
  listCognitiveMapFiles,
  listCognitiveMapRelations,
  listCognitiveMaps,
  uploadCognitiveMapFile
} from '@/api/cognitiveMap'

defineEmits(['close'])

const loading = ref(false)
const creating = ref(false)
const building = ref(false)
const uploading = ref(false)
const apiUnavailable = ref(false)
const isDragging = ref(false)
const fileInput = ref(null)
const uploadProgress = ref({ current: 0, total: 0 })
const maps = ref([])
const currentMap = ref(null)
const files = ref([])
const entities = ref([])
const relations = ref([])
const evidence = ref([])
const buildRuns = ref([])
const evaluation = ref(null)
const activeTab = ref('files')
const createForm = ref({ name: '' })
const createError = ref('')
const uploadError = ref('')
const buildError = ref('')
const buildMessage = ref('')
const buildOptions = ref({
  extractorProvider: 'local',
  timeoutSeconds: 300
})

const tabs = computed(() => [
  { id: 'files', name: `文件 ${files.value.length}` },
  { id: 'entities', name: `实体 ${entities.value.length}` },
  { id: 'relations', name: `关系 ${relations.value.length}` },
  { id: 'evidence', name: `证据 ${evidence.value.length}` }
])

const latestRun = computed(() => buildRuns.value[0] || currentMap.value?.latest_run || null)
const canRetryBuild = computed(() => currentMap.value?.status === 'failed' || latestRun.value?.status === 'failed')

const normalizeList = (payload, keys) => {
  if (Array.isArray(payload)) return payload
  for (const key of keys) {
    if (Array.isArray(payload?.[key])) return payload[key]
  }
  return []
}

const getStatusText = (status) => {
  const map = {
    draft: '草稿',
    building: '构建中',
    completed: '已完成',
    published: '已发布',
    failed: '失败'
  }
  return map[status] || status || '未处理'
}

const refreshMaps = async () => {
  loading.value = true
  apiUnavailable.value = false
  try {
    const payload = await listCognitiveMaps()
    maps.value = normalizeList(payload, ['maps', 'items', 'data'])
    if (!currentMap.value && maps.value.length > 0) {
      await selectMap(maps.value[0])
    }
  } catch (error) {
    apiUnavailable.value = true
    maps.value = []
    currentMap.value = null
  } finally {
    loading.value = false
  }
}

const refreshCurrentMapData = async () => {
  if (!currentMap.value?.id) return
  try {
    const [filePayload, entityPayload, relationPayload, evidencePayload, runsPayload, evaluationPayload] = await Promise.all([
      listCognitiveMapFiles(currentMap.value.id),
      listCognitiveMapEntities(currentMap.value.id),
      listCognitiveMapRelations(currentMap.value.id),
      listCognitiveMapEvidence(currentMap.value.id),
      listCognitiveMapBuildRuns(currentMap.value.id),
      getCognitiveMapEvaluation(currentMap.value.id)
    ])
    files.value = normalizeList(filePayload, ['files', 'items', 'data'])
    entities.value = normalizeList(entityPayload, ['entities', 'items', 'data'])
    relations.value = normalizeList(relationPayload, ['relations', 'items', 'data'])
    evidence.value = normalizeList(evidencePayload, ['evidence', 'items', 'data'])
    buildRuns.value = normalizeList(runsPayload, ['runs', 'items', 'data'])
    evaluation.value = evaluationPayload?.evaluation || null
  } catch (error) {
    files.value = []
    entities.value = []
    relations.value = []
    evidence.value = []
    buildRuns.value = []
    evaluation.value = null
  }
}

const refreshAll = async () => {
  await refreshMaps()
  await refreshCurrentMapData()
}

const selectMap = async (map) => {
  currentMap.value = map
  evaluation.value = map.evaluation || null
  buildRuns.value = map.latest_run ? [map.latest_run] : []
  buildOptions.value.extractorProvider = map.requested_extractor_provider || map.extractor_provider || buildOptions.value.extractorProvider
  buildOptions.value.timeoutSeconds = map.latest_run?.timeout_seconds || buildOptions.value.timeoutSeconds
  buildError.value = ''
  buildMessage.value = ''
  uploadError.value = ''
  await refreshCurrentMapData()
}

const handleCreate = async () => {
  const name = createForm.value.name.trim()
  if (!name) {
    createError.value = '请输入地图名称'
    return
  }
  creating.value = true
  createError.value = ''
  try {
    const created = await createCognitiveMap({
      name,
      description: ''
    })
    createForm.value.name = ''
    await refreshMaps()
    const mapId = created?.id || created?.map?.id
    const selected = maps.value.find(item => item.id === mapId)
    if (selected) await selectMap(selected)
  } catch (error) {
    createError.value = error?.message || '新建认知地图失败'
  } finally {
    creating.value = false
  }
}

const triggerFileInput = () => {
  fileInput.value?.click()
}

const handleFileSelect = async (event) => {
  await uploadFiles(Array.from(event.target.files || []))
  event.target.value = ''
}

const handleDrop = async (event) => {
  isDragging.value = false
  await uploadFiles(Array.from(event.dataTransfer.files || []))
}

const uploadFiles = async (selectedFiles) => {
  if (!currentMap.value?.id || selectedFiles.length === 0) return
  uploading.value = true
  uploadError.value = ''
  buildError.value = ''
  buildMessage.value = ''
  uploadProgress.value = { current: 0, total: selectedFiles.length }
  try {
    for (let index = 0; index < selectedFiles.length; index++) {
      uploadProgress.value.current = index + 1
      await uploadCognitiveMapFile(currentMap.value.id, selectedFiles[index])
    }
    await refreshCurrentMapData()
  } catch (error) {
    uploadError.value = error?.message || '上传文件失败'
  } finally {
    uploading.value = false
    uploadProgress.value = { current: 0, total: 0 }
  }
}

const handleBuild = async () => {
  if (!currentMap.value?.id) return
  if (files.value.length === 0) {
    buildError.value = '请先上传文件，再构建认知地图'
    buildMessage.value = ''
    return
  }
  building.value = true
  buildError.value = ''
  buildMessage.value = ''
  try {
    await buildCognitiveMap(currentMap.value.id, {
      parser_provider: 'auto',
      extractor_provider: buildOptions.value.extractorProvider,
      llm_provider: buildOptions.value.extractorProvider === 'llamaindex' ? 'project' : null,
      timeout_seconds: normalizeTimeoutSeconds(buildOptions.value.timeoutSeconds)
    })
    await refreshCurrentMapData()
    await refreshMaps()
    const engineName = buildOptions.value.extractorProvider === 'llamaindex' ? 'LlamaIndex' : '本地规则'
    buildMessage.value = `${engineName} 构建完成，已更新实体、关系和证据`
  } catch (error) {
    buildError.value = error?.message || '构建认知地图失败'
    await refreshCurrentMapData()
    await refreshMaps()
  } finally {
    building.value = false
  }
}

const normalizeTimeoutSeconds = (value) => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 300
  return Math.min(900, Math.max(30, parsed))
}

const formatDuration = (durationMs) => {
  if (durationMs === null || durationMs === undefined) return '-'
  if (durationMs < 1000) return `${durationMs}ms`
  return `${(durationMs / 1000).toFixed(1)}s`
}

const formatRatio = (value) => {
  if (value === null || value === undefined) return '-'
  return `${Math.round(Number(value) * 100)}%`
}

const formatSeconds = (value) => {
  if (value === null || value === undefined) return '-'
  return `${Number(value)}s`
}

onMounted(refreshMaps)
</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow: hidden;
  padding: 20px;
  background: #fff;
  color: #1f2937;
}

.panel-header,
.section-header,
.detail-header,
.panel-actions,
.tabs,
.summary-grid {
  display: flex;
  align-items: center;
}

.panel-header {
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid #e5e7eb;
}

.panel-header h3,
.detail-header h4 {
  margin: 0;
  font-weight: 600;
}

.panel-header h3 {
  font-size: 18px;
}

.panel-subtitle,
.detail-header p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
}

.panel-actions {
  gap: 8px;
}

.build-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.engine-select {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-size: 12px;
}

.engine-select select,
.engine-select input {
  height: 30px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #fff;
  color: #1f2937;
  font-size: 13px;
}

.engine-select select {
  min-width: 112px;
}

.engine-select input {
  width: 76px;
  padding: 0 8px;
}

.panel-btn,
.primary-btn,
.create-form button,
.tabs button {
  border: 1px solid #2563eb;
  background: #fff;
  color: #2563eb;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.panel-btn,
.primary-btn {
  padding: 6px 12px;
}

.primary-btn,
.create-form button {
  background: #2563eb;
  color: #fff;
}

.panel-btn:disabled,
.primary-btn:disabled,
.create-form button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.service-notice {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
  padding: 10px 12px;
  border: 1px solid #fde68a;
  border-radius: 6px;
  background: #fffbeb;
  color: #92400e;
  font-size: 13px;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 16px;
  height: calc(100% - 76px);
  min-height: 0;
}

.map-list-panel,
.map-detail-panel {
  min-height: 0;
  overflow: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f8fafc;
}

.map-list-panel {
  padding: 12px;
}

.map-detail-panel {
  padding: 16px;
  background: #fff;
}

.section-header {
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
}

.count {
  color: #64748b;
  font-size: 12px;
}

.create-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 68px;
  gap: 8px;
  margin-bottom: 6px;
}

.create-form input {
  min-width: 0;
  padding: 7px 9px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
}

.create-form button {
  padding: 7px 10px;
}

.form-error {
  margin-bottom: 10px;
  color: #dc2626;
  font-size: 12px;
}

.form-success {
  margin-bottom: 10px;
  color: #15803d;
  font-size: 12px;
}

.build-message {
  margin-top: -6px;
}

.map-item {
  width: 100%;
  display: grid;
  gap: 4px;
  margin-bottom: 8px;
  padding: 10px;
  text-align: left;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}

.map-item.active {
  border-color: #2563eb;
  background: #eff6ff;
}

.map-name {
  font-weight: 600;
  color: #111827;
}

.map-meta,
.map-status,
.row-meta {
  color: #64748b;
  font-size: 12px;
}

.empty-detail,
.state-text {
  color: #64748b;
  font-size: 13px;
}

.empty-detail {
  height: 100%;
  display: grid;
  place-items: center;
}

.detail-header {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.run-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.run-summary-item {
  display: grid;
  gap: 4px;
  padding: 8px 10px;
  border: 1px solid #dbeafe;
  border-radius: 6px;
  background: #eff6ff;
}

.run-value {
  color: #1e3a8a;
  font-size: 13px;
  font-weight: 600;
}

.summary-item {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f8fafc;
}

.summary-value {
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.summary-label {
  color: #64748b;
  font-size: 12px;
}

.upload-area {
  display: grid;
  place-items: center;
  min-height: 86px;
  margin-bottom: 14px;
  border: 1px dashed #94a3b8;
  border-radius: 6px;
  background: #f8fafc;
  color: #334155;
  cursor: pointer;
}

.upload-area.dragging {
  border-color: #2563eb;
  background: #eff6ff;
}

.upload-area input {
  display: none;
}

.tabs {
  gap: 8px;
  margin-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.tabs button {
  padding: 8px 10px;
  border: 0;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  background: transparent;
  color: #475569;
}

.tabs button.active {
  border-bottom-color: #2563eb;
  color: #1d4ed8;
}

.data-section {
  display: grid;
  gap: 8px;
}

.data-row,
.evidence-row {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
}

.data-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.row-title {
  min-width: 0;
  color: #111827;
  font-size: 13px;
  font-weight: 500;
}

.evidence-row p {
  margin: 6px 0 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}

@media (max-width: 920px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
