<template>
  <main class="access-denied-page">
    <section class="access-denied-card" aria-labelledby="access-denied-title">
      <h1 id="access-denied-title">无访问权限</h1>
      <p>当前账号所属单位未开通智能体平台的使用权限。</p>
      <p class="access-denied-hint">如需使用，请联系平台管理员申请开通。</p>
    </section>
  </main>
</template>

<script setup>
// 静态提示页：不触发任何认证请求，避免与运维平台登录页来回跳转。
</script>

<style scoped>
.access-denied-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-muted, #f4f6f9);
  padding: 24px;
}

.access-denied-card {
  max-width: 420px;
  width: 100%;
  background: #fff;
  border: 1px solid rgba(15, 40, 80, 0.1);
  border-radius: 12px;
  padding: 40px 36px;
  text-align: center;
  box-shadow: 0 8px 24px rgba(15, 40, 80, 0.08);
}

.access-denied-card h1 {
  margin: 0 0 16px;
  font-size: 22px;
  color: #1f2d3d;
}

.access-denied-card p {
  margin: 8px 0;
  color: #4a5a6e;
  line-height: 1.6;
}

.access-denied-hint {
  font-size: 13px;
  color: #8595a8;
}
</style>
