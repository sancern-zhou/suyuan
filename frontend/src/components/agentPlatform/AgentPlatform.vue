<template>
  <main class="agent-platform">
    <div class="platform-glow platform-glow-primary" aria-hidden="true"></div>
    <div class="platform-glow platform-glow-secondary" aria-hidden="true"></div>

    <div class="platform-content">
      <header class="platform-hero">
        <span class="platform-eyebrow">
          <span class="eyebrow-mark" aria-hidden="true"></span>
          智能体平台
        </span>
        <h1>选择智能体，开始工作</h1>
        <p>根据任务类型选择合适的智能体，让专业能力协助你更高效地完成工作。</p>
      </header>

      <div v-if="error" class="platform-error" role="alert">{{ error }}</div>

      <section class="scene-stack" aria-label="智能体应用场景">
        <section
          v-for="scene in sceneGroups"
          :key="scene.id"
          class="scene-section"
          :aria-labelledby="`scene-${scene.id}`"
        >
          <header class="scene-header">
            <span class="scene-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path
                  v-for="path in scene.iconPaths"
                  :key="path.d"
                  :class="`tone-${path.tone}`"
                  :d="path.d"
                />
              </svg>
            </span>
            <div class="scene-title-copy">
              <h2 :id="`scene-${scene.id}`">{{ scene.name }}</h2>
              <p>{{ scene.description }}</p>
            </div>
          </header>

          <div class="scene-agent-grid">
            <button
              v-for="agent in scene.agents"
              :key="agent.id"
              class="agent-card"
              type="button"
              :class="{
                running: isRunning(agent.id),
                selecting: selectingMode === agent.id
              }"
              :style="{ '--agent-accent': agent.accent }"
              :disabled="Boolean(selectingMode)"
              @click="emit('select', agent.id)"
            >
              <span v-if="isRunning(agent.id)" class="running-badge">
                <span class="running-dot" aria-hidden="true"></span>
                运行中
              </span>

              <div class="card-copy">
                <h3>{{ agent.name }}</h3>
                <p>{{ agent.description }}</p>
              </div>

              <div class="agent-tags" aria-label="能力标签">
                <span v-for="tag in agent.tags" :key="tag">{{ tag }}</span>
              </div>

              <div class="card-action">
                <span>{{ selectingMode === agent.id ? '正在进入…' : (isRunning(agent.id) ? '查看任务' : '开始使用') }}</span>
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path d="M4 10h12" />
                  <path d="m12 6 4 4-4 4" />
                </svg>
              </div>
            </button>
          </div>
        </section>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed } from 'vue'
import { AGENT_MODES, AGENT_SCENES } from '@/config/agentModes.js'

const props = defineProps({
  agents: {
    type: Array,
    default: () => AGENT_MODES
  },
  scenes: {
    type: Array,
    default: () => AGENT_SCENES
  },
  runningModes: {
    type: Array,
    default: () => []
  },
  selectingMode: {
    type: String,
    default: ''
  },
  error: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['select'])
const sceneGroups = computed(() => props.scenes.map(scene => ({
  ...scene,
  agents: scene.modeIds
    .map(mode => props.agents.find(agent => agent.id === mode))
    .filter(Boolean)
})))
const isRunning = mode => props.runningModes.includes(mode)
</script>

<style lang="scss" scoped>
.agent-platform {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: auto;
  background:
    linear-gradient(180deg, rgba(246, 249, 255, 0.3) 0%, #f6f8fc 55%, #f4f7fb 100%);
  color: #17223b;
  isolation: isolate;
}

.platform-glow {
  position: absolute;
  z-index: -1;
  border-radius: 999px;
  filter: blur(4px);
  pointer-events: none;
}

.platform-glow-primary {
  width: 500px;
  height: 500px;
  top: -280px;
  left: 14%;
  background: radial-gradient(circle, rgba(40, 120, 255, 0.12), transparent 70%);
}

.platform-glow-secondary {
  width: 420px;
  height: 420px;
  top: 4%;
  right: -200px;
  background: radial-gradient(circle, rgba(118, 86, 232, 0.08), transparent 70%);
}

.platform-content {
  width: min(1160px, calc(100% - 56px));
  margin: 0 auto;
  padding: clamp(24px, 4vh, 40px) 0 32px;
}

.platform-hero {
  max-width: 700px;
  margin-bottom: 24px;

  h1 {
    margin: 10px 0 8px;
    font-size: clamp(28px, 2.5vw, 36px);
    line-height: 1.2;
    letter-spacing: -0.025em;
    font-weight: 650;
    color: #17223b;
  }

  p {
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
    color: #65718a;
  }
}

.platform-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #2878ff;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.eyebrow-mark {
  width: 18px;
  height: 3px;
  border-radius: 999px;
  background: #2878ff;
}

.platform-error {
  margin: -10px 0 16px;
  padding: 10px 14px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #fff5f5;
  color: #b42318;
  font-size: 13px;
}

.scene-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.scene-section {
  display: grid;
  grid-template-columns: 118px minmax(0, 1fr);
  align-items: stretch;
  gap: 14px;
}

.scene-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 0 8px 0 2px;
}

.scene-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex: 0 0 auto;

  svg {
    width: 28px;
    height: 28px;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.65;
  }

  .tone-primary {
    stroke: #55647c;
  }

  .tone-accent {
    stroke: #2878ff;
  }
}

.scene-title-copy {
  min-width: 0;

  h2 {
    margin: 0 0 7px;
    color: #26344f;
    font-size: 16px;
    font-weight: 650;
  }

  p {
    margin: 0;
    color: #8993a6;
    font-size: 11px;
    line-height: 1.55;
  }
}

.scene-agent-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.agent-card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 176px;
  padding: 14px 16px;
  overflow: hidden;
  border: 1px solid #e4e9f2;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 10px 30px rgba(31, 48, 78, 0.045);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;

  &:hover:not(:disabled) {
    transform: translateY(-3px);
    border-color: color-mix(in srgb, var(--agent-accent) 35%, #e4e9f2);
    box-shadow: 0 18px 42px rgba(31, 48, 78, 0.1);

    .card-action svg {
      transform: translateX(3px);
    }
  }

  &:focus-visible {
    outline: 3px solid color-mix(in srgb, var(--agent-accent) 28%, transparent);
    outline-offset: 2px;
    border-color: var(--agent-accent);
  }

  &:disabled {
    cursor: wait;
  }

  &.selecting {
    border-color: var(--agent-accent);
  }
}

.running-badge {
  position: absolute;
  top: 14px;
  right: 16px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  border-radius: 999px;
  background: #eefaf5;
  color: #168161;
  font-size: 11px;
  font-weight: 600;
}

.running-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #20a77c;
  box-shadow: 0 0 0 3px rgba(32, 167, 124, 0.12);
}

.card-copy {
  margin-top: 0;

  h3 {
    margin: 0 0 6px;
    font-size: 16px;
    font-weight: 650;
    color: #1d2942;
  }

  p {
    min-height: 32px;
    margin: 0;
    color: #6b768d;
    font-size: 13px;
    line-height: 1.55;
  }
}

.agent-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;

  span {
    padding: 3px 7px;
    border-radius: 6px;
    background: #f4f6fa;
    color: #778197;
    font-size: 11px;
  }
}

.card-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 6px;
  color: var(--agent-accent);
  font-size: 13px;
  font-weight: 600;

  svg {
    width: 18px;
    height: 18px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.7;
    stroke-linecap: round;
    stroke-linejoin: round;
    transition: transform 0.2s ease;
  }
}

@media (max-width: 1100px) {
  .scene-section {
    grid-template-columns: 1fr;
  }

  .scene-header {
    justify-content: flex-start;
    padding: 0;
  }

  .scene-title-copy {
    display: flex;
    align-items: baseline;
    gap: 10px;

    h2 {
      margin: 0;
    }
  }
}

@media (max-width: 820px) {
  .scene-agent-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .platform-content {
    width: min(100% - 32px, 560px);
    padding-top: 24px;
  }

  .platform-hero {
    margin-bottom: 20px;
  }

  .scene-agent-grid {
    grid-template-columns: 1fr;
  }

  .agent-card {
    min-height: 208px;
  }
}
</style>
