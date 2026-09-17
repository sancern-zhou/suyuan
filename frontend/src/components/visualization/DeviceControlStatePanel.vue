<template>
  <section class="device-control-dashboard">
    <header class="dashboard-header">
      <div class="station-heading">
        <span class="eyebrow">AI DEVICE CONTROL</span>
        <strong>{{ stationName }} · 设备反控状态</strong>
        <div class="station-meta">
          <span>站点编号：{{ station.station_code || '—' }}</span>
          <span>唯一编码：{{ station.station_id || '—' }}</span>
          <span>{{ station.city_name || '' }}{{ station.district_name || '' }}</span>
        </div>
      </div>
      <div class="query-result">
        <div v-if="simulated" class="demo-badge">演示数据</div>
        <div class="online-badge" :class="snapshotAvailable ? 'online' : 'offline'">
          <i></i>
          <span>{{ snapshotAvailable ? '状态在线' : '状态未返回' }}</span>
        </div>
        <div class="result-copy">
          <strong>{{ headline }}</strong>
          <span>{{ updateTime }} · 江苏 QC 反控接口 GetQCStateInfo</span>
        </div>
      </div>
    </header>

    <div class="dashboard-body">
      <section class="device-section">
        <div class="section-title">
          <span>质控设备与阀门控制状态</span>
          <div class="legend">
            <i class="on"></i>开启 <i class="off"></i>关闭 <i class="unknown"></i>状态未提供
          </div>
        </div>
        <div class="device-grid">
          <article v-for="item in devices" :key="item.key" class="device-card" :class="statusClass(item.status)">
            <div class="device-figure">
              <img class="device-icon" :src="iconFor(item.icon)" :alt="item.name" />
            </div>
            <div class="device-info">
              <header>
                <strong>{{ item.name }}</strong>
                <span class="device-kind">{{ item.kind }}</span>
              </header>
              <div class="device-state">
                <img
                  v-if="item.icon"
                  class="switch-icon"
                  :src="item.status === '关闭' ? switchOff : switchOn"
                  :class="{ dim: !item.status }"
                  alt=""
                />
                <span class="state-text">{{ item.status || '状态未提供' }}</span>
                <small v-if="item.state_key">接口字段：{{ item.state_key }}</small>
              </div>
              <div class="action-row">
                <span v-for="action in item.allowed" :key="`a-${action}`" class="action allowed">✓ {{ action }}</span>
                <span v-for="action in item.blocked" :key="`b-${action}`" class="action blocked">⏳ {{ action }}</span>
              </div>
              <p class="device-note">{{ item.note }}</p>
            </div>
          </article>
        </div>
        <div class="precondition-note">
          <span>前置说明</span>
          <p>设备状态与开关量取自平台质控反控接口（与原平台远程反控页面同源字段）；所有反控指令均来自审核后的固定指令集，执行前必须生成待确认指令并经用户在对话中明确确认。平台受理成功不代表设备已生效，执行后系统自动回读状态复核。</p>
        </div>
      </section>

      <aside class="snapshot-panel">
        <div class="panel-title"><span>关键状态快照</span><b>{{ snapshot.length }}</b></div>
        <div v-if="snapshot.length" class="snapshot-list">
          <article v-for="(row, index) in snapshot" :key="`${row.label}-${index}`">
            <span>{{ row.label }}</span>
            <strong>{{ row.value }}</strong>
          </article>
        </div>
        <div v-else class="snapshot-empty">
          <span>—</span>
          <div><strong>暂无状态数据</strong><small>反控服务未返回快照内容；空值保持“—”，不推断、不补造。</small></div>
        </div>
        <div class="source-note">
          <span>数据来源</span>
          <p v-if="simulated">演示模式（JIANGSU_DEVICE_CONTROL_SIMULATION）：当前设备状态为预设演示数据，非平台真实状态；开关类指令作用于模拟数据，用于展示完整质控流程。</p>
          <p v-else>江苏 QC 反控服务实时状态接口。面板仅做状态展示与前置条件标注，不直接执行任何设备控制。</p>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import iconSo2 from '@/assets/devicecontrol/so2.png'
import iconNo from '@/assets/devicecontrol/no.png'
import iconCo from '@/assets/devicecontrol/co.png'
import iconO3 from '@/assets/devicecontrol/o3.png'
import iconAirGenerator from '@/assets/devicecontrol/air-generator.png'
import iconCalibrator from '@/assets/devicecontrol/dynamic-calibrator.png'
import iconAirConditioner from '@/assets/devicecontrol/air-conditioner.png'
import switchOn from '@/assets/devicecontrol/switch-on.png'
import switchOff from '@/assets/devicecontrol/switch-off.png'

const ICONS = {
  so2: iconSo2,
  no: iconNo,
  co: iconCo,
  o3: iconO3,
  'air-generator': iconAirGenerator,
  'dynamic-calibrator': iconCalibrator,
  'air-conditioner': iconAirConditioner,
}

const props = defineProps({ data: { type: Object, required: true } })

const payload = computed(() => props.data?.data?.device_control || {})
const station = computed(() => payload.value.station || props.data?.meta?.station || {})
const stationName = computed(() => station.value.station_name || station.value.station_id || '站点')
const devices = computed(() => (Array.isArray(payload.value.devices) ? payload.value.devices : []))
const snapshot = computed(() => (Array.isArray(payload.value.snapshot) ? payload.value.snapshot : []))
const snapshotAvailable = computed(() => snapshot.value.length > 0)
const simulated = computed(() => payload.value.simulated === true || props.data?.meta?.simulated === true)
const knownStates = computed(() => devices.value.filter(item => item.status).length)
const headline = computed(() => {
  if (!snapshotAvailable.value) return '状态读取完成，但反控服务未返回设备状态'
  return `状态读取完成，已回读 ${knownStates.value}/${devices.value.length} 项设备开关状态`
})
const updateTime = computed(() => {
  const raw = payload.value.updated_at
  if (!raw) return '刚刚更新'
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return String(raw)
  return date.toLocaleString('zh-CN', { hour12: false })
})

const iconFor = name => ICONS[name] || null
const statusClass = status => {
  if (!status) return 'unknown'
  if (status === '关闭') return 'off'
  return 'on'
}
</script>

<style scoped>
.device-control-dashboard { min-width: 920px; overflow: hidden; border: 1px solid #1768ac; border-radius: 10px; background: #031b37; color: #d9efff; box-shadow: inset 0 0 42px rgba(11, 113, 192, .2), 0 8px 22px rgba(8, 40, 76, .16); font-family: "Microsoft YaHei", sans-serif; }
.dashboard-header { display: flex; min-height: 88px; align-items: center; justify-content: space-between; padding: 12px 26px; border-bottom: 1px solid rgba(69, 178, 255, .68); background: linear-gradient(90deg, #063e76, #075fa8 54%, #073d72); box-sizing: border-box; box-shadow: inset 0 -12px 28px rgba(0, 153, 255, .14); }
.station-heading { display: grid; gap: 4px; }
.station-heading .eyebrow { color: #5bc7ff; font-size: 10px; letter-spacing: 2px; }
.station-heading strong { color: #fff; font-size: 21px; text-shadow: 0 0 12px rgba(71, 190, 255, .55); }
.station-meta { display: flex; gap: 18px; color: #a8d7f8; font-size: 11px; }
.query-result { display: flex; align-items: center; gap: 16px; }
.demo-badge { padding: 6px 12px; border: 1px solid rgba(255, 189, 57, .75); border-radius: 999px; background: rgba(255, 189, 57, .14); color: #ffd479; font-size: 12px; letter-spacing: 1px; }
.online-badge { display: inline-flex; align-items: center; gap: 7px; padding: 8px 14px; border: 1px solid; border-radius: 999px; font-size: 12px; }
.online-badge i { width: 8px; height: 8px; border-radius: 50%; }
.online-badge.online { border-color: rgba(55, 229, 123, .7); color: #37e57b; background: rgba(55, 229, 123, .08); }
.online-badge.online i { background: #37e57b; box-shadow: 0 0 8px #37e57b; }
.online-badge.offline { border-color: rgba(255, 189, 57, .7); color: #ffbd39; background: rgba(255, 189, 57, .08); }
.online-badge.offline i { background: #ffbd39; box-shadow: 0 0 8px #ffbd39; }
.result-copy { display: grid; gap: 6px; }
.result-copy strong { color: #fff; font-size: 15px; }
.result-copy span { color: #8ecaf1; font-size: 10px; }
.dashboard-body { display: grid; grid-template-columns: minmax(560px, 1.5fr) minmax(320px, 1fr); }
.device-section { padding: 14px 18px 16px; border-right: 1px solid #1768ac; box-sizing: border-box; }
.section-title, .panel-title { display: flex; height: 32px; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(78, 173, 238, .42); color: #e8f7ff; font-size: 13px; font-weight: 700; }
.section-title::before, .panel-title::before { width: 3px; height: 14px; margin-right: 8px; background: #1ac8ff; box-shadow: 0 0 9px #1ac8ff; content: ""; }
.section-title > span, .panel-title > span { margin-right: auto; }
.legend { display: flex; align-items: center; gap: 6px; color: #83b5d8; font-size: 10px; font-weight: 400; }
.legend i { width: 7px; height: 7px; margin-left: 8px; border-radius: 50%; }
.legend .on { background: #20df70; box-shadow: 0 0 7px #20df70; }
.legend .off { background: #7c93a8; }
.legend .unknown { background: #ffb11b; }
.device-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; padding-top: 12px; }
.device-card { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 12px; padding: 12px; border: 1px solid rgba(45, 150, 216, .42); border-left: 3px solid #7c93a8; border-radius: 4px; background: linear-gradient(135deg, rgba(5, 52, 92, .86), rgba(4, 38, 72, .82)); }
.device-card.on { border-left-color: #20df70; }
.device-card.off { border-left-color: #7c93a8; }
.device-card.unknown { border-left-color: #ffb11b; }
.device-figure { display: grid; height: 76px; place-items: center; border: 1px solid rgba(45, 151, 216, .4); border-radius: 4px; background: radial-gradient(circle at 50% 45%, rgba(24, 118, 180, .38), rgba(3, 30, 58, .9)); }
.device-icon { max-width: 86%; max-height: 62px; object-fit: contain; filter: drop-shadow(0 4px 10px rgba(0, 20, 45, .5)); }
.device-card.unknown .device-icon { opacity: .78; }
.device-info { display: grid; min-width: 0; gap: 6px; }
.device-info header { display: flex; align-items: baseline; gap: 8px; }
.device-info strong { color: #fff; font-size: 14px; }
.device-kind { padding: 1px 6px; border: 1px solid rgba(84, 200, 255, .5); border-radius: 3px; color: #54c8ff; font-size: 9px; }
.device-state { display: flex; align-items: center; gap: 8px; }
.switch-icon { width: 26px; height: 26px; object-fit: contain; }
.switch-icon.dim { opacity: .35; filter: grayscale(1); }
.state-text { color: #b7d8ef; font-size: 12px; font-weight: 700; }
.device-card.on .state-text { color: #46e88a; }
.device-card.unknown .state-text { color: #ffc86b; }
.device-state small { color: #6f9cbc; font-size: 9px; }
.action-row { display: flex; flex-wrap: wrap; gap: 6px; }
.action { padding: 2px 8px; border-radius: 3px; font-size: 10px; }
.action.allowed { border: 1px solid rgba(32, 223, 112, .55); color: #35e07c; background: rgba(32, 223, 112, .08); }
.action.blocked { border: 1px solid rgba(255, 177, 27, .5); color: #ffc86b; background: rgba(255, 177, 27, .07); }
.device-note { margin: 0; color: #7ca6c1; font-size: 9px; line-height: 14px; }
.precondition-note { margin-top: 12px; padding: 8px 10px; border: 1px solid rgba(43, 132, 191, .34); background: rgba(4, 39, 72, .72); }
.precondition-note span { color: #4ec7ff; font-size: 9px; font-weight: 700; }
.precondition-note p { margin: 4px 0 0; color: #78a4c1; font-size: 9px; line-height: 15px; }
.snapshot-panel { padding: 14px 16px 16px; background: linear-gradient(180deg, rgba(4, 42, 82, .98), rgba(3, 25, 52, .98)); box-sizing: border-box; }
.snapshot-list { max-height: 420px; overflow: auto; }
.snapshot-list article { display: grid; gap: 3px; padding: 7px 4px; border-bottom: 1px solid rgba(81, 149, 197, .28); }
.snapshot-list span { color: #6dc9f5; font-size: 9px; word-break: break-all; }
.snapshot-list strong { color: #ecf9ff; font-size: 12px; word-break: break-all; }
.snapshot-empty { display: flex; min-height: 96px; align-items: center; justify-content: center; gap: 10px; color: #ffc24a; }
.snapshot-empty > span { display: grid; width: 30px; height: 30px; place-content: center; border: 1px solid #ffc24a; border-radius: 50%; font-size: 15px; }
.snapshot-empty div { display: grid; gap: 4px; }
.snapshot-empty strong { color: #ffd8a8; font-size: 11px; }
.snapshot-empty small { max-width: 240px; color: #7da8c4; font-size: 8px; line-height: 13px; }
.source-note { margin-top: 10px; padding: 7px 9px; border: 1px solid rgba(43, 132, 191, .34); background: rgba(4, 39, 72, .72); }
.source-note span { color: #4ec7ff; font-size: 8px; font-weight: 700; }
.source-note p { margin: 3px 0 0; color: #78a4c1; font-size: 8px; line-height: 13px; }
</style>
