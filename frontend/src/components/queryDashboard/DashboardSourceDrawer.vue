<template>
  <aside v-if="open" class="source-drawer" aria-label="数据源详情">
    <div class="drawer-header">
      <h3>数据源</h3>
      <button type="button" class="close-button" @click="$emit('close')" aria-label="关闭数据源详情">×</button>
    </div>
    <div v-if="sources.length > 0" class="source-list">
      <article v-for="(source, index) in sources" :key="sourceKey(source, index)" class="source-item">
        <h4>{{ sourceTitle(source, index) }}</h4>
        <p v-if="sourceDescription(source)">{{ sourceDescription(source) }}</p>
        <dl>
          <div v-for="detail in sourceDetails(source)" :key="detail.label" class="source-detail">
            <dt>{{ detail.label }}</dt>
            <dd>{{ detail.value }}</dd>
          </div>
        </dl>
      </article>
    </div>
    <p v-else class="empty-state">暂无可展示的数据源详情。</p>
  </aside>
</template>

<script setup>
defineProps({
  open: {
    type: Boolean,
    default: false
  },
  sources: {
    type: Array,
    default: () => []
  }
})

defineEmits(['close'])

const sourceKey = (source, index) => source?.id || source?.data_id || source?.name || index

const sourceTitle = (source, index) => source?.title || source?.name || source?.data_id || `数据源 ${index + 1}`

const sourceDescription = (source) => source?.description || source?.summary || source?.content || ''

const sourceDetails = (source) => {
  const fields = [
    ['类型', source?.type || source?.category],
    ['时间', source?.updated_at || source?.time || source?.timestamp],
    ['来源', source?.source || source?.provider],
    ['状态', source?.status]
  ]
  return fields
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([label, value]) => ({ label, value: String(value) }))
}
</script>

<style scoped>
.source-drawer {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 12;
  display: flex;
  flex-direction: column;
  width: min(380px, 100%);
  height: 100%;
  border-left: 1px solid rgba(32, 49, 58, 0.14);
  background: #ffffff;
  box-shadow: -14px 0 34px rgba(22, 39, 46, 0.14);
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid rgba(32, 49, 58, 0.1);
}

h3,
h4,
p {
  margin: 0;
}

h3 {
  font-size: 15px;
  color: #20313a;
}

.close-button {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  border: 1px solid rgba(32, 49, 58, 0.16);
  border-radius: 6px;
  background: #fff;
  color: #52646c;
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
}

.source-list {
  display: grid;
  gap: 12px;
  padding: 14px;
  overflow: auto;
}

.source-item {
  display: grid;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(32, 49, 58, 0.1);
}

h4 {
  color: #20313a;
  font-size: 14px;
}

p,
dd {
  color: #52646c;
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

dl {
  display: grid;
  gap: 6px;
  margin: 0;
}

.source-detail {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 8px;
}

dt {
  color: #7a8790;
  font-size: 12px;
}

dd {
  margin: 0;
}

.empty-state {
  padding: 16px;
}
</style>
