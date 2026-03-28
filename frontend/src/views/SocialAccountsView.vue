<template>
  <div class="social-accounts-view">
    <!-- 添加账号按钮 -->
    <div class="add-account-bar">
      <button @click="showCreateModal = true" class="btn-primary">
        + 扫码添加微信
      </button>
    </div>

    <!-- 账号列表 -->
    <div v-if="loading" class="loading">
      <p>加载中...</p>
    </div>

    <div v-else-if="accounts.length === 0" class="empty">
      <p>暂无微信账号</p>
      <p class="empty-hint">点击"扫码添加微信"按钮，扫描二维码即可快速添加</p>
      <button @click="showCreateModal = true" class="btn-primary">
        扫码添加微信
      </button>
    </div>

    <div v-else class="accounts-grid">
      <div
        v-for="account in accounts"
        :key="account.id"
        class="account-card"
        :class="{
          'running': account.running,
          'logged-in': account.login_status === 'logged_in'
        }"
      >
        <div class="account-header">
          <h3>{{ account.name }}</h3>
          <span class="account-id">{{ account.id }}</span>
        </div>

        <div class="account-status">
          <div class="status-item">
            <span class="label">状态:</span>
            <span :class="['badge', account.running ? 'running' : 'stopped']">
              {{ account.running ? '运行中' : '已停止' }}
            </span>
          </div>
          <div class="status-item">
            <span class="label">登录:</span>
            <span :class="['badge', account.login_status === 'logged_in' ? 'success' : 'warning']">
              {{ account.login_status === 'logged_in' ? '已登录' : '未登录' }}
            </span>
          </div>
          <div v-if="account.bot_account" class="status-item">
            <span class="label">账号:</span>
            <span class="value">{{ account.bot_account }}</span>
          </div>
        </div>

        <div class="account-actions">
          <button
            v-if="!account.running"
            @click="startAccount(account.id)"
            class="btn-start"
            :disabled="actionLoading[account.id]"
          >
            {{ actionLoading[account.id] ? '启动中...' : '启动' }}
          </button>
          <button
            v-if="account.running"
            @click="stopAccount(account.id)"
            class="btn-stop"
            :disabled="actionLoading[account.id]"
          >
            {{ actionLoading[account.id] ? '停止中...' : '停止' }}
          </button>
          <button
            @click="showQRCode(account)"
            :disabled="!account.running || account.login_status === 'logged_in'"
            class="btn-qrcode"
          >
            {{ account.qr_code_available ? '查看二维码' : '获取二维码' }}
          </button>
          <button
            @click="deleteAccount(account.id)"
            class="btn-delete"
            :disabled="account.running"
          >
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- 二维码弹窗 -->
    <QRCodeModal
      v-if="showQRModal"
      :account-id="selectedAccountId"
      @close="showQRModal = false"
    />

    <!-- 创建账号弹窗 -->
    <CreateAccountModal
      v-if="showCreateModal"
      @close="showCreateModal = false"
      @created="handleAccountCreated"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import QRCodeModal from '@/components/social/QRCodeModal.vue'
import CreateAccountModal from '@/components/social/CreateAccountModal.vue'

const accounts = ref([])
const loading = ref(true)
const showQRModal = ref(false)
const showCreateModal = ref(false)
const selectedAccountId = ref(null)
const actionLoading = ref({})
let refreshInterval = null

const loadAccounts = async (showLoading = false) => {
  // 默认不显示loading状态（避免定时刷新时闪烁）
  if (showLoading) {
    loading.value = true
  }

  try {
    const response = await axios.get('/api/social/accounts')
    const newAccounts = response.data

    // 只在数据真正变化时更新（避免不必要的重渲染）
    if (JSON.stringify(newAccounts) !== JSON.stringify(accounts.value)) {
      accounts.value = newAccounts
      console.log('[DEBUG] 账号列表已更新', {
        oldCount: accounts.value.length,
        newCount: newAccounts.length
      })
    }
  } catch (error) {
    console.error('Failed to load accounts:', error)
    // 只在非404错误时显示警告
    if (error.response?.status !== 404) {
      console.warn('加载账号列表失败:', error.response?.data?.detail || error.message)
    }
  } finally {
    if (showLoading) {
      loading.value = false
    }
  }
}

const startAccount = async (accountId) => {
  actionLoading.value[accountId] = true
  try {
    await axios.post(`/api/social/accounts/weixin/${accountId}/start`)
    await loadAccounts()
  } catch (error) {
    console.error('Failed to start account:', error)
    alert('启动失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    actionLoading.value[accountId] = false
  }
}

const stopAccount = async (accountId) => {
  if (!confirm('确定要停止这个账号吗？')) return

  actionLoading.value[accountId] = true
  try {
    await axios.post(`/api/social/accounts/weixin/${accountId}/stop`)
    await loadAccounts()
  } catch (error) {
    console.error('Failed to stop account:', error)
    alert('停止失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    actionLoading.value[accountId] = false
  }
}

const deleteAccount = async (accountId) => {
  if (!confirm('确定要删除这个账号吗？此操作不可恢复！')) return

  actionLoading.value[accountId] = true
  try {
    await axios.delete(`/api/social/accounts/weixin/${accountId}`)
    await loadAccounts()
  } catch (error) {
    console.error('Failed to delete account:', error)
    alert('删除失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    actionLoading.value[accountId] = false
  }
}

const showQRCode = (account) => {
  selectedAccountId.value = account.id
  showQRModal.value = true
}

const handleAccountCreated = () => {
  // 账号创建后手动刷新
  loadAccounts(true)
}

const manualRefresh = () => {
  // 手动刷新
  loadAccounts(true)
}

onMounted(() => {
  // 初始加载（显示loading）
  loadAccounts(true)

  // 定时刷新状态（改为30秒，减少刷新频率）
  refreshInterval = setInterval(() => {
    // 定时刷新不显示loading状态
    loadAccounts(false)
  }, 30000)  // 30秒刷新一次
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.social-accounts-view {
  /* 移除外层padding和margin，适应管理面板 */
}

.add-account-bar {
  margin-bottom: 20px;
}

.loading, .empty {
  text-align: center;
  padding: 60px 20px;
  color: #999;
}

.accounts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.account-card {
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  padding: 20px;
  background: white;
  transition: all 0.3s;
}

.account-card.running {
  border-color: #4caf50;
  box-shadow: 0 2px 8px rgba(76, 175, 80, 0.2);
}

.account-card.logged-in {
  background: #f1f8f4;
}

.account-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.account-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.account-id {
  font-size: 12px;
  color: #999;
  background: #f5f5f5;
  padding: 4px 8px;
  border-radius: 4px;
}

.account-status {
  margin-bottom: 15px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
}

.label {
  font-weight: bold;
  color: #666;
}

.value {
  color: #333;
}

.badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
}

.badge.running {
  background: #4caf50;
  color: white;
}

.badge.stopped {
  background: #999;
  color: white;
}

.badge.success {
  background: #4caf50;
  color: white;
}

.badge.warning {
  background: #ff9800;
  color: white;
}

.account-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.account-actions button {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.account-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-start {
  background: #4caf50;
  color: white;
}

.btn-start:hover:not(:disabled) {
  background: #45a049;
}

.btn-stop {
  background: #f44336;
  color: white;
}

.btn-stop:hover:not(:disabled) {
  background: #da190b;
}

.btn-qrcode {
  background: #2196f3;
  color: white;
}

.btn-qrcode:hover:not(:disabled) {
  background: #0b7dda;
}

.btn-delete {
  background: #9e9e9e;
  color: white;
}

.btn-delete:hover:not(:disabled) {
  background: #757575;
}

.btn-primary {
  padding: 10px 20px;
  background: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: #0b7dda;
}
</style>
