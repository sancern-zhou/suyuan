<template>
  <div class="management-panel shared-conversations-panel">
    <div class="panel-header">
      <h3>共享对话</h3>
      <button class="panel-btn" @click="$emit('close')">关闭</button>
    </div>

    <template v-if="!activeShare">
      <div class="panel-toolbar">
        <input
          v-model="search"
          class="search-input"
          placeholder="搜索标题或首问"
          @keyup.enter="reload"
        />
        <button class="panel-btn" :disabled="loading" @click="reload">搜索</button>
        <button class="panel-btn primary" :disabled="shareBusy" @click="openShareDialog">
          分享我的对话
        </button>
      </div>

      <div v-if="error" class="panel-error">{{ error }}</div>
      <div v-if="loading && shares.length === 0" class="panel-hint">加载中…</div>
      <div v-else-if="shares.length === 0" class="panel-hint">还没有人分享对话。</div>

      <div class="share-list">
        <button
          v-for="share in shares"
          :key="share.share_id"
          class="share-card"
          @click="openDetail(share)"
        >
          <div class="share-card-title">{{ share.title }}</div>
          <div class="share-card-question">{{ share.first_question }}</div>
          <div class="share-card-meta">
            <span>{{ share.owner?.display_name || share.owner?.username }}</span>
            <span>{{ formatTime(share.created_at) }}</span>
            <span>{{ share.message_count }} 条消息</span>
            <span
              v-if="share.owner?.user_id === currentUserId"
              class="share-withdraw"
              @click.stop="withdraw(share)"
            >撤回</span>
          </div>
        </button>
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
      </div>
      <div class="detail-body">
        <div
          v-for="(message, index) in activeShare.messages"
          :key="index"
          class="message-row"
          :class="messageRole(message)"
        >
          <div class="message-author">{{ messageRole(message) === 'user' ? '提问' : '回答' }}</div>
          <div class="message-content">
            <template v-if="messageRole(message) === 'user'">{{ messageText(message) }}</template>
            <MarkdownRenderer v-else :content="messageText(message)" />
            <div v-if="imageAttachments(message).length" class="message-images">
              <a
                v-for="attachment in imageAttachments(message)"
                :key="attachment.resource_id"
                :href="attachment.url"
                target="_blank"
                rel="noopener"
              >
                <img :src="attachment.url" :alt="attachment.filename || '图表'" loading="lazy" />
              </a>
            </div>
            <div v-if="fileAttachments(message).length" class="message-files">
              <a
                v-for="attachment in fileAttachments(message)"
                :key="attachment.resource_id"
                :href="attachment.url"
                target="_blank"
                rel="noopener"
              >📎 {{ attachment.filename || '附件' }}</a>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div v-if="shareDialogOpen" class="share-dialog-mask" @click.self="shareDialogOpen = false">
      <div class="share-dialog">
        <div class="share-dialog-header">
          <span>选择要分享的对话</span>
          <button class="panel-btn" @click="shareDialogOpen = false">取消</button>
        </div>
        <div class="share-dialog-hint">
          分享会生成对话快照公开给本系统全部用户，图表会一并保存，之后修改或删除原对话不影响已分享内容。
        </div>
        <div v-if="shareError" class="panel-error">{{ shareError }}</div>
        <div class="share-dialog-list">
          <div v-if="mySessions.length === 0" class="panel-hint">没有可分享的会话。</div>
          <button
            v-for="session in mySessions"
            :key="session.session_id"
            class="share-dialog-item"
            :disabled="shareBusy"
            @click="doShare(session)"
          >
            <span class="share-dialog-title">{{ session.title || '新对话' }}</span>
            <span class="share-dialog-time">{{ formatTime(session.updated_at || session.created_at) }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/auth/authStore.js'
import { listSessions } from '@/api/session'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import {
  deleteSharedConversation,
  getSharedConversation,
  listSharedConversations,
  shareConversation
} from '@/api/sharedConversations'

defineEmits(['close'])

const auth = useAuthStore()
const currentUserId = auth.user?.id || ''

const shares = ref([])
const total = ref(0)
const search = ref('')
const loading = ref(false)
const error = ref('')
const activeShare = ref(null)

const shareDialogOpen = ref(false)
const mySessions = ref([])
const shareBusy = ref(false)
const shareError = ref('')

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { hour12: false })
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

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const data = await listSharedConversations({ search: search.value })
    shares.value = data.shares || []
    total.value = data.total || 0
  } catch (err) {
    error.value = err.message || '加载共享对话失败'
  } finally {
    loading.value = false
  }
}

async function openDetail(share) {
  error.value = ''
  try {
    activeShare.value = await getSharedConversation(share.share_id)
  } catch (err) {
    error.value = err.message || '加载分享内容失败'
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

async function openShareDialog() {
  shareError.value = ''
  shareDialogOpen.value = true
  try {
    const data = await listSessions({ limit: 100 })
    const rows = Array.isArray(data) ? data : data?.sessions || []
    mySessions.value = rows.filter(session => session.session_id)
  } catch (err) {
    shareError.value = err.message || '加载会话列表失败'
  }
}

async function doShare(session) {
  shareBusy.value = true
  shareError.value = ''
  try {
    await shareConversation(session.session_id)
    shareDialogOpen.value = false
    await reload()
  } catch (err) {
    shareError.value = err.message || '分享失败'
  } finally {
    shareBusy.value = false
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

.panel-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.search-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--border-2);
  border-radius: 4px;
  font-size: 13px;
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
  gap: 10px;
}

.share-card {
  text-align: left;
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 12px 14px;
  background: white;
  cursor: pointer;
}

.share-card:hover {
  border-color: var(--color-primary);
}

.share-card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: 4px;
}

.share-card-question {
  font-size: 13px;
  color: var(--text-2, #555);
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.share-card-meta {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: var(--text-3, #888);
}

.share-withdraw {
  color: var(--color-danger, #d03050);
  cursor: pointer;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.detail-title-main {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
}

.detail-title-meta {
  font-size: 12px;
  color: var(--text-3, #888);
  margin-top: 4px;
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-row {
  border: 1px solid var(--border-2);
  border-radius: 8px;
  padding: 10px 12px;
}

.message-row.user {
  background: var(--bg-2, #f7f8fa);
}

.message-author {
  font-size: 12px;
  color: var(--text-3, #888);
  margin-bottom: 6px;
}

.message-content {
  font-size: 13px;
  color: var(--text-1);
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

.message-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  font-size: 13px;
}

.share-dialog-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.share-dialog {
  width: min(520px, 90vw);
  max-height: 70vh;
  background: white;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
}

.share-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
}

.share-dialog-hint {
  font-size: 12px;
  color: var(--text-3, #888);
  margin-bottom: 10px;
}

.share-dialog-list {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.share-dialog-item {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  text-align: left;
  border: 1px solid var(--border-2);
  border-radius: 6px;
  padding: 8px 10px;
  background: white;
  cursor: pointer;
  font-size: 13px;
}

.share-dialog-item:hover {
  border-color: var(--color-primary);
}

.share-dialog-item:disabled {
  opacity: 0.5;
  cursor: wait;
}

.share-dialog-title {
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.share-dialog-time {
  color: var(--text-3, #888);
  flex-shrink: 0;
}
</style>
