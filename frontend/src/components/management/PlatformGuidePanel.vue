<template>
  <div class="management-panel platform-guide-panel">
    <div class="panel-header">
      <h3>平台使用说明</h3>
      <button class="panel-btn" type="button" @click="$emit('close')">关闭</button>
    </div>

    <div class="guide-body">
      <section v-if="usageModes.length" class="guide-section">
        <h4 class="guide-title">如何选择使用模式</h4>
        <div class="mode-grid">
          <div v-for="mode in usageModes" :key="mode.name" class="mode-card">
            <p class="mode-name">{{ mode.name }}</p>
            <p class="mode-desc">{{ mode.desc }}</p>
            <p class="mode-example">"{{ mode.example }}"</p>
          </div>
        </div>
        <p v-if="modeMotto" class="mode-motto">{{ modeMotto }}</p>
      </section>

      <section v-if="dataSourceGroups.length" class="guide-section">
        <h4 class="guide-title">数据接入情况</h4>
        <p class="guide-subtitle">
          以下为平台当前已接入的数据类别、实际可用时间范围与同步频次。平台接口类数据在提问时实时读取；
          本地同步库每 5 分钟一次高频增量、每日凌晨 2:30 全量对齐，查询结果以最近一次同步为准。
        </p>

        <div
          v-for="group in dataSourceGroups"
          :key="group.title"
          class="data-group"
        >
          <h5 class="data-group-title">{{ group.title }}</h5>
          <div class="data-table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th style="width: 20%">数据类别</th>
                  <th style="width: 8%">粒度</th>
                  <th style="width: 17%">实际可用时间范围</th>
                  <th style="width: 17%">更新频次与延迟</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in group.rows" :key="row.name">
                  <td class="cell-name">{{ row.name }}</td>
                  <td>{{ row.granularity }}</td>
                  <td class="cell-range">{{ row.range }}</td>
                  <td class="cell-sync">{{ row.sync }}</td>
                  <td class="cell-desc">{{ row.desc }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <p v-if="!usageModes.length && !dataSourceGroups.length" class="guide-empty">
        共享版本不内置使用说明，内容由各项目分支按实际模式与数据接入情况维护。
      </p>
    </div>
  </div>
</template>

<script setup>
defineEmits(['close'])

// 江苏分支按实际模式与数据接入维护本面板；共享段 main 仅保留空骨架（486c74f1）。
const usageModes = [
  {
    name: '苏环智管（首页）',
    desc: '平台首页值班入口，协调各专业智能体完成取证、研判与任务闭环。',
    example: '汇总今天江苏全省的运维态势，重点说明异常站点'
  },
  {
    name: '智能工单审核',
    desc: '按工单号、节点、状态等查询江苏故障工单与例行工单，核对处置记录，辅助人工复核并出具审核报告。',
    example: '查一下上周待审核的故障工单，按运维单位汇总问题'
  },
  {
    name: '运维问数生图',
    desc: '自然语言查询江苏城市、区县、站点监测与气象数据，完成统计分析并生成图表。',
    example: '查南京 9 月 PM2.5 日均浓度并画趋势图'
  },
  {
    name: '知识问答',
    desc: '检索授权知识库与上传材料，按需联网补充，回答附原文依据与来源区分。',
    example: '运维规程对站点断数处置的要求是什么？'
  },
  {
    name: '站点智能巡检',
    desc: '汇总全网巡检与告警线索，输出优先巡检对象和待人工确认的处置建议。',
    example: '汇总今天全省异常站点，给出巡检重点'
  },
  {
    name: '运维分析报告',
    desc: '编排工单、告警、巡检、质控等数据域子智能体，默认出具日常监管、风险研判等正式报告文档（未指明形式时按报告交付，不默认生成 Excel 底稿），耗时一般 10 分钟以上。',
    example: '生成本月运维分析报告：工单、告警、巡检、质控与率值'
  },
  {
    name: '智能设备反控',
    desc: '查询授权站点质控设备与空调状态，经人工逐次确认后执行受限反控指令。',
    example: '查看××站空调当前状态'
  },
  {
    name: '站点故障诊断',
    desc: '汇集告警、监测、巡检、工单与质控证据，研判单站故障根因并给出处置方案与工单草案。',
    example: '××站 PM10 昨天为什么断数？给出诊断与处置建议'
  },
  {
    name: '外界环境识别',
    desc: '核验雾炮喷淋、人员进出等外界环境影响事件的证据，反馈归档并跟进处置。',
    example: '查看××站最近的外界环境事件并核验证据'
  },
  {
    name: '仪器故障识别',
    desc: '核验仪器断数、供电、数采与站房故障事件的证据，反馈归档并跟进维修。',
    example: '××站仪器故障事件的证据链完整吗？'
  }
]

const modeMotto =
  '选择口诀：查态势 → 问苏环智管　｜　要审核 → 智能工单审核　｜　要数字 → 运维问数生图　｜　问依据 → 知识问答　｜　查根因 → 站点故障诊断'

const dataSourceGroups = [
  {
    title: '空气质量监测数据（省运维平台接口，实时查询）',
    rows: [
      {
        name: '江苏城市数据（13 个设区市）',
        granularity: '1 小时、1 日',
        range: '平台在线数据，历史深度以平台为准',
        sync: '接口实时读取',
        desc: '城市 AQI、首要污染物、6 项污染物浓度与城市排名'
      },
      {
        name: '江苏区县数据',
        granularity: '1 小时、1 日',
        range: '平台在线数据，历史深度以平台为准',
        sync: '接口实时读取',
        desc: '全省区县污染物浓度与排名查询'
      },
      {
        name: '站点监测数据（全省 101 个省控站）',
        granularity: '5 分钟、1 小时、1 日',
        range: '平台在线数据，历史深度以平台为准',
        sync: '接口实时读取；审核口径待平台审核完成，滞后于原始数据',
        desc: '6 项污染物浓度；区分原始/审核、工况/标况四种口径；站点异常告警判定的主要输入'
      },
      {
        name: '平台统计指标',
        granularity: '—',
        range: '平台在线数据',
        sync: '接口实时读取',
        desc: '城市/区县/站点排名、同比、达标率、超标天数、臭氧排名等统计口径'
      },
      {
        name: '率值指标（获取率/有效率/传输率等）',
        granularity: '日',
        range: '平台在线数据',
        sync: '平台按日统计产出，接口实时可查',
        desc: '一律以平台统计接口为唯一口径，平台不做自算；含 13 市综合获取率与联网率'
      }
    ]
  },
  {
    title: '运维专题数据（本地同步库，2026-07-01 起）',
    rows: [
      {
        name: '故障工单与例行工单',
        granularity: '单',
        range: '2026-07-01 至今',
        sync: '工单宽表每 5 分钟同步；工单详情接口实时读取',
        desc: '工单台账、处置流转、故障项与检查项详单；故障工单仅 Fault 类，例行工单走平台审核接口'
      },
      {
        name: '站点告警日志',
        granularity: '条',
        range: '平台历史全量，持续同步',
        sync: '每 5 分钟同步',
        desc: '101 个省控站按站点分片全覆盖，含电话记录'
      },
      {
        name: '智能事件中心',
        granularity: '事件',
        range: '2026-06-01 起自动汇聚',
        sync: '告警每 5 分钟轮询发现，异常扫描约每小时一轮；证据包生成有分钟级滞后',
        desc: '告警/异常事件线索与证据包，支撑外界环境识别与仪器故障识别；只读结构化查询'
      },
      {
        name: '巡检记录',
        granularity: '任务项',
        range: '2026-07-01 至今',
        sync: '每 5 分钟同步',
        desc: '自动巡检任务项数、超期（周期结束未完成）、周期类型/人员/站点分布'
      },
      {
        name: '质控数据（约 23 个质控试点站）',
        granularity: '任务/条',
        range: '2026 年至今（按年分表）',
        sync: '执行明细每 5 分钟同步；安排与补测每日 02:30 重建；质控曲线接口实时读取',
        desc: '质控执行、质控安排与过期任务、补测闭环、运行日志与质控监测曲线；口径为省控 101 站名录，结论不得外推全省'
      },
      {
        name: '设备与停电',
        granularity: '事件/台账',
        range: '2026-07-01 至今；站房动环供电小时自 2026-10 起',
        sync: '台账/参数/生命周期、停电报备每日 02:30 重建；动环供电小时每日 02:30 增量',
        desc: '设备生命周期事件、参数阈值与台账、停电报备单及时长；动环小时表含温湿度等 11 项编码，每年 1 月切换年份表'
      },
      {
        name: '站点与人员',
        granularity: '台账/条',
        range: '2026-07-01 至今（签到按平台数据）',
        sync: '台账与健康快照每 5 分钟同步；站点日概况每日 02:30 重建；签到与轨迹接口实时读取',
        desc: '站点台账与健康快照、站点日概况、运维单位与责任站点关系、到站签到记录与签到轨迹；签到源数据较稀疏，以实际记录数为准'
      }
    ]
  },
  {
    title: '气象数据',
    rows: [
      {
        name: '江苏逐小时气象实况（13 市+区县）',
        granularity: '1 小时',
        range: '持续积累',
        sync: '每小时第 12 分钟自动抓取上一小时实况',
        desc: '中央气象台按城市/区县自动抓取：气温、湿度、风向/风速、气压、降水；直接用名称查询，无需气象站编号'
      },
      {
        name: '历史气象库',
        granularity: '1 小时',
        range: '按库内覆盖为准',
        sync: '实况抓取每小时入库；再分析数据为既有数据集',
        desc: '江苏地面观测与区域再分析数据，用于历史气象查询与污染过程对照'
      },
      {
        name: '天气预报',
        granularity: '1 日',
        range: '未来数日（外部服务）',
        sync: '提问时实时请求外部服务',
        desc: '当前天气与未来预报，依赖外部天气服务，条件可用'
      }
    ]
  },
  {
    title: '知识与外部资料',
    rows: [
      {
        name: '授权知识库',
        granularity: '—',
        range: '持续更新',
        sync: '人工维护更新',
        desc: '江苏运维规程、标准制度、设备资料与业务规则；知识问答、故障诊断与报告口径的依据来源'
      },
      {
        name: '公开网页搜索与抓取',
        granularity: '—',
        range: '按需',
        sync: '提问时实时检索',
        desc: '仅在知识库证据不足或问题需要最新公开信息时联网补充，回答中标明网络来源'
      }
    ]
  }
]
</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow-y: auto;
  padding: 20px;
  background: white;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--border-2);
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1);
}

.panel-btn {
  padding: 6px 12px;
  border: 1px solid var(--color-primary);
  background: white;
  color: var(--color-primary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.panel-btn:hover {
  background: var(--color-primary);
  color: white;
}

.guide-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.guide-section {
  margin-bottom: 8px;
}

.guide-title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
}

.guide-subtitle {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--text-2);
}

.guide-empty {
  margin: 40px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-2);
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.mode-card {
  padding: 12px 14px;
  border: 1px solid var(--border-2);
  border-radius: 8px;
  background: var(--bg-1, #fafafa);
}

.mode-name {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-primary);
}

.mode-desc {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-1);
}

.mode-example {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-2);
}

.mode-motto {
  margin: 12px 0 0;
  padding: 10px 14px;
  border-radius: 6px;
  background: rgba(64, 128, 255, 0.08);
  font-size: 13px;
  color: var(--text-1);
}

.data-group {
  margin-bottom: 20px;
}

.data-group-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
}

.data-table-wrapper {
  overflow-x: auto;
  border: 1px solid var(--border-2);
  border-radius: 8px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 9px 12px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border-2);
}

.data-table thead th {
  position: sticky;
  top: 0;
  background: var(--bg-1, #f7f8fa);
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.data-table tbody tr:nth-child(even) {
  background: rgba(0, 0, 0, 0.015);
}

.cell-name {
  font-weight: 500;
  color: var(--text-1);
}

.cell-range {
  white-space: nowrap;
  color: var(--text-1);
}

.cell-sync {
  color: var(--text-1);
  line-height: 1.5;
}

.cell-desc {
  color: var(--text-2);
  line-height: 1.5;
}
</style>
