<template>
  <div class="create-modal-overlay" @click="close">
    <div class="create-modal" @click.stop>
      <div class="modal-header">
        <h3>添加微信账号</h3>
        <button @click="close" class="close-btn">&times;</button>
      </div>

      <div class="modal-body">
        <div v-if="creating" class="loading">
          <div class="spinner"></div>
          <p>正在初始化...</p>
        </div>

        <div v-else-if="tempAccountId && !loginSuccess" class="qrcode-container">
          <div class="instruction-text">
            <p class="step">第1步：使用微信扫描下方二维码</p>
            <p class="hint">扫描后请在手机上确认登录</p>
          </div>

          <div v-if="qrLoading" class="qr-loading">
            <div class="spinner"></div>
            <p>正在生成二维码...</p>
          </div>

          <img
            v-else-if="qrCodeUrl"
            :src="qrCodeUrl"
            alt="微信登录二维码"
            class="qrcode-image"
          />

          <div v-if="statusText" :class="['status', statusClass]">
            {{ statusText }}
          </div>

          <div class="actions">
            <button
              @click="refreshQRCode"
              class="btn-refresh"
              :disabled="refreshing"
            >
              {{ refreshing ? '刷新中...' : '刷新二维码' }}
            </button>
          </div>
        </div>

        <div v-else-if="loginSuccess" class="success-container">
          <div class="success-icon">✅</div>
          <h3>登录成功！</h3>
          <p>账号已自动创建并启动</p>
          <div class="account-info">
            <p><strong>账号ID：</strong>{{ createdAccountId }}</p>
            <p><strong>显示名称：</strong>{{ accountName }}</p>
          </div>
          <button @click="close" class="btn-done">
            完成
          </button>
        </div>

        <div v-else-if="errorMessage" class="error">
          <p class="error-title">添加失败</p>
          <p class="error-message">{{ errorMessage }}</p>
          <button @click="reset" class="btn-retry">重试</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const emit = defineEmits(['close', 'created'])

const creating = ref(true)
const tempAccountId = ref('')
const qrCodeUrl = ref('')
const qrLoading = ref(true)
const refreshing = ref(false)
const loginStatus = ref('waiting')
const loginSuccess = ref(false)
const errorMessage = ref('')
const createdAccountId = ref('')
const accountName = ref('')

let statusCheckInterval = null
let accountIdCounter = 0

const statusText = computed(() => {
  switch (loginStatus.value) {
    case 'waiting':
      return '等待扫描...'
    case 'scanned':
      return '已扫描，请在手机上确认登录'
    case 'logging_in':
      return '登录中，请稍候...'
    default:
      return ''
  }
})

const statusClass = computed(() => {
  switch (loginStatus.value) {
    case 'waiting':
      return 'status-waiting'
    case 'scanned':
      return 'status-scanned'
    case 'logging_in':
      return 'status-logging'
    default:
      return ''
  }
})

// 生成临时账号ID
const generateTempAccountId = () => {
  const timestamp = Date.now().toString(36)
  return `auto_${timestamp}`
}

// 初始化临时账号并获取二维码
const initializeTempAccount = async () => {
  creating.value = true
  errorMessage.value = ''

  try {
    // 生成临时ID
    tempAccountId.value = generateTempAccountId()
    console.log('[DEBUG] 生成临时账号ID:', tempAccountId.value)

    // 创建临时账号（自动启动）
    console.log('[DEBUG] 调用 auto-create API...')
    const response = await axios.post('/api/social/accounts/weixin/auto-create', {
      temp_id: tempAccountId.value
    })

    console.log('[DEBUG] auto-create 响应:', response.data)

    if (response.status === 200) {
      // 创建成功，获取二维码
      console.log('[DEBUG] 账号创建成功，开始获取二维码...')
      await fetchQRCode()
    } else {
      throw new Error(response.data?.detail || '创建失败')
    }
  } catch (error) {
    console.error('[ERROR] 创建临时账号失败:', error)
    console.error('[ERROR] 错误详情:', {
      message: error.message,
      response: error.response?.data
    })
    errorMessage.value = error.response?.data?.detail || error.message || '创建失败，请重试'
  } finally {
    creating.value = false
  }
}

// 获取二维码
const fetchQRCode = async () => {
  qrLoading.value = true
  errorMessage.value = ''

  try {
    const url = `/api/social/accounts/weixin/${tempAccountId.value}/qrcode`
    console.log('[DEBUG] 开始获取二维码:', { url, accountId: tempAccountId.value })

    const response = await axios.get(url, { responseType: 'blob' })
    console.log('[DEBUG] 二维码响应:', {
      status: response.status,
      dataType: response.data?.type,
      dataSize: response.data?.size
    })

    qrCodeUrl.value = URL.createObjectURL(response.data)
    console.log('[DEBUG] Blob URL创建成功:', qrCodeUrl.value)

    loginStatus.value = 'waiting'

    // 开始检查登录状态
    startStatusCheck()
  } catch (error) {
    console.error('[ERROR] 获取二维码失败:', error)
    console.error('[ERROR] 错误详情:', {
      message: error.message,
      response: error.response?.data,
      status: error.response?.status
    })
    errorMessage.value = error.response?.data?.detail || error.message || '获取二维码失败'
  } finally {
    qrLoading.value = false
  }
}

// 开始检查登录状态
const startStatusCheck = () => {
  statusCheckInterval = setInterval(checkLoginStatus, 3000)
}

// 停止检查登录状态
const stopStatusCheck = () => {
  if (statusCheckInterval) {
    clearInterval(statusCheckInterval)
    statusCheckInterval = null
  }
}

// 检查登录状态
const checkLoginStatus = async () => {
  try {
    const response = await axios.get(
      `/api/social/accounts/weixin/${tempAccountId.value}/status`
    )

    const data = response.data

    if (data.logged_in) {
      // 登录成功！
      loginStatus.value = 'logging_in'
      stopStatusCheck()

      // 等待一小段时间让账号完全初始化
      await new Promise(resolve => setTimeout(resolve, 1000))

      // 获取账号信息
      await finalizeAccount(data)
    }
  } catch (error) {
    console.error('Failed to check status:', error)
  }
}

// 完成账号创建
const finalizeAccount = async (statusData) => {
  try {
    // 使用微信昵称或bot_account作为显示名称
    const botAccount = statusData.bot_account || tempAccountId.value
    accountName.value = botAccount.replace(/^weixin_/, '微信账号-')

    // 将临时账号转为正式账号
    await axios.post(`/api/social/accounts/weixin/${tempAccountId.value}/finalize`, {
      name: accountName.value
    })

    createdAccountId.value = tempAccountId.value
    loginSuccess.value = true

    // 通知父组件
    emit('created')
  } catch (error) {
    console.error('Failed to finalize account:', error)
    errorMessage.value = error.response?.data?.detail || error.message || '账号创建失败'
  }
}

// 刷新二维码
const refreshQRCode = async () => {
  refreshing.value = true
  try {
    await axios.post(`/api/social/accounts/weixin/${tempAccountId.value}/refresh-qrcode`)
    await fetchQRCode()
  } catch (error) {
    console.error('Failed to refresh QR code:', error)
    errorMessage.value = error.response?.data?.detail || error.message || '刷新失败'
  } finally {
    refreshing.value = false
  }
}

// 重置
const reset = () => {
  tempAccountId.value = ''
  qrCodeUrl.value = ''
  loginStatus.value = 'waiting'
  loginSuccess.value = false
  errorMessage.value = ''
  createdAccountId.value = ''
  accountName.value = ''

  // 重新初始化
  initializeTempAccount()
}

const close = () => {
  stopStatusCheck()
  emit('close')
}

onMounted(() => {
  initializeTempAccount()
})

onUnmounted(() => {
  stopStatusCheck()

  // 释放blob URL
  if (qrCodeUrl.value && qrCodeUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(qrCodeUrl.value)
  }
})
</script>

<style scoped>
.create-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.create-modal {
  background: white;
  border-radius: 12px;
  padding: 30px;
  min-width: 450px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 28px;
  cursor: pointer;
  color: #999;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #f5f5f5;
  color: #333;
}

.modal-body {
  min-height: 400px;
}

.loading {
  text-align: center;
  padding: 80px 20px;
  color: #666;
}

.spinner {
  border: 4px solid #f3f3f3;
  border-top: 4px solid #2196f3;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin: 0 auto 20px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.qrcode-container {
  text-align: center;
}

.instruction-text {
  margin-bottom: 20px;
}

.instruction-text .step {
  font-size: 18px;
  font-weight: bold;
  color: #333;
  margin-bottom: 8px;
}

.instruction-text .hint {
  font-size: 14px;
  color: #999;
}

.qr-loading {
  padding: 60px 20px;
}

.qrcode-image {
  width: 280px;
  height: 280px;
  margin: 20px auto;
  display: block;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 10px;
  background: white;
}

.status {
  font-size: 16px;
  font-weight: bold;
  margin: 20px 0;
  min-height: 24px;
}

.status-waiting {
  color: #ff9800;
}

.status-scanned {
  color: #2196f3;
}

.status-logging {
  color: #4caf50;
}

.actions {
  margin-top: 20px;
}

.btn-refresh {
  padding: 10px 20px;
  background: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled) {
  background: #0b7dda;
}

.btn-refresh:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.success-container {
  text-align: center;
  padding: 40px 20px;
}

.success-icon {
  font-size: 64px;
  margin-bottom: 20px;
}

.success-container h3 {
  margin: 0 0 10px 0;
  font-size: 24px;
  color: #4caf50;
}

.success-container p {
  margin: 10px 0;
  color: #666;
}

.account-info {
  background: #f5f5f5;
  border-radius: 8px;
  padding: 15px;
  margin: 20px auto;
  max-width: 300px;
  text-align: left;
}

.account-info p {
  margin: 8px 0;
  font-size: 14px;
}

.account-info strong {
  color: #333;
}

.btn-done {
  padding: 12px 30px;
  background: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  margin-top: 20px;
  transition: all 0.2s;
}

.btn-done:hover {
  background: #45a049;
}

.error {
  text-align: center;
  padding: 60px 20px;
}

.error-title {
  font-size: 20px;
  font-weight: bold;
  color: #f44336;
  margin-bottom: 10px;
}

.error-message {
  color: #666;
  margin-bottom: 20px;
}

.btn-retry {
  padding: 10px 20px;
  background: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
}

.btn-retry:hover {
  background: #0b7dda;
}
</style>
