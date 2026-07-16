<template>
  <header v-if="agent" class="agent-workspace-header" :style="{ '--agent-accent': agent.accent }">
    <span class="workspace-agent-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24">
        <path v-for="path in agent.iconPaths" :key="path" :d="path" />
      </svg>
    </span>
    <div class="workspace-agent-copy">
      <h1>{{ agent.name }}</h1>
      <p>{{ agent.description }}</p>
    </div>
    <span class="workspace-switch-hint">从左侧智能体平台切换模式</span>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { getAgentMode } from '@/config/agentModes.js'

const props = defineProps({
  mode: {
    type: String,
    default: 'assistant'
  }
})

const agent = computed(() => getAgentMode(props.mode))
</script>

<style lang="scss" scoped>
.agent-workspace-header {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 62px;
  padding: 10px 20px;
  border-bottom: 1px solid #edf1f7;
  background: rgba(255, 255, 255, 0.96);
  flex: 0 0 auto;
}

.workspace-agent-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--agent-accent) 10%, white);
  color: var(--agent-accent);

  svg {
    width: 20px;
    height: 20px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.7;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
}

.workspace-agent-copy {
  min-width: 0;

  h1 {
    margin: 0 0 2px;
    color: #1f2a44;
    font-size: 15px;
    font-weight: 650;
  }

  p {
    margin: 0;
    overflow: hidden;
    color: #7a86a0;
    font-size: 11px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.workspace-switch-hint {
  margin-left: auto;
  color: #9aa4b8;
  font-size: 11px;
  white-space: nowrap;
}

@media (max-width: 760px) {
  .workspace-switch-hint {
    display: none;
  }
}
</style>
