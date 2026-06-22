<template>
  <section class="layer-control" aria-label="地图图层控制">
    <h3>图层</h3>
    <div class="layer-options">
      <label v-for="option in layerOptions" :key="option.key" class="layer-option">
        <input
          type="checkbox"
          :checked="Boolean(modelValue[option.key])"
          @change="toggleLayer(option.key, $event.target.checked)"
        >
        <span>{{ option.label }}</span>
      </label>
    </div>
  </section>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue'])

const layerOptions = [
  { key: 'city_metrics', label: '城市指标' },
  { key: 'stations', label: '站点' },
  { key: 'heatmap', label: '热力图' }
]

const toggleLayer = (key, enabled) => {
  emit('update:modelValue', {
    city_metrics: false,
    stations: false,
    heatmap: false,
    ...props.modelValue,
    [key]: enabled
  })
}
</script>

<style scoped>
.layer-control {
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

.layer-options {
  display: grid;
  gap: 8px;
}

.layer-option {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #3f5058;
  font-size: 13px;
  line-height: 1.35;
}

.layer-option input {
  flex: 0 0 auto;
}

.layer-option span {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
