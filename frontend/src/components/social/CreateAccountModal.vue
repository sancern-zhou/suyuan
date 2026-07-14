<template>
  <div class="create-modal-overlay" @click="close">
    <div class="create-modal" @click.stop>
      <header class="modal-header">
        <h3>添加微信账号</h3>
        <button class="close-btn" type="button" @click="close">&times;</button>
      </header>

      <main class="modal-body">
        <div v-if="currentStep === 'starting'" class="center-state">
          <div v-if="creating" class="spinner" />
          <p>{{ creating ? '正在生成专属二维码...' : '微信扫码初始化失败' }}</p>
          <p v-if="errorMessage" class="inline-error">{{ errorMessage }}</p>
          <button v-if="!creating" class="btn-primary" type="button" @click="startScan">重试</button>
        </div>

        <section v-else-if="currentStep === 'qrcode'" class="qrcode-container">
          <div class="instruction-text">
            <p class="step">使用微信扫描下方二维码</p>
            <p class="hint">当前登录用户：{{ ownerLabel }}</p>
            <p class="hint">扫码后在手机上确认即可，无需发送验证码</p>
          </div>

          <div v-if="qrLoading" class="center-state">
            <div class="spinner" />
            <p>正在加载二维码...</p>
          </div>
          <img v-else-if="qrCodeUrl" :src="qrCodeUrl" alt="微信登录二维码" class="qrcode-image">

          <p class="status">{{ statusText }}</p>
          <p v-if="errorMessage" class="inline-error">{{ errorMessage }}</p>
          <button class="btn-primary" type="button" :disabled="refreshing" @click="refreshQRCode">
            {{ refreshing ? '刷新中...' : '刷新二维码' }}
          </button>
        </section>

        <section v-else class="success-container">
          <div class="success-icon">✓</div>
          <h3>绑定成功</h3>
          <p>{{ ownerLabel }} 已绑定当前扫码微信</p>
          <div class="account-info">
            <p><strong>账号 ID：</strong>{{ scan.account_id }}</p>
            <p><strong>平台用户：</strong>{{ ownerLabel }}</p>
          </div>
          <button class="btn-done" type="button" @click="close">完成</button>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { authAxios } from '@/auth/http.js'
import { getOnboardingStep, scanOwnerLabel } from './createAccountFlow.js'

const emit = defineEmits(['close', 'created'])

const scan = ref(null)
const scanConfirmed = ref(false)
const creating = ref(false)
const qrLoading = ref(false)
const refreshing = ref(false)
const qrCodeUrl = ref('')
const loginStatus = ref('waiting')
const errorMessage = ref('')
let statusTimer = null

const currentStep = computed(() => getOnboardingStep({
  scanCreated: Boolean(scan.value),
  scanConfirmed: scanConfirmed.value
}))
const ownerLabel = computed(() => scanOwnerLabel(scan.value))
const statusText = computed(() => ({
  waiting: '等待扫描...',
  scanned: '已扫描，请在手机上确认',
  logging_in: '正在完成绑定...'
}[loginStatus.value] || '等待扫描...'))

function revokeQrUrl() {
  if (qrCodeUrl.value.startsWith('blob:')) URL.revokeObjectURL(qrCodeUrl.value)
  qrCodeUrl.value = ''
}

function stopPolling() {
  if (statusTimer) clearInterval(statusTimer)
  statusTimer = null
}

async function startScan() {
  creating.value = true
  errorMessage.value = ''
  try {
    const response = await authAxios.post('/api/social/accounts/weixin/auto-create', {})
    scan.value = response.data
    await fetchQRCode()
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || error.message || '创建失败，请重试'
  } finally {
    creating.value = false
  }
}

async function fetchQRCode() {
  if (!scan.value?.task_id) return
  qrLoading.value = true
  errorMessage.value = ''
  try {
    const response = await authAxios.get(
      `/api/social/accounts/weixin/${scan.value.task_id}/qrcode`,
      { responseType: 'blob' }
    )
    revokeQrUrl()
    qrCodeUrl.value = URL.createObjectURL(response.data)
    stopPolling()
    statusTimer = setInterval(checkLoginStatus, 3000)
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || error.message || '获取二维码失败'
  } finally {
    qrLoading.value = false
  }
}

async function checkLoginStatus() {
  if (!scan.value?.task_id) return
  try {
    const response = await authAxios.get(
      `/api/social/accounts/weixin/${scan.value.task_id}/status`
    )
    if (!response.data.logged_in) return

    loginStatus.value = 'logging_in'
    stopPolling()
    const finalized = await authAxios.post(
      `/api/social/accounts/weixin/${scan.value.task_id}/finalize`,
      {}
    )
    scan.value = { ...scan.value, ...finalized.data }
    scanConfirmed.value = true
    emit('created')
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || error.message || '绑定失败'
  }
}

async function refreshQRCode() {
  if (!scan.value?.task_id) return
  refreshing.value = true
  errorMessage.value = ''
  try {
    await authAxios.post(
      `/api/social/accounts/weixin/${scan.value.task_id}/refresh-qrcode`,
      {}
    )
    await fetchQRCode()
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || error.message || '刷新失败'
  } finally {
    refreshing.value = false
  }
}

function close() {
  stopPolling()
  revokeQrUrl()
  emit('close')
}

onMounted(startScan)
onUnmounted(() => {
  stopPolling()
  revokeQrUrl()
})
</script>

<style scoped>
.create-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
}

.create-modal {
  width: min(450px, 90vw);
  min-height: 460px;
  padding: 28px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-header h3 { margin: 0; }
.modal-body { padding-top: 26px; }
.close-btn { border: 0; background: transparent; color: #777; font-size: 28px; cursor: pointer; }
.center-state, .qrcode-container, .success-container { padding: 35px 10px; text-align: center; }
.instruction-text { margin-bottom: 18px; }
.step { margin: 0 0 8px; color: #333; font-size: 18px; font-weight: 700; }
.hint { margin: 5px 0; color: #777; font-size: 14px; }
.qrcode-image { display: block; width: 280px; height: 280px; margin: 10px auto; padding: 8px; border: 1px solid #ddd; border-radius: 8px; }
.status { min-height: 24px; color: #e48a00; font-weight: 600; }
.inline-error { color: #d93025; }
.spinner { width: 38px; height: 38px; margin: 20px auto; border: 4px solid #eee; border-top-color: #1976d2; border-radius: 50%; animation: spin 1s linear infinite; }
.btn-primary, .btn-done { padding: 10px 22px; border: 0; border-radius: 5px; color: #fff; background: #1976d2; cursor: pointer; }
.btn-primary:disabled { background: #aaa; }
.btn-done { background: #43a047; }
.success-icon { color: #43a047; font-size: 64px; }
.success-container h3 { color: #43a047; }
.account-info { margin: 20px auto; padding: 12px; border-radius: 8px; background: #f5f5f5; text-align: left; }
.account-info p { margin: 7px 0; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
