<template>
  <div class="qrcode-modal-overlay" @click="close">
    <div class="qrcode-modal" @click.stop>
      <div class="modal-header">
        <h3>微信扫码登录</h3>
        <button @click="close" class="close-btn">&times;</button>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="loading">
          <div class="spinner"></div>
          <p>正在获取二维码...</p>
        </div>

        <div v-else-if="qrCodeUrl" class="qrcode-container">
          <img :src="qrCodeUrl" alt="微信登录二维码" class="qrcode-image" />
          <p class="instruction">请使用微信扫描二维码登录</p>
          <p :class="['status', statusClass]">{{ statusText }}</p>

          <div class="actions">
            <button @click="refreshQRCode" class="btn-refresh" :disabled="refreshing">
              {{ refreshing ? '刷新中...' : '刷新二维码' }}
            </button>
          </div>
        </div>

        <div v-else class="error">
          <p>无法获取二维码</p>
          <p class="error-detail">{{ errorMessage }}</p>
          <button @click="refreshQRCode" class="btn-retry">重试</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const props = defineProps({
  accountId: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['close'])

const qrCodeUrl = ref('')
const loading = ref(true)
const refreshing = ref(false)
const loginStatus = ref('waiting')
const errorMessage = ref('')
let statusCheckInterval = null

const statusText = computed(() => {
  switch (loginStatus.value) {
    case 'waiting':
      return '等待扫描...'
    case 'scanned':
      return '已扫描，请在手机上确认登录'
    case 'confirmed':
      return '登录成功！'
    case 'expired':
      return '二维码已过期，请刷新'
    default:
      return '等待扫描...'
  }
})

const statusClass = computed(() => {
  switch (loginStatus.value) {
    case 'waiting':
      return 'status-waiting'
    case 'scanned':
      return 'status-scanned'
    case 'confirmed':
      return 'status-confirmed'
    case 'expired':
      return 'status-expired'
    default:
      return ''
  }
})

const fetchQRCode = async () => {
  loading.value = true
  errorMessage.value = ''

  try {
    const response = await axios.get(
      `/api/social/accounts/weixin/${props.accountId}/qrcode`,
      { responseType: 'blob' }
    )
    qrCodeUrl.value = URL.createObjectURL(response.data)
    loginStatus.value = 'waiting'
  } catch (error) {
    console.error('Failed to fetch QR code:', error)
    qrCodeUrl.value = ''
    errorMessage.value = error.response?.data?.detail || error.message || '未知错误'
  } finally {
    loading.value = false
  }
}

const checkStatus = async () => {
  try {
    const response = await axios.get(
      `/api/social/accounts/weixin/${props.accountId}/status`
    )

    if (response.data.logged_in) {
      loginStatus.value = 'confirmed'
      // 登录成功，关闭弹窗
      setTimeout(() => {
        emit('close')
      }, 2000)
    }
  } catch (error) {
    console.error('Failed to check status:', error)
  }
}

const refreshQRCode = async () => {
  refreshing.value = true
  try {
    // 先刷新QR码
    await axios.post(`/api/social/accounts/weixin/${props.accountId}/refresh-qrcode`)
    // 重新获取
    await fetchQRCode()
  } catch (error) {
    console.error('Failed to refresh QR code:', error)
    errorMessage.value = error.response?.data?.detail || error.message || '刷新失败'
  } finally {
    refreshing.value = false
  }
}

const close = () => {
  emit('close')
}

onMounted(() => {
  fetchQRCode()

  // 定时检查登录状态（每3秒）
  statusCheckInterval = setInterval(checkStatus, 3000)
})

onUnmounted(() => {
  if (statusCheckInterval) {
    clearInterval(statusCheckInterval)
  }
  // 释放blob URL
  if (qrCodeUrl.value && qrCodeUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(qrCodeUrl.value)
  }
})
</script>

<style scoped>
.qrcode-modal-overlay {
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

.qrcode-modal {
  background: white;
  border-radius: 12px;
  padding: 30px;
  min-width: 400px;
  max-width: 90vw;
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
  min-height: 300px;
}

.qrcode-container {
  text-align: center;
}

.qrcode-image {
  width: 300px;
  height: 300px;
  margin: 20px auto;
  display: block;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 10px;
  background: white;
}

.instruction {
  font-size: 16px;
  color: #666;
  margin-bottom: 10px;
}

.status {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 20px;
  min-height: 27px;
}

.status-waiting {
  color: #ff9800;
}

.status-scanned {
  color: #2196f3;
}

.status-confirmed {
  color: #4caf50;
}

.status-expired {
  color: #f44336;
}

.actions {
  margin-top: 20px;
}

.btn-refresh, .btn-retry {
  padding: 10px 20px;
  background: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.btn-refresh:hover:not(:disabled), .btn-retry:hover {
  background: #0b7dda;
}

.btn-refresh:disabled {
  background: #ccc;
  cursor: not-allowed;
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

.error {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}

.error-detail {
  color: #f44336;
  margin: 10px 0 20px;
  font-size: 14px;
}
</style>
