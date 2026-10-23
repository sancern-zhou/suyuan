<template>
  <Teleport to="body">
    <div v-if="visible" class="app-qrcode-overlay" @click="close">
      <div class="app-qrcode-modal" role="dialog" aria-modal="true" aria-label="扫码下载溯源 App" @click.stop>
        <button class="close-btn" type="button" aria-label="关闭" @click="close">×</button>
        <div class="app-qrcode-header">
          <h3>扫码下载溯源 App</h3>
          <p>Android 手机使用相机或浏览器扫码安装。</p>
        </div>
        <img :src="appDownloadQrcode" alt="溯源 App 下载二维码" class="app-qrcode-image" />
        <p class="app-qrcode-hint">已安装的用户无需重新扫码，App 启动时会自动检查并提示更新。</p>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { onBeforeUnmount, watch } from 'vue'
import appDownloadQrcode from '@/assets/app-download-qrcode.png'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const close = () => emit('close')

const handleKeydown = event => {
  if (event.key === 'Escape') close()
}

watch(
  () => props.visible,
  value => {
    if (value) document.addEventListener('keydown', handleKeydown)
    else document.removeEventListener('keydown', handleKeydown)
  }
)

onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))
</script>

<style scoped>
.app-qrcode-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
}

.app-qrcode-modal {
  position: relative;
  min-width: 340px;
  max-width: 90vw;
  padding: 28px 30px 22px;
  border-radius: 12px;
  background: white;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  text-align: center;
}

.close-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 4px;
  background: none;
  color: var(--text-3, #888);
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--bg-hover, #f0f2f5);
  color: var(--text-1, #333);
}

.app-qrcode-header h3 {
  margin: 0 0 6px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1, #1f2a44);
}

.app-qrcode-header p {
  margin: 0;
  font-size: 13px;
  color: var(--text-2, #555);
}

.app-qrcode-image {
  display: block;
  width: 240px;
  height: 240px;
  margin: 18px auto;
  padding: 8px;
  border: 1px solid var(--border-2, #e5e9f0);
  border-radius: 8px;
  background: white;
}

.app-qrcode-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-3, #888);
}
</style>
