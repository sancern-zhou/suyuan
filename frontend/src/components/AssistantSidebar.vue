<template>
  <aside class="assistant-sidebar" :class="{ collapsed: isCollapsed }">
    <div class="sidebar-header">
      <template v-if="!isCollapsed">
        <h2>助手中心</h2>
        <p>根据业务侧重点选择合适的智能助手</p>
      </template>
      <button class="collapse-btn" type="button" @click="toggleCollapse" :title="isCollapsed ? '展开' : '收起'">
        <span class="collapse-icon" :class="{ collapsed: isCollapsed }"></span>
      </button>
    </div>

    <div class="module-list">
      <button
        v-for="module in modules"
        :key="module.id"
        class="module-card"
        :class="{ active: isActive(module.id), disabled: !module.ready }"
        type="button"
        @click="handleModuleSelect(module.id)"
        :title="isCollapsed ? module.name : ''"
      >
        <template v-if="isCollapsed">
          <span class="module-abbr">{{ module.name.charAt(0) }}</span>
        </template>
        <template v-else>
          <div class="module-info">
            <p class="module-title">{{ module.name }}</p>
            <p class="module-desc">{{ module.desc }}</p>
          </div>
          <span class="status-badge" :class="module.ready ? 'status-ready' : 'status-pending'">
            {{ module.ready ? '已接入' : '开发中' }}
          </span>
        </template>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const props = defineProps({
  activeModule: {
    type: String,
    default: 'general-agent'
  }
})

const emit = defineEmits(['update:activeModule', 'select'])

const isCollapsed = ref(false)
const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const modules = [
  {
    id: 'quick-tracing-expert',
    name: '快速溯源场景',
    desc: '多专家协作快速溯源分析',
    ready: true
  },
  {
    id: 'deep-tracing-expert',
    name: '深度溯源场景',
    desc: 'HYSPLIT轨迹+源清单+EKMA分析',
    ready: true
  },
  {
    id: 'report-generation-expert',
    name: '报告生成场景',
    desc: '基于模板智能生成报告',
    ready: true
  },
  {
    id: 'knowledge-qa',
    name: '知识问答场景',
    desc: '基于知识库的智能问答',
    ready: true
  },
  {
    id: 'general-agent',
    name: '通用Agent',
    desc: '多轮问答与综合分析',
    ready: true
  },
  {
    id: 'knowledge-base',
    name: '知识库管理',
    desc: '管理文档与知识检索',
    ready: true,
    isManagement: true
  },
  {
    id: 'meteorology-expert',
    name: '气象分析场景',
    desc: '气象条件分析与可视化',
    ready: false
  },
  {
    id: 'data-visualization-expert',
    name: '数据可视化场景',
    desc: '灵活绘制各类专业图表',
    ready: false
  }
]

const handleModuleSelect = (moduleId) => {
  const module = modules.find(m => m.id === moduleId)

  // 管理功能跳转到独立页面
  if (module?.isManagement) {
    router.push({ name: moduleId })
    return
  }

  emit('update:activeModule', moduleId)
  emit('select', moduleId)
}

const isActive = (moduleId) => props.activeModule === moduleId
</script>

<style lang="scss" scoped>
.assistant-sidebar {
  width: 280px;
  border-right: 1px solid #edf0f5;
  background: #fafbff;
  display: flex;
  flex-direction: column;
  padding: 20px 16px;
  overflow-y: auto;
  transition: width 0.2s ease;

  &.collapsed {
    width: 60px;
    padding: 20px 8px;
  }
}

.sidebar-header {
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;

  h2 {
    margin: 0;
    font-size: 18px;
    color: #1f2a44;
    flex: 1;
  }

  p {
    margin: 6px 0 0;
    font-size: 13px;
    color: #7a86a0;
    width: 100%;
  }

  .collapsed & {
    justify-content: center;
    margin-bottom: 12px;
  }
}

.collapse-btn {
  background: transparent;
  border: none;
  padding: 4px;
  cursor: pointer;
  margin-left: auto;

  .collapsed & {
    margin: 0;
  }
}

.collapse-icon {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-left: 2px solid #9aa6c1;
  border-bottom: 2px solid #9aa6c1;
  transform: rotate(45deg);
  transition: transform 0.2s;

  &.collapsed {
    transform: rotate(-135deg);
  }
}

.module-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.module-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: 1px solid #e4e7f0;
  border-radius: 12px;
  background: #fff;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(31, 42, 68, 0.06);
  cursor: pointer;
  text-align: left;

  &:hover {
    border-color: #c5d4e8;
  }

  &.active {
    border-color: #1976d2;
    box-shadow: 0 6px 16px rgba(25, 118, 210, 0.15);
  }

  &.disabled {
    opacity: 0.9;
  }

  .collapsed & {
    justify-content: center;
    padding: 10px;
  }
}

.module-abbr {
  font-size: 16px;
  font-weight: 600;
  color: #1976d2;
}

.module-info {
  flex: 1;
}

.module-title {
  margin: 0;
  font-size: 15px;
  color: #1f2a44;
  font-weight: 600;
}

.module-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: #7a86a0;
}

.status-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  flex-shrink: 0;

  &.status-ready {
    border-color: #b3d5ff;
    color: #1976d2;
    background: #e9f3ff;
  }

  &.status-pending {
    border-color: #ffd6a5;
    color: #d9822b;
    background: #fff6ea;
  }
}
</style>
