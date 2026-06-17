<template>
  <div class="create-modal-overlay" @click="close">
    <div class="create-modal" @click.stop>
      <div class="modal-header">
        <h3>添加微信账号</h3>
        <button @click="close" class="close-btn">&times;</button>
      </div>

      <div class="modal-body">
        <form v-if="currentStep === 'profile'" class="profile-form" @submit.prevent="submitProfile">
          <div class="instruction-text">
            <p class="step">第1步：填写用户资料</p>
            <p class="hint">资料会生成一个绑定码，用于把微信联系人和系统用户关联起来</p>
          </div>

          <label class="form-field">
            <span>姓名</span>
            <input
              v-model.trim="profileForm.name"
              type="text"
              maxlength="100"
              placeholder="请输入姓名"
              :disabled="profileSubmitting"
              required
            />
          </label>

          <label class="form-field">
            <span>邮箱</span>
            <input
              v-model.trim="profileForm.email"
              type="email"
              maxlength="255"
              placeholder="可选"
              :disabled="profileSubmitting"
            />
          </label>

          <div v-if="errorMessage" class="inline-error">{{ errorMessage }}</div>

          <button class="btn-primary" type="submit" :disabled="profileSubmitting || !profileForm.name">
            {{ profileSubmitting ? '创建中...' : '生成绑定码并继续' }}
          </button>
        </form>

        <div v-else-if="accountCreating" class="loading">
          <div class="spinner"></div>
          <p>正在初始化微信账号...</p>
        </div>

        <div v-else-if="currentStep === 'qrcode'" class="qrcode-container">
          <div class="instruction-text">
            <p class="step">第2步：使用微信扫描下方二维码</p>
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

          <div v-if="errorMessage" class="inline-error">{{ errorMessage }}</div>

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

        <div v-else-if="currentStep === 'binding'" class="binding-container">
          <div class="instruction-text">
            <p class="step">第3步：发送绑定码</p>
            <p class="hint">请在微信里直接发送下面 4 位数字</p>
          </div>

          <div class="bind-code">{{ bindInstruction }}</div>

          <div class="account-info">
            <p><strong>账号ID：</strong>{{ createdAccountId }}</p>
            <p><strong>显示名称：</strong>{{ accountName }}</p>
            <p><strong>用户：</strong>{{ pendingUser?.name }}</p>
          </div>

          <div class="status status-waiting">{{ bindingStatusText }}</div>
          <div v-if="errorMessage" class="inline-error">{{ errorMessage }}</div>

          <div class="actions">
            <button class="btn-refresh" @click="checkBindStatus" :disabled="bindChecking">
              {{ bindChecking ? '检查中...' : '检查绑定状态' }}
            </button>
          </div>
        </div>

        <div v-else-if="currentStep === 'complete'" class="success-container">
          <div class="success-icon">✓</div>
          <h3>绑定成功</h3>
          <p>{{ pendingUser?.name }} 已可以通过微信正常使用</p>
          <div class="account-info">
            <p><strong>账号ID：</strong>{{ createdAccountId }}</p>
            <p><strong>显示名称：</strong>{{ accountName }}</p>
            <p><strong>绑定用户：</strong>{{ pendingUser?.name }}</p>
          </div>
          <button @click="close" class="btn-done">完成</button>
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
import { ref, computed, onUnmounted } from 'vue'
import axios from 'axios'
import {
  buildBindInstruction,
  getOnboardingStep,
  isUserBound,
} from './createAccountFlow'

const emit = defineEmits(['close', 'created'])

const profileSubmitting = ref(false)
const accountCreating = ref(false)
const tempAccountId = ref('')
const qrCodeUrl = ref('')
const qrLoading = ref(true)
const refreshing = ref(false)
const loginStatus = ref('waiting')
const loginSuccess = ref(false)
const errorMessage = ref('')
const createdAccountId = ref('')
const accountName = ref('')
const pendingUser = ref(null)
const bindInstruction = ref('')
const bound = ref(false)
const bindChecking = ref(false)
const bindingStatusText = ref('等待用户发送绑定码...')
const profileForm = ref({
  name: '',
  email: ''
})

let statusCheckInterval = null
let bindStatusInterval = null

const currentStep = computed(() => getOnboardingStep({
  pendingUser: pendingUser.value,
  loginSuccess: loginSuccess.value,
  bound: bound.value
}))

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

const submitProfile = async () => {
  profileSubmitting.value = true
  errorMessage.value = ''

  try {
    const payload = {
      name: profileForm.value.name,
      email: profileForm.value.email || null
    }
    const response = await axios.post('/api/social/users', payload)
    pendingUser.value = response.data
    bindInstruction.value = buildBindInstruction(response.data)

    await initializeTempAccount()
  } catch (error) {
    console.error('[ERROR] 创建社交用户失败:', error)
    errorMessage.value = error.response?.data?.detail || error.message || '创建用户失败，请重试'
  } finally {
    profileSubmitting.value = false
  }
}

// 初始化临时账号并获取二维码
const initializeTempAccount = async () => {
  accountCreating.value = true
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
    accountCreating.value = false
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
  stopStatusCheck()
  statusCheckInterval = setInterval(checkLoginStatus, 3000)
}

// 停止检查登录状态
const stopStatusCheck = () => {
  if (statusCheckInterval) {
    clearInterval(statusCheckInterval)
    statusCheckInterval = null
  }
}

const startBindStatusCheck = () => {
  stopBindStatusCheck()
  checkBindStatus()
  bindStatusInterval = setInterval(checkBindStatus, 3000)
}

const stopBindStatusCheck = () => {
  if (bindStatusInterval) {
    clearInterval(bindStatusInterval)
    bindStatusInterval = null
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

    startBindStatusCheck()
  } catch (error) {
    console.error('Failed to finalize account:', error)
    errorMessage.value = error.response?.data?.detail || error.message || '账号创建失败'
  }
}

const checkBindStatus = async () => {
  if (!pendingUser.value?.id || bindChecking.value) return

  bindChecking.value = true
  try {
    const response = await axios.get(`/api/social/users/${pendingUser.value.id}`)
    pendingUser.value = response.data

    if (isUserBound(response.data)) {
      bound.value = true
      bindingStatusText.value = '绑定成功'
      stopBindStatusCheck()
      emit('created')
    } else {
      bindingStatusText.value = '等待用户发送绑定码...'
    }
  } catch (error) {
    console.error('Failed to check bind status:', error)
    errorMessage.value = error.response?.data?.detail || error.message || '绑定状态检查失败'
  } finally {
    bindChecking.value = false
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
  stopStatusCheck()
  stopBindStatusCheck()
  if (qrCodeUrl.value && qrCodeUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(qrCodeUrl.value)
  }

  tempAccountId.value = ''
  qrCodeUrl.value = ''
  loginStatus.value = 'waiting'
  loginSuccess.value = false
  errorMessage.value = ''
  createdAccountId.value = ''
  accountName.value = ''
  pendingUser.value = null
  bindInstruction.value = ''
  bound.value = false
  bindingStatusText.value = '等待用户发送绑定码...'
  profileForm.value = {
    name: '',
    email: ''
  }

  // 回到资料填写步骤
}

const close = () => {
  stopStatusCheck()
  stopBindStatusCheck()
  emit('close')
}

onUnmounted(() => {
  stopStatusCheck()
  stopBindStatusCheck()

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

.profile-form,
.binding-container {
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

.form-field {
  display: block;
  text-align: left;
  margin: 0 auto 16px;
  max-width: 320px;
}

.form-field span {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.form-field input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 15px;
}

.form-field input:focus {
  outline: none;
  border-color: #2196f3;
}

.inline-error {
  max-width: 320px;
  margin: 12px auto;
  color: #f44336;
  font-size: 14px;
  line-height: 1.5;
}

.btn-primary {
  padding: 12px 24px;
  background: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #0b7dda;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
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

.bind-code {
  display: inline-block;
  padding: 14px 20px;
  margin: 8px auto 16px;
  border: 1px solid #b7d8ff;
  border-radius: 6px;
  background: #f2f8ff;
  color: #0b5cad;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0;
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
