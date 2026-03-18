<template>
  <div class="react-topbar">
    <div class="left">
      <!-- 标题已移除 -->
    </div>
  </div>
</template>

<script setup>
defineProps({
  isAnalyzing: { type: Boolean, default: false },
  isComplete: { type: Boolean, default: false },
  hasResults: { type: Boolean, default: false },
  iterations: { type: Number, default: 0 },
  maxIterations: { type: Number, default: 10 }
})
</script>

<style lang="scss" scoped>
.react-topbar {
  height: 60px;
  background: white;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  flex-shrink: 0;
}

.left h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #1a1a1a;
  font-family: 'STKaiti', 'KaiTi', 'FZYaoti', 'SimHei', 'Microsoft YaHei', serif;
  letter-spacing: 2px;
  position: relative;
  padding-left: 12px;

  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 4px;
    height: 70%;
    background: linear-gradient(180deg, rgba(0,0,0,0.8), rgba(0,0,0,0));
    border-radius: 2px;
  }

  text-shadow:
    1px 1px 0 rgba(0, 0, 0, 0.25),
    -1px -1px 0 rgba(255, 255, 255, 0.3);
}


</style>
