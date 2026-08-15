<template>
  <section class="stationhouse-dashboard">
    <header class="dashboard-header">
      <div class="station-heading">
        <span class="eyebrow">AI STATION INSPECTION</span>
        <strong>{{ station.station_name || '站房巡检' }}</strong>
        <div class="station-meta">
          <span>站点编号：{{ station.station_code || '—' }}</span>
          <span>唯一编码：{{ station.unique_code || '—' }}</span>
          <span>{{ station.city_name || '' }}{{ station.district_name || '' }}</span>
        </div>
      </div>
      <div class="inspection-result">
        <div class="score-ring" :class="scoreTone">
          <span>{{ scoreDisplay }}</span>
          <small>{{ scoreLabel }}</small>
        </div>
        <div class="result-copy">
          <strong v-if="issueCount">巡检完成，发现 <em>{{ issueCount }}</em> 项问题</strong>
          <strong v-else>{{ clearResultTitle }}</strong>
          <span>{{ updateTime }} · {{ dataSourceLabel }}</span>
        </div>
      </div>
    </header>

    <div class="dashboard-body">
      <section
        class="room-section"
        :style="{ backgroundImage: `linear-gradient(180deg, rgba(4, 38, 82, .28), rgba(2, 22, 50, .68)), url(${roomBackground})` }"
      >
        <div class="section-title">
          <span>站房设备实时状态</span>
          <div class="legend">
            <i class="normal"></i>正常 <i class="error"></i>异常 <i class="offline"></i>离线
          </div>
        </div>
        <div class="room-stage">
          <img :src="roomImage" alt="站房设备场景" />

          <div class="reading pm10" :class="statusClass('PM10')">
            <strong>{{ value('PM10') }}</strong><small>μg/m³</small>
          </div>
          <div class="reading pm25" :class="statusClass('PM2.5')">
            <strong>{{ value('PM2.5') }}</strong><small>μg/m³</small>
          </div>
          <div class="reading pollutant no" :class="statusClass('NO')"><strong>{{ value('NO') }}</strong></div>
          <div class="reading pollutant so2" :class="statusClass('SO2')"><strong>{{ value('SO2') }}</strong></div>
          <div class="reading pollutant o3" :class="statusClass('O3')"><strong>{{ value('O3') }}</strong></div>
          <div class="reading pollutant co" :class="statusClass('CO')"><strong>{{ value('CO') }}</strong></div>

          <div class="bottle-value bottle-so2" :class="statusClass('SO2GasPressAD')">{{ value('SO2GasPressAD') }}</div>
          <div class="bottle-value bottle-no" :class="statusClass('NOxGasPressAD')">{{ value('NOxGasPressAD') }}</div>
          <div class="bottle-value bottle-co" :class="statusClass('COGasPressAD')">{{ value('COGasPressAD') }}</div>
        </div>
        <div class="room-metrics">
          <article v-for="item in roomMetrics" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.detail }}</small>
          </article>
        </div>
      </section>

      <aside class="diagnosis-panel">
        <div class="summary-strip">
          <div><span>已接入参数</span><strong>{{ availableCount }}</strong></div>
          <div><span>异常项</span><strong class="danger">{{ issueCount }}</strong></div>
          <div><span>离线设备</span><strong class="warning">{{ offlineCount }}</strong></div>
        </div>

        <section class="diagnosis-section issue-section">
          <div class="panel-title"><span>异常项与诊断线索</span><b>{{ issueCount }}</b></div>
          <div v-if="issues.length" class="issue-list">
            <article v-for="(issue, index) in issues" :key="`${issue.code || 'issue'}-${index}`">
              <i></i>
              <div><strong>{{ issue.description || issue.code || '巡检异常' }}</strong><span>{{ issue.suggestion || issue.category || '建议进一步核查设备状态' }}</span></div>
            </article>
          </div>
          <div v-else class="all-clear">
            <span>✓</span>
            <div><strong>{{ clearResultTitle }}</strong><small>{{ clearResultDescription }}</small></div>
          </div>
        </section>

        <section class="diagnosis-section environment-section">
          <div class="panel-title"><span>站房动环参数</span><b>{{ environmentAvailable }}/6</b></div>
          <div class="environment-grid">
            <article v-for="item in environmentItems" :key="item.code" :class="statusClass(item.code)">
              <span>{{ item.label }}</span>
              <strong>{{ value(item.code) }} <small>{{ item.unit }}</small></strong>
            </article>
          </div>
        </section>

        <section class="diagnosis-section instrument-section">
          <div class="panel-title"><span>监测仪器状态</span><b>{{ instrumentAvailable }}/6</b></div>
          <div class="instrument-grid">
            <article v-for="item in instruments" :key="item.code" :class="statusClass(item.code)">
              <div class="instrument-icon"><span>{{ item.label }}</span></div>
              <strong>{{ value(item.code) }} <small>{{ item.unit }}</small></strong>
              <span>{{ statusText(item.code) }}</span>
            </article>
          </div>
        </section>

        <div class="source-note">
          <span>数据来源</span>
          <p>江苏自动巡检 QC、站点空气监测及站房动环接口。空值保持“—”，不推断、不补造。</p>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import roomImage from '@/assets/stationhouse/room.png'
import roomBackground from '@/assets/stationhouse/room-bg.jpg'

const props = defineProps({ data: { type: Object, required: true } })

const payload = computed(() => props.data?.data?.stationhouse || {})
const station = computed(() => payload.value.station || props.data?.meta?.station || {})
const values = computed(() => payload.value.values || {})
const issues = computed(() => Array.isArray(payload.value.issues) ? payload.value.issues : [])
const score = computed(() => Number(payload.value.score ?? props.data?.meta?.metrics?.score ?? 100))
const qcSnapshotAvailable = computed(() => payload.value.qc_snapshot_available === true)
const scoreDisplay = computed(() => qcSnapshotAvailable.value ? score.value : '—')
const scoreLabel = computed(() => qcSnapshotAvailable.value ? '巡检评分' : '数据待补')
const issueCount = computed(() => Number(payload.value.issue_count ?? issues.value.length))
const offlineCount = computed(() => Number(payload.value.offline_count || 0))
const availableCount = computed(() => Number(payload.value.available_count || Object.keys(values.value).length))
const scoreTone = computed(() => !qcSnapshotAvailable.value ? 'pending' : (score.value >= 90 ? 'good' : (score.value >= 60 ? 'medium' : 'bad')))
const dataSourceLabel = computed(() => payload.value.environment_fallback ? '多源数据融合' : 'QC实时快照')
const clearResultTitle = computed(() => '巡检完成，未发现异常')
const clearResultDescription = computed(() => qcSnapshotAvailable.value
  ? '设备告警、动环参数和最新监测值均未命中当前巡检规则'
  : '本次巡检已完成，未识别到设备告警或参数异常')
const updateTime = computed(() => {
  const raw = payload.value.updated_at
  if (!raw) return '刚刚更新'
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return String(raw)
  return date.toLocaleString('zh-CN', { hour12: false })
})

const instruments = [
  { code: 'SO2', label: 'SO₂', unit: 'μg/m³' },
  { code: 'NO', label: 'NO', unit: 'μg/m³' },
  { code: 'CO', label: 'CO', unit: 'mg/m³' },
  { code: 'O3', label: 'O₃', unit: 'μg/m³' },
  { code: 'PM10', label: 'PM₁₀', unit: 'μg/m³' },
  { code: 'PM2.5', label: 'PM₂.₅', unit: 'μg/m³' }
]
const instrumentAvailable = computed(() => instruments.filter(item => hasValue(item.code)).length)
const environmentItems = [
  { code: 'StationTemp', label: '站房温度', unit: '℃' },
  { code: 'StationHum', label: '站房湿度', unit: '%' },
  { code: 'PipeTemp', label: '总管温度', unit: '℃' },
  { code: 'PipeHum', label: '总管湿度', unit: '%' },
  { code: 'IA', label: 'A相电流', unit: 'A' },
  { code: 'VA', label: 'A相电压', unit: 'V' }
]
const environmentAvailable = computed(() => environmentItems.filter(item => hasValue(item.code)).length)
const roomMetrics = computed(() => [
  { label: '采样管路', value: `${value('SamplePipeSPress')} Pa`, detail: `温度 ${value('PipeTemp')}℃ · 湿度 ${value('PipeHum')}%` },
  { label: '站房环境', value: `${value('StationTemp')}℃ / ${value('StationHum')}%`, detail: '温度 / 相对湿度' },
  { label: '供电状态', value: `${value('IA')} A / ${value('VA')} V`, detail: 'A相电流 / A相电压' },
  { label: '质控气路', value: `${value('ZeroGasFlow')} / ${value('SpanGasFlow')}`, detail: '零气流量 / 标气流量' }
])

const hasValue = code => {
  const current = values.value[code]
  return Boolean(current && current.value !== undefined && current.value !== null && String(current.value).trim() !== '' && current.value !== '—')
}
const value = code => hasValue(code) ? values.value[code].value : '—'
const statusClass = code => {
  const current = values.value[code]
  if (!current || !hasValue(code)) return 'missing'
  if (Number(current.alarm) === 1) return 'offline'
  if (Number(current.alarm) > 1) return 'error'
  return 'normal'
}
const statusText = code => ({ normal: '运行正常', error: '状态异常', offline: '设备离线', missing: '暂无数据' }[statusClass(code)])
</script>

<style scoped>
.stationhouse-dashboard { min-width: 1020px; overflow: hidden; border: 1px solid #1768ac; border-radius: 10px; background: #031b37; color: #d9efff; box-shadow: inset 0 0 42px rgba(11, 113, 192, .2), 0 8px 22px rgba(8, 40, 76, .16); font-family: "Microsoft YaHei", sans-serif; }
.dashboard-header { display: flex; height: 88px; align-items: center; justify-content: space-between; padding: 0 26px; border-bottom: 1px solid rgba(69, 178, 255, .68); background: linear-gradient(90deg, #063e76, #075fa8 54%, #073d72); box-sizing: border-box; box-shadow: inset 0 -12px 28px rgba(0, 153, 255, .14); }
.station-heading { display: grid; gap: 4px; }.station-heading .eyebrow { color: #5bc7ff; font-size: 10px; letter-spacing: 2px; }.station-heading strong { color: #fff; font-size: 22px; text-shadow: 0 0 12px rgba(71, 190, 255, .55); }.station-meta { display: flex; gap: 18px; color: #a8d7f8; font-size: 11px; }
.inspection-result { display: flex; align-items: center; gap: 16px; }.score-ring { display: grid; width: 62px; height: 62px; place-content: center; border: 3px solid; border-radius: 50%; background: rgba(1, 28, 59, .78); box-shadow: 0 0 0 6px rgba(80, 200, 120, .12), inset 0 0 16px rgba(80, 200, 120, .18); text-align: center; }.score-ring span { font-size: 24px; font-weight: 800; line-height: 25px; }.score-ring small { font-size: 9px; }.score-ring.good { border-color: #37e57b; color: #37e57b; }.score-ring.medium { border-color: #45b6ff; color: #45b6ff; }.score-ring.bad { border-color: #ff694b; color: #ff694b; }.score-ring.pending { border-color: #ffbd39; color: #ffbd39; box-shadow: 0 0 0 6px rgba(255, 189, 57, .1), inset 0 0 16px rgba(255, 189, 57, .12); }.result-copy { display: grid; gap: 8px; }.result-copy strong { color: #fff; font-size: 16px; }.result-copy em { color: #ff704d; font-size: 22px; font-style: normal; }.result-copy span { color: #8ecaf1; font-size: 10px; }
.dashboard-body { display: grid; min-height: 610px; grid-template-columns: minmax(650px, 1.72fr) minmax(350px, .9fr); }
.room-section { position: relative; display: grid; grid-template-rows: 32px minmax(0, 1fr) 72px; padding: 14px 18px 16px; overflow: hidden; border-right: 1px solid #1768ac; background-position: center; background-size: cover; box-sizing: border-box; }.room-section::after { position: absolute; inset: 0; pointer-events: none; background: repeating-linear-gradient(0deg, rgba(102, 202, 255, .025) 0 1px, transparent 1px 4px); content: ""; }
.section-title, .panel-title { position: relative; z-index: 2; display: flex; height: 32px; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(78, 173, 238, .42); color: #e8f7ff; font-size: 13px; font-weight: 700; }.section-title::before, .panel-title::before { width: 3px; height: 14px; margin-right: 8px; background: #1ac8ff; box-shadow: 0 0 9px #1ac8ff; content: ""; }.section-title > span, .panel-title > span { margin-right: auto; }.legend { display: flex; align-items: center; gap: 6px; color: #83b5d8; font-size: 10px; font-weight: 400; }.legend i { width: 7px; height: 7px; margin-left: 8px; border-radius: 50%; }.legend .normal { background: #20df70; box-shadow: 0 0 7px #20df70; }.legend .error { background: #ff4d4f; }.legend .offline { background: #ffb11b; }
.room-stage { position: relative; z-index: 1; width: min(100%, 790px); max-height: 476px; margin: 6px auto 0; align-self: center; aspect-ratio: 1038 / 692; }.room-stage > img { display: block; width: 100%; height: 100%; object-fit: contain; filter: drop-shadow(0 12px 24px rgba(0, 15, 35, .36)); }
.reading { position: absolute; display: flex; align-items: center; justify-content: center; gap: 2px; padding: 1px 2px; overflow: hidden; border: 1px solid rgba(255,255,255,.4); border-radius: 1px; background: rgba(0, 198, 73, .9); box-sizing: border-box; color: #fff; box-shadow: 0 0 8px rgba(0, 235, 104, .3); line-height: 1; white-space: nowrap; }.reading strong { font-size: 10px; }.reading small { font-size: 6px; }.reading.missing { background: rgba(78, 99, 119, .86); box-shadow: none; }.reading.error { background: rgba(226, 53, 46, .92); }.reading.offline { background: rgba(224, 145, 17, .92); }.pm10 { left: 30.5%; top: 54.3%; width: 9.1%; height: 6.1%; }.pm25 { left: 45.2%; top: 54.4%; width: 9.1%; height: 6.1%; }.pollutant { left: 34%; width: 5.9%; height: 4.2%; }.pollutant strong { font-size: 9px; }.no { top: 66.2%; }.so2 { top: 74.8%; }.o3 { top: 81.3%; }.co { top: 87.7%; }
.bottle-value { position: absolute; top: 77.5%; width: 4%; color: #fff; font-size: 8px; text-align: center; text-shadow: 0 0 6px #000; }.bottle-so2 { left: 58.2%; }.bottle-no { left: 62.3%; }.bottle-co { left: 66.3%; }.bottle-value.error { color: #ff5454; }.bottle-value.offline, .bottle-value.missing { color: #ffd05b; }
.room-metrics { position: relative; z-index: 2; display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding-top: 8px; border-top: 1px solid rgba(70, 170, 235, .34); }.room-metrics article { display: grid; min-width: 0; align-content: center; gap: 3px; padding: 6px 9px; border: 1px solid rgba(45, 150, 216, .42); border-left: 3px solid #1edb73; border-radius: 3px; background: rgba(4, 48, 85, .78); }.room-metrics span { color: #6dc9f5; font-size: 8px; }.room-metrics strong { overflow: hidden; color: #fff; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.room-metrics small { overflow: hidden; color: #7ca6c1; font-size: 7px; text-overflow: ellipsis; white-space: nowrap; }
.diagnosis-panel { padding: 14px 16px 16px; background: linear-gradient(180deg, rgba(4, 42, 82, .98), rgba(3, 25, 52, .98)); box-sizing: border-box; }.summary-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }.summary-strip > div { display: grid; min-height: 61px; place-content: center; border: 1px solid rgba(48, 144, 212, .55); border-radius: 4px; background: rgba(11, 62, 105, .68); text-align: center; }.summary-strip span { color: #88b8d9; font-size: 9px; }.summary-strip strong { margin-top: 5px; color: #44baff; font-size: 20px; }.summary-strip .danger { color: #ff5252; }.summary-strip .warning { color: #ffc02e; }
.diagnosis-section { margin-top: 10px; }.panel-title b { min-width: 22px; padding: 2px 6px; border-radius: 10px; background: rgba(20, 159, 231, .22); color: #54c8ff; font-size: 10px; text-align: center; }.issue-section { min-height: 100px; }.issue-list { max-height: 112px; overflow: auto; }.issue-list article { display: flex; align-items: flex-start; gap: 8px; padding: 8px 4px; border-bottom: 1px solid rgba(81, 149, 197, .28); }.issue-list i { width: 6px; height: 6px; margin-top: 4px; flex: none; border-radius: 50%; background: #ff5d50; box-shadow: 0 0 7px #ff5d50; }.issue-list article div { display: grid; gap: 3px; }.issue-list strong { color: #ffd8d2; font-size: 10px; }.issue-list span { color: #85abc6; font-size: 9px; }.all-clear { display: flex; min-height: 62px; align-items: center; justify-content: center; gap: 10px; color: #34dc7a; }.all-clear > span { display: grid; width: 30px; height: 30px; place-content: center; border: 1px solid #34dc7a; border-radius: 50%; box-shadow: 0 0 13px rgba(52, 220, 122, .24); font-size: 17px; }.all-clear div { display: grid; gap: 4px; }.all-clear strong { font-size: 11px; }.all-clear small { max-width: 260px; color: #7da8c4; font-size: 8px; line-height: 13px; }
.environment-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; padding-top: 8px; }.environment-grid article { display: grid; min-height: 42px; align-content: center; gap: 4px; padding: 4px 7px; border: 1px solid rgba(45, 151, 216, .38); border-radius: 3px; background: rgba(8, 57, 96, .7); }.environment-grid span { color: #80b2d2; font-size: 8px; }.environment-grid strong { color: #ecf9ff; font-size: 10px; }.environment-grid small { color: #79a8c7; font-size: 7px; }.environment-grid article.error { border-color: #ff564f; }.environment-grid article.offline, .environment-grid article.missing { opacity: .55; }
.instrument-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; padding-top: 8px; }.instrument-grid article { display: grid; min-height: 72px; place-items: center; align-content: center; gap: 3px; border: 1px solid rgba(45, 151, 216, .46); border-radius: 4px; background: linear-gradient(180deg, rgba(14, 82, 128, .6), rgba(7, 48, 84, .72)); }.instrument-icon { display: grid; width: 44px; height: 22px; place-content: center; border: 2px solid #75dfbd; background: linear-gradient(135deg, #d8ffff, #9ee6f0); box-shadow: 0 0 10px rgba(93, 225, 208, .28); color: #0877b1; font-size: 10px; font-weight: 800; }.instrument-grid strong { color: #fff; font-size: 10px; }.instrument-grid strong small { color: #8bb8d5; font-size: 6px; }.instrument-grid article > span { color: #29dc77; font-size: 7px; }.instrument-grid article.error { border-color: #ff564f; }.instrument-grid article.error > span { color: #ff655f; }.instrument-grid article.offline, .instrument-grid article.missing { opacity: .58; }.instrument-grid article.offline > span, .instrument-grid article.missing > span { color: #ffc24a; }
.source-note { margin-top: 10px; padding: 7px 9px; border: 1px solid rgba(43, 132, 191, .34); background: rgba(4, 39, 72, .72); }.source-note span { color: #4ec7ff; font-size: 8px; font-weight: 700; }.source-note p { margin: 3px 0 0; color: #78a4c1; font-size: 7px; line-height: 12px; }
</style>
