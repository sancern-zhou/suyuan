<template>
  <div class="management-panel social-platform-panel">
    <div class="panel-header">
      <h3>社交平台管理</h3>
    </div>
    <div class="app-download-card">
      <img :src="appDownloadQrcode" alt="溯源 App 下载二维码" class="app-download-qrcode" />
      <div class="app-download-text">
        <h4>扫码下载溯源 App</h4>
        <p>Android 手机使用相机或浏览器扫码安装。</p>
        <p class="app-download-hint">已安装的用户无需重新扫码，App 启动时会自动检查并提示更新。</p>
      </div>
    </div>
    <div class="panel-embedded-content">
      <SocialAccountsView />
    </div>
  </div>
</template>

<script setup>
import SocialAccountsView from '@/views/SocialAccountsView.vue'
import appDownloadQrcode from '@/assets/app-download-qrcode.png'

defineEmits(['close'])
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
  margin-bottom: 20px;
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
  transition: all 0.2s;
}

.panel-btn:hover {
  background: var(--color-primary);
  color: white;
}

.app-download-card {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 14px 18px;
  margin-bottom: 16px;
  border: 1px solid var(--border-2);
  border-radius: 10px;
  background: var(--bg-2, #f7f8fa);
}

.app-download-qrcode {
  width: 108px;
  height: 108px;
  flex-shrink: 0;
  border-radius: 6px;
  background: white;
}

.app-download-text h4 {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
}

.app-download-text p {
  margin: 2px 0;
  font-size: 13px;
  color: var(--text-2, #555);
}

.app-download-text .app-download-hint {
  font-size: 12px;
  color: var(--text-3, #888);
}

.panel-embedded-content {
  height: calc(100% - 60px);
  min-height: 0;
  overflow-y: auto;
}

</style>
