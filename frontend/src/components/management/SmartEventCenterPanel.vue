<template>
  <section ref="rootRef" class="smart-event-center" :class="{ 'detail-mode': viewMode !== 'list', 'workbench-fit': workbenchActive }">
    <header class="panel-header">
      <div class="panel-title">
        <i class="title-mark"></i>
        <h2>{{ viewMode === 'list' ? '智能事件中心' : viewMode === 'config' ? '事件中心配置' : '智能事件详情' }}</h2>
      </div>
      <div class="header-actions">
        <template v-if="viewMode === 'list'">
          <button type="button" :disabled="loading" @click="loadEvents"><span class="button-icon">↻</span>刷新</button>
          <button type="button" class="close" @click="$emit('close')">关闭</button>
        </template>
        <button v-else type="button" class="header-back-button" @click="backToList">返回列表</button>
      </div>
    </header>

    <section v-if="viewMode === 'list'" class="event-list-page" aria-label="智能事件列表">
      <div class="list-toolbar">
        <div class="filter-row">
          <label><span>事件状态</span><select v-model="statusFilter" aria-label="状态筛选" @change="loadEvents()"><option value="">全部状态</option><option v-for="value in statusOptions" :key="value" :value="value">{{ value }}</option></select></label>
          <div ref="typeFilterRef" class="type-filter">
            <span>事件类型</span>
            <button type="button" class="type-select-trigger" :aria-expanded="typeMenuOpen" aria-label="事件类型筛选" @click="toggleTypeMenu">
              <span class="type-trigger-text">{{ typeTriggerLabel }}</span>
              <i class="type-trigger-arrow" :class="{ open: typeMenuOpen }"></i>
            </button>
            <div v-if="typeMenuOpen" class="type-menu">
              <label v-for="value in typeOptions" :key="value" class="type-option">
                <input type="checkbox" :value="value" v-model="selectedEventTypes" @change="scheduleTypeLoad" />
                <span>{{ value }}</span>
              </label>
              <div class="type-menu-actions">
                <button type="button" @click="clearTypeSelection">清空</button>
                <button type="button" @click="closeTypeMenu">完成</button>
              </div>
            </div>
          </div>
          <label v-if="levelOptions.length"><span>等级</span><select v-model="levelFilter" aria-label="等级筛选" @change="loadEvents()"><option value="">全部等级</option><option v-for="value in levelOptions" :key="value" :value="value">{{ value }}</option></select></label>
          <label class="time-filter"><span>开始时间</span><input v-model="listStartTime" type="datetime-local" aria-label="事件开始时间筛选" /></label>
          <label class="time-filter"><span>结束时间</span><input v-model="listEndTime" type="datetime-local" aria-label="事件结束时间筛选" /></label>
          <label class="keyword-filter"><span>关键词</span><input v-model="keyword" type="search" placeholder="事件编号、站点或事件名称" @keyup.enter="loadEvents" /></label>
          <button type="button" class="primary-button" :disabled="loading" @click="loadEvents">查询 <i class="search-icon" aria-hidden="true"></i></button>
          <button type="button" class="secondary-button" :disabled="loading" @click="resetFilters">重置 <span>↻</span></button>
          <button type="button" class="config-button" :disabled="loading" @click="openConfig">⚙ 设置</button>
        </div>
        <span v-if="actionMessage" class="action-message list-action-message">{{ actionMessage }}</span>
      </div>
      <div class="list-metrics">
        <div class="metric-total"><i></i><span>事件总数</span><strong>{{ listStats.total }}</strong></div>
        <div class="metric-pending"><i></i><span>待 AI 研判</span><strong>{{ pendingCount }}</strong></div>
        <div class="metric-station"><i></i><span>涉及站点</span><strong>{{ stationCount }}</strong></div>
        <div class="metric-sync"><i></i><span>最近同步</span><strong>{{ syncing ? '同步中…' : lastSyncTime }}</strong></div>
        <b>共 {{ totalEvents }} 条</b>
      </div>
      <div v-if="loading && !events.length" class="state">正在加载事件...</div>
      <div v-else-if="error && !events.length" class="state error">{{ error }}</div>
      <div v-else-if="!filteredEvents.length" class="state">暂无符合条件的智能事件</div>
      <div v-else class="event-table-wrap">
        <table class="event-table">
          <thead><tr><th>序号</th><th>状态</th><th>事件名称</th><th>线索标签</th><th>AI事件类型</th><th>数据影响</th><th>等级</th><th>站点</th><th>发生时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="(event, index) in filteredEvents" :key="event.event_id" @click="openDetail(event.event_id)">
              <td>{{ (currentPage - 1) * PAGE_SIZE + index + 1 }}</td>
              <td><span class="table-chip" :class="statusClass(event)">{{ event.event_status || '待研判' }}</span></td>
              <td><div class="event-name"><strong>{{ event.event_name || event.initial_event_name || '待研判事件' }}</strong><small>{{ event.alarm_content || '暂无具体告警内容' }}</small></div></td>
              <td class="tag-cell">
                <div class="tag-chip-wrap">
                  <span v-for="chip in visibleTagChips(event)" :key="chip.label" class="clue-chip" :class="chip.klass">{{ chip.label }}</span>
                  <button v-if="hiddenTagCount(event) > 0" type="button" class="tag-more" @click.stop="expandTags(event.event_id)">更多 {{ hiddenTagCount(event) }} 个</button>
                </div>
                <span v-if="event.pending_delta" class="delta-flag">新增线索待研判</span>
              </td>
              <td>{{ event.ai_event_type || event.event_type || '待研判' }}</td>
              <td>{{ displayDataImpact(event) }}</td>
              <td>{{ event.ai_suggested_level || '待研判' }}</td>
              <td>{{ event.site_name || event.site_id || '未知站点' }}</td>
              <td>{{ formatTime(event.latest_occurrence_time || event.event_start_time) }}</td>
              <td class="operation-cell">
                <button v-if="!hasCompletedJudgment(event) || event.pending_delta" type="button" class="ai-button" :disabled="event.archived || isAiBusy(event.event_id)" @click.stop="dispatchAiJudgment(event)">
                  {{ isAiBusy(event.event_id) ? '研判中…' : 'AI研判' }}
                </button>
                <button type="button" class="detail-button" @click.stop="openDetail(event.event_id)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <nav class="event-pagination" aria-label="事件分页">
        <span>共 {{ totalEvents }} 条，每页 {{ PAGE_SIZE }} 条</span>
        <button type="button" :disabled="loading || currentPage <= 1" @click="loadEvents(currentPage - 1)">上一页</button>
        <span>第 {{ currentPage }} / {{ totalPages }} 页</span>
        <button type="button" :disabled="loading || currentPage >= totalPages" @click="loadEvents(currentPage + 1)">下一页</button>
      </nav>
    </section>

    <section v-else-if="viewMode === 'config'" class="config-page" aria-label="事件中心配置">
      <div class="config-header">
        <h3>智能事件中心参数配置</h3>
        <p>修改后点击保存，参数将在下一次研判或数据检测时生效。</p>
      </div>
      <div v-if="configBusy" class="state">正在加载配置...</div>
      <div v-else-if="configError" class="state error">{{ configError }}</div>
      <div v-else class="config-body">
        <div class="config-section">
          <h4>事件合并</h4>
          <div class="config-row">
            <label>同日合并窗口（分钟）<input v-model.number="configDraft.event_merge_window_minutes" type="number" min="0" /></label>
          </div>
        </div>
        <div class="config-section">
          <h4>自动研判与回扫</h4>
          <div class="config-row">
            <label>自动 AI 研判<select v-model="configDraft.auto_ai_enabled"><option :value="true">开启</option><option :value="false">关闭</option></select></label>
            <label>线索扫描周期（分钟）<input v-model.number="configDraft.schedule_interval_minutes" type="number" min="1" max="1440" /></label>
            <label>延迟线索回扫（小时）<input v-model.number="configDraft.rescan_lookback_hours" type="number" min="1" max="168" /></label>
            <label>证据刷新周期（分钟）<input v-model.number="configDraft.evidence_refresh_minutes" type="number" min="1" max="1440" /></label>
            <label>每轮证据采集数<input v-model.number="configDraft.evidence_batch_size" type="number" min="1" max="1000" /></label>
            <label>AI 最大并发数<input v-model.number="configDraft.ai_max_concurrency" type="number" min="1" max="10" /></label>
            <label>失败后最多重试次数<input v-model.number="configDraft.ai_max_retries" type="number" min="0" max="10" /></label>
            <label>首次重试等待（分钟）<input v-model.number="configDraft.ai_retry_delay_minutes" type="number" min="1" max="1440" /></label>
          </div>
        </div>
        <div class="config-section">
          <h4>数据检测阈值</h4>
          <div class="config-row">
            <label>站点级断数因子数阈值<input v-model.number="configDraft.station_missing_factor_threshold" type="number" min="1" /></label>
            <label>多仪器断数因子数阈值<input v-model.number="configDraft.multi_instrument_threshold" type="number" min="1" /></label>
            <label>异常数据变化率阈值（%）<input v-model.number="configDraft.data_anomaly_threshold_pct" type="number" min="1" max="100" /></label>
            <label>PM 突升阈值（%）<input v-model.number="configDraft.pm_rise_threshold_pct" type="number" min="1" max="100" /></label>
          </div>
        </div>
        <div class="config-section">
          <h4>视频识别</h4>
          <div class="config-row">
            <label>视频标签置信度阈值<input v-model.number="configDraft.video_tag_confidence_threshold" type="number" min="0" max="1" step="0.05" /></label>
          </div>
        </div>
        <div class="config-section">
          <h4>浓度超限阈值（μg/m³，留空不检测）</h4>
          <div class="config-row">
            <label>SO2<input v-model.number="configDraft.pollutant_hour_limits.SO2" type="number" min="0" /></label>
            <label>NO2<input v-model.number="configDraft.pollutant_hour_limits.NO2" type="number" min="0" /></label>
            <label>O3<input v-model.number="configDraft.pollutant_hour_limits.O3" type="number" min="0" /></label>
            <label>PM10<input v-model.number="configDraft.pollutant_hour_limits.PM10" type="number" min="0" /></label>
            <label>PM2.5<input v-model.number="configDraft.pollutant_hour_limits['PM2.5']" type="number" min="0" /></label>
            <label>CO<input v-model.number="configDraft.pollutant_hour_limits.CO" type="number" min="0" placeholder="留空不检测" /></label>
          </div>
        </div>
        <div class="config-section">
          <h4>AI 事件类型字典</h4>
          <div class="config-row">
            <label class="full-width-label">每行一个类型，AI 研判时必须从这些类型中选取：</label>
            <textarea v-model="configDraft._aiDictionaryText" rows="6" class="dictionary-input" @blur="parseDictionaryText"></textarea>
          </div>
        </div>
        <div class="config-actions">
          <span v-if="configSaveMessage" class="config-save-msg" :class="configSaveOk ? 'ok' : 'err'">{{ configSaveMessage }}</span>
          <button type="button" class="primary-button" :disabled="configSaving" @click="saveConfig">保存配置</button>
          <button type="button" class="secondary-button" @click="backToList">返回列表</button>
        </div>
      </div>
    </section>

    <section v-else class="event-detail" aria-label="智能事件详情">
        <div v-if="detailLoading" class="state">正在加载详情...</div>
        <section v-else-if="workspaceMode === 'compare'" class="compare-view" aria-label="事件对比">
          <header class="detail-header">
            <div><h3>事件对比</h3><p>事件横向比较</p></div>
          </header>
          <article v-for="event in compareEvents" :key="event.event_id" class="compare-card">
            <strong>{{ event.event_name || event.initial_event_name }}</strong>
            <span>{{ event.site_name || event.site_id }} · {{ event.primary_clue_tag || event.event_type }}</span>
            <em>{{ event.event_status || '未研判' }}</em>
          </article>
        </section>
        <section v-else-if="workspaceMode === 'history' && selectedEvent" class="history-view" aria-label="事件操作历史">
          <header class="detail-header">
            <div><h3>操作历史</h3><p>{{ selectedEvent.event_name || selectedEvent.initial_event_name }}</p></div>
          </header>
          <div v-if="!operationRecords.length" class="state">暂无操作记录</div>
          <ol v-else class="history-list"><li v-for="(record, index) in operationRecords" :key="`${record.created_at || index}`"><strong>{{ record.action || record.operation || '事件操作' }}</strong><span>{{ record.message || record.summary || record.status || '已记录' }}</span><small>{{ formatTime(record.created_at || record.updated_at) }}</small></li></ol>
        </section>
        <div v-else-if="!selectedEvent" class="state">选择一个事件查看固定详情</div>
        <template v-else>
          <header class="detail-header">
            <div>
              <h3>{{ selectedEvent.event_name || selectedEvent.initial_event_name }}</h3>
              <p>{{ selectedEvent.site_name || selectedEvent.site_id }} · {{ selectedEvent.event_type }}</p>
            </div>
            <span class="status-badge">{{ selectedEvent.event_status || '未研判' }}</span>
          </header>
          <section class="evidence-detail-board" aria-label="证据明细">
            <div class="workbench-layout">
              <aside class="workbench-index" aria-label="证据目录">
                <div class="workbench-index-title">证据目录</div>
                <button v-for="section in workbenchSections" :key="section.key" type="button" class="workbench-index-item" :class="{ active: activeEvidenceKey === section.key }" @click="scrollToEvidence(section.key)">
                  <span>{{ section.index }}. {{ section.label }}</span>
                  <i class="index-state" :class="sourceStatusClass(section.value)"></i>
                </button>
              </aside>

              <main ref="evidenceContent" class="workbench-content" @scroll.passive="updateActiveEvidence">
                <article v-for="section in workbenchSections" :id="`smart-evidence-${section.key}`" :key="section.key" class="workbench-section">
                  <header class="workbench-section-header">
                    <h3>{{ section.index }}. {{ section.label }}</h3>
                    <span v-if="section.key !== 'event'" class="source-status" :class="sourceStatusClass(section.value)">{{ sourceStatus(section.value) }}</span>
                  </header>

                  <template v-if="section.key === 'event'">
                    <div class="event-grid">
                      <div v-for="fact in eventFacts" :key="fact.label" class="event-grid-item"><span>{{ fact.label }}</span><strong>{{ fact.value }}</strong></div>
                    </div>
                    <section class="merged-alarm-content" aria-label="全部告警内容">
                      <h4>告警内容<span class="alarm-count">（{{ detailAlarmRows.length }} 条<template v-if="detailAlarmGroups.length > 1 && detailAlarmGroups.length < detailAlarmRows.length"> · 已归并为 {{ detailAlarmGroups.length }} 组</template>）</span></h4>
                      <ol v-if="detailAlarmRows.length">
                        <li v-for="group in detailAlarmGroups" :key="group.key">
                          <template v-if="group.kind === 'single'">
                            <div class="alarm-meta"><time>{{ formatTime(group.rows[0].time) }}</time><strong>{{ group.rows[0].type }}</strong></div>
                            <p>{{ group.rows[0].content }}</p>
                          </template>
                          <template v-else>
                            <div class="alarm-meta">
                              <time>{{ alarmGroupTimeText(group) }}</time>
                              <strong>{{ group.title }}</strong>
                              <span class="alarm-group-badge">×{{ group.count }}</span>
                            </div>
                            <p v-for="(line, index) in group.summaries" :key="index" class="alarm-group-summary">{{ line }}</p>
                            <details class="alarm-group-raw">
                              <summary>展开逐条（{{ group.count }} 条）</summary>
                              <ol>
                                <li v-for="alarm in group.rows" :key="alarm.key">
                                  <div class="alarm-meta"><time>{{ formatTime(alarm.time) }}</time><strong>{{ alarm.type }}</strong></div>
                                  <p>{{ alarm.content }}</p>
                                </li>
                              </ol>
                            </details>
                          </template>
                        </li>
                      </ol>
                      <p v-else class="source-empty">暂无具体告警内容</p>
                    </section>
                    <div v-if="detailTagChips.length" class="detail-tag-row" aria-label="线索标签集合">
                      <span class="detail-tag-title">线索标签</span>
                      <div class="tag-chip-wrap">
                        <span v-for="chip in detailTagChips" :key="chip.label" class="clue-chip" :class="chip.klass" :title="chip.source">{{ chip.label }}</span>
                      </div>
                    </div>
                  </template>

                  <section v-else-if="section.key === 'judgment'" class="special-panel judgment" aria-label="AI研判结果">
                    <p v-if="selectedEvent.data_impact_conflict" class="delta-note" role="status">{{ selectedEvent.data_impact_conflict_note }}</p>
                    <template v-if="judgment?.final_response">
                      <div v-if="judgmentText" class="j-note"><MarkdownRenderer :content="judgmentText" :streaming="false" /></div>
                      <details v-if="judgmentDetails.length" :key="selectedEvent.event_id" class="judgment-details">
                        <summary>完整研判分析与依据</summary>
                        <section v-for="item in judgmentDetails" :key="item.key">
                          <h4>{{ item.label }}</h4>
                          <MarkdownRenderer :content="item.value" :streaming="false" />
                        </section>
                      </details>
                    </template>
                    <p v-else class="muted">当前状态为{{ selectedEvent?.event_status || '未研判' }}：系统已完成线索归并和标签保留，AI 研判完成后将写入事件名称、事件类型、数据影响、事件等级和摘要说明。</p>
                    <div v-if="!selectedEvent?.archived" class="disposal-actions judgment-actions">
                      <button v-if="!hasCompletedJudgment(selectedEvent) || selectedEvent?.pending_delta" type="button" class="disposal-button" :disabled="isAiBusy(String(selectedEvent?.event_id || ''))" @click="dispatchAiJudgment(selectedEvent)">
                        {{ isAiBusy(String(selectedEvent?.event_id || '')) ? '研判中…' : (judgment?.final_response ? 'AI 增量研判' : '执行 AI 研判') }}
                      </button>
                      <p v-else class="judgment-done-note">AI 研判已完成，不再提供手动研判入口；后续合并新线索或提交事件反馈时会自动发起增量研判。</p>
                    </div>
                    <div v-if="selectedEvent?.pending_delta" class="delta-note">本事件在上一轮研判后合并了 {{ (selectedEvent.pending_delta.clue_ids || []).length }} 条新线索，触发 AI 研判将进行增量研判。</div>
                    <div v-if="judgmentHistory.length" class="judgment-history">
                      <h4>研判轮次记录（共 {{ judgmentHistory.length + (judgment?.final_response ? 1 : 0) }} 轮）</h4>
                      <ol>
                        <li v-for="item in judgmentHistory" :key="`${item.round}-${item.task_id || item.archived_at}`">
                          <strong>第 {{ item.round }} 轮</strong>
                          <span>{{ formatTime(item.completed_at || item.archived_at) }}</span>
                          <MarkdownRenderer :content="item.final_response" :streaming="false" />
                        </li>
                      </ol>
                    </div>
                  </section>

                  <section v-else-if="section.key === 'disposal'" v-show="!selectedEvent.archived" class="special-panel confirmation" aria-label="处置操作">
                    <div class="disposal-actions">
                      <button type="button" class="disposal-button primary" :disabled="!['待复核', '已反馈'].includes(selectedEvent.event_status)" @click="openDispatchPage">派单处理</button>
                      <button type="button" class="disposal-button" :disabled="!['待复核', '待反馈', '已反馈'].includes(selectedEvent.event_status)" @click="openFeedbackDialog">事件反馈</button>
                      <button type="button" class="disposal-button" @click="reviewDialogVisible = true" :disabled="!selectedEvent.review_id">审核与归档</button>
                    </div>
                    <div class="operation-history-block" aria-label="操作历史">
                      <h4>操作历史</h4>
                      <p v-if="!operationRecords.length" class="source-empty">暂无处置记录</p>
                      <ol v-else class="operation-list">
                        <li v-for="(record, index) in operationRecords" :key="record.operation_id || index">
                          <strong>{{ operationActionLabel(record.action) }}</strong>
                          <span>{{ record.summary }}</span>
                          <small>{{ formatTime(record.created_at) }} · {{ record.actor?.username || '系统' }}</small>
                        </li>
                      </ol>
                    </div>
                  </section>

                  <section v-else-if="section.key === 'tasks'" class="special-panel task-section" aria-label="关联研判任务">
                    <button v-for="task in tasks" :key="task.task_id" type="button" class="task-card" @click="$emit('open-task', task)">
                      <span><strong>{{ task.title || 'AI 研判任务' }}</strong><small>{{ task.status || '待执行' }}<template v-if="task.automatic_attempts"> · 已自动尝试 {{ task.automatic_attempts }} 次</template><template v-if="task.retry_exhausted"> · 已达重试上限，请人工处理</template><template v-else-if="task.next_retry_at"> · 下次重试 {{ formatTime(task.next_retry_at) }}</template></small></span>
                      <span class="task-arrow">进入任务 →</span>
                    </button>
                    <p v-if="!tasks.length" class="source-empty">暂无关联研判任务</p>
                  </section>

                  <template v-else>
                    <p v-if="section.key === 'instrument_status'" class="source-summary">目标污染物：{{ selectedEvent.evidence_package?.collection_policy?.instrument_target_pollutants?.join('、') || '未识别' }}</p>
                    <p class="source-summary">{{ section.key === 'video' ? `可预览图片 ${videoEvidenceRows(section).length} 张` : (section.value?.summary || '尚未抓取该数据源') }}</p>
                    <div class="source-meta"><span>记录数 {{ sourceRecordCount(section.value) }}</span><span v-if="section.value?.metadata?.time_range">{{ formatTimeRange(section.value.metadata.time_range) }}</span></div>

                    <template v-if="section.key === 'video'">
                      <div v-if="videoEvidenceRows(section).length" class="video-evidence-grid">
                        <figure v-for="item in videoEvidenceRows(section)" :key="item.index" class="video-evidence-card">
                          <img v-if="item.path && videoImageUrls[item.index]" :src="videoImageUrls[item.index]" :alt="`${item.row.title || '视频'}截图`" loading="lazy" @click="previewImageUrl = videoImageUrls[item.index]">
                          <div v-else class="video-evidence-missing">暂无可预览图片</div>
                          <figcaption><strong>{{ item.row.title || '视频线索' }}</strong><span>{{ formatTime(item.row.time) }}</span></figcaption>
                        </figure>
                      </div>
                      <p v-else class="source-empty">暂无视频监控记录</p>
                    </template>
                    <template v-else-if="section.key === 'comparison'">
                      <div class="comparison-overview">
                        <div><span>目标站点</span><strong>{{ comparisonTargetName }}</strong></div>
                        <div><span>同区县对比站点</span><strong>{{ comparisonNearbyCount }}</strong><small>个</small></div>
                        <div><span>全市其余站点</span><strong>{{ comparisonCityCount }}</strong><small>个</small></div>
                      </div>
                      <div v-if="comparisonDeltaRows.length" class="comparison-analysis-grid">
                        <section class="comparison-analysis-panel">
                          <h4>事件时段均值差异</h4>
                          <table class="source-table comparison-delta-table"><thead><tr><th>污染物</th><th>本站 − 同区县</th><th>本站 − 全市其余</th></tr></thead><tbody><tr v-for="row in comparisonDeltaRows" :key="row.name"><td>{{ row.name }}</td><td>{{ row.nearby }}</td><td>{{ row.city }}</td></tr></tbody></table>
                        </section>
                        <section class="comparison-analysis-panel">
                          <h4>趋势一致性</h4>
                          <table class="source-table comparison-delta-table"><thead><tr><th>污染物</th><th>本站趋势</th><th>同区县趋势</th><th>一致性</th><th>相关系数</th><th>对齐小时</th></tr></thead><tbody><tr v-for="row in comparisonTrendRows" :key="`${row.name}-trend`"><td>{{ row.name }}</td><td>{{ row.target }}</td><td>{{ row.nearby }}</td><td>{{ row.consistent }}</td><td>{{ row.correlation }}</td><td>{{ row.hours }}</td></tr></tbody></table>
                        </section>
                      </div>
                      <div v-if="deltaChartOption" class="regional-delta-block" aria-label="区域差异柱状图">
                        <h4>区域差异（本站均值 − 区域均值，事件时段）</h4>
                        <div :ref="el => { deltaChartRef = el }" class="chart-canvas delta-canvas"></div>
                        <p class="delta-legend">蓝色柱：与周边站点差值；红色柱：与全市其余站点差值。正值表示本站高于区域背景，负值表示低于区域背景。</p>
                      </div>
                      <div v-if="comparisonChartOption" class="comparison-records-wrap">
                        <div class="comparison-chart-header">
                          <h4>目标站与对比站小时趋势</h4>
                          <div class="comparison-pollutant-switch" role="group" aria-label="片区对比污染物切换">
                            <button v-for="item in POLLUTANT_SERIES" :key="item.key" type="button" :class="{ active: comparisonPollutant === item.key }" :aria-pressed="comparisonPollutant === item.key" @click="comparisonPollutant = item.key">{{ item.label }}</button>
                          </div>
                        </div>
                        <div :ref="el => { comparisonChartRef = el }" class="chart-canvas comparison-chart-canvas" aria-label="目标站与对比站小时趋势图"></div>
                      </div>
                      <p v-if="!comparisonDeltaRows.length && !sourceRows(section).length" class="source-empty">暂无片区对比结果</p>
                    </template>
                    <template v-else-if="section.key === 'weather'">
                      <div class="minute-line-chart" aria-label="气象折线时序图">
                        <div v-if="weatherChartOption" :ref="el => { weatherChartRef = el }" class="chart-canvas weather-chart-canvas"></div>
                        <p v-else class="source-empty">暂无气象时序数据，无法绘制气象图</p>
                      </div>
                      <div v-if="sourceRows(section).length" class="source-table-wrap">
                        <table class="source-table"><thead><tr><th v-for="column in sourceColumns(section)" :key="column.key">{{ column.label }}</th></tr></thead><tbody><tr v-for="(row, index) in (section.key === 'instrument_status' ? sourceRows(section) : sourceRows(section).slice(0, 12))" :key="index"><td v-for="column in sourceColumns(section)" :key="column.key">{{ displayCell(row, column.key) }}</td></tr></tbody></table>
                      </div>
                    </template>

                    <div v-else-if="sourceRows(section).length" class="source-table-wrap" :class="{ 'monitoring-table-wrap': section.key === 'instrument_status' }">
                      <table class="source-table"><thead><tr><th v-for="column in sourceColumns(section)" :key="column.key">{{ column.label }}</th></tr></thead><tbody><tr v-for="(row, index) in (section.key === 'instrument_status' ? sourceRows(section) : sourceRows(section).slice(0, 12))" :key="index"><td v-for="column in sourceColumns(section)" :key="column.key">{{ displayCell(row, column.key) }}</td></tr></tbody></table>
                    </div>
                    <p v-else class="source-empty">暂无{{ section.label }}数据</p>
                  </template>
                </article>
              </main>
            </div>
          </section>
        </template>
      </section>
      <div v-if="dispatchDialogVisible" class="archive-overlay" role="dialog" aria-modal="true" aria-label="工单派发">
        <div class="archive-dialog dispatch-dialog">
          <header><strong>工单派发</strong><button type="button" aria-label="关闭工单派发窗口" @click="dispatchDialogVisible = false">×</button></header>
          <dl class="dispatch-facts">
            <div><dt>事件名称</dt><dd>{{ selectedEvent?.event_name || selectedEvent?.initial_event_name || '-' }}</dd></div>
            <div><dt>站点</dt><dd>{{ selectedEvent?.site_name || selectedEvent?.site_id || '-' }}</dd></div>
            <div><dt>事件等级</dt><dd>{{ selectedEvent?.ai_suggested_level || '待定' }}</dd></div>
            <div><dt>当前状态</dt><dd>{{ selectedEvent?.event_status || '待研判' }}</dd></div>
          </dl>
          <div class="dispatch-form">
            <label><span>派发工单类型</span><input v-model="dispatchOrder.type" type="text" placeholder="如：现场核查 / 仪器维修" /></label>
            <label><span>指派人员</span><input v-model="dispatchOrder.assignee" type="text" placeholder="运维处置人员" /></label>
            <label><span>工单标题</span><input v-model="dispatchOrder.title" type="text" placeholder="请输入工单标题" /></label>
            <label class="dispatch-description"><span>工单说明</span><textarea v-model="dispatchOrder.description" rows="5" /></label>
          </div>
          <div class="confirmation-actions">
            <button type="button" class="primary-button" :disabled="confirmationBusy || !dispatchOrder.title.trim()" @click="submitDispatchOrder">提交派单</button>
            <button type="button" class="secondary-button" @click="dispatchDialogVisible = false">取消</button>
          </div>
        </div>
      </div>
      <div v-if="feedbackDialogVisible" class="archive-overlay" role="dialog" aria-modal="true" aria-label="事件反馈">
        <div class="archive-dialog">
          <header><strong>事件反馈</strong><button type="button" aria-label="关闭事件反馈窗口" @click="feedbackDialogVisible = false">×</button></header>
          <p class="dialog-note">反馈将以增量对话提交给上一轮 AI 研判，研判结论会被更新替换。</p>
          <label class="dispatch-description"><span>反馈信息</span><textarea v-model="feedbackText" rows="5" placeholder="请输入现场处理结果、核查结论或补充说明" /></label>
          <label class="dispatch-attachment"><span>附件（仅记录附件名称）</span><input type="file" multiple @change="handleFeedbackAttachments" /></label>
          <p v-if="feedbackAttachmentNames.length" class="attachment-names">已选择：{{ feedbackAttachmentNames.join('、') }}</p>
          <div class="confirmation-actions">
            <button type="button" class="primary-button" :disabled="confirmationBusy || !feedbackText.trim()" @click="submitFeedback">提交反馈</button>
            <button type="button" class="secondary-button" @click="feedbackDialogVisible = false">取消</button>
          </div>
        </div>
      </div>
      <div v-if="reviewDialogVisible && selectedEvent?.review_id" class="archive-overlay" role="dialog" aria-modal="true" aria-label="审核事项">
        <div class="archive-dialog" style="height:85vh;display:flex;flex-direction:column;width:min(1000px,95vw)">
          <button type="button" @click="reviewDialogVisible = false">关闭</button>
          <TaskReviewPanel :review-id="selectedEvent.review_id" compact @updated="refreshSelectedReview" />
        </div>
      </div>
      <div v-if="previewImageUrl" class="image-preview-overlay" role="dialog" aria-modal="true" aria-label="图片预览" @click.self="previewImageUrl = ''">
        <button type="button" class="image-preview-close" aria-label="关闭图片预览" @click="previewImageUrl = ''">×</button>
        <img :src="previewImageUrl" alt="放大预览" class="image-preview-image">
      </div>
  </section>
</template>

<script setup>
import { eventAlarmRows, groupAlarmRows } from './jiangsuEventAlarms.js'
import TaskReviewPanel from '@/components/reviews/TaskReviewPanel.vue'
import { jiangsuJudgmentDetails } from './jiangsuJudgmentPresentation.js'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { authFetch } from '@/auth/http'
import * as echarts from 'echarts'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { getTaskReview } from '@/services/taskReviewsApi.js'
import {
  dispatchJiangsuSmartEventOrder,
  getJiangsuSmartEvent,
  getJiangsuSmartEventConfig,
  getJiangsuSmartEventDemoWindow,
  listJiangsuSmartEventTasks,
  listJiangsuSmartEvents,
  collectJiangsuSmartEventEvidence,
  submitJiangsuSmartEventFeedback,
  dispatchJiangsuSmartEventAiJudgment,
  saveJiangsuSmartEventConfig,
} from '@/services/jiangsuSmartEventsApi.js'

const props = defineProps({
  initialEventId: { type: String, default: '' },
  workspaceCommand: { type: Object, default: null },
  category: { type: String, default: 'all' }
})
const emit = defineEmits(['close', 'open-task'])

const DEFAULT_LIST_TIME_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})
const toDatetimeLocal = value => {
  const parts = Object.fromEntries(DEFAULT_LIST_TIME_FORMATTER.formatToParts(value).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
}
// 演示冻结窗口（由后端 /demo-window 下发）；null = 未开启冻结，使用当天滚动窗口。
const freezeRange = ref(null)
const defaultListTimeRange = () => {
  if (freezeRange.value) return { ...freezeRange.value }
  const end = new Date()
  const parts = Object.fromEntries(DEFAULT_LIST_TIME_FORMATTER.formatToParts(end).map(part => [part.type, part.value]))
  return {
    start: `${parts.year}-${parts.month}-${parts.day}T00:00`,
    end: toDatetimeLocal(end),
  }
}
const initialListTimeRange = defaultListTimeRange()
const events = ref([])
const PAGE_SIZE = 10
const currentPage = ref(1)
const totalEvents = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(totalEvents.value / PAGE_SIZE)))
const listStats = ref({ total: 0, pending: 0, stations: 0 })
const listFilters = ref({ statuses: [], types: [], levels: [] })
const activeQuery = ref({})
const applyListPage = payload => {
  events.value = payload.events || []
  totalEvents.value = payload.total ?? events.value.length
  currentPage.value = payload.page || 1
  listStats.value = payload.stats || { total: totalEvents.value, pending: 0, stations: 0 }
  listFilters.value = { statuses: [], types: [], levels: [], ...(payload.filters || {}) }
}
const selectedId = ref(props.initialEventId || '')
const selectedEvent = ref(null)
const reviewEvidence = ref([])
const tasks = ref([])
const keyword = ref('')
const statusFilter = ref('')
// 事件类型筛选以数组为准；空数组 = 入口类别全部类型（智能事件中心则为全部事件类型）。
const selectedEventTypes = ref([])
const levelFilter = ref('')
// 列表默认与后端默认查询范围一致：当天 00:00 至当前时刻（上海时间）。
const listStartTime = ref(initialListTimeRange.start)
const listEndTime = ref(initialListTimeRange.end)
const lastSync = ref(null)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const workspaceMode = ref('detail')
const compareEvents = ref([])
const evidenceFocus = ref('')
const confirmationBusy = ref(false)
const actionMessage = ref('')
const dispatchDialogVisible = ref(false)
const feedbackDialogVisible = ref(false)
const feedbackText = ref('')
const feedbackAttachmentNames = ref([])
const dispatchOrder = ref({ type: '', assignee: '运维处置人员', title: '', description: '' })
const viewMode = ref(props.initialEventId ? 'detail' : 'list')
// 与详情区 <template v-else> 分支条件一致：仅固定详情工作台启用纵向撑满布局。
const workbenchActive = computed(() => viewMode.value === 'detail' && !detailLoading.value && workspaceMode.value === 'detail' && Boolean(selectedEvent.value))
const evidenceBusy = ref(false)
const aiBusyIds = ref(new Set())
const activeEvidenceKey = ref('event')
const evidenceContent = ref(null)
const judgment = computed(() => selectedEvent.value?.ai_judgment || null)
const judgmentHistory = computed(() => Array.isArray(selectedEvent.value?.judgment_history) ? selectedEvent.value.judgment_history : [])
const judgmentRounds = computed(() => judgmentHistory.value.length + (judgment.value?.final_response ? 1 : 0))
const eventConfig = ref(null)

const judgmentText = computed(() => judgment.value?.final_response || '')
const judgmentDetails = computed(() => jiangsuJudgmentDetails(selectedEvent.value?.ai_structured_judgment))
const judgmentSummary = computed(() => judgment.value?.final_response || '')
const loadEventConfig = async () => {
  try {
    const payload = await getJiangsuSmartEventConfig()
    eventConfig.value = payload.config || null
  } catch (err) {
    eventConfig.value = null
  }
}

const configBusy = ref(false)
const configError = ref('')
const configSaving = ref(false)
const configSaveMessage = ref('')
const configSaveOk = ref(false)
const configDraft = ref({
  auto_ai_enabled: true,
  schedule_interval_minutes: 60,
  rescan_lookback_hours: 24,
  evidence_refresh_minutes: 60,
  evidence_batch_size: 30,
  ai_max_concurrency: 2,
  ai_max_retries: 3,
  ai_retry_delay_minutes: 5,

  event_merge_window_minutes: 60,
  station_missing_factor_threshold: 2,
  multi_instrument_threshold: 2,
  data_anomaly_threshold_pct: 20,
  pm_rise_threshold_pct: 20,
  video_tag_confidence_threshold: 0.7,
  pollutant_hour_limits: { SO2: 150, NO2: 200, O3: 200, PM10: 150, 'PM2.5': 75, CO: null },
  ai_event_type_dictionary: [],
  initial_naming_priority: [],
  _aiDictionaryText: '',
})

const openConfig = async () => {
  viewMode.value = 'config'
  configBusy.value = true
  configError.value = ''
  configSaveMessage.value = ''
  try {
    const payload = await getJiangsuSmartEventConfig()
    const cfg = payload.config || {}
    const limits = cfg.pollutant_hour_limits || {}
    configDraft.value = {
      ...cfg,
      auto_ai_enabled: cfg.auto_ai_enabled ?? true,
      schedule_interval_minutes: cfg.schedule_interval_minutes ?? 60,
      rescan_lookback_hours: cfg.rescan_lookback_hours ?? 24,
      evidence_refresh_minutes: cfg.evidence_refresh_minutes ?? 60,
      evidence_batch_size: cfg.evidence_batch_size ?? 30,
      ai_max_concurrency: cfg.ai_max_concurrency ?? 2,
      ai_max_retries: cfg.ai_max_retries ?? 3,
      ai_retry_delay_minutes: cfg.ai_retry_delay_minutes ?? 5,

      event_merge_window_minutes: cfg.event_merge_window_minutes ?? 60,
      station_missing_factor_threshold: cfg.station_missing_factor_threshold ?? 2,
      multi_instrument_threshold: cfg.multi_instrument_threshold ?? 2,
      data_anomaly_threshold_pct: cfg.data_anomaly_threshold_pct ?? 20,
      pm_rise_threshold_pct: cfg.pm_rise_threshold_pct ?? 20,
      video_tag_confidence_threshold: cfg.video_tag_confidence_threshold ?? 0.7,
      pollutant_hour_limits: {
        SO2: limits.SO2 ?? 150,
        NO2: limits.NO2 ?? 200,
        O3: limits.O3 ?? 200,
        PM10: limits.PM10 ?? 150,
        'PM2.5': limits['PM2.5'] ?? 75,
        CO: limits.CO ?? null,
      },
      ai_event_type_dictionary: Array.isArray(cfg.ai_event_type_dictionary) ? [...cfg.ai_event_type_dictionary] : [],
      initial_naming_priority: Array.isArray(cfg.initial_naming_priority) ? [...cfg.initial_naming_priority] : [],
      _aiDictionaryText: (cfg.ai_event_type_dictionary || []).join('\n'),
    }
  } catch (err) {
    configError.value = '加载配置失败：' + (err?.message || err)
  } finally {
    configBusy.value = false
  }
}

const parseDictionaryText = () => {
  configDraft.value.ai_event_type_dictionary = configDraft.value._aiDictionaryText
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean)
}

const saveConfig = async () => {
  parseDictionaryText()
  configSaving.value = true
  configSaveMessage.value = ''
  try {
    const { _aiDictionaryText, ...values } = configDraft.value
    await saveJiangsuSmartEventConfig(values)
    configSaveMessage.value = '配置已保存'
    configSaveOk.value = true
  } catch (err) {
    configSaveMessage.value = '保存失败：' + (err?.message || err)
    configSaveOk.value = false
  } finally {
    configSaving.value = false
  }
}
const aiDispatchDescription = computed(() => judgmentSummary.value || selectedEvent.value?.ai_data_impact || selectedEvent.value?.primary_clue_tag || '请根据事件证据完成现场核查与处置。')
const operationRecords = computed(() => Array.isArray(selectedEvent.value?.operation_records) ? selectedEvent.value.operation_records : [])
const statusOptions = computed(() => listFilters.value.statuses)
const CATEGORY_TYPES = {
  'external-environment': ['疑似雾炮喷淋', '疑似人员进入采样区干扰操作', '疑似外界环境影响'],
  'instrument-fault': ['疑似仪器故障', '疑似站房停电', '疑似公共系统异常', '疑似站房环境影响']
}
const categoryEventTypes = computed(() => CATEGORY_TYPES[props.category] || null)
const emptyTypeOptionLabel = computed(() => '全部类型')
// 入口默认勾选该类别全部类型（仪器故障 4 类 / 外界环境 3 类），勾选态与后端筛选范围一致。
selectedEventTypes.value = [...(categoryEventTypes.value || [])]
const typeOptions = computed(() => {
  // 并集：接口可用类型 ∪ 入口类别类型 ∪ 当前筛选值，保证 Agent 指定的类别外类型也能显示。
  return [...new Set([
    ...listFilters.value.types,
    ...(categoryEventTypes.value || []),
    ...selectedEventTypes.value,
  ])]
})
const levelOptions = computed(() => listFilters.value.levels || [])
// 事件类型下拉：收起时显示“全部类型”或已选摘要，展开为复选框列表。
const typeFilterRef = ref(null)
const typeMenuOpen = ref(false)
let typeLoadTimer = null
let appliedTypeKey = ''
const typeTriggerLabel = computed(() => {
  const picked = selectedEventTypes.value
  if (!picked.length) return emptyTypeOptionLabel.value
  return picked.length === 1 ? picked[0] : `${picked[0]} 等 ${picked.length} 类`
})
const toggleTypeMenu = () => {
  typeMenuOpen.value = !typeMenuOpen.value
}
const closeTypeMenu = () => {
  if (!typeMenuOpen.value) return
  typeMenuOpen.value = false
  scheduleTypeLoad()
}
const clearTypeSelection = () => {
  selectedEventTypes.value = []
  scheduleTypeLoad()
}
const scheduleTypeLoad = () => {
  // 未点“完成”就点外部关闭、或勾选变化时，300ms 防抖后按最终选择刷新一次。
  const key = JSON.stringify(selectedEventTypes.value)
  if (key === appliedTypeKey) return
  if (typeLoadTimer) clearTimeout(typeLoadTimer)
  typeLoadTimer = setTimeout(() => {
    typeLoadTimer = null
    loadEvents()
  }, 300)
}
const handleTypeMenuPointerDown = event => {
  if (!typeMenuOpen.value) return
  if (!typeFilterRef.value?.contains(event.target)) closeTypeMenu()
}
// 事件类型已由后端接口筛选，列表直接使用接口返回结果。
const filteredEvents = computed(() => events.value)
const pendingCount = computed(() => listStats.value.pending)
const stationCount = computed(() => listStats.value.stations)
const lastSyncTime = computed(() => formatTime(lastSync.value))

const tagSourceClass = source => {
  const text = String(source || '')
  if (text.includes('视频')) return 'video'
  if (text.includes('数据')) return 'data'
  if (text.includes('断数')) return 'missing'
  if (text.includes('超限')) return 'exceed'
  if (text.includes('合规')) return 'compliance'
  if (text.includes('报警')) return 'alarm'
  return ''
}
const tagChips = event => {
  const tags = Array.isArray(event?.clue_tags) ? event.clue_tags.filter(Boolean) : []
  const groups = new Map()
  for (const tag of tags) {
    const name = tag.tag_name || tag.tag_display_text || '告警线索'
    const entry = groups.get(name) || { name, count: 0, source: tag.tag_source || '' }
    entry.count += 1
    groups.set(name, entry)
  }
  if (!groups.size) {
    const fallback = event?.primary_clue_tag || event?.source_alarm_rule_type
    if (fallback) groups.set(fallback, { name: fallback, count: 1, source: '' })
  }
  return [...groups.values()].map(entry => ({
    ...entry,
    label: entry.count > 1 ? `${entry.name} x${entry.count}` : entry.name,
    klass: tagSourceClass(entry.source),
  }))
}
const expandedTagIds = ref(new Set())
const visibleTagChips = event => {
  const chips = tagChips(event)
  return expandedTagIds.value.has(String(event.event_id)) ? chips : chips.slice(0, 6)
}
const hiddenTagCount = event => {
  const chips = tagChips(event)
  return expandedTagIds.value.has(String(event.event_id)) ? 0 : Math.max(0, chips.length - 6)
}
const expandTags = id => { expandedTagIds.value = new Set(expandedTagIds.value).add(String(id)) }
const detailTagChips = computed(() => tagChips(selectedEvent.value))
const evidenceSourceEntries = computed(() => {
  const labels = { monitoring: '本站监测数据', station_alarm: '站房设备报警', acquisition_alarm: '数采报警', environment: '动力环境历史', qc_history: '质控操作记录', compliance: '运维工单检索', comparison: '片区小时对比', weather: '气象时序数据', instrument_status: '仪器状态', door: '门禁记录', video: '视频监控记录' }
  const packageData = selectedEvent.value?.evidence_package || {}
  // 平台告警源已下线，存量旧证据包中的该源不再展示。
  // 本站小时监测数据仍保留在证据包中供研判和气象联动使用，界面统一在片区对比中呈现。
  const hiddenSources = new Set(['monitoring', 'platform_alarm', 'uploaded_workbook', 'video_clip'])
  const sources = packageData.sources || {}
  const gaps = Array.isArray(packageData.gaps) ? packageData.gaps : []
  const entries = Object.entries(sources)
    .filter(([key]) => !hiddenSources.has(key))
    .map(([key, value], index) => ({ key, label: labels[key] || key, value, index: index + 1 }))
  gaps.forEach(gap => {
    if (!gap?.source || hiddenSources.has(gap.source) || entries.some(entry => entry.key === gap.source)) return
    entries.push({
      key: gap.source,
      label: labels[gap.source] || gap.source,
      value: { status: gap.status || 'unavailable', summary: gap.reason || '该数据源暂不可用', data: [] }, index: entries.length + 1,
    })
  })
  return entries
})
const workbenchSections = computed(() => [
  { key: 'event', label: '事件基础信息', value: { status: 'success', success: true }, index: 1 },
  ...evidenceSourceEntries.value.map((entry, index) => ({ ...entry, index: index + 2 })),
  { key: 'judgment', label: 'AI研判结果', index: evidenceSourceEntries.value.length + 2, value: { status: judgment.value?.final_response ? 'success' : 'empty', success: Boolean(judgment.value?.final_response) } },
  { key: 'disposal', label: '处置操作', index: evidenceSourceEntries.value.length + 3, value: { status: selectedEvent.value?.archived ? 'success' : 'empty', success: Boolean(selectedEvent.value?.archived) } },
  { key: 'tasks', label: '关联任务', index: evidenceSourceEntries.value.length + 4, value: { status: tasks.value.length ? 'success' : 'empty', success: tasks.value.length > 0 } },
])
const detailAlarmRows = computed(() => eventAlarmRows(selectedEvent.value))
const detailAlarmGroups = computed(() => groupAlarmRows(detailAlarmRows.value))
const alarmGroupTimeText = group => {
  const end = formatTime(group.endTime)
  const start = formatTime(group.startTime)
  return !group.startTime || group.startTime === group.endTime ? end : `${end} – ${start}`
}
const displayDataImpact = event => ['有数据影响', '无数据影响'].includes(event?.ai_data_impact)
  ? event.ai_data_impact : (event?.system_data_impact || '待确认')
const eventFacts = computed(() => [
  { label: '站点名称', value: selectedEvent.value?.site_name || selectedEvent.value?.site_id || '-' },
  { label: '发生时间', value: formatTime(selectedEvent.value?.latest_occurrence_time || selectedEvent.value?.event_start_time) },
  { label: '事件起始时间', value: formatTime(selectedEvent.value?.event_start_time) },
  { label: '事件结束时间', value: formatTime(selectedEvent.value?.event_end_time) },
  { label: '事件名称', value: selectedEvent.value?.event_name || selectedEvent.value?.initial_event_name || '-' },
  { label: '告警类型', value: selectedEvent.value?.source_alarm_rule_type || selectedEvent.value?.primary_clue_tag || '待识别' },
  { label: '线索数量', value: selectedEvent.value?.clue_count || detailTagChips.value.length || '-' },
  { label: 'AI事件类型', value: selectedEvent.value?.ai_event_type || '待研判' },
  { label: '处理状态', value: selectedEvent.value?.event_status || '未研判' },
  { label: '数据影响', value: displayDataImpact(selectedEvent.value) },
  { label: '系统数据影响初判', value: selectedEvent.value?.system_data_impact || '待确认' },
  { label: 'AI 研判优先级', value: selectedEvent.value?.ai_task_priority === 'urgent' ? '紧急' : '普通' },
  { label: '建议等级', value: selectedEvent.value?.ai_suggested_level || '待研判' },
  { label: '研判轮次', value: judgmentRounds.value || '待研判' },
])
const sourceColumnDefinitions = {
  station_alarm: [
    { key: 'alarmTime', label: '告警时间' }, { key: 'stationName', label: '站点名称' },
    { key: 'description', label: '告警信息' }, { key: 'alarmGrade', label: '告警等级' },
  ],
  platform_alarm: [
    { key: 'alarmtime', label: '告警时间' }, { key: 'stationName', label: '站点名称' },
    { key: 'ddruletype', label: '告警类型' }, { key: 'content', label: '告警信息' },
  ],
  acquisition_alarm: [
    { key: 'lauchTime', label: '告警时间' }, { key: 'stationName', label: '站点名称' },
    { key: 'typeStr', label: '告警类型' }, { key: 'descriptionDE', label: '告警信息' },
  ],
  environment: [
    { key: 'timePoint', label: '时间' }, { key: 'itemName', label: '监测项' },
    { key: 'value', label: '监测值' }, { key: 'mark', label: '标识' },
  ],
  qc_history: [
    { key: 'createTime', label: '记录时间' }, { key: 'stationName', label: '站点名称' },
    { key: 'missionName', label: '质控任务' }, { key: 'result', label: '质控结果' },
  ],
  compliance: [
    { key: 'createTime', label: '创建时间' }, { key: 'orderType', label: '工单类型' },
    { key: 'orderTitle', label: '工单标题' }, { key: 'workingOrderCode', label: '工单号' },
    { key: 'orderStatus', label: '工单状态' }, { key: 'handler', label: '处理人' },
  ],
  comparison: [
    { key: 'stationCode', label: '站点编码' }, { key: 'stationName', label: '站点名称' },
    { key: 'timePoint', label: '时间' }, { key: 'sO2', label: 'SO₂' },
    { key: 'nO2', label: 'NO₂' }, { key: 'co', label: 'CO' }, { key: 'o3', label: 'O₃' },
    { key: 'pM10', label: 'PM₁₀' }, { key: 'pM2_5', label: 'PM₂.₅' },
  ],
  weather: [
    { key: 'timePoint', label: '时间' }, { key: 'temperature', label: '气温' },
    { key: 'humidity', label: '湿度' }, { key: 'windSpeed', label: '风速' },
    { key: 'windDirection', label: '风向' }, { key: 'pressure', label: '气压' },
  ],
  instrument_status: [
    { key: 'pollutantName', label: '污染物' }, { key: 'dataResolution', label: '数据类型' },
    { key: 'statusName', label: '监测项' }, { key: 'targetUnit', label: '单位' },
    { key: 'timePoint', label: '时间' }, { key: 'valueSummary', label: '监测值' },
    { key: 'abnormalSummary', label: '异常点' }, { key: 'pointCount', label: '点数' },
  ],
  door: [
    { key: 'eventTime', label: '事件时间' }, { key: 'doorName', label: '门禁点' },
    { key: 'personName', label: '姓名' }, { key: 'direction', label: '出/入' },
    { key: 'eventType', label: '事件类型' },
  ],
}

const statusClass = event => {
  const status = String(event?.event_status || '')
  if (status.includes('完成') || status.includes('归档') || status.includes('已反馈')) return 'success'
  if (status.includes('处理中') || status.includes('研判') || status.includes('处置中')) return 'warning'
  return 'pending'
}

const OPERATION_ACTION_LABELS = {
  dispatch_order: '派单处置',
  event_feedback: '事件反馈',
  archive_event: '事件归档',
  confirm_ai_judgment: '人工确认研判',
  save_ai_judgment_draft: '保存确认草稿',
}
const operationActionLabel = action => OPERATION_ACTION_LABELS[action] || action || '事件操作'

const sourceStatus = source => {
  if (!source) return '未抓取'
  if (source.status === 'success') return '已获取'
  if (source.success === true && !source.status) return '已获取'
  if (source.status === 'empty') return '无记录'
  if (source.status === 'skipped') return '按条件跳过'
  if (source.status === 'unavailable') return '暂不可用'
  return source.status === 'partial' ? '部分获取' : '获取失败'
}
const sourceStatusClass = source => source?.status === 'success' || (source?.success === true && !source?.status) ? 'ok' : (source?.status === 'empty' || source?.status === 'skipped') ? 'empty' : 'bad'
const sourceRecordCount = source => {
  if (!source) return 0
  if (source.record_count != null) return source.record_count
  if (source.data?.raw_points != null) return source.data.raw_points
  if (source.data?.station_hour?.record_count != null) return Number(source.data.station_hour.record_count || 0) + Number(source.data.station_5minute?.record_count || 0)
  return Array.isArray(source.data) ? source.data.length : 0
}
const videoEvidenceRows = section => {
  const rows = sourceRows(section)
  return rows.map((row, index) => {
    const path = row?.image_path || row?.imagePath || row?.screenshot_path || row?.screenshotPath
    const evidenceIndex = reviewEvidence.value.findIndex(item => {
      const candidate = String(item?.path || '')
      return path && candidate === String(path)
    })
    return { row, index, path, evidenceIndex }
  }).filter(item => item.path)
}
const reviewEvidenceUrl = evidenceIndex => evidenceIndex >= 0 && selectedEvent.value?.review_id
  ? `/api/task-reviews/${encodeURIComponent(selectedEvent.value.review_id)}/evidence/${evidenceIndex}` : ''
const videoEvidenceUrl = item => item?.path && selectedEvent.value?.event_id
  ? `/api/jiangsu/smart-events/${encodeURIComponent(selectedEvent.value.event_id)}/video-image` : ''
const loadVideoImages = async eventId => {
  videoImageUrls.value = {}
  const response = await authFetch(`/api/jiangsu/smart-events/${encodeURIComponent(eventId)}/video-image`)
  if (response.ok) videoImageUrls.value = { 0: URL.createObjectURL(await response.blob()) }
}
const normalizeQcRow = row => ({
  ...row,
  missionName: row?.missionName || row?.Mission_Name || row?.rName || row?.taskName || row?.missionGroupName || row?.Mission_Group_Name || row?.poll || '-',
  result: row?.result || row?.Result || row?.qcResult || '-',
})
const instrumentStatusRows = source => {
  // 新证据包为映射投影（series），存量旧包为逐行原始记录，两种都兼容展示。
  const resolutions = [['five_minute', '五分钟'], ['hour', '小时']]
  const rawRows = data => Array.isArray(data) ? data : (data?.items || data?.list || data?.rows || data?.records || data?.data || [])
  const seriesRows = data => Array.isArray(data?.series) ? data.series.map(item => {
    const first = item.first_t || ''
    const last = item.last_t || ''
    const range = !first && !last
      ? '-'
      : (first && last && last !== first ? `${formatTime(first)} ~ ${formatTime(last)}` : formatTime(first || last))
    const values = [item.min, item.max].filter(value => value != null)
    const valueSummary = values.length
      ? `${values[0]}${values.length > 1 && values[0] !== values[1] ? ` ~ ${values[1]}` : ''}${item.mean != null ? `（均 ${item.mean}）` : ''}`
      : '-'
    const abnormal = Array.isArray(item.abnormal) ? item.abnormal : []
    return {
      pollutantName: item.p || '-', dataResolution: '', statusName: item.param || '-',
      targetUnit: item.unit || '-', timePoint: range, valueSummary,
      abnormalSummary: abnormal.length
        ? abnormal.slice(0, 3).map(point => `${formatTime(point.t)} ${point.v}${point.m ? `(${point.m})` : ''}`).join('；') + (abnormal.length > 3 ? ` 等${abnormal.length}个` : '')
        : '-',
      pointCount: item.n ?? '-',
    }
  }) : []
  return resolutions.flatMap(([key, label]) => {
    const data = source.data?.[key]
    const rows = Array.isArray(data?.series)
      ? seriesRows(data)
      : rawRows(data).map(row => ({
        ...row, pollutantName: row.pollutantName || row.pollutantCode || '-',
        dataResolution: label, valueSummary: row.moniterValue, abnormalSummary: '-', pointCount: '-',
      }))
    return rows.map(row => ({ ...row, dataResolution: row.dataResolution || label }))
  })
}
const sourceRows = section => {
  const source = section?.value
  if (!source) return []
  if (section.key === 'instrument_status') return instrumentStatusRows(source)
  if (Array.isArray(source.data)) {
    let rows = source.data.flatMap(row => row?.result?.alarmLogs || row?.alarmLogs || [row])
    if (section.key === 'qc_history') rows = rows.map(normalizeQcRow)
    return rows.filter(row => row && typeof row === 'object')
  }
  if (source.data && typeof source.data === 'object') {
    const rows = source.data.tableData || source.data.chartData || source.data.records || source.data.items
    return Array.isArray(rows) ? rows.filter(row => row && typeof row === 'object') : []
  }
  return []
}
const sourceColumns = source => {
  return sourceColumnDefinitions[source?.key] || []
}
const displayCell = (row, column) => {
  const value = row?.[column]
  if (value == null || value === '') return '-'
  if (/(?:time|date|_at$)/i.test(column) || (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(value.trim()))) {
    return formatTime(value)
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value).length > 72 ? `${String(value).slice(0, 72)}…` : String(value)
}

const deltaChartRef = ref(null)
const comparisonChartRef = ref(null)
const weatherChartRef = ref(null)
let deltaChartInstance = null
let comparisonChartInstance = null
let weatherChartInstance = null
const POLLUTANT_SERIES = [
  { key: 'pM10', label: 'PM10' },
  { key: 'pM2_5', label: 'PM2.5' },
  { key: 'sO2', label: 'SO2' },
  { key: 'nO2', label: 'NO2' },
  { key: 'co', label: 'CO' },
  { key: 'o3', label: 'O3' },
]
const recordPollutant = (row, key) => {
  if (!row) return null
  for (const candidate of [key, key.toUpperCase(), key.toLowerCase()]) {
    if (row[candidate] != null && row[candidate] !== '') {
      const value = Number(row[candidate])
      return Number.isFinite(value) && value > -900 ? value : null
    }
  }
  return null
}
const hourlyRecords = computed(() => {
  const data = selectedEvent.value?.evidence_package?.sources?.monitoring?.data?.station_hour?.data
  return Array.isArray(data) ? data.filter(row => row && typeof row === 'object').slice().sort((a, b) => String(a.timePoint || '').localeCompare(String(b.timePoint || ''))) : []
})
const regionalDeltas = computed(() => {
  const deltas = selectedEvent.value?.evidence_package?.sources?.comparison?.regional_deltas
  return deltas && typeof deltas === 'object' ? deltas : null
})
const comparisonTargetName = computed(() => {
  const comparison = selectedEvent.value?.evidence_package?.sources?.comparison
  return comparison?.target_station_name || comparison?.target_station?.name || comparison?.target_station_code || selectedEvent.value?.site_name || '-'
})
const comparisonNearbyCount = computed(() => selectedEvent.value?.evidence_package?.sources?.comparison?.regional_deltas?.nearby_stations?.station_count
  ?? selectedEvent.value?.evidence_package?.sources?.comparison?.peer_station_count ?? 0)
const comparisonCityCount = computed(() => selectedEvent.value?.evidence_package?.sources?.comparison?.regional_deltas?.city_rest_stations?.station_count
  ?? selectedEvent.value?.evidence_package?.sources?.comparison?.city_rest_station_count ?? 0)
const comparisonDeltaRows = computed(() => {
  const deltas = selectedEvent.value?.evidence_package?.sources?.comparison?.regional_deltas
  if (!deltas || typeof deltas !== 'object') return []
  const nearby = deltas.nearby_station_delta || {}
  const city = deltas.same_city_delta || {}
  const order = Array.isArray(deltas.pollutant_order) ? deltas.pollutant_order : POLLUTANT_SERIES.map(item => item.label)
  return order.filter(name => nearby[name] != null || city[name] != null).map(name => ({
    name,
    nearby: nearby[name] == null ? '-' : nearby[name],
    city: city[name] == null ? '-' : city[name],
  }))
})
const comparisonTrendRows = computed(() => {
  const trends = selectedEvent.value?.evidence_package?.sources?.comparison?.regional_deltas?.trend_comparison
  if (!trends || typeof trends !== 'object') return []
  const order = Array.isArray(selectedEvent.value?.evidence_package?.sources?.comparison?.regional_deltas?.pollutant_order)
    ? selectedEvent.value.evidence_package.sources.comparison.regional_deltas.pollutant_order
    : POLLUTANT_SERIES.map(item => item.label)
  return order.filter(name => trends[name]).map(name => ({
    name,
    target: trends[name].target_direction || '数据不足',
    nearby: trends[name].nearby_direction || '数据不足',
    consistent: trends[name].consistency || (trends[name].direction_consistent ? '一致' : '不一致/不足'),
    correlation: trends[name].pearson_correlation == null ? '-' : trends[name].pearson_correlation,
    hours: trends[name].aligned_hours ?? 0,
  }))
})
const comparisonPollutant = ref('pM10')
const comparisonRecords = computed(() => {
  const data = selectedEvent.value?.evidence_package?.sources?.comparison?.data
  return Array.isArray(data) ? data.filter(row => row && typeof row === 'object' && row.timePoint) : []
})
const comparisonChartOption = computed(() => {
  if (!comparisonRecords.value.length) return null
  const times = [...new Set(comparisonRecords.value.map(row => weatherTimeKey(row.timePoint)))].filter(Boolean).sort()
  const targetCode = String(selectedEvent.value?.site_id || '')
  const stations = new Map()
  for (const row of comparisonRecords.value) {
    const code = String(row.stationCode || row.code || '')
    if (!code) continue
    const station = stations.get(code) || { code, name: row.stationName || row.name || code, values: new Map() }
    station.values.set(weatherTimeKey(row.timePoint), recordPollutant(row, comparisonPollutant.value))
    stations.set(code, station)
  }
  if (!stations.size || !times.length) return null
  const ordered = [...stations.values()].sort((a, b) => Number(b.code === targetCode) - Number(a.code === targetCode) || a.name.localeCompare(b.name, 'zh-CN'))
  return {
    tooltip: { trigger: 'axis', confine: true },
    legend: { type: 'scroll', top: 0, left: 0, right: 0 },
    grid: { left: 58, right: 24, top: 52, bottom: 56 },
    xAxis: { type: 'category', boundaryGap: false, data: times, axisLabel: { hideOverlap: true, formatter: value => String(value).slice(5, 16) } },
    yAxis: { type: 'value', name: comparisonPollutant.value === 'co' ? 'mg/m³' : 'μg/m³', scale: true },
    dataZoom: [{ type: 'inside', filterMode: 'none' }, { type: 'slider', bottom: 8, height: 20, filterMode: 'none' }],
    series: ordered.map((station, index) => {
      const target = station.code === targetCode
      return {
        name: `${station.name}（${station.code}）${target ? ' · 目标站' : ''}`,
        type: 'line',
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: target ? 3 : 1.5, opacity: target ? 1 : 0.72 },
        itemStyle: target ? { color: '#d4380d' } : undefined,
        z: target ? 5 : 2 + index,
        data: times.map(time => station.values.get(time) ?? null),
      }
    }),
  }
})
const deltaChartOption = computed(() => {
  if (!regionalDeltas.value) return null
  const order = Array.isArray(regionalDeltas.value.pollutant_order) && regionalDeltas.value.pollutant_order.length
    ? regionalDeltas.value.pollutant_order
    : POLLUTANT_SERIES.map(item => item.label)
  const nearby = regionalDeltas.value.nearby_station_delta || {}
  const city = regionalDeltas.value.same_city_delta || {}
  const names = order.filter(name => nearby[name] != null || city[name] != null)
  if (!names.length) return null
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['与周边站点差值', '与全市其余站点差值'], top: 0 },
    grid: { left: 56, right: 24, top: 36, bottom: 32 },
    xAxis: { type: 'category', data: names },
    yAxis: { type: 'value', name: '差值' },
    series: [
      { name: '与周边站点差值', type: 'bar', itemStyle: { color: '#1677ff' }, data: names.map(name => nearby[name] ?? null) },
      { name: '与全市其余站点差值', type: 'bar', itemStyle: { color: '#d4380d' }, data: names.map(name => city[name] ?? null) },
    ],
  }
})
const ensureChart = (holder, instance, option) => {
  if (!holder || !option) {
    instance?.dispose()
    return null
  }
  if (instance && (instance.isDisposed() || instance.getDom() !== holder)) {
    instance.dispose()
    instance = null
  }
  const chart = instance || echarts.init(holder)
  chart.setOption(option, true)
  return chart
}
const WEATHER_SERIES = [
  { key: 'temperature', label: '气温(℃)' },
  { key: 'humidity', label: '湿度(%)' },
  { key: 'windSpeed', label: '风速(m/s)' },
  { key: 'pressure', label: '气压(hPa)' },
]
const weatherRecords = computed(() => {
  const data = selectedEvent.value?.evidence_package?.sources?.weather?.data
  const rows = Array.isArray(data) ? data.filter(row => row && typeof row === 'object' && row.timePoint) : []
  return [...rows].sort((a, b) => String(a.timePoint).localeCompare(String(b.timePoint)))
})
const weatherTimeKey = value => String(value || '').replace('T', ' ').slice(0, 19)
const weatherValue = value => {
  if (value == null || value === '' || Number(value) <= -99) return null
  return Number.isFinite(Number(value)) ? Number(value) : null
}
const weatherChartOption = computed(() => {
  if (!weatherRecords.value.length) return null
  const times = [...new Set([...weatherRecords.value, ...hourlyRecords.value].map(row => weatherTimeKey(row.timePoint)))].filter(Boolean).sort()
  const weatherByTime = new Map(weatherRecords.value.map(row => [weatherTimeKey(row.timePoint), row]))
  const pollutantsByTime = new Map(hourlyRecords.value.map(row => [weatherTimeKey(row.timePoint), row]))
  const series = POLLUTANT_SERIES.map(item => ({
    name: item.label, type: 'line', xAxisIndex: 0, yAxisIndex: item.key === 'co' ? 1 : 0,
    showSymbol: false, connectNulls: false,
    data: times.map(time => recordPollutant(pollutantsByTime.get(time), item.key)),
  }))
  series.push(...WEATHER_SERIES.map(item => ({
    name: item.label, type: 'line', xAxisIndex: item.key === 'windSpeed' ? 1 : 2,
    yAxisIndex: { windSpeed: 2, temperature: 4, humidity: 4, pressure: 5 }[item.key],
    showSymbol: false, connectNulls: false,
    data: times.map(time => weatherValue(weatherByTime.get(time)?.[item.key])),
  })))
  series.push({
    name: '风向', type: 'scatter', xAxisIndex: 1, yAxisIndex: 3,
    symbol: 'path://M-1,12 L-1,-5 L-4,-5 L0,-12 L4,-5 L1,-5 L1,12 Z',
    symbolSize: [8, 26], itemStyle: { color: '#1684f8' },
    data: times.flatMap(time => {
      const row = weatherByTime.get(time)
      const direction = weatherValue(row?.windDirection ?? row?.windDirect)
      if (direction == null || direction < 0 || direction > 360) return []
      // 气象风向表示来向；箭头指向风吹去的方向。
      return [{ value: [time, 0.5, direction], symbolRotate: 180 - direction }]
    }),
    encode: { x: 0, y: 1, tooltip: [2] },
    tooltip: { valueFormatter: value => `${value}°（来向）` },
  })
  const xAxis = [0, 1, 2].map(gridIndex => ({
    type: 'category', gridIndex, data: times, boundaryGap: false,
    name: gridIndex === 2 ? '时间' : '',
    axisLabel: { show: gridIndex === 2, hideOverlap: true, formatter: value => String(value).slice(5, 16) },
    axisTick: { show: gridIndex === 2 },
    axisLine: { show: gridIndex === 2 },
  }))
  return {
    tooltip: { trigger: 'axis', confine: true },
    legend: { type: 'scroll', top: 0, left: 0, right: 0 },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 64, right: 108, top: 56, height: 130 },
      { left: 64, right: 108, top: 240, height: 90 },
      { left: 64, right: 108, top: 386, height: 130 },
    ],
    xAxis,
    yAxis: [
      { type: 'value', gridIndex: 0, name: '浓度 (μg/m³)', scale: true },
      { type: 'value', gridIndex: 0, name: 'CO (mg/m³)', position: 'right', scale: true, splitLine: { show: false } },
      { type: 'value', gridIndex: 1, name: '风速 (m/s)', min: 0 },
      { type: 'value', gridIndex: 1, show: false, min: 0, max: 1 },
      { type: 'value', gridIndex: 2, name: '气温 (℃) / 湿度 (%)', scale: true },
      { type: 'value', gridIndex: 2, name: '气压 (hPa)', position: 'right', scale: true, splitLine: { show: false } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2], filterMode: 'none' },
      { type: 'slider', xAxisIndex: [0, 1, 2], bottom: 8, height: 22, filterMode: 'none' },
    ],
    series,
  }
})
const renderCharts = () => {
  deltaChartInstance = ensureChart(deltaChartRef.value, deltaChartInstance, deltaChartOption.value)
  comparisonChartInstance = ensureChart(comparisonChartRef.value, comparisonChartInstance, comparisonChartOption.value)
  weatherChartInstance = ensureChart(weatherChartRef.value, weatherChartInstance, weatherChartOption.value)
}
const handleChartResize = () => {
  deltaChartInstance?.resize()
  comparisonChartInstance?.resize()
  weatherChartInstance?.resize()
}
// Function refs keep one DOM element inside the section v-for. Track mount/unmount
// as well as data changes so returning to an unchanged event recreates its charts.
watch([deltaChartRef, comparisonChartRef, weatherChartRef, deltaChartOption, comparisonChartOption, weatherChartOption], renderCharts, { flush: 'post' })
const rootRef = ref(null)
let chartResizeObserver = null
onMounted(() => {
  window.addEventListener('resize', handleChartResize)
  document.addEventListener('pointerdown', handleTypeMenuPointerDown)
  // 嵌入右侧面板时宽度可拖动调整，通过容器尺寸观察同步图表尺寸
  if (typeof ResizeObserver !== 'undefined') {
    chartResizeObserver = new ResizeObserver(handleChartResize)
    if (rootRef.value) chartResizeObserver.observe(rootRef.value)
  }
})

const SHANGHAI_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})
const formatTime = value => {
  if (!value) return '时间未知'
  const text = String(value).trim()
  const naiveDateTime = text.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?$/)
  if (naiveDateTime) return `${naiveDateTime[1]} ${naiveDateTime[2]}:${naiveDateTime[3] || '00'}`
  const date = value instanceof Date ? value : new Date(text)
  if (Number.isNaN(date.getTime())) return text
  const parts = Object.fromEntries(SHANGHAI_DATE_TIME_FORMATTER.formatToParts(date).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}
const formatTimeRange = values => Array.isArray(values) ? values.map(formatTime).join(' ~ ') : formatTime(values)

let detailRequestId = 0
const selectEvent = async eventId => {
  const requestId = ++detailRequestId
  selectedId.value = eventId
  detailLoading.value = true
  try {
    tasks.value = []
    listJiangsuSmartEventTasks({ event_id: eventId }).then(payload => {
      if (requestId === detailRequestId) tasks.value = payload.tasks || []
    }).catch(() => {})
    const detail = await getJiangsuSmartEvent(eventId, { refresh: false })
    if (requestId !== detailRequestId) return
    selectedEvent.value = detail.event || null
    loadVideoImages(eventId).catch(() => {})
    reviewEvidence.value = []
    if (selectedEvent.value?.review_id) {
      try {
        const review = await getTaskReview(selectedEvent.value.review_id)
        if (requestId === detailRequestId) reviewEvidence.value = review.review?.evidence || []
      } catch (_) {
        // The event evidence table remains usable when an old review was removed.
      }
    }
    if (eventConfig.value === null) loadEventConfig()
    actionMessage.value = ''
    workspaceMode.value = 'detail'
  } catch (err) {
    if (requestId === detailRequestId) error.value = err?.message || '事件详情加载失败'
  } finally {
    if (requestId === detailRequestId) detailLoading.value = false
  }
}

const openDetail = async eventId => {
  viewMode.value = 'detail'
  await selectEvent(eventId)
}

const isAiBusy = eventId => aiBusyIds.value.has(String(eventId))

// 与后端 _bucket_judged 对齐：已有 AI 研判结论的事件不再提供手动研判入口，避免误触发整轮重判。
const hasCompletedJudgment = event => Boolean(event?.ai_judgment?.final_response)
  || Boolean(event?.ai_event_type)
  || ['AI 已研判', '待人工确认', '已确认'].includes(String(event?.event_status || ''))

const dispatchAiJudgment = async event => {
  const eventId = String(event?.event_id || '')
  if (!eventId || isAiBusy(eventId)) return
  if (hasCompletedJudgment(event) && !event.pending_delta) {
    actionMessage.value = '该事件已完成 AI 研判，无需再次触发'
    return
  }
  aiBusyIds.value = new Set(aiBusyIds.value).add(eventId)
  error.value = ''
  actionMessage.value = ''
  try {
    const payload = await dispatchJiangsuSmartEventAiJudgment(eventId)
    const updated = payload.event
    if (updated) {
      const index = events.value.findIndex(item => String(item.event_id) === eventId)
      if (index >= 0) events.value.splice(index, 1, updated)
      if (String(selectedEvent.value?.event_id) === eventId) selectedEvent.value = updated
    }
    actionMessage.value = 'AI研判任务已提交，可在任务管理中查看'
  } catch (err) {
    actionMessage.value = err?.message || 'AI研判任务提交失败'
  } finally {
    const next = new Set(aiBusyIds.value)
    next.delete(eventId)
    aiBusyIds.value = next
  }
}

const backToList = () => {
  viewMode.value = 'list'
  workspaceMode.value = 'detail'
  error.value = ''
}

const scrollToEvidence = key => {
  activeEvidenceKey.value = key
  const container = evidenceContent.value
  const target = document.getElementById(`smart-evidence-${key}`)
  if (container && target) {
    const containerTop = container.getBoundingClientRect().top
    const targetTop = target.getBoundingClientRect().top
    const nextTop = container.scrollTop + targetTop - containerTop
    container.scrollTo({ top: Math.max(0, nextTop), behavior: 'smooth' })
  }
}
const updateActiveEvidence = () => {
  const container = evidenceContent.value
  if (!container) return
  const sections = [...container.querySelectorAll('.workbench-section')]
  const containerTop = container.getBoundingClientRect().top
  const current = sections.filter(section => section.getBoundingClientRect().top <= containerTop + 8).at(-1) || sections[0]
  if (current?.id) activeEvidenceKey.value = current.id.replace('smart-evidence-', '')
}

const collectEvidence = async () => {
  if (!selectedEvent.value || evidenceBusy.value) return
  evidenceBusy.value = true
  error.value = ''
  try {
    const payload = await collectJiangsuSmartEventEvidence(selectedEvent.value.event_id)
    selectedEvent.value = payload.event || selectedEvent.value
    actionMessage.value = `证据包已更新（${payload.collected || 1} 个事件）`
  } catch (err) {
    error.value = err?.message || '证据包抓取失败'
  } finally {
    evidenceBusy.value = false
  }
}

const openDispatchPage = () => {
  actionMessage.value = ''
  dispatchOrder.value = {
    type: '',
    assignee: '运维处置人员',
    title: `${selectedEvent.value?.site_name || ''}智能事件处置工单`,
    description: aiDispatchDescription.value,
  }
  dispatchDialogVisible.value = true
}

const submitDispatchOrder = async () => {
  if (!selectedEvent.value || confirmationBusy.value) return
  confirmationBusy.value = true
  actionMessage.value = ''
  try {
    const payload = await dispatchJiangsuSmartEventOrder(selectedEvent.value.event_id, {
      order_type: dispatchOrder.value.type.trim() || null,
      assignee: dispatchOrder.value.assignee.trim() || null,
      title: dispatchOrder.value.title.trim(),
      description: dispatchOrder.value.description.trim() || null,
    })
    selectedEvent.value = payload.event || selectedEvent.value
    dispatchDialogVisible.value = false
    actionMessage.value = '派单已提交，事件进入待反馈'
  } catch (err) {
    actionMessage.value = err?.message || '派单提交失败'
  } finally {
    confirmationBusy.value = false
  }
}

const openFeedbackDialog = () => {
  actionMessage.value = ''
  feedbackText.value = ''
  feedbackAttachmentNames.value = []
  feedbackDialogVisible.value = true
}

const handleFeedbackAttachments = event => {
  feedbackAttachmentNames.value = [...(event?.target?.files || [])].map(file => file.name)
}

const submitFeedback = async () => {
  if (!selectedEvent.value || confirmationBusy.value) return
  confirmationBusy.value = true
  actionMessage.value = ''
  try {
    const payload = await submitJiangsuSmartEventFeedback(
      selectedEvent.value.event_id,
      feedbackText.value.trim(),
      feedbackAttachmentNames.value,
    )
    selectedEvent.value = payload.event || selectedEvent.value
    feedbackDialogVisible.value = false
    actionMessage.value = '反馈已提交，AI 增量研判结论将自动更新'
  } catch (err) {
    actionMessage.value = err?.message || '反馈提交失败'
  } finally {
    confirmationBusy.value = false
  }
}

const reviewDialogVisible = ref(false)
const refreshSelectedReview = async () => {
  const payload = await getJiangsuSmartEvent(selectedEvent.value.event_id, { refresh: false })
  selectedEvent.value = payload.event
}

const compare = async eventIds => {
  viewMode.value = 'detail'
  detailLoading.value = true
  try {
    const payloads = await Promise.all(eventIds.map(id => getJiangsuSmartEvent(id, { refresh: false })))
    compareEvents.value = payloads.map(payload => payload.event).filter(Boolean)
    workspaceMode.value = 'compare'
  } catch (err) {
    error.value = err?.message || '事件对比加载失败'
  } finally {
    detailLoading.value = false
  }
}

const loadEvents = async (page = 1) => {
  if (loading.value) return
  if (listStartTime.value && listEndTime.value && new Date(listStartTime.value) > new Date(listEndTime.value)) {
    error.value = '开始时间不能晚于结束时间'
    actionMessage.value = error.value
    return
  }
  stopSyncWatch()
  loading.value = true
  error.value = ''
  actionMessage.value = ''
  activeQuery.value = {
    page: Number.isInteger(page) ? page : 1,
    limit: PAGE_SIZE,
    status: statusFilter.value,
    event_types: selectedEventTypes.value.length ? selectedEventTypes.value : undefined,
    level: levelFilter.value,
    keyword: keyword.value,
    start_time: listStartTime.value || undefined,
    end_time: listEndTime.value || undefined,
  }
  appliedTypeKey = JSON.stringify(activeQuery.value.event_types || [])
  try {
    const payload = await listJiangsuSmartEvents({ ...activeQuery.value, refresh: false })
    applyListPage(payload)
    lastSync.value = payload.source_metadata?.last_sync?.synced_at || null
    loading.value = false
    watchBackgroundSync()
  } catch (err) {
    error.value = err?.message || '智能事件加载失败'
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  statusFilter.value = ''
  selectedEventTypes.value = [...(categoryEventTypes.value || [])]
  levelFilter.value = ''
  keyword.value = ''
  const range = defaultListTimeRange()
  listStartTime.value = range.start
  listEndTime.value = range.end
  loadEvents()
}

const SYNC_POLL_INTERVAL_MS = 15000
let syncGeneration = 0
let syncPollTimer = null
const syncing = ref(false)

const stopSyncWatch = () => {
  syncGeneration += 1
  if (syncPollTimer) { clearTimeout(syncPollTimer); syncPollTimer = null }
  syncing.value = false
}

const applySyncedEvents = payload => {
  applyListPage(payload)
}

const pollSyncStatus = async (generation = syncGeneration) => {
  syncPollTimer = null
  try {
    const payload = await listJiangsuSmartEvents({ ...activeQuery.value, page: currentPage.value, refresh: false })
    if (generation !== syncGeneration) return
    if (payload.source_metadata?.last_sync?.synced_at) lastSync.value = payload.source_metadata.last_sync.synced_at
    applySyncedEvents(payload)
  } catch (err) {
    // 后台读取失败时保留列表，下次轮询重试。
  }
  if (generation !== syncGeneration) return
  syncPollTimer = setTimeout(() => pollSyncStatus(generation), SYNC_POLL_INTERVAL_MS)
}

const watchBackgroundSync = () => {
  stopSyncWatch()
  syncPollTimer = setTimeout(() => pollSyncStatus(syncGeneration), SYNC_POLL_INTERVAL_MS)
}

onUnmounted(() => {
  stopSyncWatch()
  detailRequestId += 1
  window.removeEventListener('resize', handleChartResize)
  document.removeEventListener('pointerdown', handleTypeMenuPointerDown)
  if (typeLoadTimer) {
    clearTimeout(typeLoadTimer)
    typeLoadTimer = null
  }
  chartResizeObserver?.disconnect()
  chartResizeObserver = null
  deltaChartInstance?.dispose()
  comparisonChartInstance?.dispose()
  weatherChartInstance?.dispose()
  deltaChartInstance = null
  comparisonChartInstance = null
  weatherChartInstance = null
})

watch(() => props.initialEventId, value => { if (value && value !== selectedId.value) openDetail(value) })

// Agent 焦点值到固定详情证据分区的映射；未命中时不强行滚动
const EVIDENCE_FOCUS_TARGETS = {
  alarm: 'event',
  event: 'event',
  base: 'event',
  timeline: 'monitoring',
  monitoring: 'monitoring',
  data: 'monitoring',
  weather: 'weather',
  video: 'video',
  judgment: 'judgment',
  ai: 'judgment',
  impact: 'judgment',
  disposal: 'disposal',
  operation: 'disposal',
  task: 'tasks',
  tasks: 'tasks',
}
const focusEvidenceSection = async () => {
  const focusKey = String(evidenceFocus.value || '').trim().toLowerCase()
  if (!focusKey) return
  const target = EVIDENCE_FOCUS_TARGETS[focusKey]
  if (!target || !workbenchSections.value.some(section => section.key === target)) return
  await nextTick()
  scrollToEvidence(target)
}

// immediate：面板首次挂载（含右侧面板被 AI 命令打开）时也要消费当前命令
watch(() => props.workspaceCommand, command => {
  if (!command) return
  if (command.type === 'open_event_detail' && command.event_id) openDetail(String(command.event_id))
  if (command.type === 'focus_evidence' && command.event_id) {
    evidenceFocus.value = command.focus || 'evidence'
    openDetail(String(command.event_id)).then(focusEvidenceSection)
  }
  if (command.type === 'compare_events' && Array.isArray(command.event_ids)) compare(command.event_ids.map(String).filter(Boolean))
  if (command.type === 'show_operation_history' && command.event_id) {
    openDetail(String(command.event_id)).then(() => { workspaceMode.value = 'history' })
  }
  if (command.type === 'open_task' && command.task_id) {
    listJiangsuSmartEventTasks({ limit: 1000 }).then(payload => {
      const task = (payload.tasks || []).find(item => item.task_id === command.task_id || item.scheduled_task_id === command.task_id)
      if (task) emit('open-task', task)
    })
  }
  if (command.type === 'show_event_list' || command.type === 'filter_event_list') {
    viewMode.value = 'list'
    workspaceMode.value = 'detail'
    const filters = command.filters || {}
    keyword.value = filters.keyword || command.query?.keyword || ''
    statusFilter.value = filters.status || filters.event_status || ''
    levelFilter.value = filters.level || filters.ai_suggested_level || ''
    // Agent 单值 event_type 与数组 event_types 统一回填到多选；未指定类型时回到入口默认勾选。
    const commandTypes = Array.isArray(filters.event_types) && filters.event_types.length
      ? filters.event_types.map(item => String(item).trim()).filter(Boolean)
      : (String(filters.event_type || filters.type || '').trim() ? [String(filters.event_type || filters.type).trim()] : [])
    selectedEventTypes.value = commandTypes.length ? commandTypes : [...(categoryEventTypes.value || [])]
    const defaultRange = defaultListTimeRange()
    listStartTime.value = filters.start_time || filters.startTime || defaultRange.start
    listEndTime.value = filters.end_time || filters.endTime || defaultRange.end
    loadEvents()
  }
}, { deep: true, immediate: true })
// 切换入口（外界环境 ↔ 仪器故障）时，按新类别重置默认勾选并刷新列表。
watch(() => props.category, () => {
  selectedEventTypes.value = [...(categoryEventTypes.value || [])]
  loadEvents()
})
// 演示冻结模式：读取后端固定窗口并作为默认时间范围；接口缺失（未部署）时静默回退。
const applyDemoFreezeWindow = async () => {
  try {
    const payload = await getJiangsuSmartEventDemoWindow()
    if (payload?.frozen && payload?.window?.start && payload?.window?.end) {
      freezeRange.value = {
        start: toDatetimeLocal(new Date(payload.window.start)),
        end: toDatetimeLocal(new Date(payload.window.end)),
      }
      if (!activeQuery.value?.start_time) {
        listStartTime.value = freezeRange.value.start
        listEndTime.value = freezeRange.value.end
      }
    }
  } catch {
    // 非冻结模式或旧后端：保持默认当天窗口。
  }
}
applyDemoFreezeWindow().then(() => loadEvents())
</script>

<style scoped>
.event-pagination { display: flex; justify-content: flex-end; align-items: center; gap: 12px; padding: 12px 0; }
.smart-event-center { height: 100%; overflow: auto; padding: 24px; background: #f4f7fb; color: #17324d; }
.panel-header, .detail-header, .section-title, .list-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.panel-header { margin-bottom: 16px; }.eyebrow { margin: 0 0 5px; color: #2f6bff; font-size: 10px; letter-spacing: .14em; }.panel-header h2, .detail-header h3 { margin: 0; }.description, .detail-header p, .muted { color: #66758a; font-size: 12px; }.header-actions { display: flex; gap: 8px; }.header-actions button, .back-button, .task-card { border: 1px solid #c9d5e3; border-radius: 8px; background: #fff; color: #2f6bff; cursor: pointer; padding: 8px 12px; }.header-actions .close { color: #526171; }
.event-list-page, .event-detail { min-width: 0; border: 1px solid #dfe7f1; border-radius: 12px; background: #fff; box-shadow: 0 1px 2px rgba(25, 42, 70, .04); }.event-list-page { overflow: hidden; }.list-toolbar { padding: 14px 16px; border-bottom: 1px solid #dfe7f1; color: #66758a; font-size: 12px; }.filter-row { display: flex; flex-wrap: wrap; gap: 10px; flex: 1; }.filter-row input, .filter-row select { height: 36px; min-width: 150px; border: 1px solid #c9d5e3; border-radius: 8px; padding: 0 10px; background: #fff; }.filter-row input { min-width: 240px; flex: 1; }.list-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 12px 16px; border-bottom: 1px solid #edf2f7; background: #fbfcfe; }.list-metrics div { display: grid; gap: 5px; padding: 10px 12px; border: 1px solid #dfe7f1; border-radius: 10px; background: #fff; }.list-metrics span { color: #66758a; font-size: 12px; }.list-metrics strong { font-size: 20px; }.event-table-wrap { overflow: auto; }.event-table { width: 100%; min-width: 980px; border-collapse: collapse; table-layout: fixed; }.event-table th, .event-table td { padding: 12px 10px; border-bottom: 1px solid #edf2f7; vertical-align: middle; text-align: left; word-break: break-word; }.event-table th { color: #66758a; background: #fbfcfe; font-size: 12px; }.event-table td { color: #223040; font-size: 13px; }.event-table tbody tr { cursor: pointer; }.event-table tbody tr:hover { background: #f5f9ff; }.event-table th:nth-child(1) { width: 100px; }.event-table th:nth-child(2) { width: 190px; }.event-table th:nth-child(3) { width: 150px; }.event-table th:nth-child(4) { width: 140px; }.event-table th:nth-child(5) { width: 100px; }.event-table th:nth-child(6) { width: 90px; }.event-table th:nth-child(7) { width: 140px; }.event-table th:nth-child(8) { width: 170px; }.event-table th:nth-child(9) { width: 76px; }.event-name { display: grid; gap: 4px; }.event-name strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.event-name small { color: #66758a; font-size: 11px; }.table-chip { display: inline-flex; align-items: center; padding: 4px 9px; border-radius: 999px; font-size: 12px; white-space: nowrap; }.table-chip.pending { color: #526171; background: #edf2f7; }.table-chip.warning { color: #e07a1e; background: #fff2e2; }.table-chip.success { color: #1f9d65; background: #eaf9f1; }.detail-button { border: 1px solid #2f6bff; border-radius: 7px; color: #2f6bff; background: #fff; padding: 5px 10px; cursor: pointer; }.state { padding: 45px 10px; color: #66758a; text-align: center; }.state.error { color: #bd554c; }
.event-detail { padding: 20px; }.detail-toolbar { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 14px; }.evidence-button { border: 1px solid #2f6bff; border-radius: 8px; color: #2f6bff; background: #fff; padding: 8px 12px; cursor: pointer; }.evidence-button:disabled { opacity: .5; cursor: not-allowed; }.detail-header { align-items: flex-start; padding-bottom: 16px; border-bottom: 1px solid #edf2f2; }.detail-header h3 { max-width: 600px; font-size: 20px; }.status-badge { color: #e07a1e; padding: 5px 8px; border-radius: 10px; background: #fff2e2; font-size: 11px; }.facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 16px 0; }.facts div { padding: 10px; border-radius: 7px; background: #f5f9f9; }.facts dt { color: #80949a; font-size: 10px; }.facts dd { margin: 4px 0 0; color: #34545d; font-size: 12px; }.evidence-summary { margin-top: 16px; padding: 14px; border: 1px solid #e4ecf7; border-radius: 10px; background: #fbfdff; }.evidence-sources { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }.evidence-sources span { padding: 4px 8px; border-radius: 999px; background: #eaf1ff; color: #2f6bff; font-size: 11px; }.evidence-gap { color: #bb7b1c; font-size: 12px; }.evidence-detail-board { margin-top: 16px; padding: 14px; border: 1px solid #e4ecf7; border-radius: 10px; background: #fff; }.evidence-source-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 10px; }.evidence-source-card { min-width: 0; padding: 12px; border: 1px solid #e2e9f2; border-radius: 8px; background: #fbfcfe; }.evidence-source-card header, .source-meta, .monitoring-counts { display: flex; align-items: center; justify-content: space-between; gap: 8px; }.evidence-source-card header { color: #34545d; font-size: 12px; }.source-summary, .source-empty { min-height: 30px; margin: 8px 0; color: #66758a; font-size: 11px; line-height: 1.5; }.source-meta, .monitoring-counts { color: #82909f; font-size: 10px; }.source-status { padding: 3px 7px; border-radius: 999px; font-size: 10px; }.source-status.ok { color: #1f8b5b; background: #e8f8ef; }.source-status.empty { color: #8a6b1c; background: #fff5d9; }.source-status.bad { color: #b6534a; background: #ffeded; }.monitoring-counts { margin-top: 8px; color: #2f6bff; }.source-table-wrap { margin-top: 8px; overflow: auto; }.source-table { width: 100%; border-collapse: collapse; font-size: 10px; }.source-table th, .source-table td { max-width: 150px; padding: 5px 6px; border-bottom: 1px solid #e8edf3; text-align: left; vertical-align: top; word-break: break-word; }.source-table th { color: #6b7b8c; background: #f4f7fb; font-weight: 500; }.source-table td { color: #405466; }.judgment, .task-section { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf2f2; }.section-title { color: #42616a; font-size: 12px; }.section-title span { color: #82969c; font-size: 10px; }.final-response { white-space: pre-wrap; line-height: 1.7; color: #334f57; font-size: 13px; }.task-card { display: flex; align-items: center; justify-content: space-between; width: 100%; margin-top: 8px; text-align: left; }.task-card span:first-child { display: grid; gap: 4px; }.task-card small { color: #83969c; }.task-arrow { white-space: nowrap; font-size: 11px; }.confirmation { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf2f2; }.confirmation-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }.confirmation input, .confirmation textarea { width: 100%; box-sizing: border-box; border: 1px solid #d9e6e7; border-radius: 6px; padding: 8px 9px; font: inherit; font-size: 12px; }.confirmation textarea { margin-top: 8px; resize: vertical; }.confirmation-actions { display: flex; align-items: center; gap: 8px; margin-top: 8px; }.confirmation-actions button { border: 1px solid #acd5d4; border-radius: 6px; background: #effafa; color: #286e73; cursor: pointer; padding: 7px 10px; font-size: 11px; }.confirmation-actions button:disabled { cursor: not-allowed; opacity: .5; }.action-message { color: #5d7c82; font-size: 11px; }
.comparison-overview { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }.comparison-overview > div { padding: 9px; border: 1px solid #e2e9f2; background: #f7faff; }.comparison-overview span, .comparison-overview small { color: #78899a; font-size: 10px; }.comparison-overview strong { display: block; margin-top: 4px; color: #294b61; font-size: 13px; }.comparison-overview small { margin-left: 3px; }.comparison-analysis-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 14px; }.comparison-analysis-panel { min-width: 0; overflow-x: auto; }.comparison-analysis-panel h4, .comparison-records-wrap h4 { margin: 0 0 6px; color: #42616a; font-size: 12px; }.comparison-delta-table { min-width: 100%; }.comparison-delta-table th, .comparison-delta-table td { text-align: right; white-space: nowrap; }.comparison-delta-table th:first-child, .comparison-delta-table td:first-child { text-align: left; }.comparison-records-wrap { margin-top: 14px; }.comparison-chart-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }.comparison-pollutant-switch { display: flex; flex-wrap: wrap; gap: 2px; padding: 2px; background: #eef2f5; }.comparison-pollutant-switch button { min-width: 48px; border: 0; padding: 5px 8px; background: transparent; color: #607483; cursor: pointer; font-size: 10px; }.comparison-pollutant-switch button.active { background: #fff; color: #176b70; box-shadow: 0 1px 3px rgb(37 70 78 / 14%); font-weight: 600; }.comparison-chart-canvas { height: 360px; }
@media (max-width: 860px) { .smart-event-center { padding: 14px; }.list-toolbar { align-items: stretch; flex-direction: column; }.list-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }.facts { grid-template-columns: 1fr; }.comparison-analysis-grid { grid-template-columns: 1fr; } }

/* Match the legacy AI judgment workbench: fixed index and continuously expanded evidence. */
.evidence-detail-board { padding: 0; overflow: hidden; border: 1px solid #e5e9ef; border-radius: 4px; }
.workbench-layout { display: flex; flex: 1; min-height: 0; overflow: hidden; background: #fff; }
.workbench-index { flex: 0 0 190px; height: 100%; box-sizing: border-box; overflow-y: auto; border-right: 1px solid #e5e9ef; background: #f7f9fb; padding: 16px 10px; }
.workbench-index-title { padding: 0 10px 12px; color: #1f2933; font-size: 15px; font-weight: 600; }
.workbench-index-item { display: flex; align-items: center; justify-content: space-between; gap: 6px; width: 100%; min-height: 38px; border: 0; border-left: 3px solid transparent; background: transparent; color: #4b5563; cursor: pointer; padding: 8px 8px 8px 10px; text-align: left; font-size: 12px; }
.workbench-index-item:hover, .workbench-index-item.active { border-left-color: #1677ff; background: #eaf3ff; color: #0958d9; }
.index-state { flex: 0 0 8px; width: 8px; height: 8px; border-radius: 50%; background: #c3cad3; }
.index-state.ok { background: #52c41a; }.index-state.empty { background: #d9a300; }.index-state.bad { background: #d4380d; }
.workbench-content { flex: 1; min-width: 0; height: 100%; box-sizing: border-box; overflow-y: auto; padding: 16px 20px 28px; scroll-behavior: smooth; }
.workbench-section { scroll-margin-top: 10px; border-top: 1px solid #dfe5ec; padding: 14px 0 20px; }
.workbench-section:first-child { border-top: 0; padding-top: 0; }
.workbench-section-header { display: flex; align-items: center; justify-content: space-between; min-height: 30px; margin-bottom: 10px; }
.workbench-section-header h3 { margin: 0; color: #1f2933; font-size: 15px; font-weight: 600; }
.event-grid { display: grid; grid-template-columns: repeat(2, minmax(240px, 1fr)); border-top: 1px solid #e5e9ef; border-left: 1px solid #e5e9ef; }
.event-grid-item { display: grid; grid-template-columns: 90px minmax(0, 1fr); min-width: 0; border-right: 1px solid #e5e9ef; border-bottom: 1px solid #e5e9ef; }
.event-grid-item span, .event-grid-item strong { display: flex; align-items: center; min-height: 42px; padding: 8px 10px; box-sizing: border-box; overflow-wrap: anywhere; font-size: 12px; }
.event-grid-item span { background: #f7f9fb; color: #5f6b7a; font-weight: 400; }.event-grid-item strong { color: #1f2933; font-weight: 400; }
.source-summary { min-height: 0; margin: 0 0 8px; color: #66758a; font-size: 12px; line-height: 1.6; }
.source-meta { display: flex; justify-content: space-between; gap: 12px; padding: 0 0 10px; color: #82909f; font-size: 11px; }
.source-status { padding: 3px 8px; border-radius: 10px; font-size: 10px; }.source-status.ok { color: #1f8b5b; background: #e8f8ef; }.source-status.empty { color: #8a6b1c; background: #fff5d9; }.source-status.bad { color: #b6534a; background: #ffeded; }
.minute-line-chart { margin-bottom: 16px; }
.chart-canvas { width: 100%; height: 300px; }
.weather-chart-canvas { height: 580px; }
.regional-delta-block { margin-top: 16px; border-top: 1px dashed #e8e8e8; padding-top: 12px; }
.regional-delta-block h4 { margin: 0 0 8px; color: #344054; font-size: 13px; font-weight: 600; }
.delta-canvas { height: 260px; }
.delta-legend { margin: 8px 0 0; color: #888; font-size: 11px; line-height: 1.6; }
.source-table-wrap { width: 100%; overflow: auto; border: 1px solid #e5e9ef; }
.source-table { width: 100%; min-width: 720px; border-collapse: collapse; table-layout: auto; }
.source-table th, .source-table td { padding: 9px 10px; border-right: 1px solid #edf0f3; border-bottom: 1px solid #edf0f3; text-align: left; white-space: nowrap; font-size: 11px; }
.source-table th { position: sticky; top: 0; color: #5f6b7a; background: #f7f9fb; font-weight: 500; }.source-table td { max-width: 360px; overflow: hidden; color: #344054; text-overflow: ellipsis; }
.source-table tr:last-child td { border-bottom: 0; }.source-table th:last-child, .source-table td:last-child { border-right: 0; }
.source-empty { min-height: 88px; display: flex; align-items: center; justify-content: center; margin: 0; color: #8c8c8c; font-size: 12px; }
@media (max-width: 860px) { .workbench-layout { display: block; height: auto; min-height: 0; }.workbench-index { position: sticky; top: 0; z-index: 2; display: flex; width: 100%; height: auto; overflow-x: auto; border-right: 0; border-bottom: 1px solid #e5e9ef; padding: 8px; }.workbench-index-title { display: none; }.workbench-index-item { flex: 0 0 150px; border-left: 0; border-bottom: 2px solid transparent; }.workbench-index-item:hover, .workbench-index-item.active { border-bottom-color: #1677ff; }.workbench-content { height: 620px; padding: 14px; }.event-grid { grid-template-columns: 1fr; } }
.operation-cell { display: flex; flex-wrap: wrap; gap: 6px; }.ai-button { border: 1px solid #6b49d6; border-radius: 7px; color: #6b49d6; background: #fff; padding: 5px 10px; cursor: pointer; }.ai-button:disabled { opacity: .5; cursor: not-allowed; }

/* NormCraft operation-page visual system. */
.smart-event-center { height: 100%; box-sizing: border-box; overflow: auto; padding: 12px; background: #edf1f4; color: #333; }
.smart-event-center.detail-mode { padding: 0; }
.smart-event-center.detail-mode { width: calc(100% + 32px); height: calc(100% + 32px); margin: -16px; }
.panel-header { min-height: 48px; margin: -12px -12px 12px; padding: 0 16px; border-bottom: 1px solid #d9e2eb; background: #fff; }
.detail-mode .panel-header { margin: 0; }
.panel-title { display: flex; align-items: center; gap: 8px; }
.panel-title h2 { margin: 0; color: #333; font-size: 16px; font-weight: 600; letter-spacing: 0; }
.title-mark { width: 4px; height: 16px; border-radius: 1px; background: #1684f8; }
.header-actions button, .header-back-button, .back-button, .evidence-button, .primary-button, .secondary-button, .detail-button, .ai-button, .confirmation-actions button { min-height: 30px; box-sizing: border-box; border-radius: 2px; padding: 4px 12px; font-size: 12px; }
.header-actions button { border-color: #d9d9d9; color: #555; }
.header-back-button { border: 1px solid #1684f8 !important; background: #1684f8 !important; color: #fff !important; cursor: pointer; }
.header-actions button:hover, .secondary-button:hover, .back-button:hover { border-color: #1684f8; color: #1684f8; }
.button-icon { margin-right: 4px; font-size: 14px; }
.event-list-page, .event-detail { border: 0; border-radius: 0; box-shadow: none; background: transparent; }
.detail-mode .event-detail { padding: 0; }
.list-toolbar { min-height: 60px; box-sizing: border-box; padding: 12px 16px; border: 0; border-radius: 4px; background: #fff; }
.filter-row { align-items: center; gap: 12px 16px; }
.filter-row label { display: flex; align-items: center; gap: 8px; color: #555; white-space: nowrap; }
.filter-row input, .filter-row select { width: 160px; min-width: 0; height: 32px; box-sizing: border-box; border-color: #d9d9d9; border-radius: 2px; padding: 0 10px; color: #333; outline: 0; }
.filter-row .type-filter { position: relative; display: flex; align-items: center; gap: 8px; color: #555; white-space: nowrap; }
.type-select-trigger { display: inline-flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 160px; height: 32px; box-sizing: border-box; border: 1px solid #d9d9d9; border-radius: 2px; padding: 0 10px; background: #fff; color: #333; cursor: pointer; font-size: 13px; }
.type-select-trigger:hover { border-color: #1684f8; }
.type-trigger-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.type-trigger-arrow { width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #8a94a6; transition: transform .15s; }
.type-trigger-arrow.open { transform: rotate(180deg); }
.type-menu { position: absolute; top: calc(100% + 4px); left: 56px; z-index: 40; width: 280px; max-height: 300px; overflow-y: auto; background: #fff; border: 1px solid #d9d9d9; border-radius: 4px; box-shadow: 0 6px 16px rgba(25, 42, 70, .12); padding: 6px; display: flex; flex-direction: column; gap: 2px; }
.type-option { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 4px; cursor: pointer; font-size: 12px; color: #333; }
.type-option:hover { background: #f5f9ff; }
.type-option input { width: 13px; height: 13px; margin: 0; flex: 0 0 auto; accent-color: #1684f8; }
.type-menu-actions { display: flex; justify-content: space-between; gap: 8px; border-top: 1px solid #eef2f7; padding: 6px 4px 2px; margin-top: 4px; }
.type-menu-actions button { border: 1px solid #c9d5e3; border-radius: 4px; background: #fff; color: #2f6bff; cursor: pointer; padding: 3px 10px; font-size: 12px; }
.filter-row .time-filter input { width: 176px; }
.filter-row input:focus, .filter-row select:focus { border-color: #1684f8; box-shadow: 0 0 0 2px rgba(22, 132, 248, .12); }
.filter-row .keyword-filter { flex: 1; min-width: 260px; }
.filter-row .keyword-filter input { width: auto; min-width: 210px; }
.primary-button { border: 1px solid #1684f8; background: #1684f8; color: #fff; cursor: pointer; }
.search-icon { position: relative; display: inline-block; width: 9px; height: 9px; margin-left: 5px; box-sizing: border-box; border: 1.5px solid currentColor; border-radius: 50%; vertical-align: -1px; }
.search-icon::after { position: absolute; right: -4px; bottom: -2px; width: 4px; height: 1.5px; background: currentColor; content: ''; transform: rotate(45deg); transform-origin: left center; }
.secondary-button { border: 1px solid #d9d9d9; background: #fff; color: #555; cursor: pointer; }
.list-metrics { display: flex; align-items: center; gap: 0; margin-top: 10px; padding: 0 16px; border: 0; border-radius: 4px 4px 0 0; background: #fff; }
.list-metrics div { display: flex; flex: none; grid-template: none; align-items: center; gap: 7px; min-width: 150px; padding: 12px 24px 12px 0; border: 0; border-radius: 0; background: transparent; }
.list-metrics div i { width: 24px; height: 24px; border-radius: 50%; background: #8c8c8c; box-shadow: inset 0 0 0 7px rgba(255,255,255,.8); }
.list-metrics .metric-pending i { background: #fa8c16; }.list-metrics .metric-station i { background: #13c2c2; }.list-metrics .metric-sync i { background: #52c41a; }.list-metrics .metric-total i { background: #1684f8; }
.list-metrics span { color: #666; font-size: 12px; }
.list-metrics strong { color: #1684f8; font-size: 16px; font-weight: 600; white-space: nowrap; }
.list-metrics .metric-pending strong { color: #fa8c16; }.list-metrics .metric-station strong { color: #13a8a8; }.list-metrics .metric-sync strong { color: #389e0d; font-size: 12px; }
.list-metrics > b { margin-left: auto; color: #666; font-size: 12px; font-weight: 400; }
.event-table-wrap { border-top: 1px solid #e8e8e8; border-radius: 0 0 4px 4px; background: #fff; }
.event-table { min-width: 1000px; }
.event-table th, .event-table td { height: 44px; box-sizing: border-box; padding: 8px 10px; border-bottom: 1px solid #f0f3f6; text-align: center; font-size: 12px; }
.event-table th { color: #333; background: #deefff; font-weight: 600; }
.event-table td { color: #444; }
.event-table tbody tr:hover { background: #eaf5ff; }
.event-table th:nth-child(1) { width: 46px; }.event-table th:nth-child(2) { width: 72px; }.event-table th:nth-child(3) { width: 165px; }.event-table th:nth-child(4) { width: 100px; }.event-table th:nth-child(5) { width: 112px; }.event-table th:nth-child(6) { width: 82px; }.event-table th:nth-child(7) { width: 55px; }.event-table th:nth-child(8) { width: 105px; }.event-table th:nth-child(9) { width: 130px; }.event-table th:nth-child(10) { width: 150px; }
.event-name { display: block; }.event-name strong { display: block; color: #333; font-weight: 500; }
.table-chip { border-radius: 2px; padding: 3px 8px; }.table-chip.pending { color: #595959; background: #f0f0f0; }.table-chip.warning { color: #d46b08; background: #fff7e6; }.table-chip.success { color: #389e0d; background: #f6ffed; }
.operation-cell { display: table-cell; min-width: 130px; vertical-align: middle; text-align: center; white-space: nowrap; }
.operation-cell button { white-space: nowrap; }
.operation-cell .detail-button { margin-left: 6px; }
.detail-button { border-color: #1684f8; border-radius: 2px; color: #1684f8; }.ai-button { border-color: #1684f8; border-radius: 2px; background: #1684f8; color: #fff; }
.detail-toolbar { align-items: center; min-height: 44px; margin: 0; padding: 7px 12px; border-radius: 4px 4px 0 0; background: #fff; }
.back-button { border-color: transparent; background: transparent; color: #1684f8; padding-left: 0; }
.evidence-button { border-color: #1684f8; border-radius: 2px; background: #1684f8; color: #fff; }
.detail-header { margin-top: 1px; padding: 12px 16px; border: 0; background: #fff; }
.detail-header h3 { font-size: 16px; font-weight: 600; }.detail-header p { margin: 5px 0 0; }
.status-badge { border-radius: 2px; padding: 4px 9px; color: #d46b08; background: #fff7e6; }
.evidence-detail-board { margin-top: 10px; border: 0; border-radius: 4px; }
.workbench-layout { flex: 1; min-height: 0; background: #edf1f4; }
.workbench-index { flex-basis: 196px; padding: 0 8px 12px; border-right: 10px solid #edf1f4; background: #eaf5ff; }
.workbench-index-title { margin: 0 -8px 8px; padding: 12px 16px; background: #4799e8; color: #fff; font-size: 14px; }
.workbench-index-item { min-height: 40px; border: 0; border-radius: 0; padding: 8px 10px; color: #3d5366; }
.workbench-index-item:hover { border: 0; background: #d7ecff; color: #1684f8; }
.workbench-index-item.active { border: 0; background: #1684f8; color: #fff; }
.workbench-index-item.active .index-state { border-color: rgba(255,255,255,.7); }
.index-state { box-sizing: border-box; border: 2px solid #eaf5ff; }
.workbench-content { padding: 0 0 24px; background: #edf1f4; scroll-padding-top: 0; }
.workbench-section { margin: 0 0 10px; padding: 0 16px 16px; scroll-margin-top: 0; border: 0; background: #fff; }
.workbench-section .special-panel { margin: 0; padding: 0; border: 0; background: transparent; }
.disposal-actions { display: flex; gap: 10px; padding: 6px 0; }
.disposal-button { min-width: 112px; min-height: 34px; border: 1px solid #1684f8; border-radius: 2px; background: #fff; color: #1684f8; cursor: pointer; font-size: 12px; }
.disposal-button.primary { background: #1684f8; color: #fff; }
.action-page-heading { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; color: #333; }.action-page-heading span { color: #888; font-size: 12px; }
.dispatch-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0 0 12px; }.dispatch-facts div { display: grid; grid-template-columns: 90px minmax(0, 1fr); min-width: 0; border-bottom: 1px solid #eef2f6; }.dispatch-facts div:nth-last-child(-n+2) { border-bottom: 0; }.dispatch-facts dt, .dispatch-facts dd { margin: 0; padding: 8px 10px; font-size: 12px; overflow-wrap: anywhere; }.dispatch-facts dt { background: #f6f9fc; color: #555; }.dispatch-facts dd { color: #333; }
.dispatch-description { display: block; color: #555; font-size: 12px; }.dispatch-description span { display: block; margin-bottom: 6px; }.dispatch-description textarea { width: 100%; box-sizing: border-box; resize: vertical; border: 1px solid #d9d9d9; border-radius: 2px; padding: 8px; font: inherit; font-size: 12px; }
.archive-overlay { position: fixed; inset: 0; z-index: 20; display: flex; align-items: center; justify-content: center; background: rgba(0, 0, 0, .28); }.archive-dialog { width: min(560px, calc(100vw - 32px)); box-sizing: border-box; padding: 0 20px 18px; background: #fff; box-shadow: 0 8px 30px rgba(0,0,0,.18); }.archive-dialog > header { display: flex; align-items: center; justify-content: space-between; min-height: 48px; margin: 0 -20px 16px; padding: 0 20px; border-bottom: 1px solid #e8e8e8; color: #333; }.archive-dialog > header button { border: 0; background: transparent; color: #888; cursor: pointer; font-size: 22px; }
.dialog-note { margin: -4px 0 12px; color: #888; font-size: 12px; }
.workbench-section:first-child { padding-top: 0; }
.workbench-section-header { min-height: 44px; margin: 0 -16px 12px; padding: 0 16px; border-bottom: 1px solid #e8e8e8; }
.workbench-section-header h3 { color: #333; font-size: 14px; }
.event-grid { border: 0; }.event-grid-item { border: 0; border-bottom: 1px solid #eef2f6; }
.event-grid-item span { background: #f6f9fc; color: #555; }.event-grid-item strong { color: #333; }
.source-summary { color: #666; }.source-meta { flex-wrap: wrap; color: #888; font-size: 12px; }
.source-status { padding: 2px 8px; border-radius: 2px; font-size: 12px; line-height: 20px; }
.source-status.ok { color: #389e0d; background: #f6ffed; }
.source-status.empty { color: #595959; background: #f0f0f0; }
.source-status.bad { color: #d4380d; background: #fff2e8; }
.regional-delta-block h4 { margin-bottom: 8px; color: #333; font-size: 14px; font-weight: 600; line-height: 20px; }
.delta-legend { color: #888; font-size: 12px; }
.source-table-wrap { border: 0; }
.source-table th, .source-table td { height: 38px; font-size: 12px; box-sizing: border-box; border-right: 0; border-bottom: 1px solid #f0f3f6; text-align: center; }
.source-table th { color: #333; background: #deefff; font-weight: 600; }.source-table td { color: #444; }
.judgment, .confirmation, .task-section { margin-top: 10px; padding: 0 16px 16px; border: 0; border-radius: 4px; background: #fff; }
.section-title { min-height: 44px; margin: 0 -16px 12px; padding: 0 16px; border-bottom: 1px solid #e8e8e8; }
.section-title strong { color: #333; font-size: 14px; }.section-title span { color: #888; font-size: 12px; }
.final-response { color: #444; }.confirmation input, .confirmation textarea { border-color: #d9d9d9; border-radius: 2px; }
.task-card { border-color: #e8e8e8; border-radius: 2px; color: #333; }
.tag-cell { text-align: left; }
.tag-chip-wrap { display: flex; flex-wrap: wrap; gap: 4px; }
.clue-chip { display: inline-block; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border: 1px solid #d9e2eb; border-radius: 2px; padding: 2px 6px; background: #f2f8fd; color: #3d5366; font-size: 11px; }
.clue-chip.video { border-color: #d3adf7; background: #f9f0ff; color: #531dab; }
.clue-chip.data { border-color: #91d5ff; background: #e6f7ff; color: #0958d9; }
.clue-chip.alarm { border-color: #ffbb96; background: #fff2e8; color: #d4380d; }
.clue-chip.missing { border-color: #b7eb8f; background: #f6ffed; color: #389e0d; }
.clue-chip.exceed { border-color: #ffadd2; background: #fff0f6; color: #c41d7f; }
.clue-chip.compliance { border-color: #ffe58f; background: #fffbe6; color: #d48806; }
.tag-more { border: 0; background: transparent; color: #1684f8; cursor: pointer; padding: 2px 2px; font-size: 11px; }
.tag-more:hover { text-decoration: underline; }
.delta-flag { display: inline-block; margin-top: 4px; border-radius: 2px; padding: 2px 6px; background: #fff7e6; color: #d46b08; font-size: 11px; }
.detail-tag-row .clue-chip { font-size: 12px; }
.detail-tag-row { display: flex; align-items: flex-start; gap: 10px; margin-top: 12px; padding: 10px 12px; border: 1px solid #e8e8e8; border-radius: 2px; background: #fbfdff; }
.detail-tag-title { flex: none; color: #555; font-size: 12px; line-height: 22px; }
.detail-tag-row .tag-chip-wrap { flex: 1; }
.detail-tag-row .clue-chip { max-width: none; }
.merged-alarm-content { margin-top: 12px; padding: 12px 16px; border: 1px solid #e8e8e8; border-radius: 2px; background: #fbfdff; }
.merged-alarm-content h4 { margin: 0 0 10px; color: #333; font-size: 14px; font-weight: 600; line-height: 20px; }
.merged-alarm-content h4 .alarm-count { color: #888; font-weight: 400; font-size: 12px; }
.merged-alarm-content ol { margin: 0; padding-left: 18px; }
.merged-alarm-content li { margin-bottom: 10px; color: #555; font-size: 12px; line-height: 1.7; }
.merged-alarm-content li:last-child { margin-bottom: 0; }
.merged-alarm-content .alarm-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.merged-alarm-content .alarm-meta time { color: #888; font-size: 11px; }
.merged-alarm-content .alarm-meta strong { color: #1684f8; font-size: 12px; font-weight: 500; }
.merged-alarm-content p { margin: 0; color: #555; font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
.merged-alarm-content .alarm-group-badge { border-radius: 2px; padding: 1px 6px; background: #e6f7ff; color: #0958d9; font-size: 11px; line-height: 16px; }
.merged-alarm-content .alarm-group-summary { margin: 2px 0 0; color: #444; }
.merged-alarm-content .alarm-group-raw { margin-top: 6px; }
.merged-alarm-content .alarm-group-raw summary { cursor: pointer; color: #1684f8; font-size: 11px; user-select: none; }
.merged-alarm-content .alarm-group-raw summary:hover { text-decoration: underline; }
.merged-alarm-content .alarm-group-raw ol { margin: 8px 0 0; padding-left: 16px; }
.merged-alarm-content .alarm-group-raw li { margin-bottom: 8px; border-left: 2px solid #e8e8e8; padding-left: 8px; }
.merged-alarm-content .source-empty { min-height: auto; margin: 0; color: #8c8c8c; font-size: 12px; }
.delta-note { margin-top: 10px; border-left: 3px solid #fa8c16; padding: 8px 10px; background: #fff7e6; color: #d46b08; font-size: 12px; }
.judgment-history { margin-top: 12px; border-top: 1px dashed #e8e8e8; padding-top: 10px; }
.judgment-history h4 { margin: 0 0 8px; color: #555; font-size: 12px; font-weight: 600; }
.judgment-history ol { margin: 0; padding-left: 18px; }
.judgment-history li { margin-bottom: 8px; color: #666; font-size: 12px; }
.judgment-history li strong { color: #333; margin-right: 8px; }
.judgment-history li span { color: #888; font-size: 11px; }
.judgment-history li p { margin: 4px 0 0; color: #555; line-height: 1.6; overflow-wrap: anywhere; }
.judgment-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.j-chip { display: inline-block; border-radius: 2px; padding: 4px 10px; font-size: 12px; background: #f0f0f0; color: #595959; }
.j-chip.j-type { background: #e6f7ff; color: #0958d9; font-weight: 600; }
.j-chip.impact-yes { background: #fff1f0; color: #cf1322; }
.j-chip.impact-no { background: #f6ffed; color: #389e0d; }
.j-chip.impact-unknown { background: #fff7e6; color: #d46b08; }
.j-chip.j-level { background: #f9f0ff; color: #531dab; font-weight: 600; }
.j-chip.j-continuity { background: #e6fffb; color: #08979c; }
.judgment-name { margin-bottom: 8px; color: #262626; font-size: 15px; font-weight: 600; line-height: 1.5; }
.j-note { margin: 0 0 10px; color: #444; font-size: 12px; line-height: 1.8; }
.j-block { margin-bottom: 12px; border: 1px solid #eef2f7; border-radius: 2px; padding: 10px 12px; background: #fbfcfe; }
.j-block h5 { margin: 0 0 6px; color: #344054; font-size: 12px; font-weight: 600; }
.j-block p { margin: 0; color: #555; font-size: 12px; line-height: 1.7; }
.j-suggestion-list { margin: 0; padding-left: 18px; color: #555; font-size: 12px; line-height: 1.8; }
.j-data-analysis { border-left: 3px solid #1684f8; }
.analysis-item + .analysis-item { margin-top: 10px; padding-top: 10px; border-top: 1px dashed #e8e8e8; }
.analysis-item strong { display: block; margin-bottom: 4px; color: #0958d9; font-size: 12px; }
.analysis-item p { margin: 0; color: #555; font-size: 12px; line-height: 1.7; }
.clue-chip.primary-ev { border-color: #91d5ff; background: #e6f7ff; color: #0958d9; }
.j-compliance { border-left: 3px solid #d48806; }
.j-collapse { border: 1px dashed #d9d9d9; border-radius: 2px; background: #fff; }
.j-collapse summary { cursor: pointer; padding: 8px 12px; color: #555; font-size: 12px; user-select: none; }
.j-collapse summary:hover { color: #1684f8; }
.j-collapse[open] summary { border-bottom: 1px dashed #e8e8e8; }
.j-collapse .final-response { margin: 0; padding: 10px 12px; color: #555; font-size: 12px; white-space: pre-wrap; line-height: 1.8; }
.param-snapshot { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; padding: 0 12px 12px; }
.param-snapshot div { display: flex; gap: 8px; min-width: 0; padding: 6px 0; border-top: 1px solid #f0f0f0; }
.param-snapshot dt { flex: none; color: #888; font-size: 12px; }
.param-snapshot dd { margin: 0; color: #444; font-size: 12px; overflow-wrap: anywhere; }
.judgment-actions { padding: 4px 0 8px; }
.judgment-done-note { margin: 0; color: #888; font-size: 12px; line-height: 1.6; }
.operation-history-block { margin-top: 14px; border-top: 1px dashed #e8e8e8; padding-top: 10px; }
.operation-history-block h4 { margin: 0 0 8px; color: #555; font-size: 12px; font-weight: 600; }
.operation-list { margin: 0; padding-left: 18px; }
.operation-list li { margin-bottom: 8px; color: #666; font-size: 12px; }
.operation-list li strong { display: inline-block; margin-right: 8px; color: #333; }
.operation-list li span { display: block; color: #555; line-height: 1.6; overflow-wrap: anywhere; }
.operation-list li small { display: block; margin-top: 2px; color: #999; font-size: 11px; }
.dispatch-form { display: grid; gap: 10px; margin-bottom: 12px; }
.dispatch-form label { display: grid; gap: 5px; color: #555; font-size: 12px; }
.dispatch-form input, .dispatch-form select, .dispatch-form textarea { width: 100%; box-sizing: border-box; border: 1px solid #d9d9d9; border-radius: 2px; padding: 7px 10px; font: inherit; font-size: 12px; color: #333; }
.dispatch-form input:focus, .dispatch-form select:focus, .dispatch-form textarea:focus { border-color: #1684f8; outline: 0; }
.dispatch-attachment input { padding: 5px; }
.attachment-names { margin: -4px 0 10px; color: #888; font-size: 11px; }
.config-page { padding: 16px; }
.config-header { margin-bottom: 16px; }
.config-header h3 { margin: 0 0 4px; color: #333; font-size: 15px; }
.config-header p { margin: 0; color: #888; font-size: 12px; }
.config-body { background: #fff; border: 1px solid #e8e8e8; border-radius: 4px; padding: 16px; }
.config-section { margin-bottom: 18px; }
.config-section h4 { margin: 0 0 10px; color: #333; font-size: 13px; font-weight: 600; border-bottom: 1px solid #f0f0f0; padding-bottom: 6px; }
.config-row { display: flex; flex-wrap: wrap; gap: 12px; }
.config-row label { display: flex; flex-direction: column; gap: 4px; color: #555; font-size: 12px; min-width: 140px; flex: 1; }
.config-row input, .config-row select { border: 1px solid #d9d9d9; border-radius: 2px; padding: 6px 8px; font-size: 12px; color: #333; width: 100%; box-sizing: border-box; }
.config-row input:focus { border-color: #1684f8; outline: 0; }
.full-width-label { width: 100%; flex-basis: 100%; }
.dictionary-input { width: 100%; box-sizing: border-box; border: 1px solid #d9d9d9; border-radius: 2px; padding: 6px 8px; font-size: 12px; color: #333; font-family: monospace; resize: vertical; }
.dictionary-input:focus { border-color: #1684f8; outline: 0; }
.config-actions { display: flex; align-items: center; gap: 10px; margin-top: 16px; padding-top: 12px; border-top: 1px solid #f0f0f0; }
.config-save-msg { font-size: 12px; }
.config-save-msg.ok { color: #389e0d; }
.config-save-msg.err { color: #cf1322; }
.config-button { background: none; border: 1px solid #d9d9d9; border-radius: 2px; padding: 4px 10px; cursor: pointer; font-size: 12px; color: #555; }
.config-button:hover { border-color: #1684f8; color: #1684f8; }
@media (max-width: 860px) { .smart-event-center { padding: 8px; }.smart-event-center.detail-mode { width: calc(100% + 16px); height: calc(100% + 16px); margin: -8px; }.panel-header { margin: -8px -8px 8px; }.filter-row label, .filter-row .keyword-filter { width: 100%; min-width: 0; }.filter-row input, .filter-row select, .filter-row .keyword-filter input { flex: 1; width: auto; }.list-metrics { flex-wrap: wrap; }.list-metrics div { min-width: 50%; box-sizing: border-box; }.list-metrics > b { width: 100%; padding-bottom: 10px; }.workbench-index { border-right: 0; background: #eaf5ff; }.workbench-content { height: 620px; }.workbench-section { padding-right: 10px; padding-left: 10px; }.workbench-section-header { margin-right: -10px; margin-left: -10px; padding-right: 10px; padding-left: 10px; } }
</style>

<style scoped>
.judgment-details { margin-top: 16px; border-top: 1px solid #dbe5ef; padding-top: 12px; }
.judgment-details summary { cursor: pointer; font-weight: 600; }
.judgment-details section { margin-top: 14px; overflow-wrap: anywhere; }
/* Nogcon UI normalization */
.smart-event-center { background: #f5f7fa; color: #1f2937; font-family: "Microsoft YaHei", sans-serif; }
.panel-header { background: #fff; border-bottom-color: #e5e7eb; }
.title-mark { background: #1677ff; }
.event-list-page,.event-detail,.list-toolbar,.event-table-wrap,.detail-toolbar,.detail-header,.judgment,.confirmation,.task-section { border-radius: 8px; }
.event-list-page,.event-detail,.list-toolbar,.event-table-wrap,.detail-toolbar,.detail-header,.judgment,.confirmation,.task-section { box-shadow: 0 1px 4px rgba(16,24,40,.06); }
.primary-button,.header-back-button,.evidence-button,.ai-button { background: #1677ff !important; border-color: #1677ff !important; border-radius: 6px; }
.secondary-button,.detail-button,.back-button { border-radius: 6px; }
.event-table th,.source-table th { background: #f2f6fc; color: #344054; }
.event-table td,.source-table td { color: #344054; }
.workbench-index { background: #f8fafc; border-right-color: #e5e7eb; }
.workbench-index-item.active { background: #eaf3ff; color: #0958d9; border-left: 3px solid #1677ff; }
.workbench-content { background: #f5f7fa; }
.workbench-section { border-radius: 8px; }

/* 固定详情工作台纵向撑满容器，替代 100vh 固定高度：消除底部占位空白并最大化可视证据区。 */
.smart-event-center.workbench-fit { display: flex; flex-direction: column; overflow: hidden; }
.workbench-fit .event-detail { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.workbench-fit .evidence-detail-board { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.workbench-fit .workbench-layout { flex: 1; min-height: 0; }
@media (max-width: 860px) {
  .smart-event-center.workbench-fit { display: block; overflow: auto; }
  .workbench-fit .event-detail, .workbench-fit .evidence-detail-board { display: block; flex: none; }
  .workbench-fit .workbench-layout { display: block; flex: none; height: auto; min-height: 0; }
}

/* 降噪：去掉多余描边，统一改用浅底色分区（与质控详情面板同风格）。 */
.detail-tag-row { border: 0; border-radius: 6px; background: #f6f8fb; }
.merged-alarm-content { border: 0; border-radius: 6px; background: #f7f9fc; }
.j-block { border: 0; border-radius: 6px; background: #f6f8fb; }
.comparison-overview > div { border: 0; border-radius: 6px; background: #f6f8fb; }
.evidence-source-card { border: 0; border-radius: 6px; background: #f7f9fb; }
.evidence-summary { border: 0; border-radius: 6px; background: #f7faff; }
.event-grid-item span, .dispatch-facts dt { background: #f6f8fb; }
.judgment-history { border-top-color: #eef2f6; }
.analysis-item + .analysis-item { border-top-color: #eef2f6; }
</style>
