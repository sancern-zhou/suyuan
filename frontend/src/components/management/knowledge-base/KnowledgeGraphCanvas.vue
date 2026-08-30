<template>
  <div ref="root" class="knowledge-graph-canvas" @dblclick="$emit('canvas-click')">
    <div v-if="!nodes.length" class="graph-empty">当前知识库暂无图谱事实</div>
  </div>
</template>

<script setup>
import { Graph } from '@antv/g6'
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  showRelationLabels: { type: Boolean, default: true }
})
const emit = defineEmits(['ready', 'node-click', 'relation-click', 'canvas-click', 'layout-start', 'layout-end'])
const root = ref(null)
let graph = null
let observer = null

function options() {
  const nodeCount = props.nodes.length
  const linkDistance = nodeCount > 700 ? 165 : nodeCount > 250 ? 145 : 120
  const repulsion = nodeCount > 700 ? -420 : nodeCount > 250 ? -340 : -260
  return {
    container: root.value,
    autoFit: 'view',
    data: { nodes: props.nodes, edges: props.edges },
    layout: { type: 'd3-force', preventOverlap: true, nodeSize: 28, link: { distance: linkDistance }, manyBody: { strength: repulsion } },
    node: {
      type: 'circle',
      style: {
        size: datum => Math.min(52, 20 + Math.sqrt(datum.data?.degree || 0) * 6),
        fill: datum => datum.data?.color || '#3996ae',
        stroke: '#fff', lineWidth: 1.5,
        labelText: datum => datum.data?.displayLabel || datum.data?.label || '',
        labelPlacement: 'bottom', labelMaxWidth: 120, labelWordWrap: true, labelFontSize: 11
      }
    },
    edge: {
      type: datum => datum.source === datum.target ? 'loop' : 'quadratic',
      style: {
        stroke: datum => datum.data?.color || '#99add1',
        curveOffset: datum => ((datum.data?.parallelIndex || 0) - ((datum.data?.parallelCount || 1) - 1) / 2) * 22,
        endArrow: true,
        labelText: datum => props.showRelationLabels ? (datum.data?.displayLabel || datum.data?.label || '') : '',
        labelMaxWidth: 90, labelWordWrap: true, labelFontSize: 10,
        labelBackground: true, labelBackgroundFill: '#fff', labelBackgroundOpacity: 0.82
      }
    },
    behaviors: ['drag-element', 'drag-canvas', 'zoom-canvas', 'hover-activate', {
      type: 'click-select', degree: 1, state: 'selected', neighborState: 'active', unselectedState: 'inactive'
    }, { type: 'auto-adapt-label', sortNode: { type: 'degree' }, padding: 4, throttle: 80 }]
  }
}

async function render() {
  if (!root.value) return
  emit('layout-start')
  if (!graph) {
    graph = new Graph(options())
    graph.on('node:click', event => emit('node-click', event.target?.id || event.itemId))
    graph.on('edge:click', event => emit('relation-click', event.target?.id || event.itemId))
    graph.on('canvas:click', () => emit('canvas-click'))
    emit('ready', graph)
  } else {
    graph.setData({ nodes: props.nodes, edges: props.edges })
  }
  await graph.render()
  emit('layout-end')
}

const fitView = () => graph?.fitView?.()
const relayout = async () => { if (graph) { emit('layout-start'); await graph.layout(); emit('layout-end') } }
const focusNode = id => graph?.focusElement?.(String(id), { duration: 400 })
const clearFocus = () => graph?.clearStates?.()
defineExpose({ fitView, relayout, focusNode, clearFocus })

onMounted(async () => {
  await nextTick()
  await render()
  observer = new ResizeObserver(() => graph?.resize?.())
  observer.observe(root.value)
})
watch(() => [props.nodes, props.edges, props.showRelationLabels], render, { deep: true })
onUnmounted(() => {
  observer?.disconnect()
  if (graph) graph.destroy()
  graph = null
})
</script>

<style scoped>
.knowledge-graph-canvas { position: relative; min-height: 560px; height: 68vh; overflow: hidden; background: radial-gradient(circle at center, #fff, #f7f9fc); border: 1px solid #e5e7eb; border-radius: 8px; }
.graph-empty { position: absolute; inset: 0; display: grid; place-items: center; color: #667085; }
</style>
