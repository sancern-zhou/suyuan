<template>
  <div class="management-panel cognitive-map-panel">
    <div v-if="apiUnavailable" class="service-notice">
      <strong>后端接口未就绪</strong>
      <span>当前页面已接入认知地图接口，等待后端服务可用后即可显示真实数据。</span>
    </div>

    <div class="content-grid">
      <aside class="map-list-panel">
        <div class="map-list-actions">
          <button
            class="rail-btn"
            type="button"
            :aria-expanded="isMapListExpanded"
            @click="toggleMapList"
          >
            地图列表
          </button>
          <button
            class="add-map-btn"
            type="button"
            aria-label="新建地图"
            @click="toggleCreateMap"
          >
            +
          </button>
        </div>

        <div v-if="isMapListExpanded" class="map-list-dropdown">
          <template v-if="isCreateMapExpanded">
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
          </template>

          <template v-else>
            <div v-if="loading" class="state-text">加载中...</div>
            <div v-else-if="maps.length === 0" class="state-text">暂无认知地图</div>
            <div
              v-for="map in maps"
              v-else
              :key="map.id"
              class="map-item-row"
              :class="{ active: currentMap?.id === map.id }"
            >
              <button
                class="map-item"
                type="button"
                @click="selectMap(map)"
              >
                <span class="map-name">{{ map.name }}</span>
                <span class="map-meta">
                  {{ map.entity_count || 0 }} 实体 / {{ map.relation_count || 0 }} 关系
                </span>
                <span
                  class="map-status-dot"
                  :class="`status-${map.status || 'unknown'}`"
                  :title="getStatusText(map.status)"
                  :aria-label="getStatusText(map.status)"
                ></span>
              </button>
            </div>
          </template>
        </div>
      </aside>

      <main class="map-detail-panel">
        <div v-if="!currentMap" class="empty-detail">
          选择或新建认知地图
        </div>

        <template v-else>
          <div class="detail-header compact-header">
            <button class="panel-btn action-toggle" type="button" @click="openManagementDrawer('selection')">
              管理
            </button>
          </div>

          <div v-if="buildError" class="form-error build-message">{{ buildError }}</div>
          <div v-else-if="buildMessage" class="form-success build-message">{{ buildMessage }}</div>
          <div v-if="mapActionError" class="form-error build-message">{{ mapActionError }}</div>
          <div v-if="latestRun?.error || currentMap.build_error" class="form-error">
            {{ formatError(latestRun?.error || currentMap.build_error) }}
          </div>

          <input
            ref="fileInput"
            class="hidden-file-input"
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.html,.htm,.txt,.md,.csv,.json"
            @change="handleFileSelect"
          />
          <div
            v-if="isUploadDropExpanded || isDragging"
            class="drop-strip"
            :class="{ dragging: isDragging }"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @drop.prevent="handleDrop"
          >
            可将文件拖到此处补充地图语料
          </div>
          <div v-if="uploadError" class="form-error">{{ uploadError }}</div>

          <div class="workbench-layout" :class="{ 'drawer-open': isInspectorExpanded }">
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

            <aside v-if="isInspectorExpanded" class="management-drawer">
              <div class="drawer-header">
                <div>
                  <strong>{{ currentMap.name || '认知地图' }}</strong>
                  <span>{{ entities.length }} 个实体 / {{ relations.length }} 条关系</span>
                </div>
                <button class="panel-btn" type="button" @click="closeManagementDrawer">关闭</button>
              </div>

              <div class="drawer-body">
                <nav class="drawer-tree" aria-label="认知地图管理树">
                  <button
                    class="tree-node root-node"
                    type="button"
                    :class="{ active: inspectorTab === 'selection' && !selectedGraphItem }"
                    @click="showMapOverview"
                  >
                    {{ currentMap.name || '当前地图' }}
                  </button>
                  <button
                    class="tree-node"
                    type="button"
                    :class="{ active: inspectorTab === 'build' }"
                    @click="openManagementDrawer('build')"
                  >
                    构建与文件
                  </button>
                  <button
                    class="tree-node"
                    type="button"
                    :class="{ active: inspectorTab === 'binding' }"
                    @click="openManagementDrawer('binding')"
                  >
                    Agent接入
                  </button>

                  <div class="tree-group">
                    <button
                      class="tree-node group-node"
                      type="button"
                      :class="{ active: inspectorTab === 'entities' && !selectedGraphItem }"
                      @click="openManagementDrawer('entities')"
                    >
                      实体
                      <span>{{ entities.length }}</span>
                    </button>
                    <div
                      v-for="group in entityTreeGroups"
                      :key="group.type"
                      class="tree-children"
                    >
                      <div class="tree-label">{{ formatEntityType(group.type) }}</div>
                      <button
                        v-for="entity in group.items"
                        :key="entity.entity_id || entity.id || entity.name"
                        class="tree-node leaf-node"
                        type="button"
                        :class="{ active: isSelectedTreeItem('entity', entity) }"
                        @click="selectEntity(entity)"
                      >
                        {{ entity.name || '未命名实体' }}
                      </button>
                    </div>
                  </div>

                  <div class="tree-group">
                    <button
                      class="tree-node group-node"
                      type="button"
                      :class="{ active: inspectorTab === 'relations' && !selectedGraphItem }"
                      @click="openManagementDrawer('relations')"
                    >
                      关系
                      <span>{{ relations.length }}</span>
                    </button>
                    <div
                      v-for="group in relationTreeGroups"
                      :key="group.type"
                      class="tree-children"
                    >
                      <div class="tree-label">{{ formatRelationType(group.type) }}</div>
                      <button
                        v-for="relation in group.items"
                        :key="relation.relation_id || relation.id || relation.key"
                        class="tree-node leaf-node"
                        type="button"
                        :class="{ active: isSelectedTreeItem('relation', relation) }"
                        @click="selectRelation(relation)"
                      >
                        {{ relation.source_name || relation.source }} 到 {{ relation.target_name || relation.target }}
                      </button>
                    </div>
                  </div>

                  <button
                    class="tree-node"
                    type="button"
                    :class="{ active: inspectorTab === 'evidence' }"
                    @click="openManagementDrawer('evidence')"
                  >
                    证据
                    <span>{{ evidence.length }}</span>
                  </button>
                  <button
                    class="tree-node"
                    type="button"
                    :class="{ active: inspectorTab === 'files' }"
                    @click="openManagementDrawer('files')"
                  >
                    文件
                    <span>{{ files.length }}</span>
                  </button>
                </nav>

                <div class="drawer-detail">
                  <section v-if="inspectorTab === 'selection'" class="inspector-section">
                    <template v-if="selectedGraphItem">
                      <div class="selection-title">{{ selectedGraphTitle }}</div>
                      <div class="selection-meta">{{ selectedGraphMeta }}</div>

                      <div class="detail-grid">
                        <div class="detail-field">
                          <span>{{ selectedGraphItem.kind === 'relation' ? '图关系' : '图节点' }}</span>
                          <strong>
                            {{ selectedGraphItem.kind === 'relation'
                              ? formatRelationType(selectedGraphItem.raw?.relation_type || selectedGraphItem.raw?.type)
                              : formatEntityType(selectedGraphItem.raw?.entity_type || selectedGraphItem.raw?.type) }}
                          </strong>
                        </div>
                        <div class="detail-field">
                          <span>证据数</span>
                          <strong>{{ selectedGraphEvidence.length }}</strong>
                        </div>
                        <div class="detail-field">
                          <span>审核状态</span>
                          <strong>{{ selectedReviewStatus }}</strong>
                        </div>
                      </div>
                      <div class="review-actions">
                        <span class="state-text">当前详情来自 Property Graph，节点与关系保持只读。</span>
                      </div>
                      <div class="inspector-subtitle">关联证据</div>
                      <div v-if="selectedGraphEvidence.length" class="compact-list">
                        <div
                          v-for="item in selectedGraphEvidence"
                          :key="item.evidence_id || item.id || item.chunk_id"
                          class="compact-row evidence-compact-row"
                          role="button"
                          tabindex="0"
                          @click="loadEvidenceDetail(item)"
                          @keydown.enter.prevent="loadEvidenceDetail(item)"
                        >
                          {{ item.summary || item.normalized_summary || item.quote || item.text || item.content || item.text_span }}
                        </div>
                      </div>
                      <div v-else class="state-text">暂无关联证据</div>
                    </template>
                    <template v-else>
                      <div class="selection-title">{{ currentMap.name || '认知地图' }}</div>
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
                        <div class="detail-field">
                          <span>图结构</span>
                          <strong>{{ graphSourceText }}</strong>
                        </div>
                        <div v-if="latestRun?.build_requirement || currentMap.build_requirement" class="detail-field build-requirement-field">
                          <span>构建需求</span>
                          <strong>{{ latestRun?.build_requirement || currentMap.build_requirement }}</strong>
                        </div>
                      </div>
                    </template>
                    <div v-if="managementError" class="form-error">{{ managementError }}</div>
                    <div v-else-if="managementMessage" class="form-success">{{ managementMessage }}</div>
                  </section>

                  <section v-else-if="inspectorTab === 'build'" class="inspector-section">
                    <div class="selection-title">构建与文件</div>
                    <div class="build-actions inline-actions">
                      <label class="engine-select">
                        <span>抽取引擎</span>
                        <select v-model="buildOptions.extractorProvider" :disabled="building">
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
                      <label class="build-requirement-input">
                        <span>构建需求</span>
                        <textarea
                          v-model="buildOptions.buildRequirement"
                          :disabled="building"
                          rows="3"
                          placeholder="例如：用于运维模式，根据站点故障工单、告警和监测数据关系，辅助分析故障原因。"
                        ></textarea>
                      </label>
                      <button class="primary-btn" type="button" @click="handleBuild" :disabled="building">
                        {{ building ? '构建中...' : '构建地图' }}
                      </button>
                      <button v-if="canRetryBuild" class="panel-btn" type="button" @click="handleBuild" :disabled="building">
                        重试
                      </button>
                      <button
                        class="panel-btn"
                        type="button"
                        :disabled="publishingMap || building || (entities.length === 0 && relations.length === 0)"
                        @click="handlePublishMap"
                      >
                        {{ publishingMap ? '发布中' : '确认并发布' }}
                      </button>
                    </div>
                    <div class="review-actions">
                      <button class="panel-btn compact-upload" type="button" @click="triggerFileInput" :disabled="uploading">
                        {{ uploading ? `上传中 ${uploadProgress.current}/${uploadProgress.total}` : '上传文件' }}
                      </button>
                      <button class="panel-btn" type="button" @click="toggleUploadDrop">
                        {{ isUploadDropExpanded ? '收起拖拽' : '拖拽上传' }}
                      </button>
                      <button class="panel-btn danger-action" type="button" :disabled="deletingMap" @click="handleDeleteMap()">
                        {{ deletingMap ? '删除中' : '删除地图' }}
                      </button>
                    </div>
                    <div v-if="managementError" class="form-error">{{ managementError }}</div>
                    <div v-else-if="managementMessage" class="form-success">{{ managementMessage }}</div>
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

                  <section v-else-if="inspectorTab === 'binding'" class="inspector-section">
                    <div class="selection-title">Agent接入</div>
                    <div class="mode-binding-options">
                      <label
                        v-for="mode in agentModeOptions"
                        :key="mode.id"
                        class="mode-binding-option"
                      >
                        <input
                          v-model="bindingForm.agentModes"
                          type="checkbox"
                          :value="mode.id"
                          :disabled="savingBindings"
                        />
                        <span>{{ mode.name }}</span>
                      </label>
                    </div>
                    <button class="primary-btn" type="button" :disabled="savingBindings" @click="saveModeBindings">
                      {{ savingBindings ? '保存中' : '保存接入' }}
                    </button>
                    <div v-if="bindingError" class="form-error">{{ bindingError }}</div>
                    <div v-else-if="bindingMessage" class="form-success">{{ bindingMessage }}</div>
                  </section>

                  <section v-else-if="inspectorTab === 'entities'" class="inspector-section">
                    <div class="selection-title">实体</div>
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
                    <div class="selection-title">关系</div>
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
                    <div class="selection-title">证据</div>
                    <div v-if="evidence.length === 0" class="state-text">暂无证据</div>
                    <div v-else class="compact-list">
                      <div
                        v-for="item in evidence"
                        :key="item.evidence_id || item.id || item.chunk_id"
                        class="compact-row evidence-compact-row"
                        role="button"
                        tabindex="0"
                        @click="loadEvidenceDetail(item)"
                        @keydown.enter.prevent="loadEvidenceDetail(item)"
                      >
                        <strong>{{ item.title || item.source || '证据片段' }}</strong>
                        {{ item.summary || item.normalized_summary || item.quote || item.text || item.content || item.text_span }}
                      </div>
                    </div>
                    <div v-if="evidenceDetailError" class="form-error">{{ evidenceDetailError }}</div>
                    <div v-if="selectedEvidenceDetail" class="evidence-detail">
                      <strong>{{ selectedEvidenceDetail.location || selectedEvidenceDetail.evidence_id }}</strong>
                      <p>{{ selectedEvidenceDetail.text_span || selectedEvidenceDetail.normalized_summary }}</p>
                    </div>
                  </section>

                  <section v-else class="inspector-section">
                    <div class="selection-title">文件</div>
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
                </div>
              </div>
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
import { collectSettledRefreshPayloads } from '@/utils/cognitiveMapRefresh'
import {
  buildCognitiveMap,
  createCognitiveMap,
  deleteCognitiveMap,
  getCognitiveMapEvaluation,
  getCognitiveMapEvidenceDetail,
  getCognitiveMapBindings,
  listCognitiveMapBuildRuns,
  listCognitiveMapFiles,
  listCognitiveMaps,
  publishCognitiveMap,
  queryCognitiveMapGraph,
  updateCognitiveMapBindings,
  uploadCognitiveMapFile
} from '@/api/cognitiveMap'

defineEmits(['close'])

const loading = ref(false)
const creating = ref(false)
const building = ref(false)
const uploading = ref(false)
const deletingMap = ref(false)
const savingBindings = ref(false)
const publishingMap = ref(false)
const apiUnavailable = ref(false)
const isDragging = ref(false)
const isMapListExpanded = ref(false)
const isInspectorExpanded = ref(false)
const isUploadDropExpanded = ref(false)
const isCreateMapExpanded = ref(false)
const fileInput = ref(null)
const graphContainer = ref(null)
const uploadProgress = ref({ current: 0, total: 0 })
const maps = ref([])
const currentMap = ref(null)
const files = ref([])
const entities = ref([])
const relations = ref([])
const evidence = ref([])
const selectedEvidenceDetail = ref(null)
const evidenceDetailError = ref('')
const buildRuns = ref([])
const evaluation = ref(null)
const graphSource = ref('')
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
const managementError = ref('')
const managementMessage = ref('')
const mapActionError = ref('')
const bindingError = ref('')
const bindingMessage = ref('')
const bindingForm = ref({ agentModes: [] })
const buildOptions = ref({
  extractorProvider: 'llamaindex',
  timeoutSeconds: 900,
  buildRequirement: ''
})

const GRAPH_REVIEW_STATUSES = ['candidate', 'confirmed', 'needs_review', 'merged', 'published', 'rejected']

const agentModeOptions = [
  { id: 'assistant', name: '助手' },
  { id: 'expert', name: '专家' },
  { id: 'query', name: '问数' },
  { id: 'report', name: '报告' },
  { id: 'chart', name: '图表' },
  { id: 'ops', name: '运维' }
]

const latestRun = computed(() => buildRuns.value[0] || currentMap.value?.latest_run || null)
const canRetryBuild = computed(() => currentMap.value?.status === 'failed' || latestRun.value?.status === 'failed')
const graphSourceText = computed(() => {
  if (graphSource.value === 'property_graph_store') return 'Property Graph'
  if (currentMap.value?.has_property_graph_store) return 'Property Graph'
  return '未生成图结构'
})

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

const entityTreeGroups = computed(() => {
  const groups = new Map()
  entities.value.forEach(entity => {
    const type = entity.entity_type || entity.type || 'Entity'
    if (!groups.has(type)) groups.set(type, [])
    groups.get(type).push(entity)
  })
  return Array.from(groups.entries()).map(([type, items]) => ({
    type,
    items: [...items].sort((left, right) => String(left.name || '').localeCompare(String(right.name || ''), 'zh-Hans-CN'))
  }))
})

const relationTreeGroups = computed(() => {
  const groups = new Map()
  relations.value.forEach(relation => {
    const type = relation.relation_type || relation.type || 'related_to'
    if (!groups.has(type)) groups.set(type, [])
    groups.get(type).push(relation)
  })
  return Array.from(groups.entries()).map(([type, items]) => ({
    type,
    items
  }))
})

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

const selectedGraphEvidence = computed(() => {
  const evidenceIds = selectedGraphItem.value?.raw?.source_evidence_ids || []
  return evidenceIds.map(id => evidenceById.value.get(id)).filter(Boolean)
})

const loadEvidenceDetail = async (item) => {
  const evidenceId = item?.evidence_id || item?.id
  if (!currentMap.value?.id || !evidenceId) return
  evidenceDetailError.value = ''
  try {
    const payload = await getCognitiveMapEvidenceDetail(currentMap.value.id, evidenceId)
    selectedEvidenceDetail.value = payload?.evidence || null
  } catch (error) {
    selectedEvidenceDetail.value = null
    evidenceDetailError.value = error?.message || '加载证据详情失败'
  }
}

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

const buildGraphQueryPayload = () => ({
  task: currentMap.value?.name || '认知地图',
  agent_mode: 'expert',
  entity_hints: [],
  depth: 3,
  limit: 200,
  max_entities: 200,
  max_relations: 200,
  max_evidence: 200,
  allowed_review_statuses: GRAPH_REVIEW_STATUSES
})

const applyGraphPayload = (payload) => {
  graphSource.value = payload?.source || ''
  if (payload?.source !== 'property_graph_store') {
    entities.value = []
    relations.value = []
    evidence.value = []
    return
  }

  const view = payload?.view || {}
  const graphEntities = normalizeList(view, ['entities'])
  const nameById = new Map(
    graphEntities
      .map(entity => [entity.entity_id || entity.id, entity.name])
      .filter(([id]) => id)
  )

  entities.value = graphEntities
  relations.value = normalizeList(view, ['relations']).map(relation => {
    const sourceId = relation.source_entity_id || relation.source || relation.source_id
    const targetId = relation.target_entity_id || relation.target || relation.target_id
    return {
      ...relation,
      source_name: relation.source_name || nameById.get(sourceId) || sourceId,
      target_name: relation.target_name || nameById.get(targetId) || targetId
    }
  })
  evidence.value = normalizeList(view, ['evidence_summaries', 'evidence'])
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
    candidate: '候选',
    confirmed: '已确认',
    rejected: '已驳回',
    needs_review: '需复核',
    merged: '已合并',
    published: '已发布'
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
  const {
    filePayload,
    graphPayload,
    runsPayload,
    evaluationPayload,
    bindingPayload,
    hasBlockingError
  } = collectSettledRefreshPayloads(await Promise.allSettled([
    listCognitiveMapFiles(currentMap.value.id),
    queryCognitiveMapGraph(currentMap.value.id, buildGraphQueryPayload()),
    listCognitiveMapBuildRuns(currentMap.value.id),
    getCognitiveMapEvaluation(currentMap.value.id),
    getCognitiveMapBindings(currentMap.value.id)
  ]))

  if (hasBlockingError) {
    files.value = []
    entities.value = []
    relations.value = []
    evidence.value = []
    buildRuns.value = []
    evaluation.value = null
    graphSource.value = ''
    bindingForm.value.agentModes = []
  } else {
    files.value = normalizeList(filePayload, ['files', 'items', 'data'])
    if (graphPayload) {
      applyGraphPayload(graphPayload)
    } else {
      graphSource.value = ''
      entities.value = []
      relations.value = []
      evidence.value = []
    }
    buildRuns.value = normalizeList(runsPayload, ['runs', 'items', 'data'])
    evaluation.value = evaluationPayload?.evaluation || null
    bindingForm.value.agentModes = normalizeList(bindingPayload, ['bindings', 'items', 'data'])
      .filter(item => item.enabled !== false)
      .map(item => item.agent_mode)
      .filter(Boolean)
  }
  await renderGraph()
}

const clearCurrentMapData = () => {
  currentMap.value = null
  files.value = []
  entities.value = []
  relations.value = []
  evidence.value = []
  buildRuns.value = []
  evaluation.value = null
  graphSource.value = ''
  selectedEvidenceDetail.value = null
  evidenceDetailError.value = ''
  selectedGraphItem.value = null
  bindingForm.value.agentModes = []
  bindingError.value = ''
  bindingMessage.value = ''
}

const refreshAll = async () => {
  await refreshMaps()
  await refreshCurrentMapData()
}

const selectMap = async (map) => {
  currentMap.value = map
  evaluation.value = map.evaluation || null
  buildRuns.value = map.latest_run ? [map.latest_run] : []
  buildOptions.value.extractorProvider = 'llamaindex'
  buildOptions.value.timeoutSeconds = Math.max(Number(map.latest_run?.timeout_seconds || 0), 900)
  buildOptions.value.buildRequirement = map.latest_run?.build_requirement || map.build_requirement || ''
  buildError.value = ''
  buildMessage.value = ''
  uploadError.value = ''
  managementError.value = ''
  managementMessage.value = ''
  mapActionError.value = ''
  bindingError.value = ''
  bindingMessage.value = ''
  selectedGraphItem.value = null
  inspectorTab.value = 'selection'
  isUploadDropExpanded.value = false
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
    isCreateMapExpanded.value = false
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

const handleDeleteMap = async (map = currentMap.value) => {
  if (!map?.id) return
  if (!window.confirm(`确认删除认知地图“${map.name || map.id}”？`)) return

  deletingMap.value = true
  mapActionError.value = ''
  try {
    const deletedCurrentMap = currentMap.value?.id === map.id
    await deleteCognitiveMap(map.id)
    if (deletedCurrentMap) {
      clearCurrentMapData()
    }
    await refreshMaps()
    if (deletedCurrentMap && maps.value.length > 0) {
      await selectMap(maps.value[0])
    }
    if (maps.value.length === 0) {
      clearCurrentMapData()
      await renderGraph()
    }
  } catch (error) {
    mapActionError.value = error?.message || '删除认知地图失败'
  } finally {
    deletingMap.value = false
  }
}

const saveModeBindings = async () => {
  if (!currentMap.value?.id) return
  savingBindings.value = true
  bindingError.value = ''
  bindingMessage.value = ''
  try {
    await updateCognitiveMapBindings(currentMap.value.id, {
      agent_modes: bindingForm.value.agentModes,
      enabled: true,
      description: '前端认知地图管理绑定'
    })
    await refreshMaps()
    updateCurrentMapFromList()
    bindingMessage.value = bindingForm.value.agentModes.length
      ? '已接入所选模式'
      : '已取消所有模式接入'
  } catch (error) {
    bindingError.value = error?.message || '保存接入模式失败'
  } finally {
    savingBindings.value = false
  }
}

const handlePublishMap = async () => {
  if (!currentMap.value?.id) return
  publishingMap.value = true
  managementError.value = ''
  managementMessage.value = ''
  try {
    const result = await publishCognitiveMap(currentMap.value.id)
    await refreshCurrentMapData()
    await refreshMaps()
    updateCurrentMapFromList()
    const publishedEntityCount = result.published_entity_count || 0
    const publishedRelationCount = result.published_relation_count || 0
    const availableEntityCount = result.available_entity_count || 0
    const availableRelationCount = result.available_relation_count || 0
    if (publishedEntityCount > 0 || publishedRelationCount > 0) {
      managementMessage.value = `已发布 ${publishedEntityCount} 个实体、${publishedRelationCount} 条关系，Agent 可默认使用。`
    } else if (availableEntityCount > 0 || availableRelationCount > 0) {
      managementMessage.value = `当前认知地图已发布，Agent 可默认使用 ${availableEntityCount} 个实体、${availableRelationCount} 条关系。`
    } else {
      managementMessage.value = '没有可发布的实体或关系，请先构建认知地图。'
    }
  } catch (error) {
    managementError.value = error?.message || '发布认知地图失败'
  } finally {
    publishingMap.value = false
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
      timeout_seconds: normalizeTimeoutSeconds(buildOptions.value.timeoutSeconds),
      build_requirement: buildOptions.value.buildRequirement?.trim() || ''
    })
    await refreshCurrentMapData()
    await refreshMaps()
    const engineName = formatProvider(buildOptions.value.extractorProvider)
    buildMessage.value = `${engineName} 构建完成，已更新 Property Graph 图结构`
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

const getGraphItemId = (kind, item) => (
  kind === 'relation'
    ? item?.relation_id || item?.id
    : item?.entity_id || item?.id
)

const isSelectedTreeItem = (kind, item) => (
  selectedGraphItem.value?.kind === kind &&
  getGraphItemId(kind, selectedGraphItem.value?.raw) === getGraphItemId(kind, item)
)

const updateCurrentMapFromList = () => {
  if (!currentMap.value?.id) return
  const updated = maps.value.find(item => item.id === currentMap.value.id)
  if (updated) currentMap.value = updated
}

const resizeGraphSoon = async () => {
  await nextTick()
  window.requestAnimationFrame(() => {
    graphChart.value?.resize()
  })
}

const toggleMapList = async () => {
  isMapListExpanded.value = !isMapListExpanded.value
  if (isMapListExpanded.value) {
    isCreateMapExpanded.value = false
    createError.value = ''
    mapActionError.value = ''
  }
  await resizeGraphSoon()
}

const toggleCreateMap = async () => {
  isMapListExpanded.value = true
  isCreateMapExpanded.value = !isCreateMapExpanded.value
  createError.value = ''
  mapActionError.value = ''
  await resizeGraphSoon()
}

const openManagementDrawer = async (tab = 'selection') => {
  isInspectorExpanded.value = true
  inspectorTab.value = tab
  if (tab !== 'selection') selectedGraphItem.value = null
  if (tab !== 'evidence') {
    selectedEvidenceDetail.value = null
    evidenceDetailError.value = ''
  }
  await resizeGraphSoon()
}

const closeManagementDrawer = async () => {
  isInspectorExpanded.value = false
  await resizeGraphSoon()
}

const toggleUploadDrop = async () => {
  isUploadDropExpanded.value = !isUploadDropExpanded.value
  await resizeGraphSoon()
}

const selectEntity = (entity) => {
  managementError.value = ''
  managementMessage.value = ''
  selectedEvidenceDetail.value = null
  evidenceDetailError.value = ''
  selectedGraphItem.value = { kind: 'entity', raw: entity }
  inspectorTab.value = 'selection'
  isInspectorExpanded.value = true
  resizeGraphSoon()
}

const selectRelation = (relation) => {
  managementError.value = ''
  managementMessage.value = ''
  selectedEvidenceDetail.value = null
  evidenceDetailError.value = ''
  selectedGraphItem.value = { kind: 'relation', raw: relation }
  inspectorTab.value = 'selection'
  isInspectorExpanded.value = true
  resizeGraphSoon()
}

const showMapOverview = async () => {
  selectedGraphItem.value = null
  inspectorTab.value = 'selection'
  await openManagementDrawer('selection')
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
  padding: 0;
  background: transparent;
  color: #1f2937;
}

.section-header,
.detail-header,
.panel-actions {
  display: flex;
  align-items: center;
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

.build-requirement-input {
  flex: 1 1 100%;
  display: grid;
  gap: 6px;
  color: #475569;
  font-size: 12px;
}

.build-requirement-input textarea {
  width: 100%;
  min-height: 72px;
  resize: vertical;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 8px;
  background: #fff;
  color: #1f2937;
  font-size: 13px;
  line-height: 1.5;
}

.build-requirement-field {
  grid-column: 1 / -1;
}

.panel-btn,
.primary-btn,
.create-form button,
.text-btn {
  border: 0;
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

.text-btn {
  padding: 0;
  border: 0;
  color: #2563eb;
  font-size: 12px;
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
  position: relative;
  height: 100%;
  min-height: 0;
}

.map-list-panel,
.map-detail-panel {
  min-height: 0;
  overflow: auto;
  background: transparent;
}

.map-list-panel {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 20;
  overflow: visible;
  padding: 8px;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.map-list-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.rail-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 72px;
  min-height: 28px;
  padding: 6px 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #1d4ed8;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
}

.add-map-btn {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #2563eb;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}

.map-list-dropdown {
  width: 280px;
  max-height: calc(100vh - 112px);
  overflow: auto;
  margin-top: 6px;
  padding: 8px 0;
  background: transparent;
}

.map-detail-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
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
  background: transparent;
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

.map-item-row {
  width: 100%;
  display: block;
  margin-bottom: 2px;
  border-left: 2px solid transparent;
  background: transparent;
}

.map-item {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  text-align: left;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.map-item-row.active {
  border-left-color: #2563eb;
  background: transparent;
}

.map-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  color: #111827;
}

.map-meta,
.map-status,
.row-meta {
  color: #64748b;
  font-size: 12px;
}

.map-meta {
  white-space: nowrap;
}

.map-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
}

.map-status-dot.status-draft {
  background: #94a3b8;
}

.map-status-dot.status-building {
  background: #f59e0b;
}

.map-status-dot.status-completed,
.map-status-dot.status-published {
  background: #16a34a;
}

.map-status-dot.status-failed {
  background: #dc2626;
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
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 12;
  justify-content: flex-start;
  width: max-content;
  min-height: 0;
  margin-bottom: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}

.compact-header {
  flex: none;
}

.action-toggle {
  flex: 0 0 auto;
}

.mode-binding-options {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
}

.mode-binding-option {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #475569;
  font-size: 12px;
  white-space: nowrap;
}

.inline-actions {
  justify-content: flex-start;
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
  position: absolute;
  top: 66px;
  left: 62px;
  right: 390px;
  z-index: 13;
  margin-bottom: 0;
  padding: 6px 10px;
  border: 1px dashed #cbd5e1;
  border-radius: 4px;
  background: transparent;
  color: #64748b;
  font-size: 12px;
  box-shadow: none;
  backdrop-filter: none;
}

.drop-strip.dragging {
  border-color: #16a34a;
  background: transparent;
  color: #166534;
}

.workbench-layout {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  flex: 1 1 auto;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.workbench-layout.drawer-open {
  grid-template-columns: minmax(420px, 1fr) minmax(560px, 42vw);
}

.workbench-layout:not(.drawer-open) .graph-workspace {
  grid-column: 1 / -1;
}

.graph-workspace {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.graph-toolbar {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 9;
  display: flex;
  align-items: flex-start;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.graph-toolbar-actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
  pointer-events: auto;
}

.graph-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  min-width: 0;
  max-width: min(520px, calc(100vw - 64px));
  padding: 6px 8px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 6px;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
  pointer-events: auto;
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
  position: absolute;
  left: 12px;
  bottom: 78px;
  z-index: 8;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-width: min(560px, calc(100vw - 64px));
  pointer-events: none;
}

.relation-filter button {
  padding: 4px 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #475569;
  cursor: pointer;
  font-size: 12px;
  box-shadow: none;
  pointer-events: auto;
}

.graph-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
  border: 0;
  border-radius: 0;
  background: #f8fafc;
}

.graph-empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 7;
  transform: translate(-50%, -50%);
  display: grid;
  place-items: center;
  min-height: 72px;
  min-width: 280px;
  padding: 0 16px;
  border: 1px dashed #cbd5e1;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  font-size: 13px;
  box-shadow: none;
  backdrop-filter: none;
}

.management-drawer {
  position: relative;
  z-index: 10;
  width: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-left: 1px solid #e5e7eb;
  background: #fff;
  box-shadow: none;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex: 0 0 auto;
  padding: 12px 14px;
  border-bottom: 1px solid #e5e7eb;
}

.drawer-header div {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.drawer-header strong {
  overflow: hidden;
  color: #111827;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-header span {
  color: #64748b;
  font-size: 12px;
}

.drawer-body {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  min-height: 0;
  flex: 1 1 auto;
}

.drawer-tree {
  min-height: 0;
  overflow: auto;
  padding: 10px 8px;
  border-right: 1px solid #e5e7eb;
  background: #f8fafc;
}

.tree-group {
  display: grid;
  gap: 2px;
  margin-top: 4px;
}

.tree-children {
  display: grid;
  gap: 2px;
  margin-left: 10px;
  padding-left: 8px;
  border-left: 1px solid #e2e8f0;
}

.tree-label {
  padding: 7px 6px 3px;
  color: #64748b;
  font-size: 12px;
}

.tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  min-height: 30px;
  padding: 6px 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #334155;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
}

.tree-node span {
  color: #64748b;
  font-size: 12px;
}

.root-node,
.group-node {
  font-weight: 600;
}

.leaf-node {
  justify-content: flex-start;
  overflow: hidden;
  color: #475569;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-node:hover,
.tree-node.active {
  background: #e0f2fe;
  color: #075985;
}

.drawer-detail {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 14px;
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

.edit-form {
  display: grid;
  gap: 10px;
}

.edit-form label {
  display: grid;
  gap: 5px;
  color: #64748b;
  font-size: 12px;
}

.edit-form input,
.edit-form select,
.edit-form textarea {
  min-width: 0;
  width: 100%;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #fff;
  color: #111827;
  font-size: 13px;
}

.edit-form input,
.edit-form select {
  height: 32px;
  padding: 0 8px;
}

.edit-form textarea {
  resize: vertical;
  padding: 8px;
  line-height: 1.5;
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

.review-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.danger-action {
  color: #dc2626;
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
  cursor: pointer;
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

.evidence-detail {
  display: grid;
  gap: 8px;
  margin-top: 10px;
  padding: 10px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #f8fafc;
  color: #1f2937;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.evidence-detail p {
  margin: 0;
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
    height: 100%;
  }

  .detail-header {
    right: 8px;
    width: max-content;
  }

  .build-actions {
    justify-content: flex-start;
  }

  .graph-toolbar {
    top: auto;
    left: 8px;
    right: 8px;
    bottom: 8px;
    align-items: flex-start;
    flex-direction: column;
  }

  .graph-legend {
    max-width: 100%;
  }

  .relation-filter {
    top: auto;
    left: 8px;
    right: 8px;
    bottom: 86px;
  }

  .drop-strip {
    top: 122px;
    left: 8px;
    right: 8px;
  }

  .workbench-layout.drawer-open {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) minmax(320px, 58%);
  }

  .management-drawer {
    width: 100%;
    min-height: 0;
    border-top: 1px solid #e5e7eb;
    border-left: 0;
  }

  .drawer-body {
    grid-template-columns: 160px minmax(0, 1fr);
  }

}
</style>
