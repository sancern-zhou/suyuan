<template>
  <div class="management-panel shared-conversations-panel">
    <div class="panel-header">
      <h3>共享对话</h3>
    </div>

    <template v-if="!activeShare">
      <div v-if="error" class="panel-error">{{ error }}</div>

      <div v-if="loading && !shares.length" class="share-grid" aria-hidden="true">
        <div v-for="i in 4" :key="i" class="share-card skeleton-card">
          <span class="share-badge skeleton-block"></span>
          <span class="skeleton-body">
            <span class="skeleton-line" style="width: 72%"></span>
            <span class="skeleton-line" style="width: 45%"></span>
          </span>
        </div>
      </div>

      <div v-else-if="!shares.length" class="board-empty">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="8" cy="8.5" r="3" />
          <circle cx="16.5" cy="10" r="2.4" />
          <path d="M3.5 19c.4-3 2.3-4.7 4.5-4.7s4.1 1.7 4.5 4.7" />
          <path d="M14 14.6c.8-.5 1.6-.8 2.5-.8 1.9 0 3.5 1.3 3.9 3.9" />
        </svg>
        <p class="board-empty-title">还没有人分享对话</p>
        <p class="board-empty-sub">在聊天页点击 AI 回复下方的「分享」按钮，把有价值的对话分享给大家</p>
      </div>

      <div v-else class="share-list">
        <div v-for="group in shareGroups" :key="group.key" class="share-date-group">
          <button
            class="share-date-header"
            type="button"
            @click="toggleDateGroup(group.key)"
          >
            <svg
              class="share-date-chevron"
              :class="{ collapsed: collapsedDateGroups[group.key] }"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path d="m7 10 5 5 5-5" />
            </svg>
            <span>{{ group.label }}</span>
            <span class="share-date-rule"></span>
            <span class="share-date-count">{{ group.items.length }}</span>
          </button>
          <div v-if="!collapsedDateGroups[group.key]" class="share-grid">
            <button
              v-for="share in group.items"
              :key="share.share_id"
              class="share-card"
              @click="openDetail(share)"
            >
              <span class="share-badge" :style="{ background: badgeColor(share) }">{{ badgeChar(share) }}</span>
              <span class="share-card-body">
                <span class="share-card-title">{{ share.title }}</span>
                <span
                  v-if="modeChip(share)"
                  class="share-card-chip"
                  :style="{ color: modeChip(share).accent, borderColor: modeChip(share).accent }"
                >{{ modeChip(share).label }}</span>
              </span>
              <span
                v-if="share.owner?.user_id === currentUserId"
                class="share-withdraw"
                @click.stop="withdraw(share)"
              >撤回</span>
            </button>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="detail-header">
        <button class="panel-btn" @click="activeShare = null">← 返回列表</button>
        <div class="detail-title">
          <div class="detail-title-main">{{ activeShare.title }}</div>
          <div class="detail-title-meta">
            {{ activeShare.owner?.display_name || activeShare.owner?.username }} 分享于
            {{ formatTime(activeShare.created_at) }}
          </div>
        </div>
        <button
          type="button"
          class="panel-toggle-btn"
          :disabled="!reportFrameUrl"
          :title="reportCollapsed ? '显示右侧面板' : '隐藏右侧面板'"
          :aria-label="reportCollapsed ? '显示右侧面板' : '隐藏右侧面板'"
          @click="$emit('report-toggle')"
        >
          <svg class="panel-toggle-icon" viewBox="0 0 24 24" aria-hidden="true">
            <rect width="18" height="18" x="3" y="3" rx="2" />
            <path d="M15 3v18" />
            <path v-if="!reportCollapsed" d="m8 9 3 3-3 3" />
            <path v-else d="m10 15-3-3 3-3" />
          </svg>
        </button>
      </div>
      <div class="detail-body">
        <div
          v-for="(view, index) in messageViews"
          :key="index"
          class="message-row"
          :class="view.role"
        >
          <span class="message-avatar" :class="view.role">{{ view.role === 'user' ? '问' : '答' }}</span>
          <div class="message-main">
            <div class="message-content">
            <template v-if="view.role === 'user'">{{ view.text }}</template>
            <template v-else>
              <template v-for="(seg, si) in view.segments" :key="si">
                <MarkdownRenderer v-if="seg.type === 'text'" :content="seg.value" />
                <div
                  v-else
                  class="board-chart"
                  @click="openChartLightbox(view, seg.attachment)"
                >
                  <img
                    v-if="authedImageUrls[seg.attachment.url]"
                    :src="authedImageUrls[seg.attachment.url]"
                    :alt="mdImageLabel(seg.attachment)"
                  />
                  <span v-else-if="authedImageFailed[seg.attachment.url]" class="panel-hint">图表加载失败</span>
                  <span v-else class="panel-hint">图表加载中…</span>
                </div>
              </template>
              <div v-if="view.files.length" class="message-files">
                <a
                  v-for="attachment in view.files"
                  :key="attachment.resource_id || attachment.url"
                  href="#"
                  @click.prevent="downloadAttachment(attachment)"
                >📎 {{ attachment.filename || '附件' }}</a>
              </div>
            </template>
            </div>
          </div>
        </div>
      </div>
    </template>

    <ImageLightbox
      v-model:visible="lightboxVisible"
      :images="lightboxImages"
      v-model:start-index="lightboxStartIndex"
    />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, onBeforeUnmount } from 'vue'
import { useAuthStore } from '@/auth/authStore.js'
import { authFetch } from '@/auth/http.js'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import ImageLightbox from '@/components/ImageLightbox.vue'
import { AGENT_MODES } from '@/config/agentModes.js'
import {
  deleteSharedConversation,
  getSharedConversation,
  getSharedReportView,
  listSharedConversations
} from '@/api/sharedConversations'

const props = defineProps({
  reportCollapsed: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['report-open', 'report-close', 'report-toggle'])

const auth = useAuthStore()
const currentUserId = auth.user?.id || ''

const shares = ref([])
const loading = ref(false)
const error = ref('')
const activeShare = ref(null)

// 按日期分组折叠：key 为 YYYY-M-D，默认全部展开
const collapsedDateGroups = reactive({})

function toggleDateGroup(key) {
  collapsedDateGroups[key] = !collapsedDateGroups[key]
}

function dayGroupInfo(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return { key: 'unknown', label: '未知时间', date: null }
  const now = new Date()
  const startOfDay = d => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const dayDiff = Math.round((startOfDay(now) - startOfDay(date)) / 86400000)
  let label
  if (dayDiff === 0) label = '今天'
  else if (dayDiff === 1) label = '昨天'
  else if (date.getFullYear() === now.getFullYear()) label = `${date.getMonth() + 1}月${date.getDate()}日`
  else label = `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`
  return { key: `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`, label, date }
}

const shareGroups = computed(() => {
  const groups = []
  const byKey = new Map()
  for (const share of shares.value) {
    const info = dayGroupInfo(share.created_at)
    let group = byKey.get(info.key)
    if (!group) {
      group = { key: info.key, label: info.label, items: [] }
      byKey.set(info.key, group)
      groups.push(group)
    }
    group.items.push(share)
  }
  return groups
})

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { hour12: false })
}

// 卡片首字徽章：取标题首字，颜色由 share_id 稳定散列
const BADGE_PALETTE = ['#4c8bf5', '#00b8a9', '#f6416c', '#ff9f43', '#7c6ff0', '#2dc3a5', '#f0705a']

function badgeChar(share) {
  const title = String(share?.title || '').trim()
  return title ? title[0].toUpperCase() : '共'
}

function badgeColor(share) {
  let hash = 0
  for (const ch of String(share?.share_id || '')) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return BADGE_PALETTE[hash % BADGE_PALETTE.length]
}

function modeChip(share) {
  const mode = AGENT_MODES.find(item => item.id === share?.mode)
  if (!mode) return null
  return { label: mode.shortName || mode.name, accent: mode.accent || '#2878ff' }
}

function messageRole(message) {
  return String(message?.type || message?.role || '').toLowerCase() === 'user' ? 'user' : 'assistant'
}

function messageText(message) {
  const content = message?.content || message?.data?.result?.content || ''
  return typeof content === 'string' ? content : ''
}

function visibleAttachments(message) {
  return Array.isArray(message?.attachments) ? message.attachments : []
}

function imageAttachments(message) {
  return visibleAttachments(message).filter(
    attachment => String(attachment.mime_type || '').startsWith('image/') && attachment.url
  )
}

function fileAttachments(message) {
  return visibleAttachments(message).filter(
    attachment =>
      !String(attachment.mime_type || '').startsWith('image/') &&
      attachment.url &&
      String(attachment.mime_type || '') !== 'application/json'
  )
}

// 回答正文用 [[chart:<visual_id>]] 标记图表位置（与历史对话一致）。
// 图片走 authFetch blob 通道；样式对齐历史对话（居中、760px/58vh），
// 点击复用 ImageLightbox 放大。blob: URL 会被 DOMPurify 从 markdown img
// 里剥掉，因此不能走 MarkdownRenderer 的 markdown 图片路径。
const CHART_REF_RE = /\[\[chart:([^\]]+)\]\]/g

function mdImageLabel(attachment) {
  return String(attachment?.filename || '图表').replace(/[[\]]/g, '') || '图表'
}

const messageViews = computed(() => {
  const messages = activeShare.value?.messages || []
  return messages.map((message) => {
    const role = messageRole(message)
    if (role === 'user') {
      return { role, text: messageText(message), segments: [], files: [] }
    }
    const attachments = visibleAttachments(message)
    const byRef = new Map()
    for (const attachment of attachments) {
      for (const key of [attachment.visual_id, attachment.file_id, attachment.ref_id, attachment.resource_id]) {
        const ref = key == null ? '' : String(key)
        if (ref && !byRef.has(ref)) byRef.set(ref, attachment)
      }
    }
    const content = messageText(message)
    const segments = []
    const inlineUrls = new Set()
    let last = 0
    for (const match of content.matchAll(CHART_REF_RE)) {
      if (match.index > last) segments.push({ type: 'text', value: content.slice(last, match.index) })
      const attachment = byRef.get(match[1])
      if (attachment && String(attachment.mime_type || '').startsWith('image/') && attachment.url) {
        segments.push({ type: 'chart', attachment })
        inlineUrls.add(attachment.url)
      }
      // 交互图表（ECharts）面板不内联渲染，保留在附件区
      last = match.index + match[0].length
    }
    if (last < content.length) segments.push({ type: 'text', value: content.slice(last) })
    // 未被标记引用的静态图同样内联在文末（历史对话中图表均内联展示）
    for (const attachment of imageAttachments(message)) {
      if (!inlineUrls.has(attachment.url)) segments.push({ type: 'chart', attachment })
    }
    return { role, text: '', segments, files: fileAttachments(message) }
  })
})

const lightboxVisible = ref(false)
const lightboxImages = ref([])
const lightboxStartIndex = ref(0)
const reportFrameUrl = ref('')

function openChartLightbox(view, attachment) {
  const src = authedImageUrls[attachment.url]
  if (!src) return
  const images = view.segments
    .filter(seg => seg.type === 'chart' && authedImageUrls[seg.attachment.url])
    .map(seg => ({ src: authedImageUrls[seg.attachment.url], alt: mdImageLabel(seg.attachment) }))
  if (!images.length) return
  lightboxImages.value = images
  lightboxStartIndex.value = Math.max(0, images.findIndex(img => img.src === src))
  lightboxVisible.value = true
}

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const data = await listSharedConversations()
    shares.value = data.shares || []
  } catch (err) {
    error.value = err.message || '加载共享对话失败'
  } finally {
    loading.value = false
  }
}

async function openDetail(share) {
  error.value = ''
  reportFrameUrl.value = ''
  try {
    const detail = await getSharedConversation(share.share_id)
    activeShare.value = detail
    if (detail.has_report) {
      try {
        const data = await getSharedReportView(share.share_id)
        reportFrameUrl.value = data.url || ''
        emit('report-open', { url: reportFrameUrl.value, title: share.title })
      } catch {
        reportFrameUrl.value = ''
        emit('report-close')
      }
    } else {
      emit('report-close')
    }
  } catch (err) {
    error.value = err.message || '加载分享内容失败'
  }
}

// 图片/附件接口需要认证头，<img>/<a> 无法携带，改为 authFetch 取回字节。
const authedImageUrls = reactive({})
const authedImageFailed = reactive({})
let authedImageToken = 0

function attachmentUrls(messages) {
  const urls = new Set()
  for (const message of messages || []) {
    for (const attachment of visibleAttachments(message)) {
      if (attachment?.url && String(attachment.mime_type || '').startsWith('image/')) {
        urls.add(String(attachment.url))
      }
    }
  }
  return urls
}

async function loadAuthedImages(messages) {
  const token = ++authedImageToken
  for (const url of attachmentUrls(messages)) {
    if (authedImageUrls[url] || authedImageFailed[url]) continue
    try {
      const response = await authFetch(url)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const blob = await response.blob()
      if (token !== authedImageToken) return
      authedImageUrls[url] = URL.createObjectURL(blob)
    } catch {
      if (token !== authedImageToken) return
      authedImageFailed[url] = true
    }
  }
}

watch(() => activeShare.value?.messages, (messages) => {
  releaseAuthedImages()
  if (messages?.length) loadAuthedImages(messages)
})

watch(activeShare, (share) => {
  if (!share) emit('report-close')
})

function releaseAuthedImages() {
  for (const url of Object.keys(authedImageUrls)) {
    URL.revokeObjectURL(authedImageUrls[url])
    delete authedImageUrls[url]
  }
  for (const url of Object.keys(authedImageFailed)) delete authedImageFailed[url]
}

onBeforeUnmount(() => {
  emit('report-close')
  releaseAuthedImages()
})

async function downloadAttachment(attachment) {
  if (!attachment?.url) return
  try {
    const response = await authFetch(attachment.url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const blob = await response.blob()
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = attachment.filename || '附件'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(href)
  } catch (err) {
    error.value = err?.message || '附件下载失败'
  }
}

async function withdraw(share) {
  if (!window.confirm(`确定撤回分享「${share.title}」吗？`)) return
  try {
    await deleteSharedConversation(share.share_id)
    if (activeShare.value?.share_id === share.share_id) activeShare.value = null
    await reload()
  } catch (err) {
    error.value = err.message || '撤回失败'
  }
}

reload()
</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow-y: auto;
  padding: 20px;
  background: white;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--border-2);
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1);
}

.panel-btn {
  padding: 6px 12px;
  border: 1px solid var(--color-primary);
  background: white;
  color: var(--color-primary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.panel-btn:hover {
  background: var(--color-primary);
  color: white;
}

.panel-btn.primary {
  background: var(--color-primary);
  color: white;
}

.panel-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.panel-hint,
.panel-error {
  padding: 10px 4px;
  font-size: 13px;
  color: var(--text-2, #555);
}

.panel-error {
  color: var(--color-danger, #d03050);
}

.share-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
  animation: boardFadeIn 0.22s ease;
}

.share-date-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.share-date-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 2px;
  border: none;
  background: transparent;
  color: var(--text-1, #2f3a4c);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}

.share-date-header:hover {
  color: #1976d2;
}

.share-date-rule {
  flex: 1;
  height: 1px;
  background: var(--border-2, #e3e8f0);
}

.share-date-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-3, #8a94a6);
}

.share-date-chevron {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: transform 0.15s ease;
}

.share-date-chevron.collapsed {
  transform: rotate(-90deg);
}

.share-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}

.share-card {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  text-align: left;
  border: 1px solid var(--border-2, #e3e8f0);
  border-radius: 14px;
  padding: 14px 16px;
  background: white;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}

.share-card:hover {
  border-color: var(--color-primary, #1976d2);
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(25, 118, 210, 0.12);
}

.share-card:active {
  transform: translateY(0);
  box-shadow: none;
}

.share-badge {
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 17px;
  font-weight: 600;
}

.share-card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.share-card-title {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--text-1, #2f3a4c);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.share-card:hover .share-card-title {
  color: var(--color-primary, #1976d2);
}

.share-card-chip {
  font-size: 11px;
  line-height: 1;
  padding: 3px 8px;
  border: 1px solid;
  border-radius: 999px;
  background: white;
}

.share-withdraw {
  position: absolute;
  top: 8px;
  right: 12px;
  font-size: 12px;
  color: var(--color-danger, #d03050);
  opacity: 0;
  transition: opacity 0.15s ease;
}

.share-card:hover .share-withdraw {
  opacity: 1;
}

.skeleton-card {
  pointer-events: none;
}

.skeleton-block,
.skeleton-line {
  display: block;
  border-radius: 6px;
  background: linear-gradient(90deg, #eef1f6 25%, #f7f9fc 40%, #eef1f6 55%);
  background-size: 200% 100%;
  animation: skeletonShimmer 1.3s infinite;
}

.skeleton-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 2px;
}

@keyframes skeletonShimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

.board-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 56px 16px 40px;
  text-align: center;
  animation: boardFadeIn 0.22s ease;
}

.board-empty svg {
  width: 44px;
  height: 44px;
  fill: none;
  stroke: #b9c4d4;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  margin-bottom: 6px;
}

.board-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1, #2f3a4c);
}

.board-empty-sub {
  font-size: 13px;
  color: var(--text-3, #8a94a6);
  max-width: 320px;
  line-height: 1.6;
}

@keyframes boardFadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}

.detail-header {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin: 0 -4px 16px;
  padding: 10px 4px 12px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--border-2, #e3e8f0);
  animation: boardFadeIn 0.22s ease;
}

.detail-header .panel-toggle-btn {
  margin-left: auto;
  flex: 0 0 auto;
}

.panel-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  border-radius: 8px;
  transition: background-color 0.2s, color 0.2s;
}

.panel-toggle-btn:hover:not(:disabled) {
  background: var(--bg-2, #f1f4f9);
  color: var(--text-1, #2f3a4c);
}

.panel-toggle-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.panel-toggle-icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.detail-title-main {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-1, #2f3a4c);
  line-height: 1.4;
}

.detail-title-meta {
  font-size: 12px;
  color: var(--text-3, #8a94a6);
  margin-top: 4px;
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 860px;
  animation: boardFadeIn 0.22s ease;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.message-avatar {
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: white;
  margin-top: 2px;
}

.message-avatar.user {
  background: #4c8bf5;
}

.message-avatar.assistant {
  background: linear-gradient(135deg, #00b8a9, #2dc3a5);
}

.message-main {
  min-width: 0;
  border-radius: 14px;
  padding: 12px 14px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.user .message-main {
  max-width: 78%;
  background: #e8f1fc;
  border: 1px solid #d3e5fa;
  border-radius: 14px 14px 4px 14px;
}

.message-row.user .message-avatar {
  order: 2;
}

.message-row.assistant .message-main {
  flex: 1;
  background: white;
  border: 1px solid var(--border-2, #e9edf4);
  box-shadow: 0 1px 4px rgba(31, 45, 61, 0.06);
  border-radius: 4px 14px 14px 14px;
}

.message-content {
  font-size: 14px;
  line-height: 1.75;
  color: var(--text-1, #2f3a4c);
  word-break: break-word;
}

.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.message-images img {
  max-width: 100%;
  border: 1px solid var(--border-2);
  border-radius: 6px;
}

/* 内联图表：与历史对话 MarkdownRenderer 的 img 样式保持一致 */
.board-chart {
  margin: 12px auto;
  max-width: min(100%, 760px);
}

.board-chart img {
  max-width: 100%;
  max-height: 58vh;
  width: auto;
  height: auto;
  display: block;
  margin: 0 auto;
  object-fit: contain;
  border-radius: 6px;
  cursor: zoom-in;
  transition: transform 0.2s;
}

.board-chart img:hover {
  transform: scale(1.02);
}

.message-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  font-size: 13px;
}
</style>
