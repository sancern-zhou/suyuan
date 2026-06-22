<template>
  <section class="focus-panel" aria-label="当前查询焦点">
    <h3>查询焦点</h3>
    <dl>
      <div v-for="item in focusItems" :key="item.label" class="focus-row">
        <dt>{{ item.label }}</dt>
        <dd>{{ item.value }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  focus: {
    type: Object,
    default: null
  }
})

const joinValue = (value) => {
  if (Array.isArray(value) && value.length > 0) return value.join('、')
  if (value) return String(value)
  return '未指定'
}

const focusItems = computed(() => [
  { label: '范围', value: props.focus?.scope || 'province' },
  { label: '城市', value: joinValue(props.focus?.cities) },
  { label: '站点', value: joinValue(props.focus?.stations) },
  { label: '污染物', value: joinValue(props.focus?.pollutants) },
  { label: '时间', value: joinValue(props.focus?.time_range) },
  { label: '模块', value: joinValue(props.focus?.modules) }
])
</script>

<style scoped>
.focus-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid rgba(32, 49, 58, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.9);
}

h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #20313a;
}

dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.focus-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  font-size: 13px;
  line-height: 1.4;
}

dt {
  color: #73818a;
}

dd {
  min-width: 0;
  margin: 0;
  color: #263840;
  overflow-wrap: anywhere;
}
</style>
