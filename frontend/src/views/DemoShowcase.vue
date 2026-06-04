<template>
  <div class="demo-showcase">
    <!-- Hero Section -->
    <section class="hero-section">
      <div class="hero-content">
        <h1 class="hero-title">
          <span class="title-main">办公室的专业工作站</span>
          <span class="title-divider"></span>
          <span class="title-sub">口袋里的随身助理</span>
        </h1>
        <p class="hero-subtitle">
          同样的 AI 能力，适配不同的使用场景——这是"智能体"区别于传统信息化系统的关键。
        </p>
      </div>
    </section>

    <!-- Platform Cards -->
    <section class="platform-section">
      <div class="platform-container">
        <!-- Web端卡片 -->
        <div class="platform-card web-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="3" width="20" height="14" rx="2" stroke="currentColor" stroke-width="2"/>
              <path d="M8 21h8M12 17v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <h2 class="card-title">Web端 · 专业工作站</h2>
          <p class="card-subtitle">适合深度分析与专业办公</p>

          <ul class="feature-list">
            <li class="feature-item" v-for="(feature, index) in webFeatures" :key="index">
              <span class="feature-icon">✓</span>
              <span>{{ feature }}</span>
            </li>
          </ul>
        </div>

        <!-- 移动端卡片 -->
        <div class="platform-card mobile-card">
          <div class="card-icon">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="8" y="2" width="8" height="20" rx="2" stroke="currentColor" stroke-width="2"/>
              <path d="M12 18v0M10 17h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <h2 class="card-title">移动端 · 随身助理</h2>
          <p class="card-subtitle">接入微信、钉钉等日常通讯工具</p>

          <ul class="feature-list">
            <li class="feature-item" v-for="(feature, index) in mobileFeatures" :key="index">
              <span class="feature-icon">✓</span>
              <span>{{ feature }}</span>
            </li>
          </ul>
        </div>
      </div>
    </section>

    <!-- Integration Section -->
    <section class="integration-section">
      <div class="integration-content">
        <h3 class="integration-title">无缝协同，智能联动</h3>
        <p class="integration-desc">
          Web端与移动端数据实时同步，随时随地掌握空气质量动态
        </p>
        <div class="integration-visual">
          <div class="sync-animation">
            <div class="sync-circle web-sync">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="3" y="3" width="18" height="14" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M9 19h6M12 17v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </div>
            <div class="sync-connection">
              <div class="connection-line"></div>
              <div class="connection-dot"></div>
            </div>
            <div class="sync-circle mobile-sync">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="8" y="2" width="8" height="20" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M12 18v0M10 17h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const webFeatures = [
  '数据查询、深度溯源、报告生成一站式完成',
  '大屏展示，适合会商研判和集中办公',
  '完整的运维管理功能，表单审核与质量统计',
  '支持复杂分析任务的分解与多智能体协同'
]

const mobileFeatures = [
  '随手查询任意城市的实时空气质量',
  '接收污染预警和超标提醒，第一时间响应',
  '审批运维工单，不耽误现场处置进度',
  '查看自动生成的日报摘要，掌握全局动态'
]
</script>

<style scoped>
.demo-showcase {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  overflow-x: hidden;
}

/* Hero Section */
.hero-section {
  padding: 80px 20px 60px;
  text-align: center;
  color: white;
  position: relative;
  overflow: hidden;
}

.hero-section::before {
  content: '';
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle, rgba(255,255,255,0.1) 1px, transparent 1px);
  background-size: 50px 50px;
  animation: gridMove 20s linear infinite;
}

@keyframes gridMove {
  0% { transform: translate(0, 0); }
  100% { transform: translate(50px, 50px); }
}

.hero-content {
  position: relative;
  z-index: 1;
  max-width: 900px;
  margin: 0 auto;
}

.hero-title {
  font-size: clamp(28px, 5vw, 48px);
  font-weight: 700;
  margin-bottom: 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  line-height: 1.3;
}

.title-main {
  background: linear-gradient(135deg, #fff 0%, #f0f0ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.title-divider {
  width: 100px;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.8), transparent);
}

.title-sub {
  background: linear-gradient(135deg, #ffeaa7 0%, #fdcb6e 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-subtitle {
  font-size: clamp(16px, 2.5vw, 20px);
  opacity: 0.95;
  line-height: 1.6;
  max-width: 700px;
  margin: 0 auto;
  font-weight: 300;
}

/* Platform Section */
.platform-section {
  padding: 60px 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.platform-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 30px;
  align-items: stretch;
}

.platform-card {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  padding: 40px 30px;
  position: relative;
  overflow: hidden;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
}

.platform-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.web-card {
  border-top: 4px solid #667eea;
}

.mobile-card {
  border-top: 4px solid #f093fb;
}

.card-icon {
  width: 60px;
  height: 60px;
  margin: 0 auto 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
  color: #667eea;
  transition: all 0.3s ease;
}

.platform-card:hover .card-icon {
  transform: scale(1.1);
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.2) 0%, rgba(118, 75, 162, 0.2) 100%);
}

.mobile-card .card-icon {
  color: #f093fb;
  background: linear-gradient(135deg, rgba(240, 147, 251, 0.1) 0%, rgba(245, 87, 108, 0.1) 100%);
}

.mobile-card:hover .card-icon {
  background: linear-gradient(135deg, rgba(240, 147, 251, 0.2) 0%, rgba(245, 87, 108, 0.2) 100%);
}

.card-icon svg {
  width: 32px;
  height: 32px;
}

.card-title {
  font-size: 24px;
  font-weight: 700;
  text-align: center;
  margin-bottom: 8px;
  color: #2d3748;
}

.card-subtitle {
  text-align: center;
  color: #718096;
  font-size: 14px;
  margin-bottom: 24px;
  font-weight: 500;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.feature-item {
  display: flex;
  align-items: flex-start;
  margin-bottom: 16px;
  padding: 12px;
  background: rgba(102, 126, 234, 0.05);
  border-radius: 8px;
  transition: all 0.3s ease;
}

.feature-item:hover {
  background: rgba(102, 126, 234, 0.1);
  transform: translateX(4px);
}

.mobile-card .feature-item {
  background: rgba(240, 147, 251, 0.05);
}

.mobile-card .feature-item:hover {
  background: rgba(240, 147, 251, 0.1);
}

.feature-icon {
  width: 20px;
  height: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
  flex-shrink: 0;
  margin-right: 12px;
  margin-top: 2px;
}

.mobile-card .feature-icon {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.feature-item span:last-child {
  color: #4a5568;
  font-size: 14px;
  line-height: 1.5;
}

/* Integration Section */
.integration-section {
  padding: 80px 20px;
  text-align: center;
  color: white;
}

.integration-content {
  max-width: 800px;
  margin: 0 auto;
}

.integration-title {
  font-size: 32px;
  font-weight: 700;
  margin-bottom: 16px;
}

.integration-desc {
  font-size: 16px;
  opacity: 0.9;
  margin-bottom: 40px;
  line-height: 1.6;
}

.integration-visual {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 0;
}

.sync-animation {
  display: flex;
  align-items: center;
  gap: 40px;
}

.sync-circle {
  width: 80px;
  height: 80px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  animation: float 3s ease-in-out infinite;
}

.sync-circle svg {
  width: 40px;
  height: 40px;
}

.web-sync {
  animation-delay: 0s;
}

.mobile-sync {
  animation-delay: 1.5s;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.sync-connection {
  position: relative;
  width: 60px;
  height: 2px;
  background: rgba(255, 255, 255, 0.3);
}

.connection-line {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.8), transparent);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.connection-dot {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 8px;
  height: 8px;
  background: white;
  border-radius: 50%;
  animation: moveDot 2s ease-in-out infinite;
}

@keyframes moveDot {
  0%, 100% { transform: translate(-50%, -50%); }
  25% { transform: translate(-150%, -50%); }
  75% { transform: translate(50%, -50%); }
}

/* Responsive Design */
@media (max-width: 768px) {
  .hero-section {
    padding: 60px 20px 40px;
  }

  .hero-title {
    font-size: 28px;
  }

  .platform-container {
    grid-template-columns: 1fr;
    gap: 20px;
  }

  .platform-card {
    padding: 30px 24px;
  }

  .card-title {
    font-size: 20px;
  }

  .integration-section {
    padding: 60px 20px;
  }

  .integration-title {
    font-size: 24px;
  }

  .sync-animation {
    gap: 20px;
  }

  .sync-circle {
    width: 60px;
    height: 60px;
  }

  .sync-circle svg {
    width: 30px;
    height: 30px;
  }

  .sync-connection {
    width: 40px;
  }
}

@media (max-width: 480px) {
  .hero-subtitle {
    font-size: 14px;
  }

  .feature-item {
    padding: 10px;
  }

  .feature-item span:last-child {
    font-size: 13px;
  }
}
</style>
