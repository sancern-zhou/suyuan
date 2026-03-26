<template>
  <div class="react-analysis-view">
    <!-- 定时任务侧边栏 -->
    <TaskDrawer v-model="taskDrawerVisible" />

    <!-- 会话管理模态框 -->
    <SessionManagerModal
      v-model="showSessionManager"
      @restore="handleSessionRestore"
    />

    <div class="main-layout">
      <AssistantSidebar
        v-model:activeModule="activeAssistant"
        :collapsed="leftSidebarCollapsed"
        @update:collapsed="leftSidebarCollapsed = $event"
        @select="handleAssistantSelect"
        @action="handleSidebarAction"
        @loadSession="handleLoadSession"
      />

      <!-- 所有模式使用统一的分析面板 -->
      <div class="analysis-panel" ref="layoutRef">
        <div class="chat-area" :class="{ 'drag-over': chatAreaDragOver }" @dragover.prevent="handleChatAreaDragOver" @dragleave.prevent="handleChatAreaDragLeave" @drop.prevent="handleChatAreaDrop">
          <!-- 可视化面板折叠/展开按钮 -->
          <button
            v-if="hasVizContent"
            class="viz-toggle-btn"
            :class="{ expanded: rightPanelVisible }"
            @click="toggleVizPanel"
            :title="rightPanelVisible ? '隐藏右侧面板' : '显示右侧面板'"
          >
            <span class="toggle-icon">{{ rightPanelVisible ? '»' : '«' }}</span>
          </button>
          <!-- 知识库管理面板 -->
          <div v-if="managementPanel === 'knowledge-base'" class="management-panel kb-panel">
            <div class="panel-header">
              <h3>知识库管理</h3>
              <div class="panel-actions">
                <button class="panel-btn" @click="showKbCreateDialog = true">+ 新建知识库</button>
                <button class="panel-btn close-btn" @click="managementPanel = null">关闭</button>
              </div>
            </div>

            <div v-if="!kbStore.currentKb" class="kb-content">
              <!-- 公共知识库 -->
              <div v-if="kbStore.publicKbs.length > 0" class="kb-section">
                <div class="kb-section-title">公共知识库</div>
                <div
                  v-for="kb in kbStore.publicKbs"
                  :key="kb.id"
                  class="kb-item"
                  @click="selectKb(kb)"
                >
                  <div class="kb-item-header">
                    <span class="kb-name">{{ kb.name }}</span>
                    <span class="kb-badge public">公共</span>
                  </div>
                  <div class="kb-meta">{{ kb.document_count }} 文档 / {{ kb.chunk_count }} 分块</div>
                </div>
              </div>

              <!-- 个人知识库 -->
              <div v-if="kbStore.privateKbs.length > 0" class="kb-section">
                <div class="kb-section-title">我的知识库</div>
                <div
                  v-for="kb in kbStore.privateKbs"
                  :key="kb.id"
                  class="kb-item"
                  @click="selectKb(kb)"
                >
                  <div class="kb-item-header">
                    <span class="kb-name">{{ kb.name }}</span>
                    <span class="kb-badge private">个人</span>
                  </div>
                  <div class="kb-meta">{{ kb.document_count }} 文档 / {{ kb.chunk_count }} 分块</div>
                </div>
              </div>

              <div v-if="kbStore.publicKbs.length === 0 && kbStore.privateKbs.length === 0" class="kb-empty">
                暂无知识库，点击上方按钮创建
              </div>
            </div>

            <!-- 知识库详情 -->
            <div v-else class="kb-detail-full">
              <div class="kb-detail-header">
                <div class="kb-detail-title">
                  <h4>{{ kbStore.currentKb.name }}</h4>
                  <span class="kb-badge" :class="kbStore.currentKb.kb_type">
                    {{ kbStore.currentKb.kb_type === 'public' ? '公共' : '个人' }}
                  </span>
                </div>
                <div class="kb-detail-actions">
                  <button class="panel-btn small" @click="showKbEditDialog = true">编辑</button>
                  <button class="panel-btn small" @click="handleKbBack">返回</button>
                </div>
              </div>

              <div v-if="kbStore.currentKb.description" class="kb-detail-desc">{{ kbStore.currentKb.description }}</div>

              <div class="kb-detail-info">
                <span>分块策略: {{ getKbStrategyName(kbStore.currentKb.chunking_strategy) }}</span>
                <span>分块大小: {{ kbStore.currentKb.chunk_size }} 字符</span>
                <span>文档数: {{ kbStore.currentKb.document_count }}</span>
                <span>分块数: {{ kbStore.currentKb.chunk_count }}</span>
              </div>

              <!-- 文档上传 -->
              <div class="kb-upload-section">
                <div class="kb-section-title">上传文档</div>

                <!-- 分块策略选择 -->
                <div class="chunking-options">
                  <div class="option-row">
                    <div class="option-group">
                      <label>分块策略</label>
                      <select v-model="kbUploadOptions.chunking_strategy">
                        <option value="llm">LLM智能分块（默认，质量最高）</option>
                        <option value="sentence">句子分块（速度快）</option>
                        <option value="semantic">语义分块（基于Embedding）</option>
                        <option value="markdown">Markdown分块</option>
                        <option value="hybrid">混合分块</option>
                      </select>
                    </div>
                    <div class="option-group" v-if="kbUploadOptions.chunking_strategy === 'llm'">
                      <label>LLM模式</label>
                      <select v-model="kbUploadOptions.llm_mode">
                        <option value="local">本地千问3（快速，25K字符阈值）</option>
                        <option value="online">线上API（长文档，60K字符阈值）</option>
                      </select>
                    </div>
                    <div class="option-group" v-if="kbUploadOptions.chunking_strategy !== 'llm'">
                      <label>分块大小</label>
                      <input type="number" v-model.number="kbUploadOptions.chunk_size" min="64" max="2048" />
                    </div>
                    <div class="option-group" v-if="kbUploadOptions.chunking_strategy !== 'llm' && kbUploadOptions.chunking_strategy !== 'markdown'">
                      <label>分块重叠</label>
                      <input type="number" v-model.number="kbUploadOptions.chunk_overlap" min="0" max="512" />
                    </div>
                  </div>
                </div>

                <div
                  class="upload-area"
                  :class="{ dragging: kbIsDragging, uploading: kbIsUploading }"
                  @dragover.prevent="kbIsDragging = true"
                  @dragleave="kbIsDragging = false"
                  @drop.prevent="handleKbFileDrop"
                  @click="triggerKbFileInput"
                >
                  <input
                    ref="kbFileInput"
                    type="file"
                    multiple
                    accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.html,.htm,.txt,.md,.csv,.json"
                    @change="handleKbFileSelect"
                    style="display: none"
                  />
                  <div v-if="kbIsUploading" class="upload-progress">
                    <div class="spinner"></div>
                    <p>正在上传 {{ kbUploadProgress.current }}/{{ kbUploadProgress.total }}...</p>
                    <p v-if="kbUploadOptions.chunking_strategy === 'llm'" class="upload-note">LLM分块处理中，请耐心等待...</p>
                  </div>
                  <div v-else>
                    <p>点击或拖拽文件到此处上传</p>
                    <p class="upload-hint">支持 PDF、Word、Excel、HTML、TXT、Markdown 等格式</p>
                  </div>
                </div>
              </div>

              <!-- 文档列表 -->
              <div class="kb-documents-section">
                <div class="kb-section-title">文档列表 ({{ kbStore.documents.length }})</div>
                <div v-if="kbStore.documents.length === 0" class="kb-empty-docs">暂无文档</div>
                <div v-else class="kb-doc-list">
                  <div
                    v-for="doc in kbStore.documents"
                    :key="doc.id"
                    class="kb-doc-item"
                    :class="{ clickable: doc.status === 'completed' }"
                    @click="doc.status === 'completed' && viewKbChunks(doc)"
                  >
                    <div class="kb-doc-info">
                      <span class="kb-doc-name">{{ doc.filename }}</span>
                      <span class="kb-doc-meta">
                        {{ formatFileSize(doc.file_size) }} |
                        {{ doc.chunk_count }} 分块 |
                        <span :class="'status-' + doc.status">{{ getKbStatusText(doc.status) }}</span>
                        <span v-if="doc.status === 'completed'" class="view-hint">点击查看分段</span>
                      </span>
                    </div>
                    <div class="kb-doc-actions" @click.stop>
                      <button
                        v-if="doc.status === 'failed'"
                        class="kb-btn-text"
                        @click="handleKbRetry(doc.id)"
                      >
                        重试
                      </button>
                      <button class="kb-btn-text danger" @click="handleKbDeleteDoc(doc.id)">删除</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 数据抓取管理面板 -->
          <div v-else-if="managementPanel === 'fetchers'" class="management-panel fetchers-panel">
            <div class="panel-header">
              <h3>数据抓取管理</h3>
              <button class="panel-btn close-btn" @click="managementPanel = null">关闭</button>
            </div>

            <div class="fetchers-content">
              <!-- 系统状态 -->
              <div class="fetchers-status-card">
                <h4>系统状态</h4>
                <div class="status-grid" v-if="fetcherSystemStatus">
                  <div class="status-item">
                    <span class="label">调度器:</span>
                    <span :class="['status-value', fetcherSystemStatus.fetchers?.scheduler_running ? 'running' : 'stopped']">
                      {{ fetcherSystemStatus.fetchers?.scheduler_running ? '运行中' : '已停止' }}
                    </span>
                  </div>
                  <div class="status-item">
                    <span class="label">数据库:</span>
                    <span :class="['status-value', fetcherSystemStatus.database?.enabled ? 'running' : 'stopped']">
                      {{ fetcherSystemStatus.database?.enabled ? '已连接' : '未连接' }}
                    </span>
                  </div>
                  <div class="status-item">
                    <span class="label">Fetchers:</span>
                    <span class="status-value">{{ Object.keys(fetcherSystemStatus.fetchers?.fetchers || {}).length }} 个</span>
                  </div>
                  <div class="status-item">
                    <span class="label">LLM工具:</span>
                    <span class="status-value">{{ fetcherSystemStatus.llm_tools?.count || 0 }} 个</span>
                  </div>
                </div>
              </div>

              <!-- ERA5 历史数据补采 -->
              <div class="era5-card">
                <h4>ERA5 历史数据补采</h4>
                <p class="era5-desc">手动补采指定日期的 ERA5 气象数据（广东省全境 825 个网格点）</p>

                <div class="era5-controls">
                  <div class="date-input-group">
                    <label>选择日期：</label>
                    <input
                      type="date"
                      v-model="era5HistoricalDate"
                      :max="todayStr"
                      class="date-input"
                    />
                  </div>
                  <button
                    @click="fetchEra5Historical"
                    :disabled="!era5HistoricalDate || fetcherOperating"
                    class="panel-btn primary"
                  >
                    开始补采
                  </button>
                </div>

                <!-- 补采结果 -->
                <div v-if="era5FetchResult" :class="['fetch-result', era5FetchResult.success ? 'success' : 'warning']">
                  <div class="result-header">
                    <span class="result-icon">{{ era5FetchResult.success ? '✓' : '!' }}</span>
                    <span class="result-title">{{ era5FetchResult.message }}</span>
                  </div>
                  <div class="result-details">
                    <div class="result-row">
                      <span class="label">日期：</span>
                      <span class="value">{{ era5FetchResult.date }}</span>
                    </div>
                    <div class="result-row">
                      <span class="label">网格点数：</span>
                      <span class="value">{{ era5FetchResult.grid_count }}</span>
                    </div>
                    <div class="result-row">
                      <span class="label">成功：</span>
                      <span class="value success-text">{{ era5FetchResult.success_count }}</span>
                    </div>
                    <div class="result-row">
                      <span class="label">失败：</span>
                      <span :class="['value', era5FetchResult.failed_count > 0 ? 'error-text' : '']">
                        {{ era5FetchResult.failed_count }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Fetchers 列表 -->
              <div class="fetchers-list-section">
                <div class="section-header">
                  <h4>数据获取器列表</h4>
                  <button @click="refreshFetcherStatus" :disabled="fetcherLoading" class="panel-btn small">
                    {{ fetcherLoading ? '刷新中...' : '刷新' }}
                  </button>
                </div>

                <div v-if="fetcherLoading" class="fetcher-loading">
                  <div class="spinner"></div>
                  <p>加载中...</p>
                </div>

                <div v-else-if="fetcherError" class="fetcher-error">
                  <p>错误: {{ fetcherError }}</p>
                  <button @click="refreshFetcherStatus" class="panel-btn small">重试</button>
                </div>

                <div v-else class="fetcher-cards">
                  <div
                    v-for="(fetcher, name) in fetcherSystemStatus?.fetchers?.fetchers || {}"
                    :key="name"
                    class="fetcher-card"
                  >
                    <div class="fetcher-card-header">
                      <h5>{{ fetcher.name }}</h5>
                      <span :class="['status-badge', getFetcherStatusClass(fetcher.status)]">
                        {{ getFetcherStatusText(fetcher.status) }}
                      </span>
                    </div>

                    <div class="fetcher-card-info">
                      <div class="info-row">
                        <span class="label">描述:</span>
                        <span class="value">{{ fetcher.description }}</span>
                      </div>
                      <div class="info-row">
                        <span class="label">周期:</span>
                        <code class="schedule">{{ fetcher.schedule }}</code>
                      </div>
                      <div class="info-row">
                        <span class="label">版本:</span>
                        <span class="value">{{ fetcher.version }}</span>
                      </div>
                    </div>

                    <div class="fetcher-card-actions">
                      <button
                        @click="triggerFetcher(name)"
                        :disabled="fetcherOperating"
                        class="panel-btn small primary"
                      >
                        触发
                      </button>
                      <button
                        v-if="fetcher.enabled"
                        @click="pauseFetcher(name)"
                        :disabled="fetcherOperating"
                        class="panel-btn small warning"
                      >
                        暂停
                      </button>
                      <button
                        v-else
                        @click="resumeFetcher(name)"
                        :disabled="fetcherOperating"
                        class="panel-btn small success"
                      >
                        恢复
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 定时任务管理面板 -->
          <div v-else-if="managementPanel === 'scheduled-tasks'" class="management-panel scheduled-tasks-panel">
            <div class="panel-header">
              <h3>定时任务管理</h3>
              <button class="panel-btn small" @click="refreshScheduledTasks" :disabled="scheduledTasksRefreshing">
                {{ scheduledTasksRefreshing ? '刷新中...' : '刷新' }}
              </button>
              <button class="panel-btn close-btn" @click="managementPanel = null">关闭</button>
            </div>

            <div class="scheduled-tasks-content">
              <!-- 统计信息 -->
              <div class="scheduled-stats-card">
                <div class="scheduled-stat-item">
                  <div class="scheduled-stat-value">{{ scheduledTasksStore.stats.total }}</div>
                  <div class="scheduled-stat-label">总任务</div>
                </div>
                <div class="scheduled-stat-item">
                  <div class="scheduled-stat-value">{{ scheduledTasksStore.stats.running }}</div>
                  <div class="scheduled-stat-label">运行中</div>
                </div>
                <div class="scheduled-stat-item">
                  <div class="scheduled-stat-value">{{ scheduledTasksStore.stats.successRate }}%</div>
                  <div class="scheduled-stat-label">成功率</div>
                </div>
              </div>

              <!-- 任务列表 -->
              <div class="scheduled-tasks-list">
                <div v-if="scheduledTasksStore.tasks.length === 0" class="scheduled-empty-state">
                  <p>暂无定时任务</p>
                  <p class="scheduled-hint">在对话中说"创建定时任务"即可快速创建</p>
                </div>

                <div
                  v-for="task in scheduledTasksStore.tasks"
                  :key="task.task_id"
                  class="scheduled-task-card"
                >
                  <!-- 任务头部 -->
                  <div class="scheduled-task-header">
                    <div class="scheduled-task-title">
                      <span class="scheduled-task-name">{{ task.name }}</span>
                      <span :class="['scheduled-task-tag', getScheduledTaskTagClass(task.schedule_type)]">
                        {{ getScheduledTaskLabel(task.schedule_type) }}
                      </span>
                    </div>

                    <!-- 快速开关 -->
                    <label class="scheduled-switch">
                      <input
                        type="checkbox"
                        :checked="task.enabled"
                        @change="handleScheduledTaskToggle(task)"
                        :disabled="task.toggling"
                      />
                      <span class="scheduled-slider"></span>
                    </label>
                  </div>

                  <!-- 任务描述 -->
                  <div class="scheduled-task-description">
                    {{ task.description }}
                  </div>

                  <!-- 任务元信息 -->
                  <div class="scheduled-task-meta">
                    <span class="scheduled-meta-item">⏰ {{ formatScheduledNextRun(task.next_run_at) }}</span>
                    <span class="scheduled-meta-item">📋 {{ task.steps?.length || 0 }} 个步骤</span>
                    <span class="scheduled-meta-item">✅ {{ task.success_runs || 0 }}/{{ task.total_runs || 0 }}</span>
                  </div>

                  <!-- 标签 -->
                  <div class="scheduled-task-tags" v-if="task.tags && task.tags.length > 0">
                    <span v-for="tag in task.tags" :key="tag" class="scheduled-tag">
                      {{ tag }}
                    </span>
                  </div>

                  <!-- 操作按钮 -->
                  <div class="scheduled-task-actions">
                    <button
                      class="scheduled-btn scheduled-btn-execute"
                      @click="executeScheduledTask(task)"
                      :disabled="task.executing"
                      title="立即执行此任务"
                    >
                      {{ task.executing ? '执行中...' : '▶️ 立即执行' }}
                    </button>
                    <button class="scheduled-btn scheduled-btn-secondary" @click="editScheduledTask(task)">
                      编辑
                    </button>
                    <button class="scheduled-btn scheduled-btn-danger" @click="deleteScheduledTask(task)">
                      删除
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 会话历史管理面板 -->
          <div v-else-if="managementPanel === 'session-history'" class="management-panel session-history-panel">
            <div class="panel-header">
              <h3>会话历史</h3>
              <button class="panel-btn small" @click="refreshSessionHistory" :disabled="sessionHistoryLoading">
                {{ sessionHistoryLoading ? '刷新中...' : '刷新' }}
              </button>
              <button class="panel-btn small" @click="handleSessionCleanup">清理过期</button>
              <button class="panel-btn close-btn" @click="managementPanel = null">关闭</button>
            </div>

            <div class="session-history-content">
              <!-- 过滤器 -->
              <div class="session-filters">
                <button
                  v-for="filter in ['all', 'active', 'completed', 'failed', 'archived']"
                  :key="filter"
                  class="session-filter-btn"
                  :class="{ active: sessionHistoryFilter === filter }"
                  @click="sessionHistoryFilter = filter"
                >
                  <span class="filter-icon">{{ getSessionHistoryFilterIcon(filter) }}</span>
                  <span class="filter-label">{{ getSessionHistoryFilterLabel(filter) }}</span>
                  <span v-if="getSessionHistoryFilterCount(filter) > 0" class="filter-count">
                    {{ getSessionHistoryFilterCount(filter) }}
                  </span>
                </button>
              </div>

              <!-- 统计信息 -->
              <div v-if="sessionHistoryStats" class="session-stats">
                <div class="session-stat-item">
                  <span class="session-stat-icon">📊</span>
                  <div class="session-stat-info">
                    <span class="session-stat-value">{{ sessionHistoryStats.total }}</span>
                    <span class="session-stat-label">总会话数</span>
                  </div>
                </div>
                <div class="session-stat-item">
                  <span class="session-stat-icon">💾</span>
                  <div class="session-stat-info">
                    <span class="session-stat-value">{{ sessionHistoryStats.total_data_count }}</span>
                    <span class="session-stat-label">数据项</span>
                  </div>
                </div>
                <div class="session-stat-item">
                  <span class="session-stat-icon">📈</span>
                  <div class="session-stat-info">
                    <span class="session-stat-value">{{ sessionHistoryStats.total_visual_count }}</span>
                    <span class="session-stat-label">可视化</span>
                  </div>
                </div>
              </div>

              <!-- 会话列表 -->
              <div class="session-list">
                <div v-if="sessionHistoryLoading" class="session-loading">
                  <span class="session-spinner">⏳</span>
                  <p>加载会话列表...</p>
                </div>

                <div v-else-if="getFilteredSessions().length === 0" class="session-empty">
                  <span class="session-empty-icon">📭</span>
                  <p>暂无{{ sessionHistoryFilter === 'all' ? '' : getSessionHistoryFilterLabel(sessionHistoryFilter) }}会话</p>
                </div>

                <div v-else>
                  <div
                    v-for="session in getFilteredSessions()"
                    :key="session.session_id"
                    class="session-item"
                    :class="[getSessionHistoryStateClass(session.state), { 'session-expanded': session.isExpanded }]"
                  >
                    <!-- 会话头部 -->
                    <div class="session-header" @click="toggleSessionExpand(session)">
                      <div class="session-header-left">
                        <span class="session-state-icon">{{ getSessionHistoryStateIcon(session.state) }}</span>
                        <div class="session-info">
                          <div class="session-query">{{ getTruncatedQuery(session.query) }}</div>
                          <div class="session-meta">
                            <span class="session-id">{{ getShortSessionId(session.session_id) }}</span>
                            <span class="session-time">{{ formatSessionTime(session.updated_at) }}</span>
                          </div>
                        </div>
                      </div>
                      <div class="session-header-right">
                        <span class="session-expand-icon">{{ session.isExpanded ? '▲' : '▼' }}</span>
                      </div>
                    </div>

                    <!-- 展开的详情 -->
                    <div v-if="session.isExpanded" class="session-details">
                      <div class="session-detail-row">
                        <span class="session-detail-label">创建时间:</span>
                        <span class="session-detail-value">{{ formatSessionFullTime(session.created_at) }}</span>
                      </div>
                      <div class="session-detail-row">
                        <span class="session-detail-label">更新时间:</span>
                        <span class="session-detail-value">{{ formatSessionFullTime(session.updated_at) }}</span>
                      </div>

                      <div class="session-stats">
                        <div class="session-stat-box">
                          <span class="session-stat-label-small">数据</span>
                          <span class="session-stat-value-small">{{ session.data_count }}</span>
                        </div>
                        <div class="session-stat-box">
                          <span class="session-stat-label-small">图表</span>
                          <span class="session-stat-value-small">{{ session.visual_count }}</span>
                        </div>
                      </div>

                      <div class="session-actions">
                        <button
                          v-if="session.state !== 'archived'"
                          class="session-btn session-btn-primary"
                          @click.stop="handleSessionRestore(session.session_id)"
                        >
                          🔄 恢复
                        </button>
                        <button
                          v-if="session.state !== 'archived'"
                          class="session-btn session-btn-secondary"
                          @click.stop="handleSessionArchive(session.session_id)"
                        >
                          📦 归档
                        </button>
                        <button
                          class="session-btn session-btn-secondary"
                          @click.stop="handleSessionExport(session.session_id)"
                        >
                          📥 导出
                        </button>
                        <button
                          class="session-btn session-btn-danger"
                          @click.stop="handleSessionDelete(session.session_id)"
                        >
                          🗑️ 删除
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 社交平台管理面板 -->
          <div v-else-if="managementPanel === 'social-platform'" class="management-panel social-platform-panel">
            <div class="panel-header">
              <h3>社交平台管理</h3>
              <button class="panel-btn small" @click="refreshSocialPlatformStatus" :disabled="socialPlatformLoading">
                {{ socialPlatformLoading ? '刷新中...' : '刷新' }}
              </button>
              <button class="panel-btn close-btn" @click="managementPanel = null">关闭</button>
            </div>

            <div class="social-platform-content">
              <!-- 平台状态卡片 -->
              <div class="platform-cards">
                <!-- QQ平台 -->
                <div class="platform-card qq">
                  <div class="card-header">
                    <div class="platform-icon">
                      <span class="icon-qq">QQ</span>
                    </div>
                    <div class="platform-info">
                      <h4>QQ机器人</h4>
                      <span class="status-badge" :class="getPlatformStatusClass(socialPlatformStatus.qq)">
                        {{ getPlatformStatusText(socialPlatformStatus.qq) }}
                      </span>
                    </div>
                  </div>
                  <div class="card-metrics">
                    <div class="metric">
                      <span class="metric-label">消息接收</span>
                      <span class="metric-value">{{ socialPlatformMetrics.qq?.messages_received || 0 }}</span>
                    </div>
                    <div class="metric">
                      <span class="metric-label">消息发送</span>
                      <span class="metric-value">{{ socialPlatformMetrics.qq?.messages_sent || 0 }}</span>
                    </div>
                    <div class="metric">
                      <span class="metric-label">错误率</span>
                      <span class="metric-value">{{ socialPlatformMetrics.qq?.error_rate || '0%' }}</span>
                    </div>
                  </div>
                </div>

                <!-- 微信平台 -->
                <div class="platform-card weixin">
                  <div class="card-header">
                    <div class="platform-icon">
                      <span class="icon-weixin">微信</span>
                    </div>
                    <div class="platform-info">
                      <h4>微信机器人</h4>
                      <span class="status-badge" :class="getPlatformStatusClass(socialPlatformStatus.weixin)">
                        {{ getPlatformStatusText(socialPlatformStatus.weixin) }}
                      </span>
                    </div>
                  </div>
                  <div class="card-metrics">
                    <div class="metric">
                      <span class="metric-label">消息接收</span>
                      <span class="metric-value">{{ socialPlatformMetrics.weixin?.messages_received || 0 }}</span>
                    </div>
                    <div class="metric">
                      <span class="metric-label">消息发送</span>
                      <span class="metric-value">{{ socialPlatformMetrics.weixin?.messages_sent || 0 }}</span>
                    </div>
                    <div class="metric">
                      <span class="metric-label">错误率</span>
                      <span class="metric-value">{{ socialPlatformMetrics.weixin?.error_rate || '0%' }}</span>
                    </div>
                  </div>

                  <!-- 微信登录按钮 -->
                  <div class="card-actions">
                    <!-- 调试信息 -->
                    <div style="font-size: 11px; color: #999; margin-bottom: 8px;">
                      调试: logged_in={{ socialPlatformStatus.weixin?.logged_in }},
                      enabled={{ socialPlatformStatus.weixin?.enabled }},
                      按钮显示={{ !socialPlatformStatus.weixin?.logged_in }}
                    </div>
                    <button
                      v-if="!socialPlatformStatus.weixin?.logged_in"
                      class="panel-btn primary"
                      @click="showWeixinQRModal = true"
                    >
                      扫码登录
                    </button>
                  </div>
                </div>
              </div>

              <!-- 系统健康状态 -->
              <div class="health-section">
                <h4>系统健康状态</h4>
                <div class="health-cards">
                  <div class="health-card" :class="{ healthy: socialPlatformHealth.healthy }">
                    <div class="health-icon">{{ socialPlatformHealth.healthy ? '✓' : '!' }}</div>
                    <div class="health-info">
                      <span class="health-label">整体状态</span>
                      <span class="health-value">{{ socialPlatformHealth.healthy ? '运行正常' : '存在异常' }}</span>
                    </div>
                  </div>
                  <div class="health-card cache">
                    <div class="health-icon">📊</div>
                    <div class="health-info">
                      <span class="health-label">缓存命中率</span>
                      <span class="health-value">{{ socialPlatformCacheStats.hit_rate || '0%' }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 微信QR码弹窗 -->
            <div v-if="showWeixinQRModal" class="qr-modal-overlay" @click="showWeixinQRModal = false">
              <div class="qr-modal" @click.stop>
                <div class="qr-modal-header">
                  <h4>微信登录</h4>
                  <button class="close-btn" @click="showWeixinQRModal = false">×</button>
                </div>

                <div class="qr-modal-body">
                  <div v-if="weixinQRCodeUrl" class="qr-code-container">
                    <img :src="weixinQRCodeUrl" alt="微信登录QR码" class="qr-code-image" />

                    <div class="status-container">
                      <div class="status-indicator" :class="weixinLoginStatus.class">
                        {{ weixinLoginStatus.text }}
                      </div>
                    </div>

                    <div class="instructions">
                      <h5>登录步骤：</h5>
                      <ol>
                        <li>打开微信，点击右上角的"扫一扫"</li>
                        <li>扫描上方二维码</li>
                        <li>在手机上确认登录</li>
                      </ol>
                    </div>
                  </div>

                  <div v-else class="qr-loading">
                    <div class="spinner"></div>
                    <p>正在生成二维码...</p>
                  </div>
                </div>

                <div class="qr-modal-footer">
                  <button class="panel-btn secondary" @click="refreshWeixinQRCode" :disabled="weixinQRLoading">
                    {{ weixinQRLoading ? '加载中...' : '刷新二维码' }}
                  </button>
                  <button class="panel-btn primary" @click="checkWeixinLoginStatus">
                    检查状态
                  </button>
                </div>
              </div>
            </div>
          </div>

          <ReActMessageList
            v-if="!managementPanel"
            :messages="currentModeMessages"
            :show-reflexion="store.currentState.showReflexion"
            :reflexion-count="store.currentState.reflexionCount"
            :use-markdown="true"
            :assistant-mode="activeAssistant"
            :selected-message-id="selectedMessageId"
            :visualization-panel-ref="vizPanelRef"
            :on-message-click="selectMessage"
          />

          <InputBox
            v-if="!managementPanel"
            ref="inputBoxRef"
            v-model="currentModeCurrentMessage"
            :disabled="inputDisabled"
            :is-analyzing="currentModeIsAnalyzing"
            :placeholder="inputPlaceholder"
            :assistant-mode="activeAssistant"
            :use-reranker="useReranker"
            @send="handleSend"
            @pause="handlePause"
            @update:useReranker="handleRerankerChange"
            @update:agentMode="handleAgentModeChange"
          />
        </div>

        <div
          v-if="rightPanelVisible"
          class="resize-handle"
          :class="{ dragging: isDragging }"
          @mousedown="startDragging"
          @dblclick.stop="resetWidth"
          title="拖拽调整右侧面板宽度，双击恢复默认"
        ></div>

        <!-- 拖动时的透明遮罩层，用于捕获鼠标事件 -->
        <div
          v-if="isDragging"
          class="drag-overlay"
          @mouseup="stopDragging"
          @mouseleave="stopDragging"
        ></div>

        <div v-if="rightPanelVisible" class="viz-wrapper" :style="vizPanelStyle">
          <!-- 报告生成专家 -->
          <ReportGenerationPanel
            v-if="activeAssistant === 'report-generation-expert'"
            :assistant-mode="activeAssistant"
          />

          <!-- 其他模式：可视化面板 + Office文档预览面板 -->
          <template v-else>
            <!-- 标签页切换按钮 -->
            <div v-if="vizPanelVisible && officePanelVisible" class="right-panel-tabs">
              <button
                :class="['tab-btn', { active: activeRightTab === 'visualization' }]"
                @click="activeRightTab = 'visualization'"
              >
                可视化
              </button>
              <button
                :class="['tab-btn', { active: activeRightTab === 'document' }]"
                @click="activeRightTab = 'document'"
              >
                文档预览
              </button>
            </div>

            <!-- 可视化面板 -->
            <VisualizationPanel
              v-show="activeRightTab === 'visualization'"
              ref="vizPanelRef"
              :content="currentModeVisualization"
              :history="currentModeMessages"
              :selected-message-id="selectedMessageId"
              :assistant-mode="activeAssistant"
              :expert-results="currentModeExpertResults"
              @fullscreen="openFullscreen"
              @fullscreen-expert="handleExpertFullscreen"
            />

            <!-- Office文档预览面板 -->
            <OfficeDocumentPanel
              v-show="activeRightTab === 'document'"
              ref="officePanelRef"
              :history="currentModeMessages"
              :session-id="currentModeSessionId || ''"
              @submit-edit="handleOfficeEditSubmit"
            />
          </template>
        </div>
      </div>
    </div>

    <!-- 大屏模式 -->
    <FullscreenDashboard
      :visible="fullscreenMode"
      :assistant-mode="activeAssistant"
      :expert-results="currentModeExpertResults"
      @close="closeFullscreen"
    />

    <!-- 知识库创建对话框 -->
    <div v-if="showKbCreateDialog" class="dialog-overlay" @click.self="showKbCreateDialog = false">
      <div class="dialog">
        <div class="dialog-header">
          <h3>新建知识库</h3>
          <button class="btn-close" @click="showKbCreateDialog = false">×</button>
        </div>
        <div class="dialog-body">
          <div class="form-group">
            <label>名称 *</label>
            <input v-model="kbCreateForm.name" type="text" placeholder="输入知识库名称" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="kbCreateForm.description" placeholder="输入知识库描述"></textarea>
          </div>
          <div class="form-group">
            <label>类型</label>
            <select v-model="kbCreateForm.kb_type">
              <option value="private">个人知识库</option>
              <option value="public">公共知识库</option>
            </select>
          </div>
          <div class="form-group" v-if="kbCreateForm.kb_type === 'public'">
            <label>公共知识库权限</label>
            <label class="checkbox-inline">
              <input type="checkbox" v-model="kbAdminConfirm" />
              以管理员身份创建（自动携带 X-Is-Admin: true）
            </label>
            <p class="form-hint danger">提醒：公共知识库必须以管理员身份创建，否则会返回 403。</p>
          </div>
          <div class="form-group">
            <label>分块策略</label>
            <select v-model="kbCreateForm.chunking_strategy">
              <option value="llm">LLM智能分块（推荐）</option>
              <option value="sentence">句子分块</option>
              <option value="semantic">语义分块</option>
              <option value="markdown">Markdown分块</option>
              <option value="hybrid">混合分块</option>
            </select>
            <p class="form-hint">{{ getKbStrategyDesc(kbCreateForm.chunking_strategy) }}</p>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>分块大小</label>
              <input v-model.number="kbCreateForm.chunk_size" type="number" min="64" max="2048" />
            </div>
            <div class="form-group">
              <label>分块重叠</label>
              <input v-model.number="kbCreateForm.chunk_overlap" type="number" min="0" max="512" />
            </div>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn-secondary" @click="showKbCreateDialog = false">取消</button>
          <button class="btn-primary" @click="handleKbCreate" :disabled="!kbCreateForm.name">创建</button>
        </div>
      </div>
    </div>

    <!-- 知识库编辑对话框 -->
    <div v-if="showKbEditDialog" class="dialog-overlay" @click.self="showKbEditDialog = false">
      <div class="dialog">
        <div class="dialog-header">
          <h3>编辑知识库</h3>
          <button class="btn-close" @click="showKbEditDialog = false">×</button>
        </div>
        <div class="dialog-body">
          <div class="form-group">
            <label>名称 *</label>
            <input v-model="kbEditForm.name" type="text" placeholder="输入知识库名称" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="kbEditForm.description" placeholder="输入知识库描述"></textarea>
          </div>
          <div class="form-group">
            <label>
              <input type="checkbox" v-model="kbEditForm.is_default" />
              设为默认知识库
            </label>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn-secondary" @click="showKbEditDialog = false">取消</button>
          <button class="btn-primary" @click="handleKbUpdate" :disabled="!kbEditForm.name">保存</button>
        </div>
      </div>
    </div>

    <!-- 文档分段全屏对话框 -->
    <div v-if="showKbChunksDialog" class="chunks-fullscreen">
      <div class="chunks-header">
        <div class="chunks-title">
          <button class="btn-back" @click="closeKbChunksDialog">← 返回</button>
          <h2>{{ kbCurrentDoc?.filename }}</h2>
          <span class="chunks-count">共 {{ kbDocumentChunks.length }} 个分块</span>
        </div>
        <div class="chunks-actions">
          <button class="btn-secondary" @click="closeKbChunksDialog">关闭</button>
        </div>
      </div>
      <div class="chunks-content">
        <div class="chunks-list-full">
          <div v-for="(chunk, index) in kbDocumentChunks" :key="index" class="chunk-card">
            <div class="chunk-card-header">
              <span class="chunk-number">分块 #{{ chunk.chunk_index + 1 }}</span>
              <span class="chunk-length">{{ chunk.content.length }} 字符</span>
              <span class="chunk-position" v-if="chunk.start_char !== null">
                位置: {{ chunk.start_char }} - {{ chunk.end_char }}
              </span>
            </div>
            <div class="chunk-metadata" v-if="chunk.metadata && Object.keys(chunk.metadata).length > 0">
              <div class="metadata-row" v-if="chunk.metadata.topic">
                <span class="metadata-label">主题:</span>
                <span class="metadata-value">{{ chunk.metadata.topic }}</span>
              </div>
              <div class="metadata-row" v-if="chunk.metadata.section">
                <span class="metadata-label">章节:</span>
                <span class="metadata-value">{{ chunk.metadata.section }}</span>
              </div>
              <div class="metadata-row" v-if="chunk.metadata.type">
                <span class="metadata-label">类型:</span>
                <span class="metadata-value type-tag" :class="'type-' + chunk.metadata.type">
                  {{ getKbChunkTypeName(chunk.metadata.type) }}
                </span>
              </div>
            </div>
            <div class="chunk-card-body">{{ chunk.content }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useReactStore } from '@/stores/reactStore'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'
import { useScheduledTasksStore } from '@/stores/scheduledTasks'
import ReActMessageList from '@/components/ReActMessageList.vue'
import InputBox from '@/components/InputBox.vue'
import VisualizationPanel from '@/components/VisualizationPanel.vue'
import OfficeDocumentPanel from '@/components/OfficeDocumentPanel.vue'
import ReportGenerationPanel from '@/components/ReportGenerationPanel.vue'
import AssistantSidebar from '@/components/AssistantSidebar.vue'
import MeteorologyScenarioSelector from '@/components/MeteorologyScenarioSelector.vue'
import FullscreenDashboard from '@/components/dashboard/FullscreenDashboard.vue'
import TaskDrawer from '@/components/ScheduledTasks/TaskDrawer.vue'
import SessionManagerModal from '@/components/SessionManagerModal.vue'
import { restoreSession } from '@/api/session'

const router = useRouter()

const store = useReactStore()
const kbStore = useKnowledgeBaseStore()
const scheduledTasksStore = useScheduledTasksStore()

const defaultVizWidth = 30  // 默认宽度（当左侧面板未折叠时）
const collapsedVizWidth = 45  // 左侧面板折叠时的默认宽度（对话区55%，右侧面板45%）
const minVizWidth = 20
const maxVizWidth = 60

const vizWidth = ref(defaultVizWidth)
const isDragging = ref(false)
const layoutRef = ref(null)
const activeAssistant = ref('general-agent')
const fullscreenMode = ref(false)
const vizPanelRef = ref(null)  // VisualizationPanel的引用
const vizPanelVisible = ref(false)  // 可视化面板是否可见
const inputBoxRef = ref(null)  // InputBox组件的引用
const chatAreaDragOver = ref(false)  // 对话区拖拽状态
const officePanelRef = ref(null)  // OfficeDocumentPanel的引用
const officePanelVisible = ref(false)  // Office文档预览面板是否可见
const rightPanelVisible = ref(false)  // 右侧面板总体是否可见（默认隐藏，有内容时自动展开）
const leftSidebarCollapsed = ref(false)  // 左侧侧边栏折叠状态
const activeRightTab = ref('visualization')  // 右侧面板活动标签页: 'visualization' | 'document'
const taskDrawerVisible = ref(false)  // 定时任务侧边栏显示状态
const showSessionManager = ref(false)  // 会话管理模态框状态
const useReranker = ref(false)  // 精准检索开关
const selectedMessageId = ref(null)  // 当前选中的消息ID，用于显示其sources
const managementPanel = ref(null)  // 当前显示的管理面板：knowledge-base | fetchers | null
const showKbCreateDialog = ref(false)  // 知识库创建对话框
const showKbEditDialog = ref(false)  // 知识库编辑对话框
const showKbChunksDialog = ref(false)  // 文档分段对话框

// 知识库创建表单
const kbCreateForm = ref({
  name: '',
  description: '',
  kb_type: 'private',
  chunking_strategy: 'llm',
  chunk_size: 800,
  chunk_overlap: 100
})
const kbAdminConfirm = ref(localStorage.getItem('isAdmin') === 'true')

// 知识库编辑表单
const kbEditForm = ref({
  name: '',
  description: '',
  is_default: false
})

// 知识库上传选项
const kbUploadOptions = ref({
  chunking_strategy: 'llm',
  chunk_size: 800,
  chunk_overlap: 100,
  llm_mode: 'local'
})

// 知识库上传状态
const kbIsDragging = ref(false)
const kbIsUploading = ref(false)
const kbUploadProgress = ref({ current: 0, total: 0 })
const kbFileInput = ref(null)

// 知识库文档相关
const kbCurrentDoc = computed(() => kbStore.currentDoc)
const kbDocumentChunks = computed(() => kbStore.documentChunks)

// 数据抓取管理相关状态
const fetcherSystemStatus = ref(null)
const fetcherLoading = ref(false)
const fetcherError = ref(null)
const fetcherOperating = ref(false)
const era5HistoricalDate = ref('')
const era5FetchResult = ref(null)

// 定时任务管理相关状态
const scheduledTasksRefreshing = ref(false)

// 会话历史管理相关状态
const sessionHistoryLoading = ref(false)
const sessionHistoryData = ref([])
const sessionHistoryStats = ref(null)
const sessionHistoryFilter = ref('all')

// 社交平台管理相关状态
const socialPlatformLoading = ref(false)
const socialPlatformStatus = ref({
  qq: { enabled: false, running: false, logged_in: false },
  weixin: { enabled: false, running: false, logged_in: false }
})
const socialPlatformMetrics = ref({
  qq: { messages_received: 0, messages_sent: 0, error_rate: '0%' },
  weixin: { messages_received: 0, messages_sent: 0, error_rate: '0%' }
})
const socialPlatformHealth = ref({ healthy: true })
const socialPlatformCacheStats = ref({ hit_rate: '0%', size: 0 })
const showWeixinQRModal = ref(false)
const weixinQRCodeUrl = ref('')
const weixinQRLoading = ref(false)
const weixinLoginStatus = ref({ text: '等待扫描', class: 'waiting' })

// 获取今天的日期字符串
const today = new Date()
const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

const handleRerankerChange = (value) => {
  useReranker.value = value
}

const handleAgentModeChange = (value) => {
  // ✅ 处理多模式架构的模式变化
  store.switchMode(value)
  console.log('[ReactAnalysisView] Agent模式切换:', value)
}

// ========== 多模式响应式计算属性 ==========
// 确保模式切换时 UI 正确更新

// 当前模式的对话消息
const currentModeMessages = computed(() => store.currentState.messages)

// 当前模式的可视化数据
const currentModeVisualization = computed(() => store.currentState.currentVisualization)

// 当前模式的可视化历史
const currentModeVisualizationHistory = computed(() => store.currentState.visualizationHistory)

// 当前模式的专家结果
const currentModeExpertResults = computed(() => store.currentState.lastExpertResults)

// 当前模式的会话ID
const currentModeSessionId = computed(() => store.currentState.sessionId)

// 当前模式的分析状态
const currentModeIsAnalyzing = computed(() => store.currentState.isAnalyzing)

// 当前模式的当前消息
const currentModeCurrentMessage = computed(() => store.currentState.currentMessage)

const vizPanelStyle = computed(() => ({
  width: `${vizWidth.value}%`,  // 使用可拖动调整的宽度
  display: 'flex',
  flexDirection: 'column',
  overflowY: 'auto',
  maxHeight: '100vh',
  overflowX: 'hidden'
}))

const allVisualizations = computed(() => {
  const vizList = []
  if (store.currentState.visualizationHistory?.length) {
    vizList.push(...store.currentState.visualizationHistory)
  }
  if (store.currentState.currentVisualization) {
    if (store.currentState.currentVisualization.visuals) {
      // 兼容两种格式：VisualBlock格式 和 直接格式
      const visuals = store.currentState.currentVisualization.visuals.map(v => {
        if (v.payload) {
          return { ...v.payload, meta: v.meta }
        } else {
          return v
        }
      })
      vizList.push(...visuals)
    } else {
      vizList.push(store.currentState.currentVisualization)
    }
  }
  const seen = new Set()
  return vizList.filter(viz => {
    if (!viz) return false
    const key = viz.id || `${viz.type}_${JSON.stringify(viz.data || '')}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})

// 检测是否有Office文档操作
const hasOfficeDocuments = computed(() => {
  // 获取消息的引用，确保响应式
  const messages = store.messages

  // 检查每条消息
  const result = messages && messages.length > 0 && messages.some(msg => {
    if (msg && msg.type === 'observation' && msg.data && msg.data.observation) {
      const metadata = msg.data.observation.metadata || {}
      const generator = metadata.generator

      const isOfficeTool = ['word_edit', 'find_replace_word', 'accept_word_changes',
              'unpack_office', 'pack_office', 'recalc_excel', 'add_ppt_slide'].includes(generator)

      if (isOfficeTool) {
        console.log('[ReactAnalysisView] 检测到Office工具:', generator)
        const obs = msg.data.observation
        console.log('[ReactAnalysisView] observation数据:', {
          hasData: !!obs.data,
          hasPdfPreview: !!(obs.data && obs.data.pdf_preview),
          dataKeys: obs.data ? Object.keys(obs.data) : []
        })
      }

      return isOfficeTool
    }
    return false
  })

  console.log('[ReactAnalysisView] hasOfficeDocuments计算结果:', result, '消息数量:', messages?.length)
  return result
})

// 检测是否有可视化内容（图表或知识库溯源）
const hasVizContent = computed(() => {
  // 检查是否有可视化图表
  const hasCharts = allVisualizations.value && allVisualizations.value.length > 0

  // 检查是否有知识库溯源内容（选中消息且有sources）
  const hasSources = selectedMessageId.value !== null &&
    store.messages.some(msg => msg.id === selectedMessageId.value && msg.sources)

  // 检查是否有Office文档操作（检查消息中的observation + lastOfficeDocument）
  const hasOfficeFromMessages = hasOfficeDocuments.value
  const hasOfficeFromLastDoc = !!(store.lastOfficeDocument?.pdf_preview)
  const hasOffice = hasOfficeFromMessages || hasOfficeFromLastDoc

  return hasCharts || hasSources || hasOffice
})

// 监听内容变化，自动显示/隐藏面板
watch(hasVizContent, (newValue) => {
  console.log('[ReactAnalysisView] hasVizContent变化:', newValue)
  if (newValue && !vizPanelVisible.value) {
    vizPanelVisible.value = true
    console.log('[ReactAnalysisView] 设置vizPanelVisible为true')
  }
}, { immediate: true })

// 监听Office文档变化，自动显示/隐藏面板
watch(hasOfficeDocuments, (newValue) => {
  console.log('[ReactAnalysisView] hasOfficeDocuments变化:', newValue)
  officePanelVisible.value = newValue
  // 当检测到Office文档时，自动切换到文档标签页
  if (newValue) {
    activeRightTab.value = 'document'
  }
  console.log('[ReactAnalysisView] officePanelVisible已设置为:', newValue)
  console.log('[ReactAnalysisView] 面板状态:', {
    vizPanelVisible: vizPanelVisible.value,
    officePanelVisible: officePanelVisible.value,
    activeRightTab: activeRightTab.value,
    shouldShowRightPanel: vizPanelVisible.value || officePanelVisible.value
  })
}, { immediate: true })

// 监听右侧面板显示状态，自动展开/收起
watch([vizPanelVisible, officePanelVisible], ([viz, office]) => {
  const shouldShow = viz || office
  console.log('[ReactAnalysisView] 右侧面板状态变化:', {
    vizPanelVisible: viz,
    officePanelVisible: office,
    willShow: shouldShow
  })
  // 当有内容时自动展开面板，并联动左侧面板
  if (shouldShow) {
    rightPanelVisible.value = true
    // 右侧面板展开时，自动折叠左侧面板，并调整宽度为50%
    leftSidebarCollapsed.value = true
    vizWidth.value = collapsedVizWidth
  } else {
    rightPanelVisible.value = false
    // 右侧面板收起时，恢复左侧面板
    leftSidebarCollapsed.value = false
  }
}, { immediate: true })

// 监听office_document事件，自动显示文档面板
watch(() => store.lastOfficeDocument, (doc) => {
  if (doc?.pdf_preview) {
    console.log('[ReactAnalysisView] 检测到office_document事件:', {
      generator: doc.generator,
      pdf_id: doc.pdf_preview.pdf_id,
      file_path: doc.file_path
    })
    officePanelVisible.value = true
    activeRightTab.value = 'document'
  }
})

// 处理用户编辑提交
const handleOfficeEditSubmit = async (editData) => {
  try {
    // 调用后端API应用编辑
    const response = await fetch('/api/office/apply-edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: editData.file_path,
        content: editData.content,
        doc_type: editData.doc_type,
        session_id: store.currentState.sessionId || ''
      })
    })

    const result = await response.json()

    if (result.success) {
      // 显示提示消息
      showToast(result.message || '编辑已提交，正在处理...')

      // 退出编辑模式，等待Agent处理完成
      // Agent处理结果会通过SSE推送，自动更新PDF预览
      if (officePanelRef.value) {
        officePanelRef.value.cancelEdit()
      }
    } else {
      showToast('提交失败：' + result.message, 'error')
    }
  } catch (error) {
    console.error('提交编辑失败:', error)
    showToast('提交失败：' + error.message, 'error')
  }
}

// 简单的Toast提示
const showToast = (message, type = 'info') => {
  // 简单实现：使用现有的消息系统或console
  console.log(`[${type.toUpperCase()}] ${message}`)
  // TODO: 集成到现有的通知系统
}

// 切换可视化面板显示/隐藏
const toggleVizPanel = () => {
  const newState = !rightPanelVisible.value
  rightPanelVisible.value = newState
  // 联动左侧面板
  if (newState) {
    leftSidebarCollapsed.value = true
    vizWidth.value = collapsedVizWidth
  } else {
    leftSidebarCollapsed.value = false
  }
}

const openFullscreen = () => {
  fullscreenMode.value = true
}

const closeFullscreen = () => {
  fullscreenMode.value = false
  // 清理激活标签页存储
  localStorage.removeItem('activeExpertTab')
}

const handleExpertFullscreen = (expertType) => {
  // 始终保持多专家模式，但设置激活标签页
  if (!fullscreenMode.value) {
    // 首次打开时，保持当前assistantMode，但强制进入多专家模式
    fullscreenMode.value = true
    // 强制激活指定专家的标签页
    nextTick(() => {
      // 通过event bus或全局状态设置激活的专家标签
      // 这里使用localStorage作为临时方案
      localStorage.setItem('activeExpertTab', expertType)
      // 触发FullscreenDashboard更新
      window.dispatchEvent(new CustomEvent('setActiveExpertTab', { detail: expertType }))
    })
  }
}

const assistantNoticeMap = {
  'general-agent': '通用Agent已接入，支持自然语言提问和多轮交互。',
  'knowledge-base': '知识库管理页面，用于管理文档与知识检索。'
}

const assistantNotice = computed(() => {
  const noNoticeAssistants = ['general-agent']
  if (noNoticeAssistants.includes(activeAssistant.value)) {
    return ''
  }
  return assistantNoticeMap[activeAssistant.value] || '该助手尚未接入后台，敬请期待。'
})

const isAssistantReady = computed(() => {
  const readyAssistants = ['general-agent']
  return readyAssistants.includes(activeAssistant.value)
})

const inputPlaceholder = computed(() => {
  return '输入您的问题...'
})

const inputDisabled = computed(() => {
  const baseDisabled = !store.canInput && !store.isAnalyzing
  return baseDisabled || !isAssistantReady.value
})

const clampWidth = (value) => {
  return Math.min(maxVizWidth, Math.max(minVizWidth, value))
}

const updateWidthFromCursor = (clientX) => {
  if (!layoutRef.value) return
  const bounds = layoutRef.value.getBoundingClientRect()
  const vizPixels = bounds.right - clientX
  const percent = (vizPixels / bounds.width) * 100
  vizWidth.value = clampWidth(percent)
}

const handleMouseMove = (event) => {
  if (!isDragging.value) return

  // 如果鼠标按钮已经释放，自动停止拖动
  if (event.buttons === 0) {
    stopDragging()
    return
  }

  updateWidthFromCursor(event.clientX)
}

const stopDragging = () => {
  isDragging.value = false
}

const startDragging = (event) => {
  isDragging.value = true
  updateWidthFromCursor(event.clientX)
}

const resetWidth = () => {
  vizWidth.value = defaultVizWidth
}

// 对话区文件拖放处理
const handleChatAreaDragOver = (e) => {
  // 检查是否有文件被拖拽
  if (e.dataTransfer.types.includes('Files')) {
    chatAreaDragOver.value = true
    e.dataTransfer.dropEffect = 'copy'
  }
}

const handleChatAreaDragLeave = (e) => {
  // 检查鼠标是否真的离开了对话区（避免子元素触发）
  const rect = e.currentTarget.getBoundingClientRect()
  const x = e.clientX
  const y = e.clientY
  if (x < rect.left || x >= rect.right || y < rect.top || y >= rect.bottom) {
    chatAreaDragOver.value = false
  }
}

const handleChatAreaDrop = async (e) => {
  chatAreaDragOver.value = false

  const files = e.dataTransfer.files
  if (!files || files.length === 0) return

  // 如果 InputBox 有方法处理文件，调用它
  if (inputBoxRef.value && typeof inputBoxRef.value.handleFilesDrop === 'function') {
    await inputBoxRef.value.handleFilesDrop(files)
  }
}

const switchToGeneral = () => {
  activeAssistant.value = 'general-agent'
}

const handleAssistantSelect = async (moduleId) => {
  if (moduleId !== 'general-agent' && store.currentState.isAnalyzing) {
    await store.pauseAnalysis()
  }
}

// 处理侧边栏操作按钮
const handleSidebarAction = async (actionId) => {
  switch (actionId) {
    case 'tools-management':
      // 导航到工具管理页面
      router.push('/tools-management')
      break
    case 'knowledge-base':
      if (managementPanel.value === 'knowledge-base') {
        managementPanel.value = null
      } else {
        managementPanel.value = 'knowledge-base'
        await kbStore.fetchKnowledgeBases()
      }
      break
    case 'fetchers':
      if (managementPanel.value === 'fetchers') {
        managementPanel.value = null
      } else {
        managementPanel.value = 'fetchers'
        await refreshFetcherStatus()
      }
      break
    case 'scheduled-tasks':
      if (managementPanel.value === 'scheduled-tasks') {
        managementPanel.value = null
      } else {
        managementPanel.value = 'scheduled-tasks'
        await refreshScheduledTasks()
      }
      break
    case 'session-history':
      if (managementPanel.value === 'session-history') {
        managementPanel.value = null
      } else {
        managementPanel.value = 'session-history'
        await refreshSessionHistory()
      }
      break
    case 'social-platform':
      if (managementPanel.value === 'social-platform') {
        managementPanel.value = null
      } else {
        managementPanel.value = 'social-platform'
        await refreshSocialPlatformStatus()
      }
      break
    case 'restart-session':
      // 总是执行restart，确保可以重新开始
      store.restart()
      managementPanel.value = null
      // 新对话时隐藏右侧面板，同时重置所有面板状态
      vizPanelVisible.value = false
      officePanelVisible.value = false
      rightPanelVisible.value = false
      leftSidebarCollapsed.value = false
      break
  }
}

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

// 知识库管理方法
const selectKb = (kb) => {
  kbStore.selectKnowledgeBase(kb)
  // 初始化编辑表单
  kbEditForm.value = {
    name: kb.name,
    description: kb.description || '',
    is_default: kb.is_default
  }
}

const handleKbBack = () => {
  kbStore.currentKb = null
  kbStore.documents = []
}

const handleKbCreate = async () => {
  if (!kbCreateForm.value.name) return

  // 公共知识库需要管理员确认，否则后端会返回403
  if (kbCreateForm.value.kb_type === 'public' && !kbAdminConfirm.value) {
    alert('创建公共知识库需要管理员权限，请勾选确认。')
    return
  }

  try {
    // 同步管理员标识到 localStorage，供 API 请求头使用
    if (kbCreateForm.value.kb_type === 'public' && kbAdminConfirm.value) {
      localStorage.setItem('isAdmin', 'true')
    } else if (!kbAdminConfirm.value) {
      localStorage.removeItem('isAdmin')
    }

    await kbStore.createKnowledgeBase(kbCreateForm.value)
    showKbCreateDialog.value = false
    kbCreateForm.value = {
      name: '',
      description: '',
      kb_type: 'private',
      chunking_strategy: 'llm',
      chunk_size: 800,
      chunk_overlap: 100
    }
    kbAdminConfirm.value = localStorage.getItem('isAdmin') === 'true'
  } catch (e) {
    alert('创建失败: ' + e.message)
  }
}

const handleKbUpdate = async () => {
  if (!kbStore.currentKb || !kbEditForm.value.name) return

  try {
    await kbStore.updateKnowledgeBase(kbStore.currentKb.id, kbEditForm.value)
    showKbEditDialog.value = false
  } catch (e) {
    alert('更新失败: ' + e.message)
  }
}

const handleDeleteKb = async () => {
  if (!kbStore.currentKb) return
  if (!confirm(`确定要删除知识库"${kbStore.currentKb.name}"吗？此操作不可恢复。`)) return

  try {
    await kbStore.deleteKnowledgeBase(kbStore.currentKb.id)
    handleKbBack()
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

// 知识库文档上传相关方法
const triggerKbFileInput = () => {
  if (!kbIsUploading.value) {
    kbFileInput.value?.click()
  }
}

const handleKbFileSelect = async (event) => {
  const files = event.target.files
  if (files && files.length > 0) {
    await uploadKbFiles(Array.from(files))
  }
  event.target.value = ''
}

const handleKbFileDrop = async (event) => {
  kbIsDragging.value = false
  const files = event.dataTransfer?.files
  if (files && files.length > 0) {
    await uploadKbFiles(Array.from(files))
  }
}

const uploadKbFiles = async (files) => {
  if (!kbStore.currentKb || kbIsUploading.value) return

  kbIsUploading.value = true
  kbUploadProgress.value = { current: 0, total: files.length }

  for (const file of files) {
    try {
      kbUploadProgress.value.current++
      await kbStore.uploadDocument(kbStore.currentKb.id, file, {
        chunking_strategy: kbUploadOptions.value.chunking_strategy,
        chunk_size: kbUploadOptions.value.chunk_size,
        chunk_overlap: kbUploadOptions.value.chunk_overlap,
        llm_mode: kbUploadOptions.value.llm_mode
      })
    } catch (e) {
      alert(`上传"${file.name}"失败: ${e.message}`)
    }
  }

  kbIsUploading.value = false
}

const handleKbDeleteDoc = async (docId) => {
  if (!kbStore.currentKb) return
  if (!confirm('确定要删除此文档吗？')) return

  try {
    await kbStore.deleteDocument(kbStore.currentKb.id, docId)
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

const handleKbRetry = async (docId) => {
  if (!kbStore.currentKb) return
  try {
    await kbStore.retryDocument(kbStore.currentKb.id, docId)
  } catch (e) {
    alert('重试失败: ' + e.message)
  }
}

const viewKbChunks = async (doc) => {
  if (!kbStore.currentKb) return
  try {
    await kbStore.fetchDocumentChunks(kbStore.currentKb.id, doc.id)
    showKbChunksDialog.value = true
  } catch (e) {
    alert('获取分段失败: ' + e.message)
  }
}

const closeKbChunksDialog = () => {
  showKbChunksDialog.value = false
  kbStore.clearCurrentDoc()
}

// 知识库辅助方法
const getKbStrategyName = (strategy) => {
  const map = {
    sentence: '句子分块',
    semantic: '语义分块',
    markdown: 'Markdown分块',
    hybrid: '混合分块',
    llm: 'LLM智能分块'
  }
  return map[strategy] || strategy
}

const getKbStrategyDesc = (strategy) => {
  const map = {
    sentence: '按句子边界分割，适合大多数文档',
    semantic: '基于语义相似度分割，适合技术文档',
    markdown: '按Markdown标题层级分割，适合Markdown文档',
    hybrid: '多层级混合分割，适合长文档',
    llm: '使用大语言模型进行智能分割，质量最高但较慢'
  }
  return map[strategy] || ''
}

const getKbStatusText = (status) => {
  const map = {
    pending: '等待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '处理失败'
  }
  return map[status] || status
}

const getKbChunkTypeName = (type) => {
  const map = {
    paragraph: '正文',
    table: '表格',
    list: '列表',
    header: '标题',
    code: '代码'
  }
  return map[type] || type
}

// 数据抓取管理方法
const getFetcherStatusClass = (status) => {
  const classes = {
    'idle': 'idle',
    'running': 'running',
    'disabled': 'disabled',
    'error': 'error'
  }
  return classes[status] || 'unknown'
}

const getFetcherStatusText = (status) => {
  const texts = {
    'idle': '空闲',
    'running': '运行中',
    'disabled': '已禁用',
    'error': '错误'
  }
  return texts[status] || status
}

const refreshFetcherStatus = async () => {
  fetcherLoading.value = true
  fetcherError.value = null
  try {
    const response = await fetch('http://localhost:8000/api/system/status')
    const data = await response.json()
    fetcherSystemStatus.value = data
  } catch (err) {
    fetcherError.value = err.message
    console.error('Failed to fetch system status:', err)
  } finally {
    fetcherLoading.value = false
  }
}

const triggerFetcher = async (fetcherName) => {
  fetcherOperating.value = true
  try {
    const response = await fetch(`http://localhost:8000/api/fetchers/trigger/${fetcherName}`, {
      method: 'POST'
    })
    if (response.ok) {
      alert(`Fetcher "${fetcherName}" 已触发`)
      await refreshFetcherStatus()
    } else {
      const error = await response.json()
      alert(`触发失败: ${error.detail || '未知错误'}`)
    }
  } catch (err) {
    alert(`触发失败: ${err.message}`)
    console.error('Failed to trigger fetcher:', err)
  } finally {
    fetcherOperating.value = false
  }
}

const pauseFetcher = async (fetcherName) => {
  fetcherOperating.value = true
  try {
    const response = await fetch(`http://localhost:8000/api/fetchers/pause/${fetcherName}`, {
      method: 'POST'
    })
    if (response.ok) {
      alert(`Fetcher "${fetcherName}" 已暂停`)
      await refreshFetcherStatus()
    } else {
      const error = await response.json()
      alert(`暂停失败: ${error.detail || '未知错误'}`)
    }
  } catch (err) {
    alert(`暂停失败: ${err.message}`)
    console.error('Failed to pause fetcher:', err)
  } finally {
    fetcherOperating.value = false
  }
}

const resumeFetcher = async (fetcherName) => {
  fetcherOperating.value = true
  try {
    const response = await fetch(`http://localhost:8000/api/fetchers/resume/${fetcherName}`, {
      method: 'POST'
    })
    if (response.ok) {
      alert(`Fetcher "${fetcherName}" 已恢复`)
      await refreshFetcherStatus()
    } else {
      const error = await response.json()
      alert(`恢复失败: ${error.detail || '未知错误'}`)
    }
  } catch (err) {
    alert(`恢复失败: ${err.message}`)
    console.error('Failed to resume fetcher:', err)
  } finally {
    fetcherOperating.value = false
  }
}

const fetchEra5Historical = async () => {
  if (!era5HistoricalDate.value) {
    alert('请选择日期')
    return
  }

  fetcherOperating.value = true
  era5FetchResult.value = null

  try {
    const response = await fetch('http://localhost:8000/api/fetchers/era5/historical', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: era5HistoricalDate.value })
    })
    const result = await response.json()

    if (result.data) {
      era5FetchResult.value = result.data
      if (result.data.success) {
        alert('ERA5 数据补采成功')
      } else {
        alert('ERA5 数据补采完成，部分失败')
      }
    } else {
      alert('补采失败: ' + (result.detail || '未知错误'))
    }
  } catch (err) {
    alert('ERA5 数据补采失败: ' + err.message)
    console.error('Failed to fetch ERA5 historical data:', err)
  } finally {
    fetcherOperating.value = false
  }
}

// 定时任务管理方法
const refreshScheduledTasks = async () => {
  scheduledTasksRefreshing.value = true
  try {
    await Promise.all([
      scheduledTasksStore.fetchTasks(),
      scheduledTasksStore.fetchStats()
    ])
  } catch (error) {
    console.error('Failed to refresh tasks:', error)
    alert('刷新失败')
  } finally {
    scheduledTasksRefreshing.value = false
  }
}

const getScheduledTaskLabel = (type) => {
  const labels = {
    'daily_8am': '每天8:00',
    'every_2h': '每2小时',
    'every_30min': '每30分钟',
    'once': '一次性',
    'interval': '自定义间隔',
    'daily_custom': '每天自定义'
  }
  return labels[type] || type
}

const getScheduledTaskTagClass = (type) => {
  const classes = {
    'daily_8am': 'tag-success',
    'every_2h': 'tag-warning',
    'every_30min': 'tag-info'
  }
  return classes[type] || ''
}

const formatScheduledNextRun = (time) => {
  if (!time) return '未安排'
  const date = new Date(time)
  const now = new Date()
  const diff = date - now

  if (diff < 0) return '即将运行'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟后`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时后`
  return date.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

const handleScheduledTaskToggle = async (task) => {
  task.toggling = true
  try {
    if (task.enabled) {
      await scheduledTasksStore.disableTask(task.task_id)
      task.enabled = false
    } else {
      await scheduledTasksStore.enableTask(task.task_id)
      task.enabled = true
    }
  } catch (error) {
    alert('操作失败')
  } finally {
    task.toggling = false
  }
}

const executeScheduledTask = async (task) => {
  if (!confirm(`确定立即执行任务"${task.name}"吗？`)) {
    return
  }

  task.executing = true
  try {
    const result = await scheduledTasksStore.executeTaskNow(task.task_id)
    alert(`任务已开始执行，执行ID: ${result.execution_id}`)
    await refreshScheduledTasks()
  } catch (error) {
    console.error('Failed to execute task:', error)
    alert('执行失败')
  } finally {
    task.executing = false
  }
}

const editScheduledTask = (task) => {
  alert('编辑功能开发中...')
}

const deleteScheduledTask = async (task) => {
  if (!confirm(`确定删除任务"${task.name}"吗？此操作不可恢复。`)) {
    return
  }

  try {
    await scheduledTasksStore.deleteTask(task.task_id)
    alert('任务已删除')
  } catch (error) {
    alert('删除失败')
  }
}

// 会话历史管理方法
const refreshSessionHistory = async () => {
  sessionHistoryLoading.value = true
  try {
    // 获取会话列表
    const listResponse = await fetch('/api/sessions')
    if (!listResponse.ok) throw new Error('Failed to fetch sessions')
    const listData = await listResponse.json()
    sessionHistoryData.value = listData.sessions || []

    // 获取统计数据
    const statsResponse = await fetch('/api/sessions/stats')
    if (!statsResponse.ok) throw new Error('Failed to fetch stats')
    sessionHistoryStats.value = await statsResponse.json()
  } catch (error) {
    console.error('Failed to refresh session history:', error)
    alert('刷新失败')
  } finally {
    sessionHistoryLoading.value = false
  }
}

const getSessionHistoryFilterLabel = (filter) => {
  const labels = {
    'all': '全部',
    'active': '活跃',
    'completed': '已完成',
    'failed': '失败',
    'archived': '已归档'
  }
  return labels[filter] || filter
}

const getSessionHistoryFilterIcon = (filter) => {
  const icons = {
    'all': '📚',
    'active': '🔵',
    'completed': '✅',
    'failed': '❌',
    'archived': '📦'
  }
  return icons[filter] || '⚪'
}

const getSessionHistoryFilterClass = (filter) => {
  return `filter-${filter}`
}

const getSessionHistoryStateIcon = (state) => {
  const icons = {
    'active': '🔵',
    'paused': '⏸️',
    'completed': '✅',
    'failed': '❌',
    'archived': '📦'
  }
  return icons[state] || '⚪'
}

const getSessionHistoryStateClass = (state) => {
  return `state-${state}`
}

const formatSessionTime = (timestamp) => {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  const days = Math.floor(diff / 86400000)
  if (days < 7) return `${days}天前`

  return date.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const formatSessionFullTime = (timestamp) => {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const getTruncatedQuery = (query, maxLength = 80) => {
  if (query.length <= maxLength) return query
  return query.substring(0, maxLength) + '...'
}

const getRecentSessions = () => {
  // 返回最近10条会话，按更新时间排序
  const sorted = [...sessionHistoryData.value].sort((a, b) => {
    return new Date(b.updated_at) - new Date(a.updated_at)
  })
  return sorted.slice(0, 10)
}

const quickLoadSession = async (session) => {
  if (!confirm(`确定要加载对话"${getTruncatedQuery(session.query, 30)}..."吗？`)) {
    return
  }

  try {
    const response = await restoreSession(session.session_id)
    console.log('[会话恢复] API响应完整数据:', response)

    const sessionData = response.session

    if (!sessionData?.conversation_history || sessionData.conversation_history.length === 0) {
      console.warn('[会话恢复] conversation_history为空或不存在')
      alert('会话历史为空，无法恢复')
      return
    }

    // 使用新的 set 方法恢复会话状态
    store.setSessionId(sessionData.session_id)

    // 恢复对话历史
    if (Array.isArray(sessionData.conversation_history)) {
      store.setMessages(sessionData.conversation_history)
      console.log('[会话恢复] 已恢复对话历史，消息数量:', store.currentState.messages.length)
    }

    // 恢复分析状态
    if (sessionData.last_result) {
      store.currentState.lastExpertResults = sessionData.last_result
      console.log('[会话恢复] 已恢复分析结果')
    }

    // 恢复可视化历史
    if (sessionData.visualizations && Array.isArray(sessionData.visualizations)) {
      store.setVisualizationHistory(sessionData.visualizations)
      console.log('[会话恢复] 已恢复可视化历史，图表数量:', store.currentState.visualizationHistory.length)
    }

    // 恢复专家结果
    if (sessionData.expert_results) {
      store.setLastExpertResults(sessionData.expert_results)
      console.log('[会话恢复] 已恢复专家结果')
    }

    // 关闭管理面板并显示成功提示
    managementPanel.value = null
    alert(`已加载对话，共 ${store.currentState.messages.length} 条消息`)

  } catch (error) {
    console.error('Failed to restore session:', error)
    alert('加载对话失败: ' + error.message)
  }
}

const getShortSessionId = (sessionId) => {
  return sessionId.substring(0, 12)
}

const getSessionHistoryFilterCount = (filterValue) => {
  if (!sessionHistoryStats.value) return 0
  if (filterValue === 'all') return sessionHistoryStats.value.total || 0
  return sessionHistoryStats.value.by_state?.[filterValue] || 0
}

const getFilteredSessions = () => {
  if (sessionHistoryFilter.value === 'all') {
    return sessionHistoryData.value
  }
  return sessionHistoryData.value.filter(s => s.state === sessionHistoryFilter.value)
}

const handleSessionArchive = async (sessionId) => {
  try {
    const response = await fetch(`/api/sessions/${sessionId}/archive`, { method: 'POST' })
    if (!response.ok) throw new Error('Failed to archive session')
    alert(`会话 ${sessionId.substring(0, 12)}... 已归档`)
    await refreshSessionHistory()
  } catch (error) {
    console.error('Failed to archive session:', error)
    alert('归档失败: ' + error.message)
  }
}

const handleSessionExport = async (sessionId) => {
  try {
    const response = await fetch(`/api/sessions/${sessionId}/export`, { method: 'POST' })
    if (!response.ok) throw new Error('Failed to export session')
    alert(`会话 ${sessionId.substring(0, 12)}... 已导出到服务器`)
  } catch (error) {
    console.error('Failed to export session:', error)
    alert('导出失败: ' + error.message)
  }
}

const handleSessionDelete = async (sessionId) => {
  if (!confirm(`确定要删除会话 ${sessionId.substring(0, 12)}... 吗？此操作不可恢复。`)) {
    return
  }

  try {
    const response = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
    if (!response.ok) throw new Error('Failed to delete session')
    // 从列表中移除
    sessionHistoryData.value = sessionHistoryData.value.filter(s => s.session_id !== sessionId)
    // 刷新统计
    await refreshSessionHistory()
  } catch (error) {
    console.error('Failed to delete session:', error)
    alert('删除失败: ' + error.message)
  }
}

const handleSessionCleanup = async () => {
  if (!confirm('确定要清理所有过期会话吗？此操作将删除超过保留期限的已完成/失败会话。')) {
    return
  }

  try {
    const response = await fetch('/api/sessions/cleanup', { method: 'POST' })
    if (!response.ok) throw new Error('Failed to cleanup sessions')
    const data = await response.json()
    alert(`已清理 ${data.deleted_count} 个过期会话`)
    await refreshSessionHistory()
  } catch (error) {
    console.error('Failed to cleanup sessions:', error)
    alert('清理失败: ' + error.message)
  }
}

// 社交平台管理方法
const refreshSocialPlatformStatus = async () => {
  socialPlatformLoading.value = true
  try {
    // 获取平台状态
    const statusResponse = await fetch('/api/social/status')
    if (statusResponse.ok) {
      const statusData = await statusResponse.json()
      console.log('🔍 社交平台状态原始数据:', statusData)

      // 如果后端返回空channels，使用配置文件状态（临时兜底）
      if (!statusData.channels || Object.keys(statusData.channels).length === 0) {
        socialPlatformStatus.value = {
          qq: { enabled: false, running: false, logged_in: false },
          // 默认启用微信（根据配置文件 social_config.yaml）
          weixin: { enabled: true, running: false, logged_in: false }
        }
      } else {
        // 确保 logged_in 字段存在
        const channels = {}
        for (const [key, value] of Object.entries(statusData.channels)) {
          channels[key] = {
            ...value,
            logged_in: value.logged_in || false
          }
        }
        socialPlatformStatus.value = channels
      }
      console.log('✅ 社交平台状态处理后:', socialPlatformStatus.value)
      console.log('✅ 微信登录状态:', socialPlatformStatus.value.weixin?.logged_in)
      console.log('✅ 按钮应该显示:', !socialPlatformStatus.value.weixin?.logged_in)
    }

    // 获取性能指标
    const metricsResponse = await fetch('/api/social/metrics')
    if (metricsResponse.ok) {
      const metricsData = await metricsResponse.json()
      socialPlatformMetrics.value = metricsData.channels || {
        qq: { messages_received: 0, messages_sent: 0, error_rate: '0%' },
        weixin: { messages_received: 0, messages_sent: 0, error_rate: '0%' }
      }
    }

    // 获取健康状态
    const healthResponse = await fetch('/api/social/health')
    if (healthResponse.ok) {
      socialPlatformHealth.value = await healthResponse.json()
    }

    // 获取缓存统计
    const cacheResponse = await fetch('/api/social/cache/stats')
    if (cacheResponse.ok) {
      socialPlatformCacheStats.value = await cacheResponse.json()
    }
  } catch (error) {
    console.error('Failed to refresh social platform status:', error)
  } finally {
    socialPlatformLoading.value = false
  }
}

const getPlatformStatusText = (platform) => {
  if (!platform?.enabled) return '未启用'
  if (!platform?.running) return '已停止'
  if (platform?.logged_in) return '已登录'
  return '运行中'
}

const getPlatformStatusClass = (platform) => {
  if (!platform?.enabled) return 'status-disabled'
  if (!platform?.running) return 'status-stopped'
  if (platform?.logged_in) return 'status-success'
  return 'status-running'
}

const refreshWeixinQRCode = async () => {
  weixinQRLoading.value = true
  weixinQRCodeUrl.value = ''

  try {
    const response = await fetch('/api/social/weixin/qrcode')
    if (!response.ok) throw new Error('Failed to fetch QR code')

    const blob = await response.blob()
    weixinQRCodeUrl.value = URL.createObjectURL(new Blob([blob]))

    // 重置登录状态
    weixinLoginStatus.value = { text: '等待扫描', class: 'waiting' }

    // 开始轮询登录状态
    startWeixinLoginPolling()
  } catch (error) {
    console.error('Failed to fetch QR code:', error)
    alert('获取二维码失败')
  } finally {
    weixinQRLoading.value = false
  }
}

const checkWeixinLoginStatus = async () => {
  try {
    const response = await fetch('/api/social/weixin/status')
    if (!response.ok) throw new Error('Failed to check status')

    const status = await response.json()

    if (status.logged_in) {
      weixinLoginStatus.value = { text: '登录成功！', class: 'success' }
      showWeixinQRModal.value = false
      await refreshSocialPlatformStatus()

      // 停止轮询
      stopWeixinLoginPolling()
    } else if (status.scanned) {
      weixinLoginStatus.value = { text: '已扫描，等待确认', class: 'scanned' }
    }
  } catch (error) {
    console.error('Failed to check login status:', error)
  }
}

let weixinLoginPollingInterval = null

const startWeixinLoginPolling = () => {
  stopWeixinLoginPolling()
  weixinLoginPollingInterval = setInterval(() => {
    checkWeixinLoginStatus()
  }, 3000)
}

const stopWeixinLoginPolling = () => {
  if (weixinLoginPollingInterval) {
    clearInterval(weixinLoginPollingInterval)
    weixinLoginPollingInterval = null
  }
}

const toggleSessionExpand = (session) => {
  session.isExpanded = !session.isExpanded
}

// 从侧边栏快速加载会话
const handleLoadSession = async (sessionId) => {
  try {
    const response = await restoreSession(sessionId)
    console.log('[快速加载会话] API响应:', response)

    const sessionData = response.session

    if (!sessionData?.conversation_history || sessionData.conversation_history.length === 0) {
      alert('会话历史为空，无法恢复')
      return
    }

    // 更新当前会话ID（使用 Pinia 状态的 sessionId，而非 currentSessionId）
    store.setSessionId(sessionData.session_id)

    // 恢复对话历史
    if (Array.isArray(sessionData.conversation_history)) {
      store.setMessages(sessionData.conversation_history)
      console.log('[快速加载会话] 已恢复对话历史，消息数量:', store.currentState.messages.length)
    }

    // 恢复分析状态
    if (sessionData.last_result) {
      store.currentState.lastExpertResults = sessionData.last_result
    }

    // 恢复可视化历史
    if (sessionData.visualizations && Array.isArray(sessionData.visualizations)) {
      store.setVisualizationHistory(sessionData.visualizations)
    }

    // 恢复专家结果
    if (sessionData.expert_results) {
      store.setLastExpertResults(sessionData.expert_results)
    }

    // 【新增】恢复Office文档预览（用于历史对话PDF预览）
    if (sessionData.office_documents && Array.isArray(sessionData.office_documents) && sessionData.office_documents.length > 0) {
      console.log('[快速加载会话] 恢复Office文档预览，数量:', sessionData.office_documents.length)

      // 方案1：使用OfficeDocumentPanel的loadDocuments方法（推荐）
      if (officePanelRef.value && typeof officePanelRef.value.loadDocuments === 'function') {
        officePanelRef.value.loadDocuments(sessionData.office_documents)
        console.log('[快速加载会话] 已通过loadDocuments恢复Office文档')
      } else {
        // 方案2：回退方案 - 依次注入到lastOfficeDocument（兼容性）
        console.warn('[快速加载会话] loadDocuments方法不可用，使用回退方案')
        sessionData.office_documents.forEach((doc, index) => {
          setTimeout(() => {
            store.lastOfficeDocument = {
              pdf_preview: doc.pdf_preview,
              file_path: doc.file_path,
              generator: doc.generator,
              summary: doc.summary,
              timestamp: doc.timestamp
            }
            console.log('[快速加载会话] 已恢复Office文档:', index + 1, doc.file_path)
          }, index * 50)
        })
      }
    }

  } catch (error) {
    console.error('Failed to load session:', error)
    alert('加载对话失败: ' + error.message)
  }
}

// 选择消息查看来源详情（支持所有final消息）
function selectMessage(index, message) {
  const msg = message || store.currentState.messages[index]
  if (!msg) return

  // 如果点击的是final消息
  if (msg.type === 'final') {
    if (selectedMessageId.value === msg.id) {
      // 取消选择
      selectedMessageId.value = null
    } else {
      // 选择该消息
      selectedMessageId.value = msg.id
    }
  }
}

onMounted(async () => {
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', stopDragging)
  window.addEventListener('keydown', handleKeyboardShortcuts)
  await store.init()
  // 加载知识库列表并自动全选
  await kbStore.fetchKnowledgeBases()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', stopDragging)
  window.removeEventListener('keydown', handleKeyboardShortcuts)
})

// 键盘快捷键：Ctrl+1~5 切换模式
const handleKeyboardShortcuts = (e) => {
  // 检查是否在输入框中（如果在输入框中，不触发快捷键）
  if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') {
    return
  }

  // Ctrl+1~5 快速切换模式
  if (e.ctrlKey && e.key >= '1' && e.key <= '5') {
    e.preventDefault()
    const modeMap = {
      '1': 'assistant',
      '2': 'expert',
      '3': 'query',
      '4': 'code',
      '5': 'report'
    }
    const mode = modeMap[e.key]
    if (mode) {
      store.switchMode(mode)
      console.log('[键盘快捷键] 切换到模式:', mode)
    }
  }
}

const handleSend = async (payload) => {
  if (!isAssistantReady.value) return

  // 处理新的输入格式：可能是字符串（向后兼容）或对象
  const query = typeof payload === 'string' ? payload : payload.query
  const knowledgeBaseIds = typeof payload === 'object' ? payload.knowledgeBaseIds || [] : []
  const agentMode = typeof payload === 'object' ? payload.agentMode || store.agentMode : store.agentMode  // ✅ 使用store.agentMode作为默认值
  const attachments = typeof payload === 'object' ? payload.attachments || null : null  // ✅ 提取附件信息

  // 构建分析选项
  const options = {
    assistantMode: activeAssistant.value,
    knowledgeBaseIds: knowledgeBaseIds,  // 选中的知识库ID列表
    agentMode: agentMode,  // ✅ 双模式架构：assistant | expert
    attachments: attachments  // ✅ 传递附件信息
  }

  // 根据选择的助手模式调用不同的分析方法
  if (activeAssistant.value === 'general-agent') {
    // 通用Agent模式：支持真正的ReAct循环
    // 思考→行动→观察的自主决策过程
    if (store.hasResults) {
      await store.continueAnalysis(query, options)
    } else {
      await store.startAnalysis(query, options)
    }
  } else {
    // 其他助手模式未实现
    store.addMessage('error', '该助手模式尚未实现，请选择通用Agent')
  }
}

const handlePause = async () => {
  await store.pauseAnalysis()
}

// 会话恢复处理
const handleSessionRestore = async (sessionId) => {
  try {
    console.log('[会话恢复] 开始恢复会话:', sessionId)

    // 调用后端恢复接口
    const response = await restoreSession(sessionId)
    console.log('[会话恢复] API响应完整数据:', response)
    console.log('[会话恢复] response.session存在:', !!response?.session)

    const sessionData = response.session

    console.log('[会话恢复] sessionData keys:', Object.keys(sessionData || {}))
    console.log('[会话恢复] conversation_history存在:', !!sessionData?.conversation_history)
    console.log('[会话恢复] conversation_history长度:', sessionData?.conversation_history?.length)

    // 检查conversation_history是否为空
    if (!sessionData?.conversation_history || sessionData.conversation_history.length === 0) {
      console.warn('[会话恢复] conversation_history为空或不存在')
      alert('会话历史为空，无法恢复')
      return
    }

    // 打印前3条原始消息
    console.log('[会话恢复] 前3条原始消息:', sessionData.conversation_history.slice(0, 3))

    // 更新当前会话ID
    store.setSessionId(sessionData.session_id)
    console.log('[会话恢复] 已更新sessionId:', sessionData.session_id)

    // ✅ 转换旧格式消息（兼容没有 content 字段的历史消息）
    const convertedHistory = (sessionData.conversation_history || []).map((msg, index) => {
      console.log(`[会话恢复] 转换消息 ${index}:`, {
        type: msg.type,
        hasContent: !!msg.content,
        hasData: !!msg.data,
        dataKeys: msg.data ? Object.keys(msg.data) : []
      })

      // 如果已经有 content 字段，直接返回
      if (msg.content) {
        console.log(`[会话恢复] 消息 ${index} 已有content，直接返回`)
        return msg
      }

      // 转换旧格式：从 data 中提取 content
      const converted = { ...msg }

      if (msg.type === 'thought' && msg.data?.thought) {
        converted.content = msg.data.thought
        console.log(`[会话恢复] 消息 ${index} 转换thought:`, converted.content.substring(0, 50))
      } else if (msg.type === 'action' && msg.data?.action) {
        const toolName = msg.data.action.tool || ''
        converted.content = toolName ? `调用工具: ${toolName}` : '执行行动'
        console.log(`[会话恢复] 消息 ${index} 转换action:`, converted.content)
      } else if (msg.type === 'observation' && msg.data?.observation) {
        const obs = msg.data.observation
        converted.content = obs.summary || '获得结果'
        console.log(`[会话恢复] 消息 ${index} 转换observation:`, converted.content.substring(0, 50))
      } else if (msg.type === 'user') {
        // 用户消息可能直接在 data 中
        converted.content = msg.data?.content || msg.data || ''
        console.log(`[会话恢复] 消息 ${index} 转换user:`, converted.content)
      } else if (msg.type === 'final') {
        // 最终答案
        converted.content = msg.data?.answer || ''
        console.log(`[会话恢复] 消息 ${index} 转换final:`, converted.content.substring(0, 50))
      } else {
        console.warn(`[会话恢复] 消息 ${index} 无法转换，类型:`, msg.type)
      }

      return converted
    })

    console.log('[会话恢复] 转换后的消息数量:', convertedHistory.length)
    console.log('[会话恢复] 转换后前3条消息:', convertedHistory.slice(0, 3))

    // 清空现有消息并恢复会话状态到store（使用新的setMessages方法）
    console.log('[会话恢复] 清空前 store.currentState.messages 长度:', store.currentState.messages.length)

    // 使用 store 的 restoreSessionState 方法批量恢复状态
    store.setSessionId(sessionData.session_id)
    store.setMessages(convertedHistory)

    console.log('[会话恢复] 赋值后 store.currentState.messages 长度:', store.currentState.messages.length)
    console.log('[会话恢复] 赋值后 store.currentState.messages 前3条:', store.currentState.messages.slice(0, 3))

    // 等待DOM更新
    await nextTick()
    console.log('[会话恢复] nextTick后 store.currentState.messages 长度:', store.currentState.messages.length)

    // 如果有数据ID，可以加载相关数据
    if (sessionData.data_ids && sessionData.data_ids.length > 0) {
      console.log('[会话恢复] 会话包含数据ID:', sessionData.data_ids)
      // 这里可以根据需要加载数据和可视化
    }

    // 显示成功提示
    alert(`会话 ${sessionId.substring(0, 12)}... 已成功恢复，共 ${convertedHistory.length} 条消息`)
  } catch (error) {
    console.error('[会话恢复] 恢复会话失败:', error)
    console.error('[会话恢复] 错误堆栈:', error.stack)
    alert('恢复会话失败: ' + error.message)
  }
}
</script>

<style lang="scss" scoped>
.react-analysis-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f6fb;
}

.main-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.analysis-panel {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid #f0f0f5;
  min-width: 360px;
  position: relative;
  transition: background-color 0.2s, box-shadow 0.2s;

  &.drag-over {
    background: #e3f2fd;
    box-shadow: inset 0 0 0 2px #1976d2;

    &::after {
      content: '拖放文件到此处上传';
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      font-size: 18px;
      color: #1976d2;
      font-weight: 500;
      pointer-events: none;
      z-index: 100;
    }
  }
}

.management-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fafafa;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e0e0e0;
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.close-btn {
  padding: 6px 12px;
  border: 1px solid #e0e0e0;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.close-btn:hover {
  background: #f0f0f0;
}

.panel-content {
  padding: 20px;
}

.panel-content p {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.panel-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.panel-btn {
  padding: 6px 12px;
  border: 1px solid #e0e0e0;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.panel-btn:hover {
  background: #f0f0f0;
}

.panel-btn.small {
  padding: 4px 8px;
  font-size: 12px;
}

.panel-btn.danger {
  color: #ff4d4f;
  border-color: #ff4d4f;
}

.panel-btn.danger:hover {
  background: #fff1f0;
}

/* 知识库管理面板样式 */
.kb-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kb-content {
  padding: 12px 16px;
}

.kb-section {
  margin-bottom: 16px;
}

.kb-section:last-child {
  margin-bottom: 0;
}

.kb-section-title {
  font-size: 12px;
  color: #666;
  padding: 4px 0;
  font-weight: 500;
}

.kb-item {
  padding: 10px 12px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.kb-item:hover {
  border-color: #1890ff;
}

.kb-item.active {
  border-color: #1890ff;
  background: #e6f7ff;
}

.kb-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.kb-name {
  font-weight: 500;
  font-size: 14px;
}

.kb-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
}

.kb-badge.public {
  background: #e6f7ff;
  color: #1890ff;
}

.kb-badge.private {
  background: #f6ffed;
  color: #52c41a;
}

.kb-meta {
  font-size: 12px;
  color: #999;
}

.kb-empty {
  text-align: center;
  padding: 40px 20px;
  color: #999;
  font-size: 14px;
}

.kb-detail {
  border-top: 1px solid #e0e0e0;
  padding: 12px 16px;
  background: #fafafa;
}

.kb-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.kb-detail-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.kb-detail-actions {
  display: flex;
  gap: 4px;
}

.kb-detail-desc {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.kb-detail-info {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #666;
}

.scenario-selector-wrapper {
  padding: 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
}

.assistant-notice {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fff7e6;
  border-bottom: 1px solid #ffe6bf;
  color: #ad6a00;
  font-size: 13px;
}

.notice-button {
  border: none;
  background: #ffb74d;
  color: #fff;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  cursor: pointer;
}

// 可视化面板折叠/展开按钮
.viz-toggle-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 32px;
  height: 32px;
  border: 1px solid #e0e0e0;
  background: #fff;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 10;
  transition: all 0.2s;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

  &:hover {
    border-color: #1976d2;
    color: #1976d2;
    box-shadow: 0 2px 8px rgba(25, 118, 210, 0.2);
  }

  .toggle-icon {
    font-size: 16px;
    font-weight: bold;
    transition: transform 0.2s;
  }

  &.expanded .toggle-icon {
    transform: rotate(180deg);
  }
}

.viz-wrapper {
  height: 100%;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  background: #fff;
}

.right-panel-tabs {
  display: flex;
  border-bottom: 1px solid #e0e0e0;
  background: #fafafa;
  flex-shrink: 0;
}

.tab-btn {
  flex: 1;
  padding: 10px 16px;
  border: none;
  background: transparent;
  color: #666;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
}

.tab-btn:hover {
  color: #1976d2;
  background: #f0f7ff;
}

.tab-btn.active {
  color: #1976d2;
  border-bottom-color: #1976d2;
  background: #fff;
}

.resize-handle {
  width: 8px;
  cursor: col-resize;
  background: #e0e0e0;
  border-left: 1px solid #ccc;
  border-right: 1px solid #ccc;
  flex-shrink: 0;
  position: relative;
  z-index: 200;
}

.drag-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: transparent;
  z-index: 9999;
  cursor: col-resize;
}

@media (max-width: 1280px) {
  .react-analysis-view {
    height: auto;
  }

  .main-layout {
    flex-direction: column;
  }

  .analysis-panel {
    flex-direction: column;
  }

  .chat-area {
    min-width: 100%;
  }

  .resize-handle {
    height: 6px;
    width: 100%;
    cursor: row-resize;
  }

  .viz-wrapper {
    width: 100% !important;
  }
}

/* 知识库完整样式 */
.kb-detail-full {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.kb-detail-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kb-detail-title h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.kb-upload-section {
  margin-top: 16px;
  margin-bottom: 16px;
}

.chunking-options {
  margin-bottom: 12px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #e8e8e8;
}

.kb-documents-section {
  margin-top: 16px;
}

.kb-empty-docs {
  text-align: center;
  padding: 20px;
  color: #999;
  font-size: 13px;
}

.kb-doc-list {
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  overflow: hidden;
}

.kb-doc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.2s;
}

.kb-doc-item:last-child {
  border-bottom: none;
}

.kb-doc-item.clickable {
  cursor: pointer;
}

.kb-doc-item.clickable:hover {
  background: #f5f7fa;
}

.kb-doc-info {
  flex: 1;
}

.kb-doc-name {
  font-weight: 500;
  font-size: 14px;
  display: block;
}

.kb-doc-meta {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.kb-doc-actions {
  display: flex;
  gap: 4px;
}

.kb-btn-text {
  background: none;
  border: none;
  color: #1890ff;
  cursor: pointer;
  font-size: 12px;
  padding: 4px 8px;
}

.kb-btn-text:hover {
  background: #f0f7ff;
  border-radius: 4px;
}

.kb-btn-text.danger {
  color: #ff4d4f;
}

.kb-btn-text.danger:hover {
  background: #fff1f0;
}

.upload-area {
  border: 2px dashed #d9d9d9;
  border-radius: 6px;
  padding: 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.upload-area:hover,
.upload-area.dragging {
  border-color: #1890ff;
  background: #f0f7ff;
}

.upload-area.uploading {
  cursor: not-allowed;
  background: #fafafa;
}

.upload-hint {
  font-size: 12px;
  color: #999;
  margin-top: 8px;
}

.upload-note {
  font-size: 12px;
  color: #faad14;
  margin-top: 8px;
}

.upload-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #f0f0f0;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.status-completed {
  color: #52c41a;
}

.status-processing {
  color: #1890ff;
}

.status-failed {
  color: #ff4d4f;
}

.status-pending {
  color: #faad14;
}

.view-hint {
  color: #1890ff;
  margin-left: 8px;
  font-size: 11px;
}

/* 对话框样式 */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: #fff;
  border-radius: 8px;
  width: 480px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
}

.dialog-header h3 {
  margin: 0;
  font-size: 16px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
  line-height: 1;
}

.btn-close:hover {
  color: #333;
}

.dialog-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #f0f0f0;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.form-group input[type="text"],
.form-group input[type="number"],
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
}

.form-group textarea {
  min-height: 80px;
  resize: vertical;
}

.form-hint {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.form-hint.danger {
  color: #ff4d4f;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-row .form-group {
  flex: 1;
}

.checkbox-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.btn-primary {
  background: #1890ff;
  color: #fff;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:hover {
  background: #40a9ff;
}

.btn-primary:disabled {
  background: #d9d9d9;
  cursor: not-allowed;
}

.btn-secondary {
  background: #fff;
  color: #333;
  border: 1px solid #d9d9d9;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-secondary:hover {
  border-color: #40a9ff;
  color: #40a9ff;
}

.btn-back {
  background: none;
  border: 1px solid #d9d9d9;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
}

.btn-back:hover {
  border-color: #1890ff;
  color: #1890ff;
}

/* 分段全屏样式 */
.chunks-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #f5f6fb;
  z-index: 1000;
  display: flex;
  flex-direction: column;
}

.chunks-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
}

.chunks-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

.chunks-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.chunks-count {
  font-size: 14px;
  color: #666;
  background: #f0f0f0;
  padding: 4px 12px;
  border-radius: 12px;
}

.chunks-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.chunks-list-full {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chunk-card {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.chunk-card-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
}

.chunk-number {
  font-weight: 600;
  color: #1890ff;
  font-size: 14px;
}

.chunk-length {
  font-size: 13px;
  color: #666;
}

.chunk-position {
  font-size: 12px;
  color: #999;
  margin-left: auto;
}

.chunk-metadata {
  padding: 12px 20px;
  background: #f0f7ff;
  border-bottom: 1px solid #e6f0fa;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.metadata-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.metadata-label {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.metadata-value {
  font-size: 13px;
  color: #1890ff;
}

.type-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.type-paragraph {
  background: #e6f7ff;
  color: #1890ff;
}

.type-table {
  background: #f6ffed;
  color: #52c41a;
}

.type-list {
  background: #fff7e6;
  color: #fa8c16;
}

.type-header {
  background: #fff1f0;
  color: #ff4d4f;
}

.type-code {
  background: #f0f0f0;
  color: #666;
}

.chunk-card-body {
  padding: 20px;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  color: #333;
}

/* 数据抓取管理面板样式 */
.fetchers-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.fetchers-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.fetchers-status-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  border: 1px solid #e8e8e8;
}

.fetchers-status-card h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.fetchers-status-card .status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}

.fetchers-status-card .status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 4px;
  font-size: 13px;
}

.fetchers-status-card .status-item .label {
  font-weight: 500;
  color: #666;
}

.fetchers-status-card .status-value {
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.fetchers-status-card .status-value.running {
  color: #52c41a;
  background: #f6ffed;
}

.fetchers-status-card .status-value.stopped {
  color: #ff4d4f;
  background: #fff1f0;
}

.era5-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  border: 1px solid #e8e8e8;
}

.era5-card h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.era5-desc {
  margin: 0 0 16px 0;
  font-size: 13px;
  color: #666;
}

.era5-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.date-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.date-input-group label {
  font-size: 13px;
  color: #666;
  white-space: nowrap;
}

.date-input {
  padding: 6px 10px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 13px;
  color: #333;
  background: #fff;
}

.fetch-result {
  margin-top: 16px;
  border-radius: 6px;
  overflow: hidden;
}

.fetch-result.success {
  border: 1px solid #52c41a;
  background: #f6ffed;
}

.fetch-result.warning {
  border: 1px solid #faad14;
  background: #fffbe6;
}

.fetch-result .result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(0,0,0,0.1);
}

.fetch-result .result-icon {
  font-size: 16px;
  font-weight: bold;
}

.fetch-result.success .result-icon {
  color: #52c41a;
}

.fetch-result.warning .result-icon {
  color: #faad14;
}

.fetch-result .result-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.fetch-result .result-details {
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
}

.fetch-result .result-row {
  display: flex;
  align-items: center;
  font-size: 13px;
}

.fetch-result .result-row .label {
  color: #666;
  margin-right: 4px;
}

.fetch-result .result-row .value {
  color: #333;
  font-weight: 600;
}

.fetch-result .result-row .success-text {
  color: #52c41a;
}

.fetch-result .result-row .error-text {
  color: #ff4d4f;
}

.fetchers-list-section {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #e8e8e8;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.fetcher-loading,
.fetcher-error {
  text-align: center;
  padding: 30px;
  color: #999;
  font-size: 14px;
}

.fetcher-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.fetcher-card {
  background: #fafafa;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 12px;
}

.fetcher-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e8e8e8;
}

.fetcher-card-header h5 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.fetcher-card .status-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.fetcher-card .status-badge.idle {
  background: #e6f7ff;
  color: #1890ff;
}

.fetcher-card .status-badge.running {
  background: #f6ffed;
  color: #52c41a;
}

.fetcher-card .status-badge.disabled {
  background: #f5f5f5;
  color: #999;
}

.fetcher-card .status-badge.error {
  background: #fff1f0;
  color: #ff4d4f;
}

.fetcher-card-info {
  margin-bottom: 12px;
}

.fetcher-card-info .info-row {
  display: flex;
  margin-bottom: 6px;
  font-size: 13px;
}

.fetcher-card-info .info-row .label {
  font-weight: 600;
  color: #666;
  width: 60px;
  flex-shrink: 0;
}

.fetcher-card-info .info-row .value {
  color: #333;
  flex: 1;
}

.fetcher-card-info .schedule {
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.fetcher-card-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.panel-btn.primary {
  background: #1890ff;
  color: #fff;
  border-color: #1890ff;
}

.panel-btn.primary:hover {
  background: #40a9ff;
  border-color: #40a9ff;
}

.panel-btn.warning {
  background: #faad14;
  color: #fff;
  border-color: #faad14;
}

.panel-btn.warning:hover {
  background: #ffc53d;
  border-color: #ffc53d;
}

.panel-btn.success {
  background: #52c41a;
  color: #fff;
  border-color: #52c41a;
}

.panel-btn.success:hover {
  background: #73d13d;
  border-color: #73d13d;
}

/* 定时任务管理面板样式 */
.scheduled-tasks-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.scheduled-tasks-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.scheduled-stats-card {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
}

.scheduled-stat-item {
  text-align: center;
}

.scheduled-stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.scheduled-stat-label {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}

.scheduled-tasks-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.scheduled-empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

.scheduled-empty-state p {
  margin: 0;
}

.scheduled-hint {
  font-size: 12px;
  color: #999;
  margin-top: 8px;
}

.scheduled-task-card {
  padding: 12px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
}

.scheduled-task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.scheduled-task-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.scheduled-task-name {
  font-weight: 600;
  font-size: 14px;
}

.scheduled-task-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.scheduled-task-tag.tag-success {
  background: #f6ffed;
  color: #52c41a;
}

.scheduled-task-tag.tag-warning {
  background: #fff7e6;
  color: #fa8c16;
}

.scheduled-task-tag.tag-info {
  background: #e6f7ff;
  color: #1890ff;
}

.scheduled-switch {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 20px;
}

.scheduled-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.scheduled-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: 0.4s;
  border-radius: 20px;
}

.scheduled-slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 2px;
  bottom: 2px;
  background-color: white;
  transition: 0.4s;
  border-radius: 50%;
}

input:checked + .scheduled-slider {
  background-color: #52c41a;
}

input:checked + .scheduled-slider:before {
  transform: translateX(20px);
}

input:disabled + .scheduled-slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.scheduled-task-description {
  color: #666;
  font-size: 13px;
  margin-bottom: 10px;
  line-height: 1.5;
}

.scheduled-task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
}

.scheduled-meta-item {
  font-size: 12px;
  color: #999;
}

.scheduled-task-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.scheduled-tag {
  padding: 2px 8px;
  background: #f0f0f0;
  border-radius: 4px;
  font-size: 11px;
  color: #666;
}

.scheduled-task-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

.scheduled-btn {
  padding: 4px 10px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.scheduled-btn-secondary {
  background: #f0f0f0;
  color: #333;
}

.scheduled-btn-secondary:hover {
  background: #e0e0e0;
}

.scheduled-btn-danger {
  background: #ff4d4f;
  color: white;
}

.scheduled-btn-danger:hover {
  background: #ff7875;
}

.scheduled-btn-execute {
  background: #52c41a;
  color: white;
  font-weight: 500;
}

.scheduled-btn-execute:hover:not(:disabled) {
  background: #73d13d;
}

.scheduled-btn-execute:disabled {
  background: #d9d9d9;
  cursor: not-allowed;
}

/* 会话历史管理面板样式 */
.session-history-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.session-history-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.session-filters {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.session-filter-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #e8e8e8;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;
  color: #666;
}

.session-filter-btn:hover {
  background: #f0f0f0;
}

.session-filter-btn.active {
  background: #1890ff;
  color: white;
  border-color: #1890ff;
}

.filter-icon {
  font-size: 14px;
}

.filter-count {
  background: rgba(255, 255, 255, 0.3);
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.session-filter-btn.active .filter-count {
  background: rgba(255, 255, 255, 0.3);
}

.session-stats {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.session-stat-item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
}

.session-stat-icon {
  font-size: 24px;
}

.session-stat-info {
  display: flex;
  flex-direction: column;
}

.session-stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  line-height: 1;
}

.session-stat-label {
  font-size: 12px;
  color: #666;
}

/* 最近对话历史样式 */
.recent-sessions-section {
  margin-bottom: 20px;
}

.recent-sessions-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e8e8e8;
}

.recent-sessions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-session-item {
  padding: 10px 12px;
  background: #fafafa;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.recent-session-item:hover {
  background: #f0f0f0;
  border-color: #1890ff;
}

.recent-session-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.recent-session-state {
  font-size: 16px;
  flex-shrink: 0;
}

.recent-session-query {
  flex: 1;
  font-size: 13px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-session-time {
  font-size: 11px;
  color: #999;
  flex-shrink: 0;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.session-loading,
.session-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #999;
}

.session-spinner {
  font-size: 32px;
  display: block;
  margin-bottom: 12px;
  animation: spin 2s linear infinite;
}

.session-empty-icon {
  font-size: 48px;
  display: block;
  margin-bottom: 12px;
  opacity: 0.5;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.session-item {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  overflow: hidden;
  transition: all 0.2s;
}

.session-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.session-item.state-active {
  border-left: 3px solid #1890ff;
}

.session-item.state-completed {
  border-left: 3px solid #52c41a;
}

.session-item.state-failed {
  border-left: 3px solid #ff4d4f;
}

.session-item.state-archived {
  border-left: 3px solid #999;
  opacity: 0.8;
}

.session-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  cursor: pointer;
}

.session-header:hover {
  background: #fafafa;
}

.session-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.session-state-icon {
  font-size: 18px;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-query {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #666;
}

.session-id {
  font-family: monospace;
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
}

.session-time {
  color: #999;
}

.session-header-right {
  flex-shrink: 0;
}

.session-expand-icon {
  font-size: 12px;
  color: #999;
}

.session-details {
  padding: 12px;
  background: #fafafa;
  border-top: 1px solid #e8e8e8;
}

.session-detail-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
}

.session-detail-label {
  font-weight: 500;
  color: #666;
  width: 80px;
  flex-shrink: 0;
}

.session-detail-value {
  color: #333;
}

.session-stats {
  display: flex;
  gap: 12px;
  margin: 12px 0;
}

.session-stat-box {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #e8e8e8;
}

.session-stat-label-small {
  font-size: 11px;
  color: #999;
  margin-bottom: 4px;
}

.session-stat-value-small {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.session-actions {
  display: flex;
  gap: 6px;
  margin-top: 12px;
}

.session-btn {
  flex: 1;
  padding: 6px 10px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.session-btn-primary {
  background: #1890ff;
  color: white;
}

.session-btn-primary:hover {
  background: #40a9ff;
}

.session-btn-secondary {
  background: #fff;
  color: #666;
  border: 1px solid #e8e8e8;
}

.session-btn-secondary:hover {
  background: #f5f5f5;
  border-color: #d9d9d9;
}

.session-btn-danger {
  background: #fff;
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.session-btn-danger:hover {
  background: #fff1f0;
  border-color: #ffa39e;
}

/* 社交平台管理面板样式 */
.social-platform-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.social-platform-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.platform-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.platform-card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
}

.platform-card .card-header {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
}

.platform-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
}

.platform-card.qq .platform-icon {
  background: #dbeafe;
  color: #1e40af;
}

.platform-card.weixin .platform-icon {
  background: #d1fae5;
  color: #065f46;
}

.platform-info h4 {
  margin: 0 0 6px 0;
  font-size: 15px;
  font-weight: 600;
  color: #262626;
}

.status-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.status-disabled {
  background: #f3f4f6;
  color: #6b7280;
}

.status-badge.status-running {
  background: #dbeafe;
  color: #1e40af;
}

.status-badge.status-success {
  background: #d1fae5;
  color: #065f46;
}

.status-badge.status-stopped {
  background: #fef3c7;
  color: #92400e;
}

.card-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 16px;
}

.metric {
  text-align: center;
}

.metric-label {
  display: block;
  font-size: 12px;
  color: #8c8c8c;
  margin-bottom: 4px;
}

.metric-value {
  display: block;
  font-size: 18px;
  font-weight: 600;
  color: #262626;
}

.card-actions {
  padding: 12px 16px;
  background: #fafafa;
  border-top: 1px solid #e8e8e8;
}

.health-section {
  margin-top: 8px;
}

.health-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #262626;
}

.health-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.health-card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 12px;
  display: flex;
  gap: 10px;
}

.health-card.healthy {
  border-color: #52c41a;
  background: #f6ffed;
}

.health-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f3f4f6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.health-card.healthy .health-icon {
  background: #52c41a;
  color: #fff;
}

.health-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.health-label {
  font-size: 12px;
  color: #8c8c8c;
}

.health-value {
  font-size: 14px;
  font-weight: 500;
  color: #262626;
}

/* QR码弹窗样式 */
.qr-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.qr-modal {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 420px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.qr-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
}

.qr-modal-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #262626;
}

.qr-modal-header .close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #8c8c8c;
  cursor: pointer;
  padding: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.qr-modal-header .close-btn:hover {
  background: #f3f4f6;
  color: #262626;
}

.qr-modal-body {
  padding: 20px;
}

.qr-code-container {
  text-align: center;
}

.qr-code-image {
  width: 260px;
  height: 260px;
  margin: 0 auto 16px;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  display: block;
}

.status-container {
  margin: 16px 0;
}

.status-indicator {
  display: inline-block;
  padding: 8px 16px;
  border-radius: 16px;
  font-size: 14px;
  font-weight: 500;
}

.status-indicator.waiting {
  background: #fef3c7;
  color: #92400e;
}

.status-indicator.scanned {
  background: #dbeafe;
  color: #1e40af;
}

.status-indicator.success {
  background: #d1fae5;
  color: #065f46;
}

.instructions {
  margin-top: 16px;
  text-align: left;
  background: #fafafa;
  padding: 12px;
  border-radius: 6px;
}

.instructions h5 {
  margin: 0 0 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: #262626;
}

.instructions ol {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #595959;
  line-height: 1.8;
}

.qr-loading {
  text-align: center;
  padding: 60px 20px;
  color: #8c8c8c;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e8e8e8;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.qr-modal-footer {
  display: flex;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid #e8e8e8;
  justify-content: flex-end;
}

.qr-modal-footer .panel-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.qr-modal-footer .panel-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.qr-modal-footer .panel-btn.primary {
  background: #52c41a;
  color: white;
}

.qr-modal-footer .panel-btn.primary:hover:not(:disabled) {
  background: #389e0d;
}

.qr-modal-footer .panel-btn.secondary {
  background: #f3f4f6;
  color: #262626;
}

.qr-modal-footer .panel-btn.secondary:hover:not(:disabled) {
  background: #e8e8e8;
}
</style>
