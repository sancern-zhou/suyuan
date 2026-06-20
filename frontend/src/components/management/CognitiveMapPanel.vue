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
      <span>当前页面已接入认知地图接口，等待后端服务可用后即可显示真实数据。</span>
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
          <div class="detail-header compact-header">
            <div>
              <h4>{{ currentMap.name }}</h4>
              <p v-if="currentMap.description">{{ currentMap.description }}</p>
            </div>
            <div class="build-actions">
              <label class="engine-select">
                <span>抽取引擎</span>
                <select v-model="buildOptions.extractorProvider" :disabled="building">
                  <option value="local">本地规则</option>
                  <option value="llamaindex">开源图谱引擎</option>
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
          <div v-if="latestRun?.error || currentMap.build_error" class="form-error">
            {{ formatError(latestRun?.error || currentMap.build_error) }}
          </div>

          <div class="workspace-toolbar">
            <div class="metric-strip">
              <span class="metric-pill">文件 {{ files.length }}</span>
              <span class="metric-pill">实体 {{ entities.length }}</span>
              <span class="metric-pill">关系 {{ relations.length }}</span>
              <span class="metric-pill">证据 {{ evidence.length }}</span>
              <span class="metric-pill">状态 {{ getStatusText(latestRun?.status || currentMap.status) }}</span>
              <span class="metric-pill">覆盖 {{ formatRatio(evaluation?.entity_evidence_ratio) }}</span>
            </div>
            <button
              class="panel-btn compact-upload"
              :class="{ dragging: isDragging }"
              type="button"
              @click="triggerFileInput"
              :disabled="uploading"
              @dragover.prevent="isDragging = true"
              @dragleave="isDragging = false"
              @drop.prevent="handleDrop"
            >
              {{ uploading ? `上传中 ${uploadProgress.current}/${uploadProgress.total}` : '上传文件' }}
            </button>
            <input
              ref="fileInput"
              class="hidden-file-input"
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.html,.htm,.txt,.md,.csv,.json"
              @change="handleFileSelect"
            />
          </div>
          <div
            class="drop-strip"
            :class="{ dragging: isDragging }"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @drop.prevent="handleDrop"
          >
            可将文件拖到此处补充地图语料
          </div>
          <div v-if="uploadError" class="form-error">{{ uploadError }}</div>

          <div class="workbench-layout">
            <section class="graph-workspace">
              <div class="graph-toolbar">
                <div class="graph-legend">
                  <button
                    v-for="category in graphCategories"
                    :key="category.rawName"
                    class="legend-item"
                    :class="{ muted: isEntityTypeHidden(category.rawName) }"
                    type="button"
                    @click="toggleEntityType(category.rawName)"
                  >
                    <i :style="{ backgroundColor: category.itemStyle.color }"></i>
                    {{ category.name }}
                  </button>
                </div>
                <div class="graph-toolbar-actions">
                  <button class="panel-btn" type="button" @click="clearGraphFilters">显示全部</button>
                  <button class="panel-btn" type="button" @click="fitGraph">适配视图</button>
                </div>
              </div>
              <div v-if="relationTypes.length" class="relation-filter">
                <button
                  v-for="type in relationTypes"
                  :key="type"
                  type="button"
                  :class="{ muted: isRelationTypeHidden(type) }"
                  @click="toggleRelationType(type)"
                >
                  {{ formatRelationType(type) }}
                </button>
              </div>
              <div v-if="entities.length === 0" class="graph-empty-state">
                暂无可视化数据，请先上传文件并构建地图
              </div>
              <div v-else-if="graphNodes.length === 0" class="graph-empty-state">
                当前筛选条件下暂无节点
              </div>
              <div ref="graphContainer" class="graph-canvas"></div>
            </section>

            <aside class="inspector-panel">
              <div class="inspector-tabs">
                <button
                  v-for="tab in inspectorTabs"
                  :key="tab.id"
                  type="button"
                  :class="{ active: inspectorTab === tab.id }"
                  @click="inspectorTab = tab.id"
                >
                  {{ tab.name }}
                </button>
              </div>

              <section v-if="inspectorTab === 'selection'" class="inspector-section">
                <template v-if="selectedGraphItem">
                  <div class="selection-title">{{ selectedGraphTitle }}</div>
                  <div class="selection-meta">{{ selectedGraphMeta }}</div>
                  <p v-if="selectedGraphDescription" class="selection-description">
                    {{ selectedGraphDescription }}
                  </p>
                  <div class="detail-grid">
                    <div class="detail-field">
                      <span>证据数</span>
                      <strong>{{ selectedGraphEvidence.length }}</strong>
                    </div>
                    <div class="detail-field">
                      <span>审核状态</span>
                      <strong>{{ selectedReviewStatus }}</strong>
                    </div>
                  </div>
                  <div class="inspector-subtitle">关联证据</div>
                  <div v-if="selectedGraphEvidence.length" class="compact-list">
                    <div
                      v-for="item in selectedGraphEvidence"
                      :key="item.evidence_id || item.id || item.chunk_id"
                      class="compact-row evidence-compact-row"
                    >
                      {{ item.text_span || item.normalized_summary || item.text || item.content || item.quote }}
                    </div>
                  </div>
                  <div v-else class="state-text">暂无关联证据</div>
                </template>
                <template v-else>
                  <div class="selection-empty">点击图谱中的实体或关系查看详情</div>
                  <div class="detail-grid">
                    <div class="detail-field">
                      <span>抽取引擎</span>
                      <strong>{{ formatProvider(latestRun?.extractor_provider || currentMap.extractor_provider) }}</strong>
                    </div>
                    <div class="detail-field">
                      <span>耗时</span>
                      <strong>{{ formatDuration(latestRun?.duration_ms) }}</strong>
                    </div>
                    <div class="detail-field">
                      <span>分块</span>
                      <strong>{{ latestRun?.chunk_count ?? '-' }}</strong>
                    </div>
                    <div class="detail-field">
                      <span>超时</span>
                      <strong>{{ formatSeconds(latestRun?.timeout_seconds || buildOptions.timeoutSeconds) }}</strong>
                    </div>
                  </div>
                </template>
              </section>

              <section v-else-if="inspectorTab === 'entities'" class="inspector-section">
                <div v-if="entities.length === 0" class="state-text">暂无实体</div>
                <div v-else class="compact-list">
                  <button
                    v-for="entity in entities"
                    :key="entity.entity_id || entity.id || entity.name"
                    class="compact-row selectable-row"
                    type="button"
                    @click="selectEntity(entity)"
                  >
                    <span class="row-title">{{ entity.name }}</span>
                    <span class="row-meta">{{ formatEntityType(entity.type || entity.entity_type) }}</span>
                  </button>
                </div>
              </section>

              <section v-else-if="inspectorTab === 'relations'" class="inspector-section">
                <div v-if="relations.length === 0" class="state-text">暂无关系</div>
                <div v-else class="compact-list">
                  <button
                    v-for="relation in relations"
                    :key="relation.relation_id || relation.id || relation.key"
                    class="compact-row selectable-row"
                    type="button"
                    @click="selectRelation(relation)"
                  >
                    <span class="row-title">
                      {{ relation.source_name || relation.source }} 到 {{ relation.target_name || relation.target }}
                    </span>
                    <span class="row-meta">{{ formatRelationType(relation.type || relation.relation_type) }}</span>
                  </button>
                </div>
              </section>

              <section v-else-if="inspectorTab === 'evidence'" class="inspector-section">
                <div v-if="evidence.length === 0" class="state-text">暂无证据</div>
                <div v-else class="compact-list">
                  <div
                    v-for="item in evidence"
                    :key="item.evidence_id || item.id || item.chunk_id"
                    class="compact-row evidence-compact-row"
                  >
                    <strong>{{ item.title || item.source || '证据片段' }}</strong>
                    {{ item.text_span || item.normalized_summary || item.text || item.content || item.quote }}
                  </div>
                </div>
              </section>

              <section v-else class="inspector-section">
                <div v-if="files.length === 0" class="state-text">暂无文件</div>
                <div v-else class="compact-list">
                  <div
                    v-for="file in files"
                    :key="file.file_id || file.id || file.filename"
                    class="compact-row"
                  >
                    <span class="row-title">{{ file.filename || file.name }}</span>
                    <span class="row-meta">{{ getStatusText(file.status) }}</span>
                  </div>
                </div>
              </section>
            </aside>
          </div>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
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
const graphContainer = ref(null)
const uploadProgress = ref({ current: 0, total: 0 })
const maps = ref([])
const currentMap = ref(null)
const files = ref([])
const entities = ref([])
const relations = ref([])
const evidence = ref([])
const buildRuns = ref([])
const evaluation = ref(null)
const graphChart = ref(null)
const selectedGraphItem = ref(null)
const hiddenEntityTypes = ref([])
const hiddenRelationTypes = ref([])
const inspectorTab = ref('selection')
const createForm = ref({ name: '' })
const createError = ref('')
const uploadError = ref('')
const buildError = ref('')
const buildMessage = ref('')
const buildOptions = ref({
  extractorProvider: 'local',
  timeoutSeconds: 300
})

const inspectorTabs = computed(() => [
  { id: 'selection', name: '选择' },
  { id: 'entities', name: `实体 ${entities.value.length}` },
  { id: 'relations', name: `关系 ${relations.value.length}` },
  { id: 'evidence', name: `证据 ${evidence.value.length}` },
  { id: 'files', name: `文件 ${files.value.length}` }
])

const latestRun = computed(() => buildRuns.value[0] || currentMap.value?.latest_run || null)
const canRetryBuild = computed(() => currentMap.value?.status === 'failed' || latestRun.value?.status === 'failed')

const providerLabels = {
  local: '本地规则',
  llamaindex: '开源图谱引擎',
  llamaindex_property_graph: '开源图谱引擎',
  project: '项目模型'
}

const entityTypeLabels = {
  Station: '监测站',
  Pollutant: '污染物',
  Metric: '指标',
  TimeWindow: '时间窗口',
  Region: '区域',
  DataSource: '数据源',
  AnalysisMethod: '分析方法',
  EmissionSource: '排放源',
  ProcessMechanism: '过程机理',
  ControlMeasure: '管控措施',
  StandardRule: '标准规则',
  Finding: '发现',
  Hypothesis: '假设',
  Dataset: '数据集',
  Tool: '工具',
  AgentRole: '智能体角色',
  Entity: '实体'
}

const relationTypeLabels = {
  located_in: '位于',
  measures: '监测',
  has_alias: '别名',
  belongs_to_category: '属于类别',
  affects: '影响',
  indicates: '指示',
  supports: '支持',
  contradicts: '矛盾',
  requires_data: '需要数据',
  derived_from: '来源于',
  regulated_by: '受规则约束',
  applies_to: '适用于',
  produces: '产生',
  consumes: '消耗',
  uses_method: '使用方法',
  has_limitation: '存在限制',
  handled_by_agent: '由智能体处理',
  related_to: '相关'
}

const graphPalette = [
  '#2563eb',
  '#16a34a',
  '#dc2626',
  '#9333ea',
  '#ea580c',
  '#0891b2',
  '#4f46e5',
  '#64748b'
]

const graphCategories = computed(() => {
  const types = Array.from(new Set(entities.value.map(entity => entity.entity_type || entity.type || '未分类')))
  return types.map((type, index) => ({
    name: formatEntityType(type),
    rawName: type,
    itemStyle: {
      color: graphPalette[index % graphPalette.length]
    }
  }))
})

const relationTypes = computed(() => (
  Array.from(new Set(relations.value.map(relation => relation.relation_type || relation.type || 'related_to')))
))

const evidenceById = computed(() => {
  const index = new Map()
  evidence.value.forEach(item => {
    const id = item.evidence_id || item.id
    if (id) index.set(id, item)
  })
  return index
})

const graphNodes = computed(() => {
  const categoryIndex = new Map(graphCategories.value.map((category, index) => [category.rawName, index]))
  return entities.value
    .filter(entity => !isEntityTypeHidden(entity.entity_type || entity.type || '未分类'))
    .map(entity => {
      const type = entity.entity_type || entity.type || '未分类'
      const evidenceCount = entity.source_evidence_ids?.length || 0
      return {
        id: entity.entity_id || entity.id || `${type}:${entity.name}`,
        name: entity.name,
        value: evidenceCount,
        category: categoryIndex.get(type) || 0,
        symbolSize: Math.max(34, Math.min(62, 34 + evidenceCount * 6)),
        raw: entity,
        label: {
          show: true,
          formatter: '{b}'
        }
      }
    })
})

const graphLinks = computed(() => {
  const nodeIds = new Set(graphNodes.value.map(node => node.id))
  return relations.value
    .map(relation => {
      const type = relation.relation_type || relation.type || 'related_to'
      if (isRelationTypeHidden(type)) return null
      const source = relation.source_entity_id || relation.source || relation.source_id
      const target = relation.target_entity_id || relation.target || relation.target_id
      if (!nodeIds.has(source) || !nodeIds.has(target)) return null
      return {
        source,
        target,
        value: type,
        raw: relation,
        label: {
          show: true,
          formatter: formatRelationType(type)
        },
        lineStyle: {
          width: 1.5,
          opacity: 0.62
        }
      }
    })
    .filter(Boolean)
})

const graphOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: (params) => {
      if (params.dataType === 'edge') {
        const raw = params.data.raw || {}
        return `${raw.source_name || params.data.source} 到 ${raw.target_name || params.data.target}<br/>关系：${formatRelationType(params.data.value)}<br/>证据：${raw.source_evidence_ids?.length || 0}`
      }
      const raw = params.data.raw || {}
      return `${raw.name || params.name}<br/>类型：${formatEntityType(raw.entity_type || raw.type)}<br/>证据：${raw.source_evidence_ids?.length || 0}`
    }
  },
  legend: {
    show: false
  },
  series: [
    {
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      categories: graphCategories.value,
      data: graphNodes.value,
      links: graphLinks.value,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      force: {
        repulsion: 220,
        gravity: 0.08,
        edgeLength: [80, 150],
        friction: 0.35
      },
      label: {
        color: '#111827',
        fontSize: 11,
        overflow: 'truncate',
        width: 86
      },
      edgeLabel: {
        color: '#475569',
        fontSize: 10
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: {
          width: 3
        }
      }
    }
  ]
}))

const selectedGraphTitle = computed(() => {
  if (!selectedGraphItem.value) return ''
  const raw = selectedGraphItem.value.raw || {}
  if (selectedGraphItem.value.kind === 'relation') {
    return `${raw.source_name || raw.source || raw.source_entity_id} 到 ${raw.target_name || raw.target || raw.target_entity_id}`
  }
  return raw.name || ''
})

const selectedGraphMeta = computed(() => {
  if (!selectedGraphItem.value) return ''
  const raw = selectedGraphItem.value.raw || {}
  return selectedGraphItem.value.kind === 'relation'
    ? formatRelationType(raw.relation_type || raw.type)
    : formatEntityType(raw.entity_type || raw.type)
})

const selectedGraphDescription = computed(() => {
  const raw = selectedGraphItem.value?.raw || {}
  return raw.description || ''
})

const selectedGraphEvidence = computed(() => {
  const evidenceIds = selectedGraphItem.value?.raw?.source_evidence_ids || []
  return evidenceIds.map(id => evidenceById.value.get(id)).filter(Boolean)
})

const selectedReviewStatus = computed(() => (
  getReviewStatusText(selectedGraphItem.value?.raw?.review_status)
))

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

const formatProvider = (provider) => providerLabels[provider] || provider || '未构建'

const formatEntityType = (type) => entityTypeLabels[type] || type || '未分类'

const formatRelationType = (type) => relationTypeLabels[type] || type || '相关'

const getReviewStatusText = (status) => {
  const map = {
    pending: '待审核',
    approved: '已确认',
    rejected: '已驳回',
    modified: '已修正'
  }
  return map[status] || status || '未审核'
}

const formatError = (message) => {
  if (!message) return ''
  return String(message)
    .replace(/^Failed to build cognitive map:\s*/i, '构建认知地图失败：')
    .replace(/Cognitive map extraction timed out after ([\d.]+) seconds/gi, '认知地图抽取超过 $1 秒')
    .replace(/Cognitive map stale building state exceeded ([\d.]+) seconds/gi, '认知地图构建状态超过 $1 秒未更新')
    .replace(/llamaindex unavailable/gi, '开源图谱引擎不可用')
    .replace(/No files uploaded for cognitive map/gi, '请先上传文件')
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
  await renderGraph()
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
  selectedGraphItem.value = null
  inspectorTab.value = 'selection'
  clearGraphFilters()
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
    const engineName = formatProvider(buildOptions.value.extractorProvider)
    buildMessage.value = `${engineName} 构建完成，已更新实体、关系和证据`
  } catch (error) {
    buildError.value = formatError(error?.message || '构建认知地图失败')
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
  if (durationMs < 1000) return `${durationMs}毫秒`
  return `${(durationMs / 1000).toFixed(1)}秒`
}

const formatRatio = (value) => {
  if (value === null || value === undefined) return '-'
  return `${Math.round(Number(value) * 100)}%`
}

const formatSeconds = (value) => {
  if (value === null || value === undefined) return '-'
  return `${Number(value)}秒`
}

const isEntityTypeHidden = (type) => hiddenEntityTypes.value.includes(type)

const isRelationTypeHidden = (type) => hiddenRelationTypes.value.includes(type)

const toggleEntityType = (type) => {
  hiddenEntityTypes.value = isEntityTypeHidden(type)
    ? hiddenEntityTypes.value.filter(item => item !== type)
    : [...hiddenEntityTypes.value, type]
}

const toggleRelationType = (type) => {
  hiddenRelationTypes.value = isRelationTypeHidden(type)
    ? hiddenRelationTypes.value.filter(item => item !== type)
    : [...hiddenRelationTypes.value, type]
}

const clearGraphFilters = () => {
  hiddenEntityTypes.value = []
  hiddenRelationTypes.value = []
}

const selectEntity = (entity) => {
  selectedGraphItem.value = { kind: 'entity', raw: entity }
  inspectorTab.value = 'selection'
}

const selectRelation = (relation) => {
  selectedGraphItem.value = { kind: 'relation', raw: relation }
  inspectorTab.value = 'selection'
}

const renderGraph = async () => {
  await nextTick()
  if (!graphContainer.value) return
  if (!graphChart.value) {
    graphChart.value = echarts.init(graphContainer.value)
    graphChart.value.on('click', (params) => {
      if (params.dataType === 'node') {
        selectEntity(params.data.raw || {})
      } else if (params.dataType === 'edge') {
        selectRelation(params.data.raw || {})
      }
    })
  }
  graphChart.value.setOption(graphOption.value, true)
  graphChart.value.resize()
}

const fitGraph = async () => {
  await renderGraph()
}

const handleResize = () => {
  graphChart.value?.resize()
}

watch([entities, relations], async () => {
  await renderGraph()
})

watch([hiddenEntityTypes, hiddenRelationTypes], async () => {
  selectedGraphItem.value = null
  await renderGraph()
})

onMounted(() => {
  window.addEventListener('resize', handleResize)
  refreshMaps()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  graphChart.value?.dispose()
  graphChart.value = null
})
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
.panel-actions {
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
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 14px;
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
  margin-bottom: 10px;
}

.compact-header {
  flex: 0 0 auto;
}

.workspace-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex: 0 0 auto;
  margin-bottom: 8px;
}

.metric-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.metric-pill {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 8px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  white-space: nowrap;
}

.compact-upload {
  flex: 0 0 auto;
}

.compact-upload.dragging {
  border-color: #16a34a;
  color: #15803d;
}

.hidden-file-input {
  display: none;
}

.drop-strip {
  flex: 0 0 auto;
  margin-bottom: 10px;
  padding: 6px 10px;
  border: 1px dashed #cbd5e1;
  border-radius: 4px;
  background: #f8fafc;
  color: #64748b;
  font-size: 12px;
}

.drop-strip.dragging {
  border-color: #16a34a;
  background: #f0fdf4;
  color: #166534;
}

.workbench-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 12px;
  flex: 1 1 auto;
  min-height: 0;
}

.graph-workspace {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 10px;
  min-height: 0;
}

.graph-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.graph-toolbar-actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}

.graph-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  min-width: 0;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #475569;
  cursor: pointer;
  font-size: 12px;
}

.legend-item i {
  width: 9px;
  height: 9px;
  flex: 0 0 auto;
  border-radius: 50%;
}

.legend-item.muted,
.relation-filter button.muted {
  opacity: 0.38;
  text-decoration: line-through;
}

.relation-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.relation-filter button {
  padding: 4px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: #fff;
  color: #475569;
  cursor: pointer;
  font-size: 12px;
}

.graph-canvas {
  width: 100%;
  height: 100%;
  min-height: 520px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f8fafc;
}

.graph-empty-state {
  display: grid;
  place-items: center;
  min-height: 72px;
  border: 1px dashed #cbd5e1;
  border-radius: 6px;
  background: #f8fafc;
  color: #64748b;
  font-size: 13px;
}

.inspector-panel {
  min-height: 0;
  overflow: auto;
  padding: 10px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
}

.inspector-tabs {
  display: flex;
  gap: 4px;
  position: sticky;
  top: 0;
  z-index: 1;
  margin: -10px -10px 10px;
  padding: 10px 10px 8px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
  overflow-x: auto;
}

.inspector-tabs button {
  flex: 0 0 auto;
  padding: 5px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: #475569;
  cursor: pointer;
  font-size: 12px;
}

.inspector-tabs button.active {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}

.inspector-section,
.compact-list {
  display: grid;
  gap: 8px;
}

.selection-title {
  color: #111827;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
}

.selection-meta,
.selection-description {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}

.selection-empty {
  padding: 10px;
  border: 1px dashed #cbd5e1;
  border-radius: 6px;
  color: #64748b;
  font-size: 13px;
  text-align: center;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.detail-field {
  display: grid;
  gap: 4px;
  padding: 8px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #f8fafc;
}

.detail-field span,
.inspector-subtitle {
  color: #64748b;
  font-size: 12px;
}

.detail-field strong {
  min-width: 0;
  color: #111827;
  font-size: 13px;
  font-weight: 600;
  word-break: break-word;
}

.inspector-subtitle {
  margin-top: 4px;
  font-weight: 600;
}

.compact-row {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #fff;
  text-align: left;
}

.selectable-row {
  cursor: pointer;
}

.selectable-row:hover {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.evidence-compact-row {
  color: #475569;
  font-size: 12px;
  line-height: 1.55;
  word-break: break-word;
}

.evidence-compact-row strong {
  display: block;
  margin-bottom: 3px;
  color: #111827;
}

.row-title {
  min-width: 0;
  color: #111827;
  font-size: 13px;
  font-weight: 500;
  word-break: break-word;
}

@media (max-width: 920px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .workbench-layout {
    grid-template-columns: 1fr;
  }

  .graph-canvas {
    height: 420px;
    min-height: 420px;
  }
}
</style>
