import { createApp, ref, h } from 'vue'
import ChartPanel from './components/visualization/ChartPanel.vue'

// Native clients fetch authenticated resources themselves and deliver JSON.
// This page accepts data only; credentials are never placed in its URL.
const spec = ref(null)
window.renderSuyuanChart = value => { spec.value = value }
createApp({ setup: () => () => spec.value
  ? h(ChartPanel, { data: spec.value, customHeight: `${Math.max(300, window.innerHeight - 8)}px` })
  : h('p', '正在加载图表…') }).mount('#app')
document.body.style.cssText = 'margin:0;padding:4px;box-sizing:border-box;background:white;font-family:system-ui'
window.suyuanChartReady = true
