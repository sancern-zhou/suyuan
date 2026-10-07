<template>
  <div class="reply-outcomes">
    <article v-for="item in outcomes.files" :key="item.group.group_id" class="file-card">
      <button class="file-summary" @click.stop="$emit('preview', item.resource.resource_id)">
        <span class="file-icon" :class="iconClass(item.group.primary?.format || item.resource.format)">{{ badge(item.group.primary?.format || item.resource.format) }}</span>
        <span class="file-copy"><strong>{{ item.group.primary?.label || item.resource.label }}</strong><small>{{ formats(item.group) }} · 点击查看</small></span>
        <span class="chevron">›</span>
      </button>
      <ResourcePreviewActions :resource="item.resource" :group="item.group" compact />
    </article>
    <details v-if="outcomes.others.length" @toggle="opened = $event.target.open">
      <summary>其他成果（{{ outcomes.others.length }}）</summary>
      <template v-if="opened">
        <div v-for="item in outcomes.others" :key="item.group.group_id">
          <InlineChartCard v-if="item.resource.renderer === 'chart'" :resource="item.resource" />
          <AuthenticatedImage v-else :source="item.resource.content_url" :alt="item.resource.label" class="outcome-image" @click="$emit('preview', item.resource.resource_id)" />
        </div>
      </template>
    </details>
  </div>
</template>
<script setup>
import { computed, ref } from 'vue'
import { replyOutcomes } from '@/services/replyOutcomes.js'
import ResourcePreviewActions from './resources/ResourcePreviewActions.vue'
import AuthenticatedImage from './AuthenticatedImage.vue'
import InlineChartCard from './InlineChartCard.vue'
const props = defineProps({ message: Object, messages: Array, resources: Array })
defineEmits(['preview'])
const opened = ref(false)
const outcomes = computed(() => replyOutcomes(props.message, props.messages, props.resources || []))
const badge = format => ({ docx: 'Word', xlsx: 'Excel', pptx: 'PPT', html: '报告', qmd: '报告' })[format] || String(format || '文件').toUpperCase()
const iconClass = format => ['xls', 'xlsx', 'csv'].includes(format) ? 'green' : format === 'pdf' ? 'red' : ['ppt', 'pptx'].includes(format) ? 'orange' : 'blue'
const formats = group => [...new Set(group.resources.map(r => r.format).filter(f => f !== 'qmd'))].map(f => f.toUpperCase()).join(' · ')
</script>
<style scoped>
.reply-outcomes { margin-top: 12px; display: grid; gap: 10px; }
.file-card { max-width: 480px; min-width: 0; border: 1px solid #e8eaed; border-radius: 12px; background: white; padding: 14px; }
.file-summary { width: 100%; padding: 0; border: 0; background: none; display: flex; align-items: center; gap: 12px; cursor: pointer; text-align: left; }
.file-icon { flex: 0 0 44px; height: 52px; border-radius: 6px; color: white; display: grid; place-items: center; font-size: 11px; font-weight: 600; }
.blue { background: #377ce1; }.green { background: #24a16e; }.red { background: #e56363; }.orange { background: #e89443; }
.file-copy { min-width: 0; flex: 1; display: grid; gap: 7px; }.file-copy strong { font-size: 14px; color: #222; font-weight: 500; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.file-copy small { color: #9298a1; font-size: 11px; }.chevron { color: #b8bdc4; font-size: 22px; }
summary { color: #818994; cursor: pointer; font-size: 12px; padding: 8px 0; }.outcome-image { width: 100%; height: auto; cursor: zoom-in; }
</style>
