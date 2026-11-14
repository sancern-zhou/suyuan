<template>
  <section class="inline-html-card">
    <header>
      <span class="label">{{ resource.label || '交互报告' }}</span>
      <span class="actions">
        <button type="button" @click="$emit('preview', resource.resource_id)">面板打开</button>
        <button type="button" @click="expanded = !expanded">{{ expanded ? '收起' : '展开' }}</button>
      </span>
    </header>
    <div :class="{ fullscreen: expanded }">
      <button v-if="expanded" type="button" class="close-html" @click="expanded = false">关闭报告</button>
      <iframe
        ref="frame"
        class="frame"
        :src="resource.content_url"
        :title="resource.label || '交互报告'"
        sandbox="allow-scripts allow-forms"
        :style="frameStyle"
      />
    </div>
  </section>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { isRuntimeHeightEvent, previewFrameHeight } from '@/services/inlineHtmlFrame.js'

const props = defineProps({ resource: { type: Object, required: true } })
defineEmits(['preview'])

const frame = ref(null)
const expanded = ref(false)
const reportedHeight = ref(0)

// opaque sandbox origin 下 event.origin 恒为 "null"，校验只能落在
// event.source（必须确为本卡片的 iframe）与消息形状上。
const onMessage = event => {
  if (!frame.value || event.source !== frame.value.contentWindow) return
  if (!isRuntimeHeightEvent(event.data)) return
  reportedHeight.value = Number(event.data.height)
}

onMounted(() => window.addEventListener('message', onMessage))
onBeforeUnmount(() => window.removeEventListener('message', onMessage))

const frameStyle = computed(() => {
  if (expanded.value) return null
  return { height: `${previewFrameHeight(reportedHeight.value)}px` }
})
</script>
<style scoped>
.inline-html-card { width: 100%; min-width: 0; box-sizing: border-box; margin: 16px 0; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; background: white; }
header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; font-size: 13px; }
.label { min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; color: #222; }
.actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
button { border: 0; background: transparent; color: #2878ff; cursor: pointer; white-space: nowrap; }
.frame { display: block; width: 100%; border: 0; background: white; }
.fullscreen { position: fixed; inset: 0; z-index: 2000; background: white; overflow: hidden; padding-top: 40px; box-sizing: border-box; }
.fullscreen .frame { height: 100%; }
.close-html { position: fixed; top: 12px; right: 18px; z-index: 2001; }
</style>
