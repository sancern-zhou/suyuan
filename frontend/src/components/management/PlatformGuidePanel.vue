<template>
  <div class="management-panel platform-guide-panel">
    <div class="panel-header">
      <h3>平台使用说明</h3>
      <button class="panel-btn" type="button" @click="$emit('close')">关闭</button>
    </div>

    <div class="guide-body">
      <section class="guide-section">
        <h4 class="guide-title">如何选择使用模式</h4>
        <div class="mode-grid">
          <div v-for="mode in usageModes" :key="mode.name" class="mode-card">
            <p class="mode-name">{{ mode.name }}</p>
            <p class="mode-desc">{{ mode.desc }}</p>
            <p class="mode-example">"{{ mode.example }}"</p>
          </div>
        </div>
        <p class="mode-motto">
          选择口诀：要数字 → 问数生图　｜　问依据 → 知识问答　｜　查原因 → 专家分析　｜　要交付 → 报告生成
        </p>
      </section>

      <section class="guide-section">
        <h4 class="guide-title">数据接入情况</h4>
        <p class="guide-subtitle">以下为平台当前已接入的数据类别与实际可用时间范围，可直接在对话中查询使用。</p>

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
                  <th style="width: 24%">数据类别</th>
                  <th style="width: 10%">粒度</th>
                  <th style="width: 18%">实际可用时间范围</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in group.rows" :key="row.name">
                  <td class="cell-name">{{ row.name }}</td>
                  <td>{{ row.granularity }}</td>
                  <td class="cell-range">{{ row.range }}</td>
                  <td class="cell-desc">{{ row.desc }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
defineEmits(['close'])

const usageModes = [
  {
    name: '问数生图',
    desc: '自然语言查数据，可自动绘制趋势、对比等图表。',
    example: '查 9 月 1—7 日 PM2.5 日均值并画趋势图'
  },
  {
    name: '知识问答',
    desc: '检索政策文件与技术规范，业务解读可追溯。',
    example: '环境空气质量新旧标准的差别？'
  },
  {
    name: '专家分析',
    desc: '综合气象、站点、排放清单等多领域研判成因。',
    example: '昨晚 PM2.5 抬升是局地还是区域输送？'
  },
  {
    name: '报告生成',
    desc: '自主规划任务、调度其他模式，产出正式文档，耗时一般 10 分钟以上。',
    example: '分析 11—12 月气象条件与污染物相关性'
  }
]

const dataSourceGroups = [
  {
    title: '空气质量监测数据',
    rows: [
      {
        name: '许昌市空气质量小时（中大平台）',
        granularity: '1 小时',
        range: '2022-01-01 至今',
        desc: '城市 AQI、首要污染物、6 项污染物浓度；时间跨度最长，适合长期趋势'
      },
      {
        name: '许昌市空气质量日（中大平台）',
        granularity: '1 日',
        range: '2022-01-01 至今',
        desc: '城市日均浓度、AQI、达标情况；适合年度/季度对比'
      },
      {
        name: '许昌市国控站 5 分钟（中大平台）',
        granularity: '5 分钟',
        range: '2026-08-26 至今',
        desc: 'PM₁₀、SO₂、NO₂、CO、O₃、NOₓ；站点快速告警的主要输入'
      },
      {
        name: '许昌市国控站小时（中大平台）',
        granularity: '1 小时',
        range: '2026-01-01 至今',
        desc: '6 个国控站逐小时浓度；PM₂.₅ 告警判定使用该源'
      },
      {
        name: '许昌市国控站日（中大平台）',
        granularity: '1 日',
        range: '2026-01-01 至今',
        desc: '国控站日数据，发布比小时数据晚约 1 天'
      },
      {
        name: '乡镇站小时',
        granularity: '1 小时',
        range: '2026-01-01 至今',
        desc: '76 个乡镇/街道站；用于国控点的污染趋势分析（受接口限制部分时间数据还有缺失，目前在逐步回补）'
      },
      {
        name: '乡镇站日',
        granularity: '1 日',
        range: '2026-01-01 至今',
        desc: '76 个乡镇/街道站；用于国控点的污染趋势分析'
      },
      {
        name: '全省城市数据（发布数据）',
        granularity: '小时、日',
        range: '2026-10-10 至今',
        desc: '全省 18 个城市的小时和日数据及日排名查询；城市月/年累计官方统计见"河南省环境空气质量月报"'
      },
      {
        name: '全省区县数据（发布数据）',
        granularity: '小时、日',
        range: '2026-10-10 至今',
        desc: '全省 190 个区县的小时和日数据及排名查询'
      },
      {
        name: '许昌市月度报表（中大平台）',
        granularity: '月',
        range: '2021年7月至今',
        desc: '城市污染物浓度均值、评价用百分位浓度、分指数与综合指数、空气质量等级分布、总体天数与达标情况、浓度极值、单项达标统计、各污染物超标与污染级别天数、分污染物有效天数与超标率、超标城市统计（区域对比用）、超标强度、单项/唯一超标天数、首要污染物统计等指标查询，支持新旧标准对比'
      },
      {
        name: '许昌市年度报表（中大平台）',
        granularity: '年',
        range: '2021年至今',
        desc: '年度空气质量综合报表查询'
      },
      {
        name: '许昌市 PM2.5 年均值（中大平台）',
        granularity: '年',
        range: '2021年至今',
        desc: '该年 PM2.5 实际统计年均浓度（μg/m³）'
      },
      {
        name: '许昌市 10 县市区官方月报统计（省/国家平台月报）',
        granularity: '月、累计',
        range: '2020-01 ~ 2026-09',
        desc: '许昌市及魏都区、开发区、东城区、示范区、建安区、鄢陵县、襄城县、禹州市、长葛市的官方月度与 1-N 月累计统计（剔除沙尘）：PM2.5、PM10、SO2、NO2、CO-95、O3-8H-90、优良天数、重污染天数（2023 年起）、综合指数；官方发布值，非逐日明细聚合，适合县域长期对比与年度总结'
      },
      {
        name: '河南省环境空气质量月报（官方月报统计）',
        granularity: '月、累计',
        range: '2025-12 起（逐期发布）',
        desc: '全省及 19 个省辖市（区）（含济源示范区、郑州航空港区）、88 个省辖市所辖区、101 个县（市）的官方月度与 1-N 月累计统计及官方同比：PM2.5、PM10、O3、优良天数、重度及以上污染天数、综合指数；城市月度/累计统计的官方口径，可用于许昌在全省的位次与横向对比'
      },
      {
        name: '许昌市年度目标与实际（官方考核定版）',
        granularity: '年',
        range: '2015 ~ 2026',
        desc: '上级下达的年度目标值（PM10、PM2.5、优良天、重污染天，2026 年为在途目标）与国家网口径实际完成值：PM2.5、PM10、SO2、NO2、CO、优良天、重污染天（剔沙尘）、臭氧超标天；年度目标值的唯一来源，年度考核与完成情况问题优先用此数据'
      },
      {
        name: '许昌市 10 县市区年度目标与实际（考核定版）',
        granularity: '年',
        range: '2020 ~ 2025',
        desc: '市本级及 9 个县（市、区）的年度目标、实际值与完成判定（剔除沙尘考核口径）：PM10、PM2.5、优良天、重污染天；重污染天与月报口径在 2023 年差 3—4 天（沙尘天），年度考核以本表为准；2020 年仅重污染天'
      },
      {
        name: '河南省 18 地市年度目标完成情况（省考核）',
        granularity: '年',
        range: '2021 ~ 2025',
        desc: '全省 18 个地市（含济源）的省考核口径目标完成情况：PM10、PM2.5、优良天、重污染天目标与实际、完成判定，2022—2023 年含 5—9 月臭氧超标天数；适合许昌在全省的年度考核横向比较；2025 年省表未定稿，仅目标与判定可用'
      },
      {
        name: '168 城市全国排名（生态环境部）',
        granularity: '月、累计',
        range: '2026-01 ~ 2026-07',
        desc: '全国 168 个重点城市的综合指数与 PM2.5 浓度及排名（倒序，1=最差），当月与 1-N 月累计；仅用于全国排名与城市横向对比，浓度绝对值以本地口径为准'
      }
    ]
  },
  {
    title: '气象与空气质量预报数据',
    rows: [
      {
        name: '许昌气象实况',
        granularity: '1 小时',
        range: '2024-12-31 至今',
        desc: '温度、湿度、风向/风速、气压、降水'
      },
      {
        name: '气象再分析（边界层高度、云量等）',
        granularity: '1 小时',
        range: '2025-07-31 至今',
        desc: '模式/再分析数据，不是地面站实测'
      },
      {
        name: 'NMC 许昌小时预报',
        granularity: '3 小时',
        range: '未来 7 天滚动',
        desc: '逐 3 小时的气温、湿度、风向/风速、降水概率'
      },
      {
        name: '中国天气网日预报',
        granularity: '1 日',
        range: '未来 15 天',
        desc: '第 8—15 天为趋势展望，精度低于前 7 天'
      },
      {
        name: '空气质量预报（空气质量发布 APP）',
        granularity: '1 日',
        range: '未来 7 天',
        desc: 'AQI 范围、等级、首要污染物（来源为环境监测总站）'
      }
    ]
  },
  {
    title: '企业门禁、排放和知识资料',
    rows: [
      {
        name: '企业门禁数据',
        granularity: '日',
        range: '2026年4月14日 至今',
        desc: '各企业违规次数、违规车辆特征'
      },
      {
        name: '企业排放源清单',
        granularity: '年度静态',
        range: '清单版本 2026-09',
        desc: '约 2300 家有坐标企业'
      },
      {
        name: '排污许可证资料',
        granularity: '静态',
        range: '1328 家',
        desc: '许昌市许可证企业身份、许可污染物、许可附件'
      },
      {
        name: '项目知识库',
        granularity: '—',
        range: '持续更新',
        desc: '知识问答、报告口径和业务解释；公开的技术规范、标准、政策文件和已授权资料'
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

.cell-desc {
  color: var(--text-2);
  line-height: 1.5;
}
</style>
